"""Preview a spectrum at its export aspect ratio, scale and canvas size."""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QCheckBox, QComboBox

from orcaview.gui.structure_image_dialog import ImageExportDialog
from orcaview.i18n import tr


_PLOT_SIZES = {
    "original": (900, 550),
    "1:1": (900, 900),
    "4:3": (900, 675),
    "16:9": (960, 540),
}


class SpectrumImageDialog(ImageExportDialog):
    def __init__(self, name, snapshot_for_grid, initial_grid, parent=None):
        super().__init__(name, parent, prefix="spectrumImage", title=tr("Export spectrum image"),
                         save_title=tr("Export spectrum"))
        self._snapshot_for_grid = snapshot_for_grid
        self._has_grid = initial_grid is not None
        self.ratio_box = QComboBox()
        self.ratio_box.setObjectName("spectrumImageRatio")
        self.ratio_box.setAccessibleName(tr("Aspect ratio"))
        for key in _PLOT_SIZES:
            self.ratio_box.addItem(tr("Original") if key == "original" else key, key)
        self.form.insertRow(1, tr("Aspect ratio"), self.ratio_box)
        self.grid = QCheckBox(tr("Grid lines"))
        self.grid.setObjectName("spectrumImageGrid")
        self.grid.setChecked(bool(initial_grid))
        self.form.insertRow(3, self.grid)
        self.form.setRowVisible(self.grid, self._has_grid)
        self.setTabOrder(self.format_choice, self.ratio_box)
        self.setTabOrder(self.ratio_box, self.scale_box)
        self.setTabOrder(self.scale_box, self.grid)
        self.setTabOrder(self.grid, self.transparent)
        self.ratio_box.currentIndexChanged.connect(self._update_snapshot)
        self.grid.toggled.connect(self._update_snapshot)
        self._update_snapshot()
        self._format_changed()

    def _update_snapshot(self):
        # Keep any custom padding or crop when the logical plot shape changes.
        pad_x = pad_y = 0
        if self.snapshot is not None:
            old_width, old_height = self._scaled_size()
            pad_x = self.width_box.value() - old_width
            pad_y = self.height_box.value() - old_height
        size = QSize(*_PLOT_SIZES[self.ratio_box.currentData()])
        grid = self.grid.isChecked() if self._has_grid else None
        self.snapshot = self._snapshot_for_grid(grid, size)
        width, height = self._scaled_size()
        self._set_canvas_fields(width + pad_x, height + pad_y)
        self._refresh()
