"""Natural atomic orbital projections for spherical AOs (Reed, Weinstock & Weinhold)."""

from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path

import numpy as np

from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.results.orbital_surface import _check_cancel


@lru_cache(maxsize=1)
def atomic_reference():
    path = Path(__file__).with_name("data") / "atomic_partitions.json"
    return json.loads(path.read_text(encoding="ascii"))


def _powers(metric):
    e, u = np.linalg.eigh(metric)
    if e[0] <= 1e-12*e[-1] or e[-1] <= 0:
        raise ValueError("The AO basis is linearly dependent for NAO decomposition.")
    root = np.sqrt(e)
    return (u*root) @ u.T, (u/root) @ u.T


def _core_count(z, removed):
    if 57 <= z < 71 and 47 <= removed <= 58:
        return "4s3p2d1f"
    if 89 <= z < 103 and 79 <= removed <= 90:
        return "5s4p3d2f"
    config = atomic_reference()["ecp_core"].get(str(removed))
    if config is None:
        raise ValueError("The ECP core configuration is unavailable for NAO decomposition.")
    return config


def nao_projection(wave, s, density, cancel=None):
    if wave.core_electrons is None:
        raise ValueError("NAO decomposition requires known effective nuclear charges.")
    shell_ids = defaultdict(list)
    offset = 0
    for shell in wave.shells:
        size = len(shell.functions)
        if size != 2*shell.angular+1:
            raise ValueError("NAO decomposition requires spherical d and higher shells.")
        shell_ids[shell.atom_index, shell.angular].append(np.arange(offset, offset+size))
        offset += size
    covariant = s @ density @ s
    pre = np.zeros_like(s)
    occupations = np.zeros(len(s))
    groups = [[], [], []]  # core, valence, Rydberg
    reference = atomic_reference()["core_valence_shells"]
    for (atom, l), shells in shell_ids.items():
        _check_cancel(cancel)
        ids = np.array(shells)
        radial = []
        for matrix in (s, covariant):
            blocks = matrix[ids[:, None, :, None], ids[None, :, None, :]]
            radial.append(blocks.trace(axis1=2, axis2=3)/ids.shape[1])
        _, inv = _powers(radial[0])
        eig, vec = np.linalg.eigh(inv @ radial[1] @ inv)
        transform = inv @ vec[:, ::-1]
        for m in ids.T:
            pre[np.ix_(m, m)] = transform
        z = ATOMIC_NUMBERS[wave.molecule.atoms[atom].element]
        if z >= len(reference):
            raise ValueError("The atomic valence configuration is unavailable for NAO decomposition.")
        removed = _core_count(z, wave.core_electrons[atom] if wave.core_electrons else 0)
        core, valence = reference[z]
        for n, row in enumerate(ids):
            occupations[row] = eig[-1-n]
            rank = n + (int(removed[2*l]) if l < 4 else 0)
            group = 2
            if l < 4 and rank < int(core[2*l]):
                group = 0
            elif l < 4 and rank < int(valence[2*l]) and eig[-1-n] > 1e-10:
                group = 1
            groups[group].extend(row)
    # Orthogonalize core, then occupancy-weighted valence, then the residual space.
    # A final intra-atom, intra-l rotation leaves all reported group sums invariant.
    orbitals = np.zeros_like(s)
    earlier = []
    for group, indices in enumerate(groups):
        _check_cancel(cancel)
        if not indices:
            continue
        block = pre[:, indices]
        if earlier:
            q = orbitals[:, earlier]
            block -= q @ (q.T @ s @ block)
        root, inv = _powers(block.T @ s @ block)
        if group == 1:
            u, _, vt = np.linalg.svd(root*occupations[indices], full_matrices=False)
            inv = inv @ (u @ vt)
        orbitals[:, indices] = block @ inv
        earlier.extend(indices)
    projection = orbitals.T @ s
    if not np.allclose(projection @ orbitals, np.eye(len(s)), atol=2e-6, rtol=0):
        raise ValueError("The natural atomic orbitals could not be orthonormalized.")
    return projection
