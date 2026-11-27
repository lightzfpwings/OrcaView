"""Distance-based display bonds and valence accounting for explicitly drawn bonds."""

import math
from itertools import product
from typing import Tuple

from .elements import COVALENT_RADII
from .models import Bond, Molecule


DEFAULT_BOND_DISTANCE_FACTOR = 1.20
_NEIGHBOR_OFFSETS = tuple(product((-1, 0, 1), repeat=3))


def connected_component(bonds, anchor):
    """Atom indices reachable from anchor through the chemical topology."""
    neighbors = {}
    for bond in bonds:
        if not bond.is_covalent:
            continue
        neighbors.setdefault(bond.a, []).append(bond.b)
        neighbors.setdefault(bond.b, []).append(bond.a)
    component = {anchor}
    pending = [anchor]
    while pending:
        for index in neighbors.get(pending.pop(), ()):
            if index not in component:
                component.add(index)
                pending.append(index)
    return frozenset(component)


def occupied_valences(molecule, bonds, *, ambiguous_donors=None):
    """Count explicit valence and optionally collect unresolved aromatic protonation sites."""
    occupied = [0] * len(molecule.atoms)
    aromatic = {}
    for bond in bonds:
        occupied[bond.a] += bond.valence_at(bond.a)
        occupied[bond.b] += bond.valence_at(bond.b)
        if bond.style == "aromatic":
            aromatic.setdefault(bond.a, set()).add(bond.b)
            aromatic.setdefault(bond.b, set()).add(bond.a)
    if not aromatic:
        return occupied

    # Only delocalize cyclic edges. A partial bond on a side chain still
    # contributes its written 1.5, even when attached to an aromatic carbon.
    for a, b in _bridges(aromatic):
        aromatic[a].remove(b)
        aromatic[b].remove(a)
    conjugated = set()
    possible_donors = set()
    for i, neighbors in aromatic.items():
        if not neighbors:
            continue
        degree = len(neighbors)
        element = molecule.atoms[i].element
        sigma_valence = occupied[i] - degree * .5
        if element in ("O", "S", "Se", "Te") or (element in ("N", "P") and sigma_valence >= 3):
            # The lone pair belongs to the ring; neither of its ring bonds
            # requires an additional unit of valence on this heteroatom.
            occupied[i] = sigma_valence
        elif element in ("C", "N", "P"):
            # A fused ring carbon with three ring neighbors has only one
            # participating pi orbital and thus occupies 3 + 1 valences.
            occupied[i] = sigma_valence + 1
            conjugated.add(i)
            if element in ("N", "P"):
                possible_donors.add(i)

    # With an odd conjugated segment, one neutral N (or P) can supply the
    # remaining pair, e.g. pyrrole. Do not select a tautomer arbitrarily when
    # several distinct unprotonated nitrogens could supply it.
    while conjugated:
        component = {conjugated.pop()}
        stack = list(component)
        while stack:
            for neighbor in aromatic[stack.pop()] & conjugated:
                conjugated.remove(neighbor)
                component.add(neighbor)
                stack.append(neighbor)
        donors = component & possible_donors
        if len(component) % 2:
            if len(donors) == 1:
                occupied[donors.pop()] -= 1
            elif donors and ambiguous_donors is not None:
                ambiguous_donors.append(tuple(sorted(donors)))
    return occupied


def _bridges(neighbors):
    """Find noncyclic edges by iterative depth-first search."""
    discovered, lowest, bridges = {}, {}, []
    for start in neighbors:
        if start in discovered:
            continue
        discovered[start] = lowest[start] = len(discovered)
        stack = [(start, None, iter(neighbors[start]))]
        while stack:
            i, parent, adjacent = stack[-1]
            j = next(adjacent, None)
            if j is None:
                stack.pop()
                if parent is not None:
                    lowest[parent] = min(lowest[parent], lowest[i])
                    if lowest[i] > discovered[parent]:
                        bridges.append((parent, i))
            elif j not in discovered:
                discovered[j] = lowest[j] = len(discovered)
                stack.append((j, i, iter(neighbors[j])))
            elif j != parent:
                lowest[i] = min(lowest[i], discovered[j])
    return bridges


def display_bonds(molecule: Molecule, distance_factor: float = DEFAULT_BOND_DISTANCE_FACTOR) -> Tuple[Bond, ...]:
    if molecule.bonds or molecule.bonds_explicit:
        return molecule.bonds
    return infer_bonds(molecule, distance_factor)


def covalent_bonds(molecule: Molecule) -> Tuple[Bond, ...]:
    """Chemical connectivity for geometry editing and external structure engines."""
    return tuple(bond for bond in display_bonds(molecule) if bond.is_covalent)


def infer_bonds(molecule: Molecule, distance_factor: float = DEFAULT_BOND_DISTANCE_FACTOR) -> Tuple[Bond, ...]:
    molecule.validate_structure(allow_empty=True)
    atoms = molecule.atoms
    radii = [COVALENT_RADII.get(atom.element, .85) for atom in atoms]
    largest_cutoff = distance_factor * (2*max(radii, default=0.))
    if not largest_cutoff > .1:
        return ()
    # A bonded pair must occupy the same or adjacent cells, including at the cutoff.
    width = max(1., math.nextafter(largest_cutoff, math.inf))
    cells = {}
    by_atom = [[] for _ in atoms]
    for j, atom in enumerate(atoms):
        x, y, z = math.floor(atom.x/width), math.floor(atom.y/width), math.floor(atom.z/width)
        for dx, dy, dz in _NEIGHBOR_OFFSETS:
            for i in cells.get((x+dx, y+dy, z+dz), ()):
                other = atoms[i]
                distance = math.sqrt((other.x-atom.x)**2 + (other.y-atom.y)**2 + (other.z-atom.z)**2)
                if .1 < distance <= distance_factor*(radii[i]+radii[j]):
                    by_atom[i].append(Bond(i, j))
        cells.setdefault((x, y, z), []).append(j)
    # For each first endpoint the second endpoints arrived in input order.
    return tuple(bond for row in by_atom for bond in row)
