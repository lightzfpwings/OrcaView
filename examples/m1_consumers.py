"""Exercise M1 with synthetic M5/M6 payloads and a plain-Python M7-style table.

This example checks object exchange and project persistence. The fixture values
do not validate an ORCA parser, a numerical analysis engine or a GUI module.
"""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.core.results import DatasetAxis, ResultDataset
from orcaview.core.snapshots import SelectionContext


NATIVE_FIXTURE = b'''{
  "synthetic_fixture": true,
  "h1_displacement_angstrom": 0.05,
  "energy_hartree": -75.0
}
'''
ANALYSIS_FIXTURE = b'''{
  "synthetic_fixture": true,
  "method": "Hirshfeld",
  "charges_reversed_atom_order": [null, 0.2, -0.4],
  "missing_reason": "Synthetic fixture omits the second hydrogen charge"
}
'''


def _fixture(directory, filename, raw):
    path = directory / filename
    path.write_bytes(raw)
    artifact = ArtifactRef.from_bytes(raw, "orcaview.synthetic-json", str(path))
    assert artifact.sha256 == ArtifactRef.from_file(path, artifact.format).sha256
    return json.loads(raw), artifact


def build_example(directory):
    """Write explicit fixture bytes, then return a session and its two dataset IDs."""
    native, native_file = _fixture(directory, "native-fixture.json", NATIVE_FIXTURE)
    analysis, analysis_file = _fixture(directory, "analysis-fixture.json", ANALYSIS_FIXTURE)
    session = Session()
    document = session.document
    initial = document.head
    oxygen, hydrogen1, hydrogen2 = initial.molecule.atoms
    moved = replace(initial.molecule, atoms=(
        oxygen,
        replace(hydrogen1, z=hydrogen1.z + native["h1_displacement_angstrom"]),
        hydrogen2,
    ))
    native_source = Provenance("import", "m1.synthetic-native", "1", (native_file,),
                               (("synthetic_fixture", "true"),))
    frame = document.add_frame(initial.ref, "synthetic-step-1", moved,
                               initial.atom_ids, native_source)
    energy = ResultDataset(
        "energy", frame.ref, native_source, "float64", (), "hartree",
        (native["energy_hartree"],), quality=("synthetic-fixture",),
    )
    charges = ResultDataset(
        "atomic_charge", frame.ref,
        Provenance("analysis", "m1.synthetic-analysis", "1", (analysis_file,),
                   (("synthetic_fixture", "true"),)),
        "float64", (3,), "e", tuple(analysis["charges_reversed_atom_order"]),
        (DatasetAxis("atom", frame.atom_ids[::-1]),),
        missing_reason=analysis["missing_reason"], method=analysis["method"],
        density="total", quality=("synthetic-fixture",),
    )
    document.add_dataset(energy)
    document.add_dataset(charges)
    document.publish_revision(
        initial.ref, replace(initial.molecule, atoms=initial.molecule.atoms[::-1]),
        initial.atom_ids[::-1],
    )
    return session, energy.dataset_id, charges.dataset_id


def main():
    with TemporaryDirectory(prefix="orcaview-m1-consumers-") as temporary:
        directory = Path(temporary)
        session, energy_id, charges_id = build_example(directory)
        project = directory / "consumers.oview.json"
        save_project(session, project)
        document = load_project(project).document
        assert document.records() == session.document.records()
        energy = document.dataset(energy_id)
        charges = document.dataset(charges_id)
        geometry = document.resolve(charges.geometry)
        original_hash = geometry.content_hash
        assert energy.geometry == charges.geometry
        assert energy.shape == () and energy.axes == ()
        assert charges.valid_mask == (False, True, True)
        rows = sorted(zip(charges.axes[0].ids, charges.values), key=lambda row: (
            geometry.molecule.atoms[geometry.index_of(row[0])].element,
            geometry.index_of(row[0]),
        ))
        selection = SelectionContext(geometry.ref, tuple(atom_id for atom_id, _ in rows))
        assert selection.indices(geometry) == tuple(geometry.index_of(atom_id) for atom_id, _ in rows)
        assert document.resolve(charges.geometry).content_hash == original_hash
        print("合成消费样例；临时 fixture、项目及来源哈希已核对，保存重开通过。")
        print(f"当前 head：修订 {document.head.ref.revision}；结果：修订 "
              f"{geometry.ref.revision} / 帧 {geometry.ref.frame_id}。")
        print(f"能量（合成值）：{energy.values[0]:.2f} {energy.unit}。")
        for table_row, (atom_id, value) in enumerate(rows, 1):
            source_row = geometry.index_of(atom_id)
            element = geometry.molecule.atoms[source_row].element
            shown = "缺失" if value is None else f"{value:+.2f} {charges.unit}"
            print(f"表格第 {table_row} 行 {element}：原帧第 {source_row + 1} 行，"
                  f"head 第 {document.head.index_of(atom_id) + 1} 行，{shown}。")
        print(f"缺失原因：{charges.missing_reason}。")
        print("显示排序和选择保留原帧引用及科学坐标。")


if __name__ == "__main__":
    main()
