"""Read Gaussian basis functions and signed molecular orbitals from Molden text."""

from array import array
from dataclasses import dataclass, replace
from io import StringIO
import math
import re
from typing import Optional

from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.core.models import Molecule
from orcaview.io._quantum_geometry import number
from orcaview.orca.orbital_files import ORBITAL_SET_LABELS
from orcaview.results.orbital_basis import GaussianShell


_HEADER = re.compile(r"(?im)^[ \t]*\[([^\]\r\n]+)\][^\r\n]*")


@dataclass(frozen=True)
class MolecularOrbital:
    spin: str
    number: int  # zero-based within the spin channel, as in ORCA
    energy: Optional[float]
    occupation: float
    symmetry: str
    coefficients: array


@dataclass(frozen=True)
class MoldenOrbitals:
    molecule: Molecule
    shells: tuple
    orbitals: tuple
    kind: str = "mo"
    core_electrons: Optional[tuple] = ()

    @property
    def complete_density(self):
        size = sum(len(shell.functions) for shell in self.shells)
        counts = [sum(mo.spin == spin for mo in self.orbitals) for spin in ("Alpha", "Beta")]
        return self.kind != "unso" and counts[0] == size and counts[1] in (0, size) and any(
            mo.occupation > 0 for mo in self.orbitals)

    def frontiers(self):
        """Indices of the highest occupied and lowest empty canonical MO within each spin."""
        if self.kind != "mo":
            return {}
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
                                              l in spherical, orca, atom_index=center)
            shells.append(shell)
    if not shells:
        raise ValueError("Empty Molden [GTO] basis.")
    return tuple(shells)


def _orbitals(bodies, basis_size, kind):
    orbitals = []
    spin_counts = {"Alpha": 0, "Beta": 0}

    def finish():
        has_energy = kind in ("mo", "qro")
        if not {"occup", "spin"} <= metadata.keys() or (has_energy and "ene" not in metadata) or not entries:
            raise ValueError("Incomplete Molden [MO] orbital metadata or coefficients.")
        spin = metadata["spin"].capitalize()
        if spin not in spin_counts:
            raise ValueError(f"Unsupported Molden spin channel: {spin}")
        coefficients = array("d", [0.]) * basis_size
        for index, value in entries.items():
            coefficients[index] = value
        occupation = _finite(metadata["occup"])
        # UNSOs diagonalize the spin density. Relaxed correlated densities can
        # also have non-N-representable eigenvalues, which the file reports verbatim.
        low, high = (-1, 1) if kind == "unso" else (0, 2)
        if (kind != "natural" and not low-1e-7 <= occupation <= high+1e-7) or not any(coefficients):
            raise ValueError("Invalid Molden occupation or all-zero orbital coefficients.")
        if kind != "natural":
            occupation = max(low, min(high, occupation))
        energy = _finite(metadata["ene"]) if has_energy else None
        orbitals.append(MolecularOrbital(spin, spin_counts[spin], energy,
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


def _molecular_state(molecule, orbitals, size, core, kind):
    """Infer a determinant's input charge and multiplicity only for complete spin channels."""
    alpha = [mo.occupation for mo in orbitals if mo.spin == "Alpha"]
    beta = [mo.occupation for mo in orbitals if mo.spin == "Beta"]
    # Molden geometry often has only coordinates and a neutral charge default.
    electrons = molecule.electron_count
    if (electrons - molecule.multiplicity + 1) % 2:
        molecule = replace(molecule, multiplicity=1+electrons % 2)
    if kind == "unso":
        # Spin-density eigenvalues carry no total electron count. Use the file's
        # spin trace only when compatible with the geometry's charge default.
        trace = abs(sum(alpha + beta))
        unpaired = round(trace)
        compatible = (len(alpha) == size and not beta and abs(trace-unpaired) < 1e-5
                      and unpaired <= electrons and (electrons-unpaired) % 2 == 0)
        return replace(molecule, multiplicity=1+(unpaired if compatible else electrons % 2))
    if core is None or len(alpha) != size or (beta and len(beta) != size):
        return molecule
    ne = sum(alpha + beta)
    if not any(alpha + beta) or abs(ne-round(ne)) > 1e-5:
        return molecule
    charge = sum(ATOMIC_NUMBERS[a.element] for a in molecule.atoms) - sum(core) - round(ne)
    if any(abs(n - round(n)) > 1e-7 for n in alpha + beta):
        if kind not in ("natural", "uno"):
            return molecule
        # A spatial density determines the charge, but generally not the spin.
        return replace(molecule, charge=charge, multiplicity=1+(round(ne)+sum(core))%2)
    if beta:
        if max(alpha + beta) > 1:
            return molecule
        unpaired = abs(sum(alpha) - sum(beta))
    else:
        unpaired = sum(round(n) == 1 for n in alpha)
    return replace(molecule, charge=charge, multiplicity=1+round(unpaired))


def _core_electrons(molecule, pseudo):
    core = [0] * len(molecule.atoms)
    for body in pseudo:
        for line in body.splitlines():
            if not line.strip():
                continue
            # ORCA 6 [Pseudo] reports symbol, atom index and effective nuclear charge.
            fields = line.split()
            if len(fields) != 3:
                return None
            atom = int(fields[1]) - 1
            effective = _finite(fields[2])
            if not 0 <= atom < len(core) or not effective.is_integer():
                return None
            z = ATOMIC_NUMBERS[molecule.atoms[atom].element]
            if not 0 <= effective <= z:
                return None
            core[atom] = z-int(effective)
    return tuple(core)


def read_molden_orbitals(raw, molecule, *, kind="mo"):
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
    for a, b in sections.get("orcaview orbital set", ()):
        marked = text[a:b].strip().lower()
        if marked not in ORBITAL_SET_LABELS:
            raise ValueError("Unknown orbital set in Molden file.")
        kind = marked
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
    orbitals = _orbitals((text[a:b] for a, b in sections["mo"]), size, kind)
    core = None
    if not {"core", "nval", "ecp"}.intersection(sections):
        core = _core_electrons(molecule, (text[a:b] for a, b in sections.get("pseudo", ())))
    molecule = _molecular_state(molecule, orbitals, size, core, kind)
    return MoldenOrbitals(molecule, shells, orbitals, kind, core)
