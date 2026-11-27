"""Display signed isosurfaces in the molecular camera, with vector image export."""

import math
import logging
import os

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPolygonF

from orcaview.gui.orbital_depth import VectorOcclusion, molecular_capsules
from orcaview.gui.viewport import MoleculeViewport
from orcaview.i18n import tr


PHASE_COLORS = {1: "#447cc1", -1: "#dc754b"}


def _paint_triangle(painter, screen, light, inks, a, b, c, path=None):
    if path is not None and path.isEmpty():
        return
    p, q, r = screen[a], screen[b], screen[c]
    low, high = min(light[a], light[b], light[c]), max(light[a], light[b], light[c])
    if high-low <= 3:
        painter.setBrush(inks[(low+high)//2])
    else:
        # A linear intensity in screen space must reproduce all three
        # vertex intensities. This also makes both faces agree along a shared edge.
        ux, uy, vx, vy = q.x()-p.x(), q.y()-p.y(), r.x()-p.x(), r.y()-p.y()
        det = ux*vy-uy*vx
        if abs(det) < 1e-9:
            return
        du, dv = light[b]-light[a], light[c]-light[a]
        gx, gy = (du*vy-dv*uy)/det, (ux*dv-vx*du)/det
        norm = gx*gx+gy*gy
        dark = (low-light[a])/norm
        bright = (high-light[a])/norm
        gradient = QLinearGradient(p.x()+gx*dark, p.y()+gy*dark, p.x()+gx*bright, p.y()+gy*bright)
        gradient.setColorAt(0., inks[low])
        gradient.setColorAt(1., inks[high])
        painter.setBrush(gradient)
    if path is None:
        painter.drawPolygon(QPolygonF((p, q, r)))
    else:
        painter.drawPath(path)


class OrbitalViewport(MoleculeViewport):
    surface_changed = Signal()

    def __init__(self):
        self.surface = None
        self._surface_radius = 0.
        self._atom_radii = ()
        self._layer = self._layer_key = None
        self._gpu = None
        self._raster = None
        self._probe_gpu = True
        self.renderer_name = "CPU"
        super().__init__(result_view=True)
        self.set_phase_colors(PHASE_COLORS)

    def set_phase_colors(self, colors):
        self._inks = {}
        self._phase_rgba = {s: QColor(c).getRgbF() for s, c in colors.items()}
        for sign, value in colors.items():
            rgb = QColor(value).getRgb()[:3]
            inks = []
            for i in range(161):
                t = i / 160
                inks.append(QColor(*(min(255, round(c*(.52+.48*t) + 42*t*t)) for c in rgb), 204))
            self._inks[sign] = inks
        self._rgba_table = [[ink.getRgb() for ink in self._inks[s]] for s in (1, -1)]
        self._layer_key = None
        self.update()

    def set_surface(self, surface):
        self.surface = surface
        self._raster = None
        if surface is None and self._gpu is not None:
            self._gpu.clear_mesh()
        self._layer = self._layer_key = None
        self._surface_radius = 0.
        if surface:
            cx, cy, cz = self._center
            self._surface_radius = max((math.hypot(x-cx, y-cy, z-cz) for x, y, z in surface.vertices),
                                       default=0.)
        self._update_fit_radius()
        self.update()
        self.surface_changed.emit()

    def release_renderer(self):
        self._raster = None
        if self._gpu is not None:
            self._gpu.close()
            self._gpu = None

    def set_grid_center(self, grid):
        if not self.molecule.atoms:
            self._center = grid.point(*((n-1)/2 for n in grid.shape))

    def has_exportable_structure(self):
        return super().has_exportable_structure() or bool(self.surface and self.surface.faces)

    def _update_fit_radius(self):
        if self._center_distances:
            super()._update_fit_radius()
        else:
            self._fit_radius = 1.2
        self._fit_radius = max(self._fit_radius, .86*self._surface_radius)

    def _draw_molecule(self, painter, scale, projected, selection_labels=(), hover=()):
        super()._draw_molecule(painter, scale, projected, selection_labels, hover)
        if not self.surface or not self.surface.faces:
            return
        axes = tuple(self.transform(*a) for a in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
        ox, oy = self.width()/2 + self._pan.x(), self.height()/2 + self._pan.y()
        bonds = () if self.appearance.model == "space-filling" else self.visual_bonds
        capsules = molecular_capsules(projected, scale, bonds, self._stick_half_width)
        if painter.device() is not self:
            # The image-export QPicture retains scalable geometry and the current colors.
            self._draw_surface(painter, scale, ox, oy, axes, capsules)
            return
        # Supersample the complete transparent layer. Antialiasing individual
        # translucent polygons would create seams on every shared interior edge.
        dpr = self.devicePixelRatioF()
        key = (axes, scale, ox, oy, self.width(), self.height(), dpr, self._center, capsules)
        if key != self._layer_key:
            self._layer = self._surface_layer(axes, scale, ox, oy, dpr, capsules)
            self._layer_key = key
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self.rect(), self._layer)
        painter.restore()

    def _surface_layer(self, axes, scale, ox, oy, dpr, capsules=()):
        if self._probe_gpu:
            self._probe_gpu = False
            if os.environ.get("ORCAVIEW_ORBITAL_RENDERER", "").lower() != "cpu":
                from .orbital_gpu import create_renderer
                self._gpu = create_renderer()
            self.renderer_name = self._gpu.name if self._gpu is not None else "CPU"
            self.setToolTip(tr("Orbital renderer: {name}", name=self.renderer_name))
        if self._gpu is not None:
            try:
                return self._gpu.render(self.surface, self._center, self._surface_radius, axes, scale, ox, oy,
                                        self.width(), self.height(), dpr, self._phase_rgba, capsules)
            except (self._gpu.wgpu.GPUError, RuntimeError, OSError, MemoryError, ValueError) as exc:
                logging.getLogger(__name__).warning("Using the CPU orbital renderer: %s", exc)
                self.release_renderer()
                self.renderer_name = "CPU"
                self.setToolTip(tr("Orbital renderer: {name}", name=self.renderer_name))
        try:
            from .orbital_raster import OrbitalRaster
            if self._raster is None:
                self._raster = OrbitalRaster(self.surface, self._center)
            return self._raster.render(self._center, axes, scale, ox, oy, self.width(), self.height(),
                                       max(1.25, dpr), self._rgba_table, capsules)
        except ImportError:
            pass  # A minimal Qt install can still paint and export the complete mesh.
        factor = max(2., dpr)
        layer = QImage(math.ceil(self.width()*factor), math.ceil(self.height()*factor),
                       QImage.Format.Format_ARGB32_Premultiplied)
        layer.fill(Qt.GlobalColor.transparent)
        with QPainter(layer) as painter:
            painter.scale(factor, factor)
            self._draw_surface(painter, scale, ox, oy, axes, capsules)
        return layer

    def _draw_surface(self, painter, scale, ox, oy, axes, capsules=()):
        occlusion = VectorOcclusion(capsules)
        cx, cy, cz = self._center
        (xx, xy, xz), (yx, yy, yz), (zx, zy, zz) = axes
        lx, ly, lz = (-.35*u + .46*v + .81*w for u, v, w in axes)
        light = [min(160, round(160*max(0., lx*x + ly*y + lz*z))) for x, y, z in self.surface.normals]
        screen, depths = [], []
        for px, py, pz in self.surface.vertices:
            x, y, z = px-cx, py-cy, pz-cz
            screen.append(QPointF(ox+scale*(xx*x+yx*y+zx*z), oy-scale*(xy*x+yy*y+zy*z)))
            depths.append(xz*x+yz*y+zz*z)
        points = [(p.x(), p.y(), z*scale) for p, z in zip(screen, depths)]
        visible = []
        for face in self.surface.faces:
            corners = face[:-1]
            a, b, c, d = (screen[i] for i in (corners[0], corners[1], corners[2], corners[-1]))
            if (c.x()-a.x())*(d.y()-b.y()) >= (c.y()-a.y())*(d.x()-b.x()):
                continue
            visible.append((sum(depths[i] for i in corners)/len(corners), face[-1], corners))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)
        visible.sort()
        for _, sign, corners in visible:
            a = corners[0]
            for b, c in zip(corners[1:-1], corners[2:]):
                path = occlusion.visible_path((points[a], points[b], points[c]))
                _paint_triangle(painter, screen, light, self._inks[sign], a, b, c, path)
        painter.restore()
