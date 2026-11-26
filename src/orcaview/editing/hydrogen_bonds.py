"""Restrained pre-optimization of explicitly marked donor–H···acceptor contacts."""

from dataclasses import replace
import math

from orcaview.core.geometry import connected_component, covalent_bonds
from orcaview.core.models import Molecule

from .commands import OptimizeCoordinates
from .optimization import _calculate_points


DEFAULT_DISTANCE = 1.90
DEFAULT_ANGLE = 170.0


def optimize_hydrogen_bonds(snapshot, distance=DEFAULT_DISTANCE, angle=DEFAULT_ANGLE):
    molecule = snapshot.molecule
    if (type(distance) not in (int, float) or not 0.5 <= distance <= 5.0
            or type(angle) not in (int, float) or not 90 <= angle <= 180):
        raise ValueError("Choose an H···A distance from 0.50 to 5.00 Å and a D–H···A angle from 90 to 180°.")
    if molecule.charge != 0 or molecule.multiplicity != 1:
        raise ValueError("3D force-field optimization currently supports neutral singlets.")
    covalent = covalent_bonds(molecule)
    triples = []
    active = set()
    for bond in molecule.bonds:
        if bond.style != "hydrogen_bond":
            continue
        h, a = (bond.a, bond.b) if molecule.atoms[bond.a].element == "H" else (bond.b, bond.a)
        neighbors = [b.b if b.a == h else b.a for b in covalent if h in (b.a, b.b)]
        if (len(neighbors) != 1 or molecule.atoms[neighbors[0]].element == "H"
                or neighbors[0] == a):
            raise ValueError("Each marked hydrogen must have one covalently bonded donor atom.")
        triples.append((neighbors[0], h, a))
        for i in (h, a):
            if i not in active:
                active.update(connected_component(covalent, i))
    if not triples:
        raise ValueError("Mark a hydrogen bond between an explicit H and an acceptor first.")

    # Keep spectator molecules out of the force field (including its nonbonded terms).
    rows = sorted(active)
    local = {idx: n for n, idx in enumerate(rows)}
    graph = tuple(replace(b, a=local[b.a], b=local[b.b]) for b in covalent if b.a in active)
    assembly = Molecule(molecule.name, tuple(molecule.atoms[i] for i in rows), graph, bonds_explicit=True)
    mapped = [(local[d], local[h], local[a]) for d, h, a in triples]
    restraints = {"triples": mapped, "distance": distance, "angle": angle}
    points, response = _calculate_points(assembly, "hbonds", graph, contact_restraints=restraints)
    for donor, hydrogen, acceptor in mapped:
        dh = tuple(d - h for d, h in zip(points[donor], points[hydrogen]))
        ah = tuple(a - h for a, h in zip(points[acceptor], points[hydrogen]))
        length = math.hypot(*ah)
        product = length * math.hypot(*dh)
        if product:
            cosine = sum(x * y for x, y in zip(dh, ah)) / product
            actual = math.degrees(math.acos(max(-1., min(1., cosine))))
        if not product or abs(length - distance) > .15 or abs(actual - angle) > 12:
            raise ValueError("The force field could not satisfy the hydrogen-bond targets. Check the starting geometry or adjust the targets.")
    coordinates = [(a.x, a.y, a.z) for a in molecule.atoms]
    for original, xyz in zip(rows, points):
        coordinates[original] = tuple(xyz)
    return OptimizeCoordinates(response["method"], tuple(coordinates))
