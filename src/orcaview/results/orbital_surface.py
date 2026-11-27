"""Sample a signed MO on a Cartesian grid and extract its two isosurfaces."""

from bisect import bisect_left, bisect_right
from concurrent.futures import CancelledError
from dataclasses import dataclass
from functools import lru_cache
import math

from orcaview.core.units import BOHR_IN_ANGSTROM
from orcaview.core.volume_grid import VolumeGrid
from orcaview.results.orbital_basis import orbital_expansion


def _check_cancel(event):
    if event is not None and event.is_set():
        raise CancelledError()


def sample_grid(expansion, axes, cancel=None):
    """Exploit the separability of each Cartesian Gaussian along x, y and z."""
    nx, ny, nz = map(len, axes)
    grid = [0.] * (nx*ny*nz)
    for center, primitives, terms in expansion:
        relative = [tuple(v-c for v in axis) for axis, c in zip(axes, center)]
        powers = [sorted({p[axis] for p, _ in terms}) for axis in range(3)]
        for exponent, weight in primitives:
            _check_cancel(cancel)
            # Outside this box the Gaussian factor is below exp(-50).
            radius = math.sqrt(50 / exponent)
            tables, starts = [], []
            for coords, degrees in zip(relative, powers):
                start = bisect_left(coords, -radius)
                points = coords[start:bisect_right(coords, radius)]
                ev = [math.exp(-exponent*v*v) for v in points]
                tables.append({p: [e * v**p for e, v in zip(ev, points)] for p in degrees})
                starts.append(start)
            sx, sy, sz = starts
            for (px, py, pz), coefficient in terms:
                xs, ys, zs = tables[0][px], tables[1][py], tables[2][pz]
                factor = weight * coefficient
                for ix, x in enumerate(xs, sx):
                    if not ix % 16:
                        _check_cancel(cancel)
                    base = (ix*ny + sy)*nz + sz
                    fx = factor*x
                    for y in ys:
                        fxy = fx*y
                        j = base
                        for z in zs:
                            grid[j] += fxy*z
                            j += 1
                        base += nz
    return grid


@dataclass(frozen=True)
class OrbitalSurface:
    vertices: tuple  # Cartesian angstroms
    faces: tuple     # three or four outward-wound indices, then phase (+1 or -1)
    clipped: bool
    normals: tuple = ()  # unit Cartesian field gradients, oriented out of each lobe


_CORNERS = tuple((x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1))
_TETRAHEDRA = ((0, 4, 6, 7), (0, 6, 2, 7), (0, 2, 3, 7),
               (0, 3, 1, 7), (0, 1, 5, 7), (0, 5, 4, 7))


@dataclass(frozen=True)
class SurfaceQuality:
    label: str
    max_intervals: int
    spacing_bohr: float
    min_intervals: int
    cube_subdivisions: int


# Display order is shared with the viewer. "fine" is the saved key for the highest setting.
SURFACE_QUALITIES = {
    "coarse": SurfaceQuality("Coarse", 52, .25, 24, 1),
    "standard": SurfaceQuality("Standard", 76, .17, 36, 2),
    "smooth": SurfaceQuality("Smooth", 100, .12, 48, 3),
    "fine": SurfaceQuality("Best", 128, .09, 64, 4),
}


def _cut_polygons(mask):
    """Precompute outward polygon order; all cells share the same face diagonals."""
    polygons = []
    for tetra in _TETRAHEDRA:
        inside = [k for k in tetra if mask & (1 << k)]
        outside = [k for k in tetra if not mask & (1 << k)]
        if not inside or not outside:
            continue
        if len(inside) == 2:
            a, b = inside
            c, d = outside
            edges = [(a, c), (a, d), (b, d), (b, c)]
        else:
            edges = [(a, b) for a in inside for b in outside]
        mid = [tuple((x+y)/2 for x, y in zip(_CORNERS[a], _CORNERS[b])) for a, b in edges[:3]]
        u, v = (tuple(y-x for x, y in zip(mid[0], point)) for point in mid[1:])
        normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        outward = (b-a for a, b in zip(_CORNERS[inside[0]], _CORNERS[outside[0]]))
        if sum(a*b for a, b in zip(normal, outward)) < 0:
            edges.reverse()
        polygons.append(tuple((min(a, b), max(a, b)) for a, b in edges))
    return tuple(polygons)


_CASES = tuple(_cut_polygons(mask) for mask in range(256))


def _crossing_cells(values, shape, level, cancel):
    nx, ny, nz = shape
    sx, sy = ny*nz, nz
    for x in range(nx-1):
        _check_cancel(cancel)
        for y in range(ny-1):
            base = x*sx + y*sy
            # Bounds of successive xy planes spare most cells in empty space.
            a, b, c, d = values[base], values[base+sy], values[base+sx], values[base+sx+sy]
            low, high = min(a, b, c, d), max(a, b, c, d)
            for z in range(nz-1):
                i = base+z+1
                aa, bb, cc, dd = values[i], values[i+sy], values[i+sx], values[i+sx+sy]
                next_low, next_high = min(aa, bb, cc, dd), max(aa, bb, cc, dd)
                lo, hi = min(low, next_low), max(high, next_high)
                if lo < level <= hi or lo < -level <= hi:
                    yield x, y, z, (a, aa, b, bb, c, cc, d, dd)
                a, b, c, d = aa, bb, cc, dd
                low, high = next_low, next_high


class _SurfaceMesh:
    """Neighboring tetrahedra share their intersections and oriented field normals."""

    def __init__(self, lattice, sample):
        self.lattice, self.sample = lattice, sample
        _, ny, nz = lattice.shape
        self.strides = (ny*nz, nz, 1)
        self.offsets = tuple((x*ny+y)*nz+z for x, y, z in _CORNERS)
        self.vertices, self.normals, self.faces = [], [], []
        self.edges = {1: {}, -1: {}}
        self.gradients = {}
        self.clipped = False

    def _gradient(self, i, position):
        if i not in self.gradients:
            partials = []
            for axis, (k, count) in enumerate(zip(position, self.lattice.shape)):
                left, right = list(position), list(position)
                left[axis], right[axis] = max(0, k-1), min(count-1, k+1)
                partials.append((self.sample(*right)-self.sample(*left))/(right[axis]-left[axis]))
            self.gradients[i] = tuple(sum(p*r for p, r in zip(partials, col)) for col in zip(*self.lattice.reciprocal))
        return self.gradients[i]

    def _vertex(self, cell, base, values, m, n, iso, sign):
        i, j = base+self.offsets[m], base+self.offsets[n]
        t = (iso-values[m])/(values[n]-values[m])
        key = (i, i) if t == 0 else (j, j) if t == 1 else (i, j)
        edges = self.edges[sign]
        if key not in edges:
            start = tuple(a+b for a, b in zip(cell, _CORNERS[m]))
            end = tuple(a+b for a, b in zip(cell, _CORNERS[n]))
            point = tuple(u+(v-u)*t for u, v in zip(start, end))
            normals = zip(self._gradient(i, start), self._gradient(j, end))
            g = tuple(-sign*(u+(v-u)*t) for u, v in normals)
            length = math.hypot(*g) or 1.
            edges[key] = len(self.vertices)
            self.vertices.append(self.lattice.point(*point))
            self.normals.append(tuple(v/length for v in g))
            if any(v == 0 or v == size-1 for v, size in zip(point, self.lattice.shape)):
                self.clipped = True
        return edges[key]

    def add_cell(self, x, y, z, values, level):
        low, high = min(values), max(values)
        base = x*self.strides[0] + y*self.strides[1] + z
        for sign in (1, -1):
            iso = sign*level
            if not low < iso <= high:
                continue
            mask = sum(1 << k for k, val in enumerate(values) if val >= iso)
            if sign < 0:
                mask ^= 255
            for polygon in _CASES[mask]:
                indices = [self._vertex((x, y, z), base, values, a, b, iso, sign) for a, b in polygon]
                # An exact vertex-level crossing can collapse two edges to one point.
                face = tuple(dict.fromkeys(indices))
                if len(face) >= 3:
                    if self.lattice.determinant < 0:
                        face = face[::-1]
                    self.faces.append((*face, sign))

    def finish(self):
        return OrbitalSurface(tuple(self.vertices), tuple(self.faces), self.clipped, tuple(self.normals))


def _surface(values, lattice, level, cancel):
    _, ny, nz = lattice.shape
    mesh = _SurfaceMesh(lattice, lambda x, y, z: values[(x*ny+y)*nz+z])
    for x, y, z, corners in _crossing_cells(values, lattice.shape, level, cancel):
        mesh.add_cell(x, y, z, corners, level)
    return mesh.finish()


def _orbital_axes(expansion, level, quality):
    # A primitive contributes at most A r^l exp(-a r^2). Outside the union
    # of these boxes their summed absolute contribution is below the isovalue.
    # This encloses outer lobes even when the field is small near the nuclei.
    count = sum(len(primitives) for _, primitives, _ in expansion)
    lower, upper = [math.inf]*3, [-math.inf]*3
    for center, primitives, terms in expansion:
        half_l = .5*sum(terms[0][0])
        angular_bound = sum(abs(v) for _, v in terms)
        for exponent, weight in primitives:
            if not weight:
                continue
            log_bound = (math.log(abs(weight)) + math.log(angular_bound) + math.log(count)
                         - math.log(level) - half_l*math.log(exponent))
            outside = log_bound
            if half_l:
                # In s=a*r^2 the envelope peaks at s=l/2. Find its outer crossing.
                inside = half_l
                if log_bound + half_l*math.log(inside) <= inside:
                    continue
                outside = max(inside+1, log_bound)
                while log_bound + half_l*math.log(outside) > outside:
                    outside *= 2
                for _ in range(24):
                    mid = (inside+outside)/2
                    if log_bound + half_l*math.log(mid) > mid:
                        inside = mid
                    else:
                        outside = mid
            if outside <= 0:
                continue
            radius = math.sqrt(outside/exponent)
            for k, coord in enumerate(center):
                lower[k] = min(lower[k], coord-radius)
                upper[k] = max(upper[k], coord+radius)
    if lower[0] == math.inf:
        return ()
    width = max(hi-lo for lo, hi in zip(lower, upper))
    preset = SURFACE_QUALITIES[quality]
    step = max(width/preset.max_intervals, min(preset.spacing_bohr, width/preset.min_intervals))
    axes = []
    for lo, hi in zip(lower, upper):
        half = math.ceil(.5*(hi-lo)/step) + 2
        axes.append(tuple((lo+hi)/2 + i*step for i in range(-half, half+1)))
    return axes


def _check_settings(level, quality):
    if not math.isfinite(level) or level <= 0:
        raise ValueError("The isovalue must be positive.")
    if quality not in SURFACE_QUALITIES:
        raise ValueError("Unknown surface quality.")


def make_orbital_surface(wave, index, level=.05, cancel=None, *, quality="smooth"):
    _check_settings(level, quality)
    expansion = orbital_expansion(wave.shells, wave.orbitals[index].coefficients)
    axes = _orbital_axes(expansion, level, quality)
    if not axes:
        return OrbitalSurface((), (), False)
    origin = tuple(axis[0]*BOHR_IN_ANGSTROM for axis in axes)
    steps = tuple(tuple((axis[1]-axis[0])*BOHR_IN_ANGSTROM if j == k else 0. for j in range(3))
                  for k, axis in enumerate(axes))
    lattice = VolumeGrid(tuple(map(len, axes)), origin, steps)
    return _surface(sample_grid(expansion, axes, cancel), lattice, level, cancel)


def _slope(a, b):
    if (a > 0 and b > 0) or (a < 0 and b < 0):
        # A centered slope resolves smooth curvature. The monotonicity limiter
        # keeps the Hermite segment within the original Cube samples.
        return math.copysign(min(abs(.5*a + .5*b), 2*min(abs(a), abs(b))), a)
    return 0.


def _interpolator(values, shape, factor):
    """Separable monotone Hermite interpolation of a Cube, evaluated only near the surface."""
    nx, ny, nz = shape
    weights = []
    for k in range(factor):
        t = k/factor
        weights.append((t*t*(3-2*t), t*(1-t)**2, t*t*(t-1)))

    def axis_sampler(count, previous):
        @lru_cache(maxsize=32768)
        def sample(i, j, refined):
            a, part = divmod(refined, factor)
            left = previous(i, j, a)
            if part == 0:
                return left
            right = previous(i, j, a+1)
            delta = right-left
            slope_a = _slope(left-previous(i, j, a-1), delta) if a else delta
            slope_b = _slope(delta, previous(i, j, a+2)-right) if a+2 < count else delta
            blend, wa, wb = weights[part]
            return left + blend*delta + wa*slope_a + wb*slope_b
        return sample

    z_value = axis_sampler(nz, lambda x, y, z: values[(x*ny+y)*nz+z])
    y_value = axis_sampler(ny, lambda x, rz, y: z_value(x, y, rz))
    x_value = axis_sampler(nx, lambda ry, rz, x: y_value(x, rz, ry))
    return lambda rx, ry, rz: x_value(ry, rz, rx)


def make_cube_surface(cube, index, level=.05, cancel=None, *, quality="smooth"):
    _check_settings(level, quality)
    grid, field = cube.grid, cube.fields[index]
    if not any(field.minimum < iso <= field.maximum for iso in (level, -level)):
        return OrbitalSurface((), (), False)
    factor = SURFACE_QUALITIES[quality].cube_subdivisions
    if factor == 1:
        return _surface(field.values, grid, level, cancel)
    shape = tuple((n-1)*factor+1 for n in grid.shape)
    fine = VolumeGrid(shape, grid.origin, tuple(tuple(c/factor for c in step) for step in grid.steps))
    sample = _interpolator(field.values, grid.shape, factor)
    mesh = _SurfaceMesh(fine, sample)
    width = factor+1
    offsets = tuple((a*width+b)*width+c for a, b, c in _CORNERS)
    for x, y, z, _ in _crossing_cells(field.values, grid.shape, level, cancel):
        # The monotone filter stays within the native cell's eight sample
        # extrema. Only crossing cells need interpolation, even on large grids.
        _check_cancel(cancel)
        fx, fy, fz = x*factor, y*factor, z*factor
        block = [sample(fx+a, fy+b, fz+c) for a in range(width) for b in range(width) for c in range(width)]
        for a in range(factor):
            for b in range(factor):
                for c in range(factor):
                    start = (a*width+b)*width+c
                    corners = tuple(block[start+k] for k in offsets)
                    mesh.add_cell(fx+a, fy+b, fz+c, corners, level)
    return mesh.finish()
