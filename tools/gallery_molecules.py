"""Capture the water dimer editor and the hydroxyl radical's population controls."""

import subprocess
import sys
import time
from pathlib import Path

from orcaview.application.session import Session
from orcaview.cli_io import load_session
from orcaview.cli_results import pick_dataset
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.gui.design_panel import DesignPanel
from orcaview.gui.population_dialog import PopulationDialog
from orcaview.gui.population_map import PALETTES, PopulationStyle, available_populations


def _water_dimer(app, output):
    atoms = (Atom("O", 0, 0, 0), Atom("H", .96, 0, 0), Atom("H", -.25, .92, 0),
             Atom("O", 3.25, .40, .20), Atom("H", 3.90, 1.10, .18), Atom("H", 3.75, -.39, .40))
    bonds = (Bond(0, 1), Bond(0, 2), Bond(3, 4), Bond(3, 5), Bond(1, 3, 1, "hydrogen_bond"))
    document = Session(Molecule("Water dimer", atoms, bonds, bonds_explicit=True)).document
    panel = DesignPanel()
    try:
        panel.set_document(document)
        panel.resize(1020, 460)
        panel.show()
        app.processEvents()
        before = document.head.ref
        panel._start_structure_job("HB", distance=1.90, angle=170.)
        deadline = time.monotonic() + 90
        while panel._structure_job is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.02)
        if document.head.ref == before or panel._structure_job is not None:
            raise RuntimeError(f"Water dimer optimization failed: {panel.status.text()}")
        panel.canvas.fit()
        panel.viewport.fit()
        panel.viewport.zoom = 1.85
        panel.viewport.rotate_view("z", 15)
        app.processEvents()
        if not panel.grab().save(str(output)):
            raise OSError(f"Could not save {output}")
    finally:
        panel.close()


def capture_molecules(app, output: Path):
    _water_dimer(app, output / "hydrogen-bond-design.png")
    log = Path(__file__).resolve().parents[1] / "examples/populations/hydroxyl.out"
    # Use the same structure export and camera settings as the published CLI example.
    subprocess.run([sys.executable, "-m", "orcaview", "render", str(log), str(output / "hydroxyl-spin.png"),
                    "--population", "mulliken-spin", "--population-scale", "bwr", "--population-symmetric",
                    "--labels", "--rotate", "y:76", "--rotate", "z:12", "--zoom", "1.65",
                    "--width", "600", "--height", "355"], check=True)

    datasets = load_session(log).document.records()[1]
    spin = pick_dataset(datasets, "mulliken-spin")
    limit = max(abs(value) for value in spin.values if value is not None)
    style = PopulationStyle(colors=PALETTES["BWR"], color_atoms=True, range_mode="manual",
                            lower=-limit, upper=limit, midpoint=0.)
    dialog = PopulationDialog(available_populations(datasets, spin.geometry), spin.dataset_id, style)
    try:
        dialog.show()
        app.processEvents()
        path = output / "population-controls.png"
        if not dialog.grab().save(str(path)):
            raise OSError(f"Could not save {path}")
    finally:
        dialog.close()
