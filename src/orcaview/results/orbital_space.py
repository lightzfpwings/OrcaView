"""Atom-centered numerical integration of the selected MO density in bohr."""

from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.core.units import BOHR_IN_ANGSTROM
from orcaview.results.orbital_basis import orbital_expansion
from orcaview.results.orbital_surface import _check_cancel


@lru_cache(maxsize=1)
def _reference_densities():
    # CC BY 4.0 atomref-proatoms v2.0.0. See THIRD_PARTY_NOTICES.md.
    with ZipFile(Path(__file__).with_name("data") / "proatomic_density_neutral.zip") as archive:
        with archive.open("proatomic_density_neutral.csv") as stream:
            table = np.loadtxt(stream, delimiter=",", skiprows=1)
    return table[:, 0], np.log(table[:, 1:].T)


def _becke_weights(distances, centers, radii, cancel):
    weights = np.ones_like(distances)
    for a in range(len(centers)):
        _check_cancel(cancel)
        for b in range(a):
            ab = np.linalg.norm(centers[a]-centers[b])
            if ab < 1e-9:
                raise ValueError("Real-space partitions need distinct nuclear positions.")
            mu = np.clip((distances[:, a]-distances[:, b])/ab, -1., 1.)
            u = (radii[a]-radii[b])/(radii[a]+radii[b])
            mu += np.clip(u/(u*u-1), -.5, .5)*(1-mu*mu)
            for _ in range(3):
                mu = .5*mu*(3-mu*mu)
            weights[:, a] *= .5*(1-mu)
            weights[:, b] *= .5*(1+mu)
    return weights/np.sum(weights, axis=1, keepdims=True)


def _orbital_values(points, expansion):
    values = np.zeros(len(points))
    for center, primitives, terms in expansion:
        dx, dy, dz = (points-center).T
        r2 = dx*dx + dy*dy + dz*dz
        radial = sum(c*np.exp(-a*r2) for a, c in primitives)
        polynomial = sum(c*dx**i*dy**j*dz**k for (i,j,k), c in terms)
        values += radial*polynomial
    return values


def _product_grid(radial, polar):
    node, weight = np.polynomial.legendre.leggauss(radial)
    r = (1+node)/(1-node)
    radial_weight = weight*2*r*r/(1-node)**2
    z, w = np.polynomial.legendre.leggauss(polar)
    phi = np.arange(2*polar)*np.pi/polar
    sin = np.sqrt(1-z*z)
    directions = np.stack(np.broadcast_arrays(sin[:, None]*np.cos(phi), sin[:, None]*np.sin(phi), z[:, None]), axis=-1)
    points = r[:, None, None]*directions.reshape(-1, 3)
    volume = radial_weight[:, None]*(np.repeat(w, len(phi))*np.pi/polar)
    return points.reshape(-1, 3), volume.ravel()


def _partition_parameters(molecule, method):
    from .orbital_nao import atomic_reference

    atoms = molecule.atoms
    if not atoms:
        raise ValueError("Atomic partitions require at least one atom.")
    centers = np.array([(a.x, a.y, a.z) for a in atoms])/BOHR_IN_ANGSTROM
    numbers = [ATOMIC_NUMBERS[a.element] for a in atoms]
    bragg = atomic_reference()["bragg_angstrom"]
    if any(z >= len(bragg) or bragg[z] is None for z in numbers):
        raise ValueError("No atomic size reference for this real-space partition.")
    radii = np.array([bragg[z] for z in numbers])/BOHR_IN_ANGSTROM
    if method == "hirshfeld" and max(numbers) > len(_reference_densities()[1]):
        raise ValueError("Hirshfeld reference densities cover hydrogen through lawrencium.")
    return centers, radii, numbers


def _stockholder_shares(distances, numbers, measure):
    x, logrho = _reference_densities()
    logs = np.column_stack([np.interp(distances[:, j], x, logrho[z-1], right=-np.inf)
                            for j, z in enumerate(numbers)])
    logs[distances > 20.] = -np.inf
    peak = logs.max(axis=1)
    valid = np.isfinite(peak)
    weights = np.exp(logs[valid]-peak[valid, None])
    return (measure[valid]/weights.sum(axis=1)) @ weights, measure[~valid].sum()


def cube_composition(cube, field, method, cancel=None):
    """Trapezoidal integral of an explicitly selected orbital amplitude on its affine grid."""
    centers, radii, numbers = _partition_parameters(cube.molecule, method)
    shape = np.array(cube.grid.shape)
    steps = np.array(cube.grid.steps) / BOHR_IN_ANGSTROM
    origin = np.array(cube.grid.origin) / BOHR_IN_ANGSTROM
    dv = abs(cube.grid.determinant) / BOHR_IN_ANGSTROM**3
    values = np.asarray(field.values)
    shares = np.zeros(len(centers))
    unresolved = 0.
    for start in range(0, len(values), 2048):
        _check_cancel(cancel)
        end = min(start+2048, len(values))
        indices = np.column_stack(np.unravel_index(np.arange(start, end), cube.grid.shape))
        distances = np.linalg.norm((origin + indices @ steps)[:, None, :] - centers, axis=2)
        edges = ((indices == 0) | (indices == shape-1)).sum(axis=1)
        measure = dv*np.exp2(-edges.astype(float))*np.square(values[start:end])
        if method == "becke":
            shares += measure @ _becke_weights(distances, centers, radii, cancel)
        else:
            contribution, tail = _stockholder_shares(distances, numbers, measure)
            shares += contribution
            unresolved += tail
    if unresolved > 3e-4*(shares.sum()+unresolved):
        raise ValueError("Too much orbital density lies outside the Hirshfeld reference grid.")
    return shares


def atomic_composition(wave, coefficients, method, norm, cancel=None):
    centers, radii, numbers = _partition_parameters(wave.molecule, method)
    expansion = orbital_expansion(wave.shells, coefficients)
    previous = None
    for nrad, polar in ((32, 9), (48, 14), (72, 20), (106, 28)):
        grid, dv = _product_grid(nrad, polar)
        result = np.zeros(len(centers))
        unresolved = 0.
        for i in range(len(centers)):
            scale = radii[i]
            for start in range(0, len(grid), 1536):
                _check_cancel(cancel)
                sl = slice(start, start+1536)
                points = centers[i]+scale*grid[sl]
                distances = np.linalg.norm(points[:, None, :]-centers, axis=2)
                becke = _becke_weights(distances, centers, radii, cancel)
                measure = dv[sl]*scale**3*becke[:, i]*_orbital_values(points, expansion)**2
                if method == "becke":
                    result[i] += measure.sum()
                else:
                    contribution, tail = _stockholder_shares(distances, numbers, measure)
                    result += contribution
                    unresolved += tail
        if previous is not None and abs(result.sum()+unresolved-norm) < 5e-4*norm:
            if np.max(abs(result-previous)) < 3e-4*norm:
                if unresolved > 3e-4*norm:
                    raise ValueError("Too much orbital density lies outside the Hirshfeld reference grid.")
                return result
        previous = result
    raise ValueError("Real-space orbital integration did not converge. Choose an AO-based method.")
