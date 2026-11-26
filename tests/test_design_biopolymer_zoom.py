"""Mouse-wheel magnification in the two biopolymer Design views."""

import os
import unittest

from orcaview.application.document import MoleculeDocument
from orcaview.application.session import Session
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.core.provenance import Provenance

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QPushButton
    from orcaview.gui.design_panel import DesignPanel
except ModuleNotFoundError as exc:
    if not exc.name.startswith("PySide6"):
        raise
    DesignPanel = None


def wheel(view, point, *, ticks=0, pixels=0):
    event = QWheelEvent(point, view.mapToGlobal(point), QPoint(0, pixels), QPoint(0, ticks),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(view, event)


@unittest.skipUnless(DesignPanel, "requires Qt")
class DesignBiopolymerZoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = DesignPanel()
        self.addCleanup(self.panel.close)
        self.panel.resize(1100, 600)
        self.panel.show()
        self.app.processEvents()

    def test_named_dna_and_legacy_peptide_zoom_in_both_views(self):
        # A deposited DNA backbone can be annotated even when several atoms are missing.
        dna = Molecule("DNA", (Atom("P", 0, 0, 0), Atom("O", 1.5, 0, .1), Atom("C", 2.5, 1, .3)),
                       (Bond(0, 1), Bond(1, 2)), bonds_explicit=True)
        dna_doc = MoleculeDocument.from_molecule(dna, Provenance("import", parameters=(("polymer_roles", "BBB"),)))
        peptide = Molecule("Old project",
                           tuple(Atom(e, float(i), float(i % 3), .2 * (i % 2)) for i, e in enumerate("NCCONCCO")),
                           (Bond(0, 1), Bond(1, 2), Bond(2, 3, 2), Bond(2, 4), Bond(4, 5), Bond(5, 6), Bond(6, 7, 2)),
                           bonds_explicit=True)
        for doc in (dna_doc, MoleculeDocument.from_molecule(peptide)):
            with self.subTest(molecule=doc.head.molecule.name):
                self.panel.set_document(doc)
                self.app.processEvents()
                head = doc.head
                canvas, view = self.panel.canvas, self.panel.viewport
                home = canvas.atom_position(1)
                home3d = QPointF(*view._project_atoms()[1][1][:2])
                scale, scale3d = canvas._scale(), view._projection_scale()
                for widget, focus in ((canvas, home), (view, home3d)):
                    wheel(widget, focus, ticks=120)
                    self.assertAlmostEqual(widget.zoom, 1.12)
                    wheel(widget, focus, pixels=4)
                    self.assertGreater(widget.zoom, 1.12)
                    wheel(widget, focus, ticks=120 * 60)
                    self.assertEqual(widget.zoom, 8.)
                self.assertAlmostEqual(canvas._scale() / scale, 8.)
                self.assertAlmostEqual(view._projection_scale() / scale3d, 8.)
                self.assertLess((canvas.atom_position(1) - home).manhattanLength(), 1e-8)
                self.assertLess((QPointF(*view._projected[1][:2]) - home3d).manhattanLength(), 1e-8)
                self.assertEqual(canvas._target_at(home), (1,))
                self.assertEqual(view._target_at(home3d), (1,))
                self.assertIs(doc.head, head)
                for widget, focus in ((canvas, home), (view, home3d)):
                    wheel(widget, focus, ticks=-120 * 60)
                    self.assertEqual(widget.zoom, .3)
                self.panel.findChild(QPushButton, "designFit").click()
                view.fit()
                self.assertEqual((canvas.zoom, view.zoom), (1., 1.))
                self.assertEqual(canvas.atom_position(1), home)
                self.assertEqual(QPointF(*view._project_atoms()[1][1][:2]), home3d)

    def test_switch_to_small_molecule_restores_original_controls(self):
        panel = self.panel
        mol = Molecule("peptide fragment", (Atom("N", 0, 0, 0), Atom("C", 1.45, 0, 0)), (Bond(0, 1),))
        panel.set_document(MoleculeDocument.from_molecule(mol, Provenance("import", parameters=(("polymer_roles", "BB"),))))
        canvas, view = panel.canvas, panel.viewport
        focus = QPointF(50, 60)
        for widget in (canvas, view):
            wheel(widget, focus, ticks=4800)
            self.assertEqual(widget.zoom, 8.)
        panel.set_document(Session().document)
        self.assertEqual((canvas.zoom, view.zoom), (1., 1.))
        for _ in range(40):
            wheel(canvas, focus, ticks=120)
            wheel(view, focus, ticks=120)
        self.assertEqual((canvas.zoom, view.zoom), (1., 4.))
