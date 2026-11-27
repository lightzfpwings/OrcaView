"""AO overlaps, density natural orbitals and per-orbital population partitions."""

from array import array
from dataclasses import dataclass, replace
from functools import cached_property, lru_cache

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
    powers = sorted({powers for f in functions for powers, _ in f})
    transform = np.array([[dict(f).get(p, 0.) for p in powers] for f in functions])
    return np.array(powers).T, transform


def _moments(la, lb, pa, pb, half_inverse):
    """Moments about both centers of the normalized 1-D Gaussian product."""
    t = np.empty((la+1, lb+1, pa.size))
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


def _shell_overlap(a, b):
    ap, ac = np.asarray(a.primitives).T
    bp, bc = np.asarray(b.primitives).T
    exponent = (ap[:, None] + bp).ravel()
    u = (ap[:, None] / (ap[:, None]+bp)).ravel()
    v = (bp / (ap[:, None]+bp)).ravel()
    distance = np.subtract(b.center, a.center)
    weight = (ac[:, None]*bc).ravel() * (np.pi/exponent)**1.5
    weight *= np.exp(-exponent*u*v*np.dot(distance, distance))
    pa, ta = _angular_matrix(a.functions)
    pb, tb = _angular_matrix(b.functions)
    product = weight
    for axis in range(3):
        moments = _moments(a.angular, b.angular, distance[axis]*v, -distance[axis]*u, .5/exponent)
        product = product*moments[pa[axis, :, None], pb[axis]]
    return ta @ product.sum(axis=-1) @ tb.T


def overlap_matrix(shells, cancel=None):
    offsets = np.cumsum([0, *(len(s.functions) for s in shells)])
    overlap = np.empty((offsets[-1], offsets[-1]))
    for i, a in enumerate(shells):
        _check_cancel(cancel)
        rows = slice(offsets[i], offsets[i+1])
        for j in range(i+1):
            if j % 32 == 0:
                _check_cancel(cancel)
            cols = slice(offsets[j], offsets[j+1])
            block = _shell_overlap(a, shells[j])
            overlap[rows, cols] = block
            overlap[cols, rows] = block.T
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
        self._overlap = self._eigen = self._nao = None

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

    @cached_property
    def density(self):
        if not self.source.complete_density:
            raise ValueError("This method needs the complete electron-density orbital set.")
        occupied = [mo for mo in self.source.orbitals if mo.occupation != 0]
        c = np.array([mo.coefficients for mo in occupied])
        return (c.T*np.array([mo.occupation for mo in occupied])) @ c

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
        if method in SPACE_METHODS:
            from .orbital_space import atomic_composition
            c = np.asarray(mo.coefficients)
            raw = atomic_composition(self.source, c, method, float(c @ self.overlap(cancel) @ c), cancel)
            values = raw[:, None]
        else:
            c = np.asarray(mo.coefficients)
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
                w = c*c if method == "stout" else np.diag(self.density)
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
