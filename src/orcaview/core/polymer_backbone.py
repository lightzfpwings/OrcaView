"""Identify the main covalent paths of peptides and DNA without modifying their topology."""

from itertools import permutations, product

from .models import COORDINATE_STYLES


def validate_polymer_roles(roles, atom_count):
    """Validate optional, row-aligned backbone roles from an external record."""
    if not isinstance(roles, str) or (roles and (len(roles) != atom_count or not set(roles) <= {"B", "S", "."})):
        raise ValueError("Invalid polymer atom roles")


def validate_backbone_links(links, roles):
    """Check a source's optional, canonical 2D backbone edges in its own atom order."""
    if links is None:
        return
    if not isinstance(links, tuple):
        raise ValueError("Invalid backbone links")
    previous = (-1, -1)
    for edge in links:
        if (not isinstance(edge, tuple) or len(edge) != 2 or any(type(i) is not int for i in edge)
                or not 0 <= edge[0] < edge[1] < len(roles) or edge <= previous
                or roles[edge[0]] != "B" or roles[edge[1]] != "B"):
            raise ValueError("Invalid backbone link")
        previous = edge


def _peptide_units(elements, neighbors):
    """Find N–Cα–C(=O) units, retaining only the atoms on the main path."""
    carbonyls = {c for c, edges in enumerate(neighbors) if elements[c] == "C" and
                 any(elements[o] == "O" and order >= 1.5 and len(neighbors[o]) == 1
                     for o, order in edges.items())}
    units = []
    for alpha, edges in enumerate(neighbors):
        if elements[alpha] != "C" or any(order != 1 for order in edges.values()):
            continue
        for carbon in edges.keys() & carbonyls:
            for n in edges:
                if elements[n] == "N":
                    units.append((n, alpha, carbon))
    return units


def _dna_units(elements, neighbors):
    """Identify deoxyribose by the ring O, glycosidic N, and exocyclic C5′."""
    def attached(atom, element):
        return [i for i, order in neighbors[atom].items() if elements[i] == element and order == 1]

    units = []
    for ring_o, element in enumerate(elements):
        if element != "O":
            continue
        carbons = attached(ring_o, "C")
        if len(carbons) != 2:
            continue
        for c1, c4 in permutations(carbons):
            if not attached(c1, "N"):
                continue
            # The path C1′–C2′–C3′–C4′ closes the sugar ring, whereas C5′
            # is outside it. Ribose has an extra exocyclic oxygen at C2′.
            c2_candidates = {i for i in attached(c1, "C") if not attached(i, "O")}
            for c3, c5 in permutations(attached(c4, "C"), 2):
                if not c2_candidates.intersection(attached(c3, "C")):
                    continue
                for o3, o5 in product(attached(c3, "O"), attached(c5, "O")):
                    path = (o5, c5, c4, c3, o3)
                    phosphates = attached(o5, "P")
                    units.append((phosphates[0], *path) if phosphates else path)
    return units


def _chain_atoms(units, neighbors, allow_monomer):
    """Retain actual residues joined end-to-start, including unphosphorylated ends."""
    if allow_monomer:
        return {atom for unit in units for atom in unit}
    starts = {unit[0] for unit in units}
    ends = {unit[-1] for unit in units}
    return {atom for unit in units
            if ends.intersection(neighbors[unit[0]]) or starts.intersection(neighbors[unit[-1]])
            for atom in unit}


def topology_roles(molecule, polymer=None) -> str:
    """Mark backbone (B), other polymer atoms (S) and unrelated fragments (.).

    An empty string means no polymer was recognized. Unannotated structures
    require joined residue motifs; a known polymer source can also identify a
    single residue. Only stored connectivity is used.
    """
    if not molecule.bonds:
        return ""
    elements = [atom.element for atom in molecule.atoms]
    if not {"C", "N", "O"}.issubset(elements):
        return ""
    neighbors = [{} for _ in elements]
    for b in molecule.bonds:
        if b.is_covalent and b.style not in COORDINATE_STYLES:
            neighbors[b.a][b.b] = neighbors[b.b][b.a] = b.valence_order

    backbone = _chain_atoms(_peptide_units(elements, neighbors), neighbors, polymer == "protein")
    dna = _chain_atoms(_dna_units(elements, neighbors), neighbors, polymer == "dna")
    # A deposited chain can also have a phosphate on its final 3′ oxygen.
    backbone.update(p for o in dna if elements[o] == "O" for p in neighbors[o] if elements[p] == "P")
    backbone.update(dna)
    if not backbone:
        return ""
    roles = ["."] * len(elements)
    for atom in backbone:
        roles[atom] = "B"
    pending = list(backbone)
    while pending:
        previous = pending.pop()
        for atom in neighbors[previous]:
            if roles[atom] == ".":
                roles[atom] = "S"
                pending.append(atom)
    return "".join(roles)
