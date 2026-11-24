"""Pure-Python synthetic fixture for the M1 workspace; no external calculation.

The public fixture bytes are the source evidence, rather than an ORCA output or
an analysis-engine result. Reopening the project does not require a source file.
"""

from dataclasses import replace

from orcaview.application.document import MoleculeDocument
from orcaview.application.session import Session
from orcaview.core.models import Atom, Bond, CalculationSpec, Molecule
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.core.results import DatasetAxis, ResultDataset


FOUNDATION_FIXTURE_BYTES = b'''{
  "synthetic_fixture": true,
  "coordinate_unit": "angstrom",
  "atoms": [["O", 0.0, 0.0, 0.0],
            ["H", 0.758602, 0.0, 0.586541],
            ["H", -0.758602, 0.0, 0.586541]],
  "frame_h1_displacement_angstrom": [0.0, 0.0, 0.05],
  "energy_hartree": -75.0,
  "atomic_charge_e": [-0.8, null, 0.4],
  "missing_reason": "Synthetic fixture omits the first hydrogen charge"
}
'''


def build_foundation_demo() -> Session:
    """Return four revisions, one actual fixture frame and two synthetic datasets."""
    artifact = ArtifactRef.from_bytes(FOUNDATION_FIXTURE_BYTES, "orcaview.synthetic-json")
    source = Provenance(
        "fixture", "orcaview.m1-demo", "1", (artifact,),
        (("synthetic_fixture", "true"),),
    )
    molecule = Molecule(
        "Water · M1 synthetic example",
        (Atom("O", 0.0, 0.0, 0.0), Atom("H", 0.758602, 0.0, 0.586541),
         Atom("H", -0.758602, 0.0, 0.586541)),
        (Bond(0, 1), Bond(0, 2)),
    )
    document = MoleculeDocument.from_molecule(molecule, source)
    root = document.head
    oxygen, hydrogen1, hydrogen2 = molecule.atoms
    frame = document.add_frame(
        root.ref, "synthetic-step-1",
        replace(molecule, atoms=(oxygen, replace(hydrogen1, z=hydrogen1.z + 0.05), hydrogen2)),
        root.atom_ids, source,
    )
    document.add_dataset(ResultDataset(
        "energy", frame.ref, source, "float64", (), "hartree", (-75.0,),
        quality=("synthetic-fixture",),
    ))
    document.add_dataset(ResultDataset(
        "atomic_charge", frame.ref, source, "float64", (3,), "e", (-0.8, None, 0.4),
        (DatasetAxis("atom", frame.atom_ids),),
        missing_reason="The sample provides no charge for the first hydrogen atom",
        method="Mulliken (synthetic)", density="total", quality=("synthetic-fixture",),
    ))
    deleted = document.publish_revision(
        root.ref,
        replace(molecule, name="OH · Deletion demo (synthetic)", atoms=(oxygen, hydrogen1),
                bonds=(Bond(0, 1),), multiplicity=2),
        root.atom_ids[:2], source,
    )
    restored = document.restore_revision(deleted.ref, root.ref)
    document.publish_revision(
        restored.ref,
        replace(molecule, atoms=(hydrogen1, hydrogen2, oxygen), bonds=(Bond(2, 0), Bond(2, 1))),
        (root.atom_ids[1], root.atom_ids[2], root.atom_ids[0]), source,
    )
    return Session.from_document(document, CalculationSpec(), "")
