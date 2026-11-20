"""Schoenflies point groups of labelled Cartesian structures."""

from functools import lru_cache
from math import isinf

from .models import Molecule
from .symmetry import DEFAULT_TOLERANCE, RotationAxis, analyze_rotations


def _alignment(first, second):
    """Absolute cosine between two unoriented unit vectors."""
    return abs(sum(a * b for a, b in zip(first, second)))


@lru_cache(maxsize=8)
def geometric_symmetry(molecule: Molecule, tolerance: float = DEFAULT_TOLERANCE) -> tuple[str, RotationAxis]:
    """Return the geometry's point group and principal proper axis in one search.

    The tolerance (Å) applies to same-element atom correspondence under each
    operation. A degenerate geometry or an inconsistent set of near-symmetries
    yields “未定”. Charges, bonds and electronic state do not enter this test.
    """
    analysis = analyze_rotations(molecule, tolerance)
    principal = analysis.principal
    if not molecule.atoms:
        return "—", principal
    if len(molecule.atoms) == 1:
        return "Kh", principal
    if not analysis.closed:
        # Independently passing operations near the tolerance boundary may
        # fail to form a point group. The verified rotation axis still exists.
        return "未定", principal

    # An orientation-reversing operation is stored as -R, for a proper
    # rotation R. Its order *as R* is 1 for inversion and 2 for a reflection.
    proper = [op for op in analysis.operations if op.determinant == 1]
    improper = [op for op in analysis.operations if op.determinant == -1]
    inversion = any(op.order == 1 for op in improper)
    mirrors = [op.direction for op in improper if op.order == 2]
    if isinf(principal.order):
        return ("D∞h" if inversion else "C∞v"), principal
    if not analysis.operations:
        return "未定", principal
    n = int(principal.order)
    if n == 1:
        if mirrors:
            return "Cs", principal
        return ("Ci" if inversion else "C1"), principal

    # Finite polyhedral groups are exactly those with non-collinear C3+
    # axes. Their largest rotation orders distinguish I, O and T.
    axis = principal.direction
    if n >= 3 and any(op.order >= 3 and _alignment(axis, op.direction) < 0.95
                      for op in proper):
        if n == 5:
            return ("Ih" if inversion else "I"), principal
        if n == 4:
            return ("Oh" if inversion else "O"), principal
        if n == 3:
            if inversion:
                return "Th", principal
            return ("Td" if mirrors else "T"), principal

    # Once a transformation itself has passed atom matching, its direction
    # is used only to distinguish parallel and perpendicular symmetry elements.
    dihedral = any(op.order == 2 and _alignment(axis, op.direction) < 0.15
                   for op in proper)
    horizontal = any(_alignment(axis, normal) > 0.95 for normal in mirrors)
    if horizontal:
        return f"{'D' if dihedral else 'C'}{n}h", principal
    if dihedral:
        return (f"D{n}d" if mirrors else f"D{n}"), principal
    if mirrors:
        return f"C{n}v", principal
    if improper:
        return f"S{2 * n}", principal
    return f"C{n}", principal


def point_group(molecule: Molecule, tolerance: float = DEFAULT_TOLERANCE) -> str:
    """Return only the Schoenflies symbol."""
    return geometric_symmetry(molecule, tolerance)[0]
