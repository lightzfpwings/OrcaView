"""Synthetic M6 result for the desktop workspace, built without Qt or an engine."""

import json
from typing import Tuple

from orcaview.analysis import (
    HIRSHFELD_CHARGE, AnalysisRequest, WavefunctionRef, adapt_hirshfeld_fixture,
)
from orcaview.application.session import Session
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.gui.foundation_demo import build_foundation_demo


def build_result_demo() -> Tuple[Session, str]:
    """Return the M1 water history and a late M6 result bound to its original frame."""
    session = build_foundation_demo()
    document = session.document
    frame = next(s for s in document.records()[0] if s.ref.frame_id == "synthetic-step-1")
    oxygen, first_h, second_h = frame.atom_ids

    # The analysis adapter consumes declared wavefunction metadata only.
    placeholder = ArtifactRef.from_bytes(b"OrcaView synthetic Molden placeholder; metadata only.\n",
                                         "molden", "synthetic-metadata.molden")
    wavefunction = WavefunctionRef(
        artifact=placeholder, geometry=frame.ref, geometry_sha256=frame.content_hash,
        atom_ids=(second_h, oxygen, first_h),
        provenance=Provenance("fixture", "orcaview.m7-demo", "1", frame.provenance.parents,
                              (("synthetic_fixture", "true"),)),
        source_unit="angstrom", basis_convention="spherical", has_basis=True, has_orbitals=True,
        has_occupations=True, spin_type="restricted", has_ecp=False, densities=("total",), periodic=False,
    )
    request = AnalysisRequest(HIRSHFELD_CHARGE.capability_id, wavefunction, density="total")
    fixture = b'{"synthetic_fixture":true,"atom_order":["H2","O","H1"],"charges_e":[0.0,-0.2,null]}'
    result = adapt_hirshfeld_fixture(
        request, frame, ArtifactRef.from_bytes(fixture, "orcaview.synthetic-json", "synthetic-charges.json"),
        tuple(json.loads(fixture)["charges_e"]), missing_reason="The synthetic example omits the first hydrogen atom’s charge",
    )
    dataset, = result.datasets
    document.add_dataset(dataset)
    return session, dataset.dataset_id
