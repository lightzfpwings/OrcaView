"""Round-trip synthetic M6 data through M1 using an M5 result frame and atom IDs."""

from dataclasses import replace
import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from orcaview.analysis import (
    HIRSHFELD_CHARGE,
    AnalysisRequest,
    WavefunctionRef,
    adapt_hirshfeld_fixture,
    check_capability,
)
from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.core.snapshots import SelectionContext
from orcaview.results import commit_orca_output, inspect_orca_output


NATIVE_FIXTURE = Path(__file__).resolve().parent / "m5_orca" / "water-sp.out"
ANALYSIS_FIXTURE = '''{
  "synthetic_fixture": true,
  "charges_in_wavefunction_order": [0.0, -0.2, null],
  "partial_missing_reason": "合成值省略了第一个氢原子的电荷",
  "whole_missing_reason": "合成样例省略了整个电荷载荷"
}
'''.encode("utf-8")


def main() -> None:
    with TemporaryDirectory(prefix="orcaview-m6-") as temporary:
        directory = Path(temporary)
        native_path = directory / "synthetic-water.out"
        copyfile(NATIVE_FIXTURE, native_path)
        inspected = inspect_orca_output(native_path)
        imported = commit_orca_output(inspected)
        document, frame = imported.document, imported.frame

        wavefunction_path = directory / "metadata-only.molden"
        wavefunction_path.write_bytes(b"Synthetic artifact placeholder. No wavefunction data.\n")
        artifact = ArtifactRef.from_file(wavefunction_path, "molden")
        oxygen, first_hydrogen, second_hydrogen = frame.atom_ids
        source_order = (second_hydrogen, oxygen, first_hydrogen)
        wavefunction = WavefunctionRef(
            artifact=artifact,
            geometry=frame.ref,
            geometry_sha256=frame.content_hash,
            atom_ids=source_order,
            provenance=Provenance(
                "synthetic-source", "examples.m6_analysis", "1", (inspected.artifact,),
            ),
            source_unit="angstrom",
            basis_convention="spherical",
            has_basis=True,
            has_orbitals=True,
            has_occupations=True,
            spin_type="restricted",
            has_ecp=False,
            densities=("total",),
            periodic=False,
        )
        request = AnalysisRequest(
            capability_id=HIRSHFELD_CHARGE.capability_id, wavefunction=wavefunction, density="total",
        )
        capability = check_capability(request, frame)
        assert not capability.available
        assert {issue.code for issue in capability.issues} == {"internal_engine_unavailable"}

        fixture_path = directory / "synthetic-charges.json"
        fixture_path.write_bytes(ANALYSIS_FIXTURE)
        fixture_bytes = fixture_path.read_bytes()
        fixture = ArtifactRef.from_bytes(fixture_bytes, "orcaview.synthetic-json", str(fixture_path))
        payload = json.loads(fixture_bytes)

        base = document.head
        first_atom, second_atom, third_atom = base.molecule.atoms
        new_atoms = (replace(second_atom, z=second_atom.z + 0.1), third_atom, first_atom)
        edited = document.publish_revision(
            base.ref, replace(base.molecule, atoms=new_atoms), (first_hydrogen, second_hydrogen, oxygen),
        )

        partial = adapt_hirshfeld_fixture(
            request, document.resolve(request.wavefunction.geometry), fixture,
            tuple(payload["charges_in_wavefunction_order"]), missing_reason=payload["partial_missing_reason"],
        )
        missing = adapt_hirshfeld_fixture(
            request, frame, fixture, None, missing_reason=payload["whole_missing_reason"],
        )
        for result in (partial, missing):
            assert result.task.status == "synthetic-fixture"
            document.add_dataset(result.datasets[0])

        project = directory / "analysis.oview.json"
        save_project(Session(tracked_document=document), project)
        for path in (native_path, wavefunction_path, fixture_path):
            path.unlink()
        reopened = load_project(project).document

    assert reopened.records() == document.records()
    partial_data = reopened.dataset(partial.datasets[0].dataset_id)
    missing_data = reopened.dataset(missing.datasets[0].dataset_id)
    source_frame = reopened.resolve(partial_data.geometry)
    assert source_frame == frame and reopened.head == edited
    assert imported.datasets[0].geometry == partial_data.geometry == missing_data.geometry
    assert partial_data.axes[0].ids == missing_data.axes[0].ids == source_order
    assert partial_data.valid_mask == (True, True, False)
    assert missing_data.values is None and missing_data.valid_mask is None
    for parent in (artifact, fixture, inspected.artifact):
        assert reopened.artifact(parent.artifact_id) == parent
        assert parent in partial_data.provenance.parents

    print("M5 文本、M6 来源及电荷均为合成演示。项目在删除临时来源文件后成功重开。")
    print(f"计算能力不可用。{capability.issues[0].reason}")
    print(f"编辑修订 {edited.ref.revision}，分析绑定修订 {source_frame.ref.revision} 的实际帧。")
    # The display can sort rows independently of both source-file order and the editable head.
    rows = sorted(zip(partial_data.axes[0].ids, partial_data.values), key=lambda row: (row[1] is None, row[1]))
    selection = SelectionContext(source_frame.ref, tuple(atom_id for atom_id, _ in rows))
    frame_indices = selection.indices(source_frame)
    assert frame_indices == (0, 2, 1)
    assert tuple(edited.index_of(atom_id) for atom_id in selection.atom_ids) == (2, 1, 0)
    for (atom_id, value), source_index in zip(rows, frame_indices):
        element = source_frame.molecule.atoms[source_index].element
        shown = "缺失" if value is None else f"{value:+.2f} {partial_data.unit}"
        print(f"{element}  {shown}  实际帧第 {source_index + 1} 行，编辑头第 {edited.index_of(atom_id) + 1} 行。")
    print(f"部分缺失原因为{partial_data.missing_reason}。全部缺失原因为{missing_data.missing_reason}。")


if __name__ == "__main__":
    main()
