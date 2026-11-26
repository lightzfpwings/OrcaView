"""Capture the spectrum settings windows using published ORCA example outputs."""

from pathlib import Path

from orcaview.gui.spectrum_preview import SpectrumPreview
from orcaview.orca.log_spectra import parse_log_spectra


FIXTURES = Path(__file__).resolve().parents[1] / "artifacts/public/validation/results-0.1.0a12"


def capture_spectra(app, output: Path):
    examples = (
        ("tdcd/peroxide.out", "Electronic circular dichroism (CD) (Length gauge)", "spectrum-plot.png"),
        ("nmr/water-shield.out", "NMR chemical shielding", "nmr-spectrum.png"),
    )
    for log, title, filename in examples:
        tables = parse_log_spectra((FIXTURES / log).read_text(encoding="utf-8"))
        table = next(table for table in tables if table.title == title)
        preview = SpectrumPreview()
        try:
            preview.set_spectrum(table)
            preview.open_plot()
            dialog = preview._dialog
            dialog.resize(940, 700 if table.kind == "nmr" else 620)
            dialog.figure.setFocus()
            app.processEvents()
            if not dialog.export_button.isEnabled() or not dialog.figure.profile.curve:
                raise RuntimeError(f"No curve rendered for {log}")
            if not dialog.grab().save(str(output / filename)):
                raise OSError(f"Could not save {output / filename}")
        finally:
            preview.set_spectrum(None)
            preview.close()
