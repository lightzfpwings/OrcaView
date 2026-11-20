"""Import synthetic ORCA text and navigate the results after reopening a project."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.snapshots import SelectionContext
from orcaview.results import commit_orca_output, inspect_orca_output


def main() -> None:
    examples = Path(__file__).resolve().parent
    fixture_directory = examples / "m5_orca"
    fixture = json.loads((fixture_directory / "manifest.json").read_text(encoding="utf-8"))["files"][0]
    source = fixture_directory / fixture["path"]

    session = Session()
    session.open_xyz(examples / "water.xyz")
    document = session.document
    historical = document.head
    oxygen, first_hydrogen, second_hydrogen = historical.molecule.atoms
    oxygen_id, first_hydrogen_id, second_hydrogen_id = historical.atom_ids
    edited = document.publish_revision(
        historical.ref,
        replace(historical.molecule, atoms=(
            oxygen, second_hydrogen, replace(first_hydrogen, z=first_hydrogen.z + 0.1),
        )),
        (oxygen_id, second_hydrogen_id, first_hydrogen_id),
    )

    inspection = inspect_orca_output(source, document=document, target=historical.ref)
    if not inspection.importable:
        raise RuntimeError(inspection.issues)
    assert inspection.artifact.sha256 == fixture["sha256"]
    assert inspection.evidence.optimization_converged is None
    imported = commit_orca_output(inspection, document=document)
    assert imported.frame.parent == historical.ref
    assert imported.frame.atom_ids == historical.atom_ids
    assert imported.document.head == edited

    imported_session = Session.from_document(imported.document, session.calculation, session.source_path)
    with TemporaryDirectory(prefix="orcaview-m5-") as temporary:
        directory = Path(temporary)
        project = directory / "native-results.oview.json"
        save_project(imported_session, project)
        reopened = load_project(project).document

        missing_source = directory / "water-without-mulliken.out"
        start, end = fixture["source_lines"]["mulliken_charges"]
        lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
        missing_source.write_text("".join(lines[:start - 1] + lines[end:]), encoding="utf-8")
        missing_import = commit_orca_output(inspect_orca_output(missing_source))
        missing_charges = next(item for item in missing_import.datasets if item.unit == "e")
        assert missing_charges.values is None and missing_charges.missing_reason
        assert missing_charges.geometry == missing_import.frame.ref
        assert missing_charges.axes[0].ids == missing_import.frame.atom_ids

    assert reopened.records() == imported.document.records()
    results = {item.unit: reopened.dataset(item.dataset_id) for item in imported.datasets}
    energy = results["hartree"]
    charges = results["e"]
    frame = reopened.resolve(energy.geometry)
    assert frame == imported.frame and frame.ref.frame_id is not None
    assert frame.coordinates() == historical.coordinates()
    assert energy.shape == ()
    assert energy.values == (fixture["expected"]["final_single_point_energy_hartree"],)
    assert charges.geometry == frame.ref and charges.axes[0].ids == frame.atom_ids
    assert charges.values == tuple(fixture["expected"]["mulliken_atomic_charges_e"])
    assert charges.valid_mask == (True, True, True)
    for dataset in (energy, charges):
        artifact = reopened.artifact(dataset.provenance.parents[0].artifact_id)
        assert artifact == inspection.artifact

    print("合成解析样例，已核对源文件 SHA-256 及项目保存和重开。")
    print(f"编辑修订 {reopened.head.ref.revision}，结果修订 {frame.ref.revision}，帧 {frame.ref.frame_id}。")
    print(f"单点能 {energy.values[0]:.12f} {energy.unit}，源文件第 {inspection.evidence.energy_line} 行。")
    rows = sorted(zip(charges.axes[0].ids, charges.values), key=lambda row: row[1], reverse=True)
    selection = SelectionContext(charges.geometry, tuple(atom_id for atom_id, _ in rows))
    for (atom_id, value), original_index in zip(rows, selection.indices(frame)):
        element = frame.molecule.atoms[original_index].element
        current_index = reopened.head.index_of(atom_id)
        print(f"{element}  Mulliken {value:+.6f} {charges.unit}  源帧第 {original_index + 1} 行，"
              f"编辑头第 {current_index + 1} 行。")
    print("该文件只包含单点计算，几何优化状态为空。")
    print(f"省略电荷表的变体仍保留实际帧和原子轴。缺失原因是{missing_charges.missing_reason}")


if __name__ == "__main__":
    main()
