"""Screen-space curves following the supported edges of a polymer backbone."""

from collections import Counter, defaultdict
from dataclasses import dataclass
import math

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath


def chain_paths(edges):
    """Order each open strand, cycle, or arm of a junction exactly once."""
    neighbors = defaultdict(set)
    for a, b in edges:
        if a != b:
            neighbors[a].add(b)
            neighbors[b].add(a)
    visited = set()
    paths = []

    def follow(a, b):
        strand = [a]
        while (a, b) not in visited:
            visited.update(((a, b), (b, a)))
            strand.append(b)
            if len(neighbors[b]) != 2:
                break
            first, second = neighbors[b]
            a, b = b, second if first == a else first
        if len(strand) > 1:
            paths.append(tuple(strand))

    for start in sorted(i for i in neighbors if len(neighbors[i]) != 2):
        for next_atom in sorted(neighbors[start]):
            follow(start, next_atom)
    # The only remaining edges belong to cycles without an endpoint or junction.
    for start in sorted(neighbors):
        for next_atom in sorted(neighbors[start]):
            follow(start, next_atom)
    return tuple(paths)


@dataclass(frozen=True)
class TraceSegment:
    a: int
    b: int
    path: QPainterPath
    depth: float


def _fair(values, passes, periodic):
    # Repeated binomial averaging removes bond-scale zigzags without fitting a
    # different secondary structure. Open ends and junctions are pinned.
    count = len(values)
    for _ in range(passes):
        result = values.copy()
        for i in range(0 if periodic else 1, count if periodic else count - 1):
            result[i] = (values[i-1] + values[i] * 2. + values[(i+1) % count]) * .25
        values = result
    return values


def _handles(points, periodic):
    handles = []
    for i, p in enumerate(points):
        if not periodic and i == 0:
            handles.append((points[1] - p) / 3.)
        elif not periodic and i == len(points) - 1:
            handles.append((p - points[i-1]) / 3.)
        else:
            incoming = p - points[i-1]
            outgoing = points[(i+1) % len(points)] - p
            left = math.hypot(incoming.x(), incoming.y())
            right = math.hypot(outgoing.x(), outgoing.y())
            # Shared incoming/outgoing handles give matching tangents. Bounding
            # them by the shorter projected edge avoids loops on a tight turn.
            handle = QPointF()
            if min(left, right) > 1e-9:
                handle = (incoming / left + outgoing / right) * (min(left, right) / 6.)
            handles.append(handle)
    return handles


def project_trace(paths, positions, depths, *, independent_sketch=False, phosphate_sites=()):
    """Return displayed atom positions and one cubic segment per supplied edge.

    The source positions and molecular coordinates are never mutated. Original
    atom indices stay available for picking. A detached, manually laid-out
    sketch interpolates its exact points.
    """
    displayed = list(positions)
    segments = []
    phosphate_sites = set(phosphate_sites)
    ends = Counter(i for strand in paths for i in {strand[0], strand[-1]})
    for strand in paths:
        # A loop attached to another strand shares a fixed junction at its seam.
        periodic = strand[0] == strand[-1] and ends[strand[0]] == 1
        nodes = strand[:-1] if periodic else strand
        # Short chains and small rings retain their characteristic size. Six
        # passes on a long chain average over roughly two adjacent backbone atoms.
        limit = 12 if not phosphate_sites.isdisjoint(nodes) else 6
        passes = 0 if independent_sketch else min(limit, (len(nodes) - 1) // 4)
        points = _fair([positions[i] for i in nodes], passes, periodic)
        z = _fair([depths[i] for i in nodes], passes, periodic)
        handles = _handles(points, periodic)
        for i, p in zip(nodes, points):
            displayed[i] = p
        for k, (a, b) in enumerate(zip(strand, strand[1:])):
            j = (k+1) % len(points)
            curve = QPainterPath(points[k])
            curve.cubicTo(points[k] + handles[k], points[j] - handles[j], points[j])
            segments.append(TraceSegment(a, b, curve, (z[k] + z[j]) * .5))
    return tuple(displayed), tuple(segments)
