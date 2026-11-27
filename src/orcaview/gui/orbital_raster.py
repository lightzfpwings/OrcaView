"""Scan-convert indexed orbital triangles in batches for desktops without a GPU."""

from array import array

from PySide6.QtGui import QImage


def phase_indices(mesh):
    phases = {1: array("I"), -1: array("I")}
    for face in mesh.faces:
        indices = phases[face[-1]]
        indices.extend(face[:3])
        if len(face) == 5:
            indices.extend((face[0], face[2], face[3]))
    return phases


class OrbitalRaster:
    def __init__(self, mesh, center):
        import numpy as np

        self.mesh, self.origin = mesh, center
        self.vertices = (np.asarray(mesh.vertices)-center).astype("f")
        self.normals = np.asarray(mesh.normals, dtype="f")
        indices = phase_indices(mesh)
        self.positive = len(indices[1])//3
        indices[1].extend(indices[-1])
        self.triangles = np.frombuffer(indices[1], dtype="uint32").reshape(-1, 3)

    def render(self, center, axes, scale, ox, oy, width, height, dpr, palette):
        import numpy as np

        w, h = max(1, round(width*dpr)), max(1, round(height*dpr))
        camera = np.asarray(axes, dtype="f")
        xyz = self.vertices @ camera + (np.asarray(self.origin)-center) @ camera
        x = (ox+xyz[:, 0]*scale)*dpr-.5
        y = (oy-xyz[:, 1]*scale)*dpr-.5
        light = self.normals @ (camera @ np.array([-.35, .46, .81], dtype="f"))
        depth = np.full(w*h, -np.inf, dtype="f")
        image = np.zeros((w*h, 4), dtype="uint8")
        colors = np.asarray(palette, dtype="uint8")
        # Bound temporaries for overlapping surfaces and close-up views.
        for first in range(0, len(self.triangles), 2048):
            tri = self.triangles[first:first+2048]
            xs, ys = x[tri], y[tri]
            dx1, dx2 = xs[:, 1]-xs[:, 0], xs[:, 2]-xs[:, 0]
            dy1, dy2 = ys[:, 1]-ys[:, 0], ys[:, 2]-ys[:, 0]
            area = dx1*dy2-dx2*dy1
            keep = np.flatnonzero((area < -1e-9) & (ys.max(axis=1) >= 0) & (ys.min(axis=1) < h)
                                  & (xs.max(axis=1) >= 0) & (xs.min(axis=1) < w))
            if not len(keep):
                continue
            area = area[keep]
            xs, ys, tri = xs[keep], ys[keep], tri[keep]
            anchor_x, anchor_y = xs[:, 0], ys[:, 0]
            order = np.argsort(ys, axis=1)
            x0, x1, x2 = np.take_along_axis(xs, order, axis=1).T
            y0, y1, y2 = np.take_along_axis(ys, order, axis=1).T
            start = np.ceil(y0).clip(0, h).astype(int)
            counts = np.ceil(y2).clip(0, h).astype(int)-start
            rows = np.repeat(np.arange(len(tri)), counts)
            offset = np.cumsum(counts)-counts
            line = np.arange(len(rows))+np.repeat(start-offset, counts)
            left = x0[rows]+(line-y0[rows])*((x2-x0)/(y2-y0))[rows]
            upper = np.divide(x1-x0, y1-y0, out=np.zeros_like(x0), where=y1>y0)
            lower = np.divide(x2-x1, y2-y1, out=np.zeros_like(x0), where=y2>y1)
            right = np.where(line < y1[rows], x0[rows]+(line-y0[rows])*upper[rows],
                             x1[rows]+(line-y1[rows])*lower[rows])
            a = np.ceil(np.minimum(left, right)).clip(0, w).astype(int)
            lengths = np.ceil(np.maximum(left, right)).clip(0, w).astype(int)-a
            visible = lengths > 0
            rows, line, a, lengths = (v[visible] for v in (rows, line, a, lengths))
            # Interpolate depth and vertex illumination across each scan line.
            def plane(values):
                v0, v1, v2 = values[tri].T
                gx = ((v1-v0)*dy2[keep]-(v2-v0)*dy1[keep])/area
                gy = (dx1[keep]*(v2-v0)-dx2[keep]*(v1-v0))/area
                return gx, v0-gx*anchor_x-gy*anchor_y, gy

            zx, z0, zy = plane(xyz[:, 2])
            lx, l0, ly = plane(light)
            ends = np.cumsum(lengths)
            begin = 0
            while begin < len(rows):
                before = ends[begin]-lengths[begin]
                end = max(begin+1, int(ends.searchsorted(before+262144, side="right")))
                span = lengths[begin:end]
                row = np.repeat(rows[begin:end], span)
                py = np.repeat(line[begin:end], span)
                px = np.arange(ends[end-1]-before)+np.repeat(a[begin:end]-(ends[begin:end]-span-before), span)
                pixel = py*w+px
                z = (z0[row]+zx[row]*px+zy[row]*py).astype("f")
                np.maximum.at(depth, pixel, z)
                front = z >= depth[pixel]
                t = ((l0[row]+lx[row]*px+ly[row]*py)*160).round().clip(0, 160).astype(int)
                sign = (first+keep[row] >= self.positive).astype(int)
                image[pixel[front]] = colors[sign[front], t[front]]
                begin = end
        return QImage(image.data, w, h, 4*w, QImage.Format.Format_RGBA8888).copy()
