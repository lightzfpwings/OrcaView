"""Read Gaussian basis functions and signed molecular orbitals from Molden text."""

from array import array
from dataclasses import dataclass, replace
from io import StringIO
import math
import re

from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.core.models import Molecule
from orcaview.io._quantum_geometry import number
from orcaview.results.orbital_basis import GaussianShell


_HEADER = re.compile(r"(?im)^[ \t]*\[([^\]\r\n]+)\][^\r\n]*")


@dataclass(frozen=True)
class MolecularOrbital:
    spin: str
    number: int  # zero-based within the spin channel, as in ORCA
    energy: float
    occupation: float
    symmetry: str
    coefficients: array


@dataclass(frozen=True)
class MoldenOrbitals:
    molecule: Molecule
    shells: tuple
    orbitals: tuple

    def frontiers(self):
        """Indices of the highest occupied and lowest empty MO within each spin."""
        labels = {}
        for spin in ("Alpha", "Beta"):
            channel = [(i, mo) for i, mo in enumerate(self.orbitals) if mo.spin == spin]
            occupied = [(mo.energy, i) for i, mo in channel if mo.occupation > 1e-7]
            empty = [(mo.energy, i) for i, mo in channel if mo.occupation <= 1e-7]
            if occupied:
                labels[max(occupied)[1]] = "HOMO"
            if empty:
                labels[min(empty)[1]] = "LUMO"
        return labels


def _finite(text):
    value = number(text)
    if not math.isfinite(value):
        raise ValueError("Non-finite number in Molden wavefunction.")
    return value


def _shells(body, molecule, spherical, orca):
    lines = (line.split() for line in StringIO(body) if line.strip())
    shells = []
    center = None
    for fields in lines:
        if fields[0].isdigit():
            center = int(fields[0]) - 1
            if not 0 <= center < len(molecule.atoms):
                raise ValueError("Invalid atom index in Molden [GTO].")
            continue
        label = fields[0].lower()
        if label not in ("s", "p", "sp", "d", "f", "g", "h"):
            raise ValueError(f"Unsupported Molden basis shell: {label}")
        if center is None or len(fields) not in (2, 3):
            raise ValueError("Invalid Molden [GTO] shell header.")
        count = int(fields[1])
        if count <= 0:
            raise ValueError("A Molden shell requires at least one Gaussian primitive.")
        rows = []
        for _ in range(count):
            values = next(lines, ())
            if len(values) != 1 + len(label):
                raise ValueError("Missing exponent or contraction coefficients in Molden [GTO].")
            row = tuple(_finite(v) for v in values)
            if row[0] <= 0:
                raise ValueError("Molden primitive exponents must be positive.")
            rows.append(row)
        for column, symbol in enumerate(label, 1):
            l = "spdfgh".index(symbol)
            shell = GaussianShell.from_molden(molecule.atoms[center], l, [(r[0], r[column]) for r in rows],
                                              l in spherical, orca)
            shells.append(shell)
    if not shells:
        raise ValueError("Empty Molden [GTO] basis.")
    return tuple(shells)


def _orbitals(bodies, basis_size):
    orbitals = []
    spin_counts = {"Alpha": 0, "Beta": 0}

    def finish():
        if not {"ene", "occup", "spin"} <= metadata.keys() or not entries:
            raise ValueError("Incomplete Molden [MO] orbital metadata or coefficients.")
        spin = metadata["spin"].capitalize()
        if spin not in spin_counts:
            raise ValueError(f"Unsupported Molden spin channel: {spin}")
        coefficients = array("d", [0.]) * basis_size
        for index, value in entries.items():
            coefficients[index] = value
        occupation = _finite(metadata["occup"])
        if not 0 <= occupation <= 2 or not any(coefficients):
            raise ValueError("Invalid Molden occupation or all-zero orbital coefficients.")
        orbitals.append(MolecularOrbital(spin, spin_counts[spin], _finite(metadata["ene"]),
                                         occupation, metadata.get("sym", ""), coefficients))
        spin_counts[spin] += 1

    for body in bodies:
        metadata, entries = {}, {}
        for line in StringIO(body):
            line = line.strip()
            if not line:
                continue
            if "=" in line:
                if entries:
                    finish()
                    metadata, entries = {}, {}
                key, value = (s.strip() for s in line.split("=", 1))
                key = key.lower()
                if key in metadata:
                    raise ValueError("Duplicate Molden [MO] metadata field.")
                metadata[key] = value
            else:
                fields = line.split()
                if len(fields) != 2:
                    raise ValueError("Invalid Molden [MO] coefficient record.")
                index = int(fields[0]) - 1
                if not 0 <= index < basis_size or index in entries:
                    raise ValueError("Invalid or duplicate AO coefficient index in Molden [MO].")
                entries[index] = _finite(fields[1])
        if metadata or entries:
            finish()
    if not orbitals:
        raise ValueError("Empty Molden [MO] section.")
    return tuple(orbitals)


def _molecular_state(molecule, orbitals, size, pseudo):
    """Infer a determinant's input charge and multiplicity only for complete spin channels."""
    alpha = [mo.occupation for mo in orbitals if mo.spin == "Alpha"]
    beta = [mo.occupation for mo in orbitals if mo.spin == "Beta"]
    if len(alpha) != size or (beta and len(beta) != size):
        return molecule
    if not any(alpha + beta) or any(abs(n - round(n)) > 1e-7 for n in alpha + beta):
        return molecule
    if beta:
        if max(alpha + beta) > 1:
            return molecule
        unpaired = abs(sum(alpha) - sum(beta))
    else:
        unpaired = sum(round(n) == 1 for n in alpha)
    charges = [ATOMIC_NUMBERS[a.element] for a in molecule.atoms]
    for body in pseudo:
        for line in body.splitlines():
            if not line.strip():
                continue
            # ORCA 6 [Pseudo] reports symbol, atom index and effective nuclear charge.
            fields = line.split()
            if len(fields) != 3:
                return molecule
            atom = int(fields[1]) - 1
            effective = _finite(fields[2])
            if not 0 <= atom < len(charges) or not effective.is_integer() or not 0 <= effective <= charges[atom]:
                return molecule
            charges[atom] = int(effective)
    return replace(molecule, charge=sum(charges)-round(sum(alpha)+sum(beta)), multiplicity=1+round(unpaired))


def read_molden_orbitals(raw, molecule):
    """Return None for geometry/vibration-only input. Preserve the geometry reader's atom order."""
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    headers = list(_HEADER.finditer(text))
    sections = {}
    for i, match in enumerate(headers):
        name = match[1].strip().lower()
        end = headers[i+1].start() if i+1 < len(headers) else len(text)
        sections.setdefault(name, []).append((match.end(), end))
    if "mo" not in sections:
        return None
    if len(sections.get("gto", ())) != 1 or "sto" in sections:
        raise ValueError("Molecular orbitals require a Molden [GTO] Gaussian basis.")
    orca = any("orca_2mkl" in text[a:b].lower() for a, b in sections.get("title", ()))
    spherical = set()
    for key in sections:
        if not re.fullmatch(r"(?:\d+[dfgh])+", key):
            continue
        if key == "5d":
            spherical.add(3)  # historical Molden shorthand for [5D7F]
        for size, label in re.findall(r"(\d+)([dfgh])", key):
            l = "spdfgh".index(label)
            if int(size) == 2*l+1:
                spherical.add(l)
            elif int(size) == (l+1)*(l+2)//2:
                spherical.discard(l)
            else:
                raise ValueError(f"Unknown Molden angular convention: {key}")
    if orca and "9g" in sections:
        spherical.add(5)  # orca_2mkl also uses this flag for its spherical h extension
    a, b = sections["gto"][0]
    shells = _shells(text[a:b], molecule, spherical, orca)
    size = sum(len(shell.functions) for shell in shells)
    orbitals = _orbitals((text[a:b] for a, b in sections["mo"]), size)
    if not {"core", "nval", "ecp"}.intersection(sections):
        molecule = _molecular_state(molecule, orbitals, size, (text[a:b] for a, b in sections.get("pseudo", ())))
    return MoldenOrbitals(molecule, shells, orbitals)
