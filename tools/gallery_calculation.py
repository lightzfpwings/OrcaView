"""Capture the input workspace and the energy history of the archived water calculation."""

from pathlib import Path

from PySide6.QtCore import Qt

from orcaview.gui.foundation_panel import FoundationPanel
from orcaview.gui.main_window import MainWindow
from orcaview.gui.result_import import read_native_session


EXAMPLE = (Path(__file__).resolve().parents[1] / "artifacts/public/validation"
           / "ORCA-6.1.1-macOS-arm64/optfreq")


def capture_calculation(app, output):
    window = MainWindow()
    try:
        window.session.open_xyz(Path(__file__).resolve().parents[1] / "examples/water.xyz")
        window.session.apply_input_preview((EXAMPLE / "job.inp").read_text())
        window._load_controls()
        window.tree_dock.hide()
        window.show()
        app.processEvents()
        window.resize(1120, 890)
        window.resizeDocks([window.inspector_dock], [413], Qt.Orientation.Horizontal)
        window.resizeDocks([window.bottom_dock], [250], Qt.Orientation.Vertical)
        window.viewport.rotate_view('x', -65)
        window.viewport.zoom = 1.65
        app.processEvents()
        region = window.workspace_tabs.geometry().united(window.inspector_dock.geometry())
        region = region.united(window.bottom_dock.geometry())
        if not window.grab(region).save(str(output / "input-preview.png")):
            raise OSError("Could not save the input workspace image")
    finally:
        window.close()

    session = read_native_session(EXAMPLE / "job.out")
    panel = FoundationPanel()
    try:
        panel.set_document(session.document)
        panel.set_log_report(session.log_report, standalone=True)
        panel.resize(1040, 594)
        panel.show()
        app.processEvents()
        if not panel.grab().save(str(output / "calculation-results.png")):
            raise OSError("Could not save the calculation results image")
    finally:
        panel.close()
