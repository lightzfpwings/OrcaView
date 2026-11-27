"""Orthographic depth of the atom spheres and bond sticks in the orbital view."""

from functools import lru_cache
import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPolygonF


def molecular_capsules(projected, scale, bonds, stick_width):
    """Store endpoints, depth and radius in logical viewport pixels."""
    capsules = []
    for x, y, z, radius in projected:
        capsules.append((x, y, z*scale, x, y, z*scale, radius))
    for bond in bonds:
        ax, ay, az, _ = projected[bond.a]
        bx, by, bz, _ = projected[bond.b]
        dx, dy = bx-ax, by-ay
        length = math.hypot(dx, dy)
        if length < .01:
            continue  # The molecule painter omits end-on strokes.
        radius = stick_width(bond, scale)
        for i in range(bond.order):
            offset = (i-(bond.order-1)/2)*3.1*radius/length
            capsules.append((ax-dy*offset, ay+dx*offset, az*scale,
                             bx-dy*offset, by+dx*offset, bz*scale, radius))
    return tuple(capsules)


def depth_buffer(capsules, width, height, dpr, scale):
    """Rasterize only each primitive's bounding rectangle, in camera angstroms."""
    import numpy as np

    depth = np.full((height, width), -np.inf, dtype='f')
    for ax, ay, az, bx, by, bz, radius in capsules:
        x0 = max(0, math.floor((min(ax, bx)-radius)*dpr))
        y0 = max(0, math.floor((min(ay, by)-radius)*dpr))
        x1 = min(width, math.ceil((max(ax, bx)+radius)*dpr))
        y1 = min(height, math.ceil((max(ay, by)+radius)*dpr))
        if x0 >= x1 or y0 >= y1:
            continue
        x = (np.arange(x0, x1)+.5)/dpr-ax
        y = ((np.arange(y0, y1)+.5)/dpr-ay)[:, None]
        dx, dy, dz = bx-ax, by-ay, bz-az
        length = math.hypot(dx, dy)
        if length < 1e-8:
            disk = radius*radius-x*x-y*y
            z = max(az, bz)
        else:
            along = (dx*x+dy*y)/length
            across = (dy*x-dx*y)/length
            span = radius*radius-across*across
            t = np.clip(along+dz/math.hypot(length, dz)*np.sqrt(np.maximum(span, 0)), 0, length)
            disk = span-(along-t)**2
            z = az+dz*t/length
        front = (z+np.sqrt(np.maximum(disk, 0)))/scale
        region = depth[y0:y1, x0:x1]
        np.maximum(region, front, out=region, where=disk >= 0)
    return depth.ravel()


@lru_cache(maxsize=64)
def _directions(count):
    return tuple((math.cos(2*math.pi*i/count), math.sin(2*math.pi*i/count)) for i in range(count))


class _Shadow:
    """Projection of the part of a capsule in front of a triangle's plane."""

    def __init__(self, capsule):
        self.ax, self.ay, self.az, self.bx, self.by, self.bz, self.r = capsule
        self.dx, self.dy, self.dz = self.bx-self.ax, self.by-self.ay, self.bz-self.az
        self.length = math.hypot(self.dx, self.dy)
        self.norm = math.hypot(self.length, self.dz)
        self.bounds = (min(self.ax, self.bx)-self.r, min(self.ay, self.by)-self.r,
                       max(self.ax, self.bx)+self.r, max(self.ay, self.by)+self.r)
        self.front = max(self.az, self.bz)+self.r
        self.silhouette = QPainterPath()
        if self.length < 1e-8:
            self.silhouette.addEllipse(QPointF(self.ax, self.ay), self.r, self.r)
        else:
            line = QPainterPath(QPointF(self.ax, self.ay))
            line.lineTo(self.bx, self.by)
            stroker = QPainterPathStroker()
            stroker.setWidth(2*self.r)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            self.silhouette = stroker.createStroke(line)

    def covers(self, point):
        x, y, z = point
        x, y = x-self.ax, y-self.ay
        if self.length < 1e-8:
            disk = self.r**2-x*x-y*y
            axis_z = max(self.az, self.bz)
        else:
            along = (self.dx*x+self.dy*y)/self.length
            across = (self.dy*x-self.dx*y)/self.length
            span = self.r**2-across**2
            if span < 0:
                return False
            t = min(self.length, max(0., along+self.dz/self.norm*math.sqrt(span)))
            disk = span-(along-t)**2
            axis_z = self.az+self.dz*t/self.length
        return disk >= 0 and z <= axis_z+math.sqrt(disk)

    def cut(self, normal, offset):
        """Trace the convex outline using support points of the clipped end balls and cylinder."""
        nx, ny, nz = normal
        ha = nx*self.ax+ny*self.ay+nz*self.az-offset
        dh = nx*self.dx+ny*self.dy+nz*self.dz
        hb = ha+dh
        if max(ha, hb) <= -self.r:
            return None
        if min(ha, hb) >= self.r:
            return self.silhouette
        count = max(24, min(256, math.ceil(math.pi*math.sqrt(self.r/.10))))
        outline = []
        for ux, uy in _directions(count):
            p = nx*ux+ny*uy
            q = max(1e-14, math.hypot(ux-p*nx, uy-p*ny, p*nz))
            ts = [0., 1.] if self.norm else [0.]
            if abs(dh) > 1e-12:
                # Along the cylinder, maximize u·center - p*h + q*sqrt(r²-h²).
                k = (ux*self.dx+uy*self.dy)/dh-p
                h = self.r*k/math.hypot(k, q)
                t = (h-ha)/dh
                if 0 < t < 1 and h < -p*self.r:
                    ts.append(t)
            maximum = -math.inf
            for t in ts:
                h = ha+t*dh
                if h < -self.r:
                    continue
                x, y = self.ax+t*self.dx, self.ay+t*self.dy
                if h >= -p*self.r:
                    x, y = x+self.r*ux, y+self.r*uy
                else:
                    s = math.sqrt(max(0., self.r**2-h*h))/q
                    x, y = x-h*nx+s*(ux-p*nx), y-h*ny+s*(uy-p*ny)
                support = ux*x+uy*y
                if support > maximum:
                    maximum, best = support, QPointF(x, y)
            outline.append(best)
        path = QPainterPath()
        path.addPolygon(QPolygonF(outline))
        path.closeSubpath()
        return path


class VectorOcclusion:
    """Clip vector triangles in page coordinates without embedding a raster mask."""

    def __init__(self, capsules):
        self.shadows = [_Shadow(c) for c in capsules]
        self.tiles = {}
        self.large = []
        if len(self.shadows) > 24:
            for shadow in self.shadows:
                l, t, r, b = (math.floor(v/64) for v in shadow.bounds)
                if (r-l+1)*(b-t+1) > 64:
                    self.large.append(shadow)
                else:
                    for i in range(l, r+1):
                        for j in range(t, b+1):
                            self.tiles.setdefault((i, j), []).append(shadow)

    def _nearby(self, x0, x1, y0, y1):
        if not self.tiles:
            return self.shadows
        l, r, t, b = (math.floor(v/64) for v in (x0, x1, y0, y1))
        if (r-l+1)*(b-t+1) > 64:
            return self.shadows
        if l == r and t == b:
            return (*self.large, *self.tiles.get((l, t), ()))
        candidates = dict.fromkeys(self.large)
        for i in range(l, r+1):
            for j in range(t, b+1):
                candidates.update(dict.fromkeys(self.tiles.get((i, j), ())))
        return candidates

    def visible_path(self, points):
        if not self.shadows:
            return None
        xs, ys, zs = zip(*points)
        x0, x1, y0, y1, z0 = min(xs), max(xs), min(ys), max(ys), min(zs)
        result = plane = None
        for shadow in self._nearby(x0, x1, y0, y1):
            left, top, right, bottom = shadow.bounds
            if x1 <= left or x0 >= right or y1 <= top or y0 >= bottom or z0 >= shadow.front:
                continue
            if all(shadow.covers(p) for p in points):
                return QPainterPath()
            if plane is None:
                a, b, c = points
                ux, uy, uz = (v-w for v, w in zip(b, a))
                vx, vy, vz = (v-w for v, w in zip(c, a))
                nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
                length = math.copysign(math.hypot(nx, ny, nz), nz)
                if abs(nz) < 1e-12:
                    return QPainterPath()
                normal = (nx/length, ny/length, nz/length)
                plane = normal, sum(u*v for u, v in zip(normal, a))
            cut = shadow.cut(*plane)
            if cut is not None:
                if result is None:
                    result = QPainterPath()
                    result.addPolygon(QPolygonF([QPointF(x, y) for x, y, _ in points]))
                    result.closeSubpath()
                result = result.subtracted(cut)
                if result.isEmpty():
                    return result
        return result  # None means the original triangle remains fully visible.
