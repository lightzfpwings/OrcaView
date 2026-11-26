"""Distance-based display bonds and valence accounting for explicitly drawn bonds."""

import math
from typing import Tuple

from .elements import COVALENT_RADII
from .models import Bond, Molecule


DEFAULT_BOND_DISTANCE_FACTOR = 1.20


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
    bonds = []
    for i, first in enumerate(molecule.atoms):
        for j in range(i + 1, len(molecule.atoms)):
            second = molecule.atoms[j]
            distance = math.sqrt((first.x - second.x) ** 2 + (first.y - second.y) ** 2 + (first.z - second.z) ** 2)
            cutoff = distance_factor * (COVALENT_RADII.get(first.element, 0.85) + COVALENT_RADII.get(second.element, 0.85))
            if 0.1 < distance <= cutoff:
                bonds.append(Bond(i, j))
    return tuple(bonds)
