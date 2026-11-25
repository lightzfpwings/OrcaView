"""Place explicit hydrogens without moving the existing atoms of a Cartesian sketch."""

from dataclasses import replace
import json
import math

from orcaview.core.elements import COVALENT_RADII
from orcaview.core.geometry import display_bonds, occupied_valences
from orcaview.core.models import Atom, Bond

from .coordinates import _cross, _dot, _unit


# Neutral valences used by the design editor. Higher-valence P/S and metals are
# left as drawn; atom-local formal charges and radicals are not part of the model.
_NEUTRAL_VALENCE = {"B": 3, "C": 4, "N": 3, "O": 2, "F": 1, "Si": 4,
                    "P": 3, "S": 2, "Cl": 1, "Br": 1, "I": 1}


def missing_hydrogens(molecule):
    """Return new (parent index, H) pairs and any perceived coordinate-only bonds."""
    if molecule.charge or molecule.multiplicity != 1:
        raise ValueError("Automatic H addition supports neutral singlets. Add H manually for other electronic states.")
    bonds = display_bonds(molecule)
    perceived = None
    if bonds and not (molecule.bonds or molecule.bonds_explicit):
        from orcaview.io.babel_geometry import geometry_payload, with_perceived_orders
        from orcaview.io.babel_structure import run_babel_worker

        payload = geometry_payload(molecule, bonds=bonds)
        payload["infer_orders"] = True
        orders = run_babel_worker(json.dumps(payload, allow_nan=False).encode(), "perceive-orders").get("orders")
        perceived = bonds = with_perceived_orders(bonds, orders)
    occupied = occupied_valences(molecule, bonds)
    # A neutral total can hide opposite local charges, for example in a nitro
    # group. No atom-local charge information distinguishes an O- from an OH.
    if any(atom.element in ("B", "N", "O", "F") and total > _NEUTRAL_VALENCE[atom.element]
           for atom, total in zip(molecule.atoms, occupied)):
        raise ValueError("The structure contains atoms with ambiguous formal charge. Add H manually.")

    result = []
    placed = molecule
    for index, atom in enumerate(molecule.atoms):
        # An unresolved half bond leaves a fractional deficit. Only fill whole H.
        count = math.floor(_NEUTRAL_VALENCE.get(atom.element, 0) - occupied[index])
        for _ in range(count):
            hydrogen = attached_hydrogen(placed, index, bonds)
            bonds += (Bond(index, len(placed.atoms)),)
            placed = replace(placed, atoms=placed.atoms + (hydrogen,))
            result.append((index, hydrogen))
    return tuple(result), perceived


def _directions(neighbors, cosine):
    """Ideal local bond directions first, plus a sphere for crowded or unusual sites."""
    yield (1., 0., 0.)
    if neighbors:
        # Sample the cone making the desired angle to the first bond. An XY
        # tangent keeps the first branches of a planar sketch easy to select.
        first = neighbors[0]
        tangent = (-first[1], first[0], 0.)
        tangent = _unit(tangent, "Bond direction") if math.hypot(*tangent) > 1e-10 else (1., 0., 0.)
        normal = _cross(first, tangent)
        sine = math.sqrt(1 - cosine * cosine)
        for i in range(24):
            angle = math.tau * i / 24
            yield tuple(cosine * u + sine * (v * math.cos(angle) + w * math.sin(angle))
                        for u, v, w in zip(first, tangent, normal))
    if len(neighbors) in (2, 3):
        # Intersect the two bond-angle cones. Both faces are candidates, so
        # the existing third bond or a nearby fragment selects the open face.
        first, second = neighbors[:2]
        normal = _cross(first, second)
        total = tuple(a + b for a, b in zip(first, second))
        length = math.hypot(*total)
        if length > 1e-8 and math.hypot(*normal) > 1e-8:
            bisector = _unit(total, "Bond direction")
            normal = _unit(normal, "Bond direction")
            along = max(-1., 2 * cosine / length)
            across = math.sqrt(1 - along * along)
            for sign in (1, -1):
                yield tuple(along * d + sign * across * n for d, n in zip(bisector, normal))
                yield tuple(sign * n for n in normal)
        opposite = tuple(-sum(axis) for axis in zip(*neighbors))
        if math.hypot(*opposite) > 1e-8:
            yield _unit(opposite, "Bond direction")

    # The phase changes as the site fills so successive manual clicks remain
    # distinct even at very high coordination.
    golden_angle = math.pi * (3 - math.sqrt(5))
    for i in range(96):
        z = 1 - 2 * (i + .5) / 96
        radius = math.sqrt(1 - z * z)
        phi = (i + len(neighbors)) * golden_angle
        yield radius * math.cos(phi), radius * math.sin(phi), z


def attached_hydrogen(molecule, anchor, bonds):
    """Return one H using the existing geometry without imposing a valence limit."""
    atom = molecule.atoms[anchor]
    length = .74 if atom.element == "H" else COVALENT_RADII.get(atom.element, .85) + COVALENT_RADII["H"]
    origin = (atom.x, atom.y, atom.z)
    bonded = {b.b if b.a == anchor else b.a: b.order for b in bonds if anchor in (b.a, b.b)}
    neighbors = []
    nearby = []
    for i, other in enumerate(molecule.atoms):
        if i == anchor:
            continue
        delta = tuple(v - p for v, p in zip((other.x, other.y, other.z), origin))
        distance = math.hypot(*delta)
        if i in bonded and distance > 1e-8:
            neighbors.append(_unit(delta, "Bond direction"))
        if distance < length + 3.:
            nearby.append(delta)
    order = max(bonded.values(), default=1)
    cosine = {1: -1 / 3, 2: -.5, 3: -1.}[order]

    def score(direction):
        position = tuple(length * d for d in direction)
        clearance = min((math.dist(position, point) for point in nearby), default=math.inf)
        projections = [_dot(direction, n) for n in neighbors]
        if len(neighbors) <= 3:
            penalty = max((abs(dot - cosine) for dot in projections), default=0.)
        else:
            penalty = max(projections)
        projected_gap = min((math.hypot(position[0] - x, position[1] - y) for x, y, _ in nearby),
                            default=math.inf)
        projected_gap = min(.45, math.hypot(*position[:2]), projected_gap)
        # When a lone single bond has rotational freedom, tilt the new bond
        # slightly so the remaining two tetrahedral sites project separately.
        preferred_z = .45 if len(neighbors) == 1 and order == 1 else 0.
        return min(.8, clearance), -round(penalty, 8), projected_gap, -abs(direction[2] - preferred_z), clearance

    direction = max(_directions(neighbors, cosine), key=score)
    xyz = tuple(p + length * d for p, d in zip(origin, direction))
    if not math.isclose(math.dist(origin, xyz), length, rel_tol=1e-3):
        raise ValueError("The coordinate precision does not allow this distance. The edit was not applied.")
    return Atom("H", *xyz)
