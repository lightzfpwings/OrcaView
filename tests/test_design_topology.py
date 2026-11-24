"""Stable atom identities, explicit bond editing and project compatibility."""

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.geometry import display_bonds
from orcaview.core.models import Atom, Bond, BOND_STYLES, Molecule
from orcaview.editing import (AttachAtom, DeleteAtoms, EditorService, GeometryEditCommand, MoveAtom,
                              ReorderAtoms, SetBond)
from orcaview.editing.diagnostics import design_diagnostics


class DesignTopologyTests(unittest.TestCase):
    def setUp(self):
        self.session = Session(Molecule("H2", (Atom("H", 0, 0, 0), Atom("H", .74, 0, 0))))
        self.editor = EditorService(self.session.document)
        self.ids = self.session.document.head.atom_ids

    def apply(self, operation):
        preview = self.editor.preview(GeometryEditCommand(self.editor.expected, operation))
        return self.editor.commit(preview).snapshot

    def test_deleting_last_inferred_bond_roundtrips_as_explicit_empty(self):
        self.assertEqual(display_bonds(self.session.molecule), (Bond(0, 1),))
        self.apply(SetBond(*self.ids, 0))
        self.assertEqual(display_bonds(self.session.molecule), ())
        self.assertEqual(display_bonds(self.editor.undo().snapshot.molecule), (Bond(0, 1),))
        self.editor.redo()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "atoms.oview.json"
            save_project(self.session, path)
            self.assertEqual(json.loads(path.read_text())["schema_version"], 8)
            doc = load_project(path).document
            self.assertEqual(doc.head.atom_ids, self.ids)
            self.assertEqual(display_bonds(doc.head.molecule), ())
            self.assertEqual(display_bonds(doc.records()[0][0].molecule), (Bond(0, 1),))

    def test_change_order_and_move_preserve_identity_and_other_coordinates(self):
        changed = self.apply(SetBond(*reversed(self.ids), 2))
        moved = self.apply(MoveAtom(self.ids[1], 1.2, .3, -.4))
        self.assertEqual(moved.atom_ids, self.ids)
        self.assertEqual(moved.molecule.atoms, (changed.molecule.atoms[0], Atom("H", 1.2, .3, -.4)))
        self.assertEqual(moved.molecule.bonds, (Bond(0, 1, 2),))
        self.assertEqual(self.editor.undo().snapshot.molecule, changed.molecule)
        with self.assertRaises(ValueError):
            self.apply(SetBond(self.ids[0], "missing", 1))
        self.assertTrue(self.editor.can_redo)

    def test_unchanged_project_keeps_legacy_wire_format(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.oview.json"
            save_project(self.session, path)
            raw = json.loads(path.read_text())
            self.assertEqual(raw["schema_version"], 2)
            self.assertNotIn("bonds_explicit", raw["document"]["snapshots"][0]["molecule"])
            self.assertEqual(display_bonds(load_project(path).molecule), (Bond(0, 1),))

    def test_styled_bonds_preserve_direction_through_edits_and_save(self):
        donor, acceptor = reversed(self.ids)
        self.apply(SetBond(donor, acceptor, 1, "coordinate_arrow"))
        added = self.apply(AttachAtom(acceptor, Atom("C", -1., 0., 0.), 1, "hashed_wedge"))
        reordered = self.apply(ReorderAtoms((added.atom_ids[2], donor, acceptor)))
        self.assertEqual(reordered.molecule.bonds, (Bond(1, 2, 1, "coordinate_arrow"), Bond(2, 0, 1, "hashed_wedge")))
        deleted = self.apply(DeleteAtoms((added.atom_ids[2],)))
        self.assertEqual(deleted.molecule.bonds, (Bond(0, 1, 1, "coordinate_arrow"),))
        self.assertEqual(self.editor.undo().snapshot.molecule, reordered.molecule)
        self.assertEqual(self.editor.redo().snapshot.molecule, deleted.molecule)
        self.apply(SetBond(acceptor, donor, 1, "coordinate_arrow"))
        self.assertEqual(self.session.molecule.bonds, (Bond(1, 0, 1, "coordinate_arrow"),))
        self.apply(SetBond(donor, acceptor, 2))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "styles.oview.json"
            save_project(self.session, path)
            self.assertEqual(json.loads(path.read_text())["schema_version"], 9)
            self.assertEqual(load_project(path).document.records(), self.session.document.records())

    def test_all_styles_and_legacy_wire_schemas(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "style.oview.json"
            for order, styles in BOND_STYLES.items():
                for style in styles:
                    with self.subTest(order=order, style=style):
                        bond = Bond(0, 1, order, style)
                        molecule = Molecule("H2", self.session.molecule.atoms, (bond,))
                        session = Session(molecule)
                        save_project(session, path)
                        record = json.loads(path.read_text())
                        if style == "plain":
                            self.assertEqual(record["schema_version"], 1)
                            self.assertEqual(record["molecule"]["bonds"], [{"a": 0, "b": 1, "order": order}])
                        else:
                            self.assertEqual(record["schema_version"], 9)
                        self.assertEqual(load_project(path).molecule, molecule)
            for order, style in ((1, "aromatic"), (2, "partial_triple"), (3, "wedge"), (0, "coordinate")):
                with self.subTest(order=order, style=style), self.assertRaises(ValueError):
                    SetBond(*self.ids, order, style)
            self.apply(SetBond(*self.ids, 3))
            save_project(self.session, path)
            record = json.loads(path.read_text())
            self.assertEqual(record["schema_version"], 8)
            bond_record = record["document"]["snapshots"][-1]["molecule"]["bonds"][0]
            self.assertNotIn("style", bond_record)
            self.assertEqual(load_project(path).molecule.bonds, (Bond(0, 1, 3),))
            bond_record["style"] = "partial_triple"
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "unknown fields"):
                load_project(path)

    def test_fractional_and_coordinate_bonds_contribute_to_valence_by_endpoint(self):
        atoms = (Atom("C", 0., 0., 0.),) + tuple(Atom("C", i, 1., 0.) for i in range(4))
        molecule = Molecule("mixed", atoms,
                            (Bond(0, 1, 2, "aromatic"), Bond(0, 2, 3, "partial_triple"),
                             Bond(0, 3, 1, "coordinate"), Bond(0, 4, 1, "coordinate_arrow")))
        self.assertFalse(design_diagnostics(molecule))
        reverse = Bond(3, 0, 1, "coordinate")
        self.assertEqual((reverse.valence_at(3), reverse.valence_at(0)), (0, 1))
        molecule = Molecule("mixed", atoms, (*molecule.bonds[:2], reverse, molecule.bonds[-1]))
        self.assertTrue(any("C1" in issue and "(5)" in issue for issue in design_diagnostics(molecule)))
