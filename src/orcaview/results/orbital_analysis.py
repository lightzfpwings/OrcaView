"""AO overlaps, density natural orbitals and per-orbital population partitions."""

from array import array
from dataclasses import dataclass, replace
from functools import cached_property, lru_cache
from itertools import combinations_with_replacement, islice, product

import numpy as np

from orcaview.io.molden_orbitals import MolecularOrbital
from orcaview.results.orbital_surface import _check_cancel


METHODS = {
    "mulliken": "Mulliken", "lowdin": "Löwdin", "scpa": "Ros–Schuit (SCPA)",
    "stout": "Stout–Politzer", "bickelhaupt": "Bickelhaupt", "nao": "Natural atomic orbitals (NAO)",
    "hirshfeld": "Hirshfeld", "becke": "Becke",
}
SPACE_METHODS = ("becke", "hirshfeld")


@lru_cache(maxsize=32)
def _angular_matrix(functions):
    polynomials = [dict(f) for f in functions]
    powers = sorted(set().union(*polynomials))
    transform = np.array([[f.get(p, 0.) for p in powers] for f in polynomials])
    return np.array(powers).T, transform


def _moments(la, lb, pa, pb, half_inverse):
    """Moments about both centers of the normalized 1-D Gaussian product."""
    t = np.empty((la+1, lb+1, *pa.shape))
    t[0, 0] = 1.
    for i in range(la):
        t[i+1, 0] = pa*t[i, 0]
        if i:
            t[i+1, 0] += i*half_inverse*t[i-1, 0]
    for j in range(lb):
        t[:, j+1] = pb*t[:, j]
        if j:
            t[:, j+1] += j*half_inverse*t[:, j-1]
        for i in range(1, la+1):
            t[i, j+1] += i*half_inverse*t[i-1, j]
    return t


class _ShellGroup:
    """Shells with the same angular functions and number of radial primitives."""

    def __init__(self, members):
        offsets, shells = zip(*members)
        shell = shells[0]
        self.powers, self.transform = _angular_matrix(shell.functions)
        self.angular = shell.angular
        self.centers = np.asarray([s.center for s in shells], dtype=float)
        primitives = np.asarray([s.primitives for s in shells], dtype=float)
        self.exponents, self.weights = primitives.transpose(2, 0, 1)
        self.indices = np.asarray(offsets)[:, None] + np.arange(len(shell.functions))


def _overlap_blocks(a, b, rows, cols):
    # Each row is one shell pair, each column one primitive pair within its contraction.
    ap, bp = a.exponents[rows, :, None], b.exponents[cols, None, :]
    sums = ap+bp
    exponent = sums.reshape(len(rows), -1)
    u, v = (ap/sums).reshape(exponent.shape), (bp/sums).reshape(exponent.shape)
    distance = b.centers[cols]-a.centers[rows]
    weight = (a.weights[rows, :, None]*b.weights[cols, None, :]).reshape(exponent.shape)
    weight *= (np.pi/exponent)**1.5 * np.exp(-exponent*u*v*(distance**2).sum(axis=1)[:, None])
    half_inverse = .5/exponent
    integrals = weight
    for axis in range(3):
        delta = distance[:, axis, None]
        moments = _moments(a.angular, b.angular, delta*v, -delta*u, half_inverse)
        integrals = integrals*moments[a.powers[axis, :, None], b.powers[axis]]
    cartesian = np.moveaxis(integrals.sum(axis=-1), -1, 0)
    return a.transform @ cartesian @ b.transform.T


def overlap_matrix(shells, cancel=None):
    """Contract each shell pair once and scatter the blocks into Molden AO order."""
    _check_cancel(cancel)
    members = {}
    offset = 0
    for shell in shells:
        members.setdefault((shell.functions, len(shell.primitives)), []).append((offset, shell))
        offset += len(shell.functions)
    groups = [_ShellGroup(group) for group in members.values()]
    overlap = np.empty((offset, offset))
    for i, a in enumerate(groups):
        for b in groups[:i+1]:
            if a is b:
                pairs = combinations_with_replacement(range(len(a.centers)), 2)
            else:
                pairs = product(range(len(a.centers)), range(len(b.centers)))
            # Bound the Cartesian moment temporaries even for highly contracted g/h shells.
            terms = a.powers.shape[1]*b.powers.shape[1]*a.exponents.shape[1]*b.exponents.shape[1]
            batch = max(1, min(1024, 131072//terms))
            while chunk := list(islice(pairs, batch)):
                _check_cancel(cancel)
                rows, cols = np.asarray(chunk).T
                blocks = _overlap_blocks(a, b, rows, cols)
                row_ao, col_ao = a.indices[rows], b.indices[cols]
                overlap[row_ao[:, :, None], col_ao[:, None, :]] = blocks
                overlap[col_ao[:, :, None], row_ao[:, None, :]] = blocks.swapaxes(1, 2)
    return overlap


@dataclass(frozen=True)
class OrbitalComposition:
    # Percentages, with columns s, p, d, ... in the AO methods or one atomic column in real space.
    percentages: np.ndarray
    norm: float

    @classmethod
    def normalized(cls, values):
        norm = float(values.sum())
        if not np.all(np.isfinite(values)) or not np.isfinite(norm) or norm <= 0:
            raise ValueError("The orbital has zero or invalid norm.")
        return cls((values/norm)*100, norm)


class CubeOrbitalAnalysis:
    def __init__(self, cube):
        self.source = cube

    def composition(self, field, method, cancel=None):
        from .orbital_space import cube_composition
        if method not in SPACE_METHODS:
            raise ValueError("This method requires atomic orbital coefficients.")
        values = cube_composition(self.source, field, method, cancel)
        return OrbitalComposition.normalized(values[:, None])


class OrbitalAnalysis:
    """Share basis integrals between orbital selections. Publish only completed matrices."""

    def __init__(self, wave):
        self.source = wave
        self.atoms = np.repeat([s.atom_index for s in wave.shells], [len(s.functions) for s in wave.shells])
        self.angular = np.repeat([s.angular for s in wave.shells], [len(s.functions) for s in wave.shells])
        self._overlap = self._eigen = self._nao = self._populations = None

    def overlap(self, cancel=None):
        if self._overlap is None:
            self._overlap = overlap_matrix(self.source.shells, cancel)
        return self._overlap

    def eigenbasis(self, cancel=None):
        if self._eigen is None:
            eig, vectors = np.linalg.eigh(self.overlap(cancel))
            if eig[0] < -1e-8*eig[-1]:
                raise ValueError("The AO overlap matrix is not positive semidefinite.")
            keep = eig > eig[-1]*max(len(eig)*np.finfo(float).eps, 1e-12)
            self._eigen = np.sqrt(eig[keep]), vectors[:, keep]
        return self._eigen

    def _occupied_orbitals(self):
        if not self.source.complete_density:
            raise ValueError("This method needs the complete electron-density orbital set.")
        return [mo for mo in self.source.orbitals if mo.occupation != 0]

    @cached_property
    def density(self):
        occupied = self._occupied_orbitals()
        c = np.array([mo.coefficients for mo in occupied])
        density = (c.T*np.array([mo.occupation for mo in occupied])) @ c
        self._populations = density.diagonal()
        return density

    def _ao_populations(self, cancel):
        if self._populations is None:
            values = np.zeros(len(self.atoms))
            for mo in self._occupied_orbitals():
                _check_cancel(cancel)
                values += mo.occupation*np.square(mo.coefficients)
            self._populations = values
        return self._populations

    def natural_orbitals(self, cancel=None):
        wave = self.source
        if not wave.complete_density:
            raise ValueError("Natural orbitals require a complete electron-density orbital set.")
        # A single orthonormal spatial set already diagonalizes its supplied density.
        # Retain the input axes within equally occupied subspaces.
        ordered = sorted(wave.orbitals, key=lambda mo: -mo.occupation)
        if all(mo.spin == "Alpha" for mo in ordered):
            c = np.array([mo.coefficients for mo in ordered])
            if np.allclose(c @ self.overlap(cancel) @ c.T, np.eye(len(c)), atol=2e-5, rtol=0):
                orbitals = tuple(replace(mo, number=i, energy=None) for i, mo in enumerate(ordered))
                return replace(wave, kind="natural", orbitals=orbitals)
        roots, vectors = self.eigenbasis(cancel)
        _check_cancel(cancel)
        metric = roots[:, None]*vectors.T
        eig, rotation = np.linalg.eigh(metric @ self.density @ metric.T)
        _check_cancel(cancel)
        occupations = eig[::-1]
        if occupations[-1] < -2e-5 or occupations[0] > 2+2e-5:
            raise ValueError("The supplied orbitals give an invalid electron density.")
        c = (vectors/roots) @ rotation[:, ::-1]
        c *= np.where(c[np.argmax(abs(c), axis=0), np.arange(c.shape[1])] < 0, -1, 1)
        orbitals = tuple(MolecularOrbital("Alpha", i, None, float(np.clip(n, 0, 2)), "",
                                          array("d", col)) for i, (n, col) in enumerate(zip(occupations, c.T)))
        return replace(wave, kind="natural", orbitals=orbitals)

    def composition(self, mo, method, cancel=None):
        _check_cancel(cancel)
        c = np.asarray(mo.coefficients)
        if method in SPACE_METHODS:
            from .orbital_space import atomic_composition
            raw = atomic_composition(self.source, c, method, float(c @ self.overlap(cancel) @ c), cancel)
            values = raw[:, None]
        else:
            if method == "scpa":
                raw = c*c
            elif method == "mulliken":
                raw = c*(self.overlap(cancel) @ c)
            elif method == "lowdin":
                roots, vectors = self.eigenbasis(cancel)
                raw = (vectors @ (roots*(vectors.T @ c)))**2
            elif method in ("stout", "bickelhaupt"):
                # Allocate each full AO-pair cross term once, using complementary weights.
                s = self.overlap(cancel)
                w = c*c if method == "stout" else self._ao_populations(cancel)
                raw = np.empty_like(c)
                for start in range(0, len(c), 128):
                    _check_cancel(cancel)
                    rows = slice(start, start+128)
                    den = w[rows, None]+w
                    ratio = np.divide(w[rows, None], den, out=np.full_like(den, .5), where=den!=0)
                    raw[rows] = 2*c[rows]*((s[rows]*ratio) @ c)
            elif method == "nao":
                from .orbital_nao import nao_projection
                if self._nao is None:
                    self._nao = nao_projection(self.source, self.overlap(cancel), self.density, cancel)
                raw = (self._nao @ c)**2
            else:
                raise ValueError("Unknown orbital decomposition method.")
            values = np.zeros((len(self.source.molecule.atoms), int(self.angular.max())+1))
            np.add.at(values, (self.atoms, self.angular), raw)
        return OrbitalComposition.normalized(values)
