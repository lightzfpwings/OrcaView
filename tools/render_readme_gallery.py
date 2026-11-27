"""Render the example figures from the checked-out OrcaView application."""

import argparse
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "images"


def render(output):
    # Open Babel and the CLI renderer may start fresh Python/Qt processes.
    os.environ.update(QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="1", QT_FONT_DPI="96",
                      QT_STYLE_OVERRIDE="Fusion", QT_HASH_SEED="0", ORCAVIEW_HEADLESS="1",
                      PYTHONPATH=os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH")])))
    sys.path.insert(0, str(ROOT / "src"))
    from PySide6.QtCore import QLocale
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from orcaview.gui import typography
    from orcaview.gui.main_window import STYLE
    from gallery_calculation import capture_calculation
    from gallery_molecules import capture_molecules
    from gallery_spectra import capture_spectra

    expected = {"hydrogen-bond-design.png", "hydroxyl-spin.png", "population-controls.png",
                "input-preview.png", "calculation-results.png", "spectrum-plot.png", "nmr-spectrum.png"}
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as temp:
        work = Path(temp)
        os.environ["ORCAVIEW_CONFIG_DIR"] = str(work / "preferences")
        QLocale.setDefault(QLocale("en_US"))
        app = QApplication(["OrcaView"])
        app.setApplicationName("OrcaView")
        app.setStyle("Fusion")
        app.setCursorFlashTime(0)
        app.setFont(typography.interface_font("en"))
        app.setStyleSheet(typography.stylesheet(STYLE))
        for capture in (capture_molecules, capture_calculation, capture_spectra):
            capture(app, work)

        generated = {p.name for p in work.glob("*.png")}
        if generated != expected:
            raise ValueError(f"Unexpected set of example figures: {sorted(generated ^ expected)}")
        for name in sorted(generated):
            if QImage(str(work / name)).isNull():
                raise ValueError(f"Could not decode {name}")
        for name in sorted(generated):
            destination = output / name
            image = work / name
            if destination.exists() and destination.read_bytes() == image.read_bytes():
                continue
            image.replace(destination)
            print(f"Updated {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ASSETS)
    render(parser.parse_args().output.resolve())
