"""Planar starting geometries for rings in a molecular sketch."""

from dataclasses import replace
import math

from orcaview.core.elements import COVALENT_RADII
from orcaview.core.geometry import display_bonds
from orcaview.core.models import Atom, Bond


CARBON_RING_SIZES = range(3, 13)
# Vertex zero is the carbon used for attachment. Order i joins vertices i and i+1.
HETEROCYCLES = {
    "pyrrole":    ("CCNCC", (2, 1, 1, 2, 1)),
    "furan":      ("CCOCC", (2, 1, 1, 2, 1)),
    "thiophene":  ("CCSCC", (2, 1, 1, 2, 1)),
    "imidazole":  ("CNCCN", (2, 1, 2, 1, 1)),
    "pyrazole":   ("CCNNC", (2, 1, 1, 2, 1)),
    "pyridine":   ("CNCCCC", (2, 1, 2, 1, 2, 1)),
    "pyrimidine": ("CNCNCC", (2, 1, 2, 1, 2, 1)),
    "pyrazine":   ("CNCCNC", (2, 1, 2, 1, 2, 1)),
}


def ring_composition(size, benzene, heterocycle):
    if size in CARBON_RING_SIZES and type(benzene) is bool:
        if heterocycle is None and (not benzene or size == 6):
            return "C" * size, (2, 1) * 3 if benzene else (1,) * size
        if not benzene and isinstance(heterocycle, str):
            template = HETEROCYCLES.get(heterocycle)
            if template and len(template[0]) == size:
                return template
    raise ValueError("Choose a carbon ring with 3 to 12 atoms or a listed aromatic ring.")


def open_direction(anchor, bonds, xyz, u, v):
    """Point the new bond into the largest gap between projected neighbour bonds."""
    directions = []
    for bond in bonds:
        if not bond.is_covalent or anchor not in (bond.a, bond.b):
            continue
        other = bond.b if bond.a == anchor else bond.a
        dx = xyz[other][u] - xyz[anchor][u]
        dy = xyz[other][v] - xyz[anchor][v]
        if math.hypot(dx, dy) > 1e-9:
            directions.append(math.atan2(dy, dx))
    if not directions:
        return 0.
    directions.sort()
    following = directions[1:] + [directions[0] + math.tau]
    start, stop = max(zip(directions, following), key=lambda pair: pair[1] - pair[0])
    return (start + stop) / 2


def insert_ring(molecule, operation, anchor):
    bonds = display_bonds(molecule)
    existing = [(atom.x, atom.y, atom.z) for atom in molecule.atoms]
    u, v = ("XYZ".index(axis) for axis in operation.plane)
    count = operation.size
    elements, orders = ring_composition(count, operation.benzene, operation.heterocycle)
    # Sketch lengths in angstrom. Saturated rings are flat initial sketches.
    edge = 1.40 if 2 in orders else 1.52
    radius = edge / (2 * math.sin(math.pi / count))
    vertices = [math.pi + math.tau * i / count for i in range(count)]
    # The explicit single-carbon document is the design page's starting sketch.
    use_seed = (anchor == 0 and len(existing) == 1 and molecule.atoms[0].element == "C"
                and molecule.bonds_explicit)
    if anchor is None:
        origin = operation.center
        center_offset = 0.
        direction = 0.
        step = math.tau / (24 * count)
    else:
        origin = existing[anchor]
        attachment = COVALENT_RADII["C"] + COVALENT_RADII.get(molecule.atoms[anchor].element, .85)
        center_offset = radius if use_seed else radius + attachment
        direction = open_direction(anchor, bonds, existing, u, v)
        step = math.tau / 24

    # Try the intended direction first, then nearby angles on either side.
    for attempt in range(24):
        turn = (attempt + 1) // 2 if attempt % 2 else -(attempt // 2)
        angle = direction + turn * step
        center = list(origin)
        center[u] += center_offset * math.cos(angle)
        center[v] += center_offset * math.sin(angle)
        positions = []
        for vertex in vertices:
            point = center.copy()
            point[u] += radius * math.cos(angle + vertex)
            point[v] += radius * math.sin(angle + vertex)
            positions.append(point)
        if use_seed:
            positions = positions[1:]
        if all(math.dist(point, old) >= .85 for point in positions for old in existing):
            break
    else:
        raise ValueError("The ring overlaps existing atoms. Choose another position.")

    first = len(existing)
    rows = ([anchor] if use_seed else []) + list(range(first, first + len(positions)))
    ring_bonds = tuple(Bond(rows[i], rows[(i + 1) % count], order) for i, order in enumerate(orders))
    if anchor is not None and not use_seed:
        ring_bonds += (Bond(anchor, first),)
    new_elements = elements[1:] if use_seed else elements
    new_atoms = tuple(Atom(symbol, *point) for symbol, point in zip(new_elements, positions))
    return replace(molecule, atoms=molecule.atoms + new_atoms,
                   bonds=bonds + ring_bonds, bonds_explicit=True)
