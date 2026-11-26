"""Element-preserving orthogonal symmetries of a finite Cartesian geometry (Å)."""

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass
from itertools import product
from typing import Optional, Tuple

from .models import Molecule


Vector = Tuple[float, float, float]
DEFAULT_TOLERANCE = 0.05


@dataclass(frozen=True)
class RotationAxis:
    order: float  # 1 for no distinguished rotation axis, infinity for linear geometries
    direction: Optional[Vector]


@dataclass(frozen=True)
class SymmetryOperation:
    """For determinant -1 the operation is inversion times the reported proper rotation."""

    determinant: int
    order: int
    direction: Optional[Vector]


@dataclass(frozen=True)
class RotationAnalysis:
    principal: RotationAxis
    operations: Tuple[SymmetryOperation, ...]
    closed: bool = True


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v):
    return math.sqrt(_dot(v, v))


def _unit(v):
    length = _norm(v)
    return tuple(x / length for x in v)


def _canonical(v):
    # Resolve the sign of an unoriented line in the input coordinate frame.
    pivot = max((2, 1, 0), key=lambda i: round(abs(v[i]), 10))
    return tuple(-x for x in v) if v[pivot] < 0 else v


def _frame(a, b):
    u = _unit(a)
    normal = _cross(u, b)
    if _norm(normal) == 0:
        return None
    w = _unit(normal)
    return u, _cross(w, u), w


def _matrix(source, target, sign):
    # The images of two independent vectors determine exactly one isometry per handedness.
    return tuple(tuple(target[0][i]*source[0][j] + target[1][i]*source[1][j]
                       + sign*target[2][i]*source[2][j] for j in range(3)) for i in range(3))


def rotation_axis_angle(matrix, sign=1):
    """Return the unit axis and angle in radians of the proper rotation sign * matrix."""
    # Extract a quaternion from R = sign * matrix. The diagonal branch is stable near pi.
    m = tuple(tuple(sign * x for x in row) for row in matrix)
    trace = sum(m[i][i] for i in range(3))
    skew = (m[2][1]-m[1][2], m[0][2]-m[2][0], m[1][0]-m[0][1])
    if trace > 0:
        w = math.sqrt(1 + trace) / 2
        v = tuple(x / (4*w) for x in skew)
    else:
        i = max(range(3), key=lambda k: m[k][k])
        j, k = (i + 1) % 3, (i + 2) % 3
        t = math.sqrt(max(0, 1 + m[i][i] - m[j][j] - m[k][k])) / 2
        v = [0., 0., 0.]
        v[i], v[j], v[k] = t, (m[j][i]+m[i][j])/(4*t), (m[k][i]+m[i][k])/(4*t)
        w = skew[i]/(4*t)
    length = _norm(v)
    if length < 1e-12:
        return None, 0.0
    axis = tuple(x / length for x in v)
    return axis, 2 * math.atan2(length, w)


def rotation_matrix(axis, angle, sign=1):
    """Build a right-handed rotation from a unit axis and an angle in radians."""
    if axis is None:
        return ((sign, 0, 0), (0, sign, 0), (0, 0, sign))
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    skew = ((0, -z, y), (z, 0, -x), (-y, x, 0))
    return tuple(tuple(sign * (c*(i == j) + (1-c)*axis[i]*axis[j] + s*skew[i][j])
                       for j in range(3)) for i in range(3))


class _Matcher:
    def __init__(self, points, elements, tolerance):
        self.points, self.elements, self.tolerance = points, elements, tolerance
        self.width = 2 * tolerance
        self.cells = defaultdict(list)
        for i, p in enumerate(points):
            key = tuple(math.floor(x / self.width) for x in p)
            self.cells[(elements[i], *key)].append(i)

    def match(self, matrix):
        options = []
        for e, p in zip(self.elements, self.points):
            q = tuple(_dot(row, p) for row in matrix)
            cells = [range(math.floor((x - self.tolerance) / self.width),
                           math.floor((x + self.tolerance) / self.width) + 1) for x in q]
            hits = []
            for cell in product(*cells):
                for j in self.cells.get((e, *cell), ()):
                    distance = math.dist(q, self.points[j])
                    if distance <= self.tolerance:
                        hits.append((distance, j))
            if not hits:
                return None
            options.append([j for _, j in sorted(hits)])
        first = tuple(row[0] for row in options)
        if len(set(first)) == len(first):
            return first
        # A geometric operation must induce a bijection, including crowded or coincident sites.
        assigned = {}
        for i in sorted(range(len(options)), key=lambda j: len(options[j])):
            queue, via, seen = deque([i]), {}, {i}
            end = None
            while queue and end is None:
                current = queue.popleft()
                for target in options[current]:
                    owner = assigned.get(target)
                    if owner is None:
                        end = current, target
                        break
                    if owner not in seen:
                        seen.add(owner)
                        via[owner] = current, target
                        queue.append(owner)
            if end is None:
                return None
            current, target = end
            assigned[target] = current
            while current != i:
                current, target = via[current]
                assigned[target] = current
        result = [None] * len(options)
        for target, source in assigned.items():
            result[source] = target
        return tuple(result)


def _refine(matrix, points, mapping):
    """One small least-squares rotation correction using all matched coordinates."""
    covariance = [[0.] * 3 for _ in range(3)]
    rhs = [0.] * 3
    for p, j in zip(points, mapping):
        q = tuple(_dot(row, p) for row in matrix)
        delta = _cross(q, points[j])
        for i in range(3):
            rhs[i] += delta[i]
            for k in range(i + 1):
                covariance[i][k] += q[i]*q[k]
    trace = sum(covariance[i][i] for i in range(3))
    rows = [tuple((trace if i == k else 0.) - covariance[max(i,k)][min(i,k)]
                  for k in range(3)) for i in range(3)]
    # Solve (trace(C) I - C) omega = sum(q cross target) for the three angular corrections.
    columns = (_cross(rows[1], rows[2]), _cross(rows[2], rows[0]), _cross(rows[0], rows[1]))
    det = _dot(rows[0], columns[0])
    if det <= 0:
        return matrix
    delta = tuple(_dot(col, rhs) / det for col in columns)
    angle = _norm(delta)
    if angle < 1e-12:
        return matrix
    correction = rotation_matrix(_unit(delta), angle, 1)
    return tuple(tuple(_dot(row, col) for col in zip(*matrix)) for row in correction)


def _verified_operation(matrix, sign, mapping, points, tolerance):
    visited = set()
    period = 1
    for i in range(len(mapping)):
        if i not in visited:
            j, length = i, 0
            while j not in visited:
                visited.add(j)
                length += 1
                j = mapping[j]
            period = math.lcm(period, length)
    # On a planar molecule an odd permutation period can still leave a plane reflection
    # acting on the unoccupied normal. Doubling it bounds the period of R = -operation.
    denominator = 2*period if sign < 0 and period % 2 else period
    axis, angle = rotation_axis_angle(matrix, sign)
    numerator = round(angle * denominator / math.tau)
    order = denominator // math.gcd(numerator, denominator)
    snapped = rotation_matrix(axis, math.tau * numerator / denominator, sign)
    if any(math.dist(tuple(_dot(row, p) for row in snapped), points[j]) > tolerance
           for p, j in zip(points, mapping)):
        return None
    return SymmetryOperation(sign, order, _canonical(axis) if order > 1 else None)


def _linear_axis(points, seed, tolerance):
    # Refine the farthest-atom direction to the best-fit straight line for rounded XYZ files.
    if max(_norm(_cross(p, seed)) for p in points) > 2*tolerance:
        return None
    covariance = [tuple(sum(p[i]*p[j] for p in points) for j in range(3)) for i in range(3)]
    direction = seed
    for _ in range(5):
        direction = _unit(tuple(_dot(row, direction) for row in covariance))
    if all(_norm(_cross(p, direction)) <= tolerance/2 for p in points):
        return _canonical(direction)
    return None


def _find_operations(points, elements, radii, tolerance):
    shells = defaultdict(list)
    for i, (element, radius) in enumerate(zip(elements, radii)):
        shells[element].append((radius, i))
    for shell in shells.values():
        shell.sort()
    spans = []
    for e, radius in zip(elements, radii):
        shell = shells[e]
        spans.append((bisect_left(shell, (radius-tolerance, -1)), bisect_right(shell, (radius+tolerance, len(points)))))

    def anchor(levers):
        # Long baselines limit angular error, and a small elemental shell prunes possible images.
        minimum = max(levers) * .65
        return min((i for i, length in enumerate(levers) if length >= minimum),
                   key=lambda i: (spans[i][1]-spans[i][0], -levers[i], i))

    def targets(i):
        lo, hi = spans[i]
        return (j for _, j in shells[elements[i]][lo:hi])

    a = anchor(radii)
    u = _unit(points[a])
    b = anchor([_norm(_cross(u, p)) for p in points])
    source = _frame(points[a], points[b])
    length = math.dist(points[a], points[b])
    matcher = _Matcher(points, elements, tolerance * 3)
    found = {}
    for i in targets(a):
        for j in targets(b):
            if i == j or abs(math.dist(points[i], points[j]) - length) > 2*tolerance:
                continue
            target = _frame(points[i], points[j])
            if target is None:
                continue
            for sign in (1, -1):
                matrix = _matrix(source, target, sign)
                mapping = matcher.match(matrix)
                if mapping is None or (sign, mapping) in found:
                    continue
                matrix = _refine(matrix, points, mapping)
                op = _verified_operation(matrix, sign, mapping, points, tolerance)
                if op is not None:
                    found[sign, mapping] = op
    # A single angular step can match a very slightly distorted ring while
    # its half-turn misses by many times the tolerance. Require the whole
    # cyclic subgroup of every proposed generator to have passed verification.
    identity = (1, tuple(range(len(points))))
    valid = set()
    for key in found:
        if key in valid:
            continue
        sign, permutation = key
        cycle = {key}
        power_sign, power = key
        while (power_sign, power) != identity:
            power_sign *= sign
            power = tuple(permutation[i] for i in power)
            if (power_sign, power) not in found:
                break
            cycle.add((power_sign, power))
        else:
            valid.update(cycle)
    operations = tuple(op for key, op in found.items() if key in valid)
    # At a tolerance boundary different, individually verified axes may still
    # generate a product that fails atom matching. Check closure by generators.
    generated, generators = {identity}, []
    for key in found:
        if key not in valid or key in generated:
            continue
        generators.append(key)
        pending = deque(generated)
        while pending:
            sign, mapping = pending.popleft()
            for generator_sign, generator in generators:
                composed = sign*generator_sign, tuple(generator[i] for i in mapping)
                if composed not in valid:
                    return operations, False
                if composed not in generated:
                    generated.add(composed)
                    pending.append(composed)
    return operations, identity in valid


def analyze_rotations(molecule: Molecule, tolerance: float = DEFAULT_TOLERANCE) -> RotationAnalysis:
    """Discover rigid atom permutations at an absolute Cartesian matching tolerance in Å."""
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Symmetry tolerance must be positive and finite")
    no_axis = RotationAxis(1, None)
    if len(molecule.atoms) < 2:
        return RotationAnalysis(no_axis, ())
    atoms = sorted((a.element, a.x, a.y, a.z) for a in molecule.atoms)
    magnitude = max(abs(v) for row in atoms for v in row[1:])
    if not math.isfinite(magnitude):
        raise ValueError("Symmetry analysis requires finite coordinates")
    if magnitude == 0 or tolerance < math.ulp(magnitude):
        return RotationAnalysis(no_axis, (), closed=False)
    # Keep dot products, the least-squares determinant and spatial grid indices
    # representable even when a file's coordinates use extreme numerical scales.
    if magnitude > 1e12 or magnitude < 1e-6:
        atoms = [(e, x/magnitude, y/magnitude, z/magnitude) for e, x, y, z in atoms]
        tolerance /= magnitude
    center = tuple(math.fsum(row[i] for row in atoms) / len(atoms) for i in (1, 2, 3))
    points = [tuple(x-c for x, c in zip(row[1:], center)) for row in atoms]
    elements = [row[0] for row in atoms]
    radii = [_norm(p) for p in points]
    farthest = max(range(len(points)), key=radii.__getitem__)
    if radii[farthest] <= tolerance/2:
        return RotationAnalysis(no_axis, (), closed=False)
    line = _linear_axis(points, _unit(points[farthest]), tolerance)
    if line is not None:
        inversion = rotation_matrix(None, 0., -1)
        matched = _Matcher(points, elements, tolerance).match(inversion)
        operations = (SymmetryOperation(-1, 1, None),) if matched is not None else ()
        return RotationAnalysis(RotationAxis(math.inf, line), operations)
    operations, closed = _find_operations(points, elements, radii, tolerance)
    proper = [op for op in operations if op.determinant > 0 and op.order > 1]
    if not proper:
        return RotationAnalysis(no_axis, operations, closed)
    highest = max(op.order for op in proper)
    candidates = [op.direction for op in proper if op.order == highest]
    improper = [op for op in operations if op.determinant < 0 and op.order > 2]

    def preference(v):
        # In D2d, prefer the C2 on the S4 axis. Resolve truly equivalent axes in input space.
        coaxial = max((op.order for op in improper if abs(_dot(v, op.direction)) > .999), default=0)
        return (coaxial, *(round(abs(v[i]), 8) for i in (2, 1, 0)), *(round(x, 8) for x in v))

    return RotationAnalysis(RotationAxis(highest, max(candidates, key=preference)), operations, closed)


def principal_rotation_axis(molecule: Molecule, tolerance: float = DEFAULT_TOLERANCE) -> RotationAxis:
    return analyze_rotations(molecule, tolerance).principal
