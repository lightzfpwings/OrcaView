"""Run a synthetic water example through import, frame binding, reordering and project reload."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.provenance import Provenance
from orcaview.core.results import DatasetAxis, ResultDataset


def main():
    session = Session()
    session.open_xyz(Path(__file__).with_name("water.xyz"))
    doc = session.document
    initial = doc.head
    o, h1, h2 = initial.molecule.atoms
    moved = replace(initial.molecule, atoms=(o, replace(h1, z=h1.z + 0.05), h2))
    frame = doc.add_frame(initial.ref, "fixture-step-1", moved, initial.atom_ids,
                          Provenance("fixture", "m1.example", "1"))

    # Two example producers use the same ordered atom axis and the same source frame.
    sources = (("import", "Mulliken", (-0.8, 0.4, 0.4)), ("analysis", "Hirshfeld", (-0.4, 0.2, 0.2)))
    result_ids = []
    for kind, method, charges in sources:
        dataset = ResultDataset(
            "atomic_charge", frame.ref, Provenance(kind, "m1.synthetic." + kind, "1"),
            "float64", (3,), "e", charges, (DatasetAxis("atom", frame.atom_ids),),
            method=method, density="total", quality=("synthetic-fixture",),
        )
        doc.add_dataset(dataset)
        result_ids.append(dataset.dataset_id)

    doc.publish_revision(initial.ref, replace(initial.molecule, atoms=(h2, h1, o)), initial.atom_ids[::-1])
    with TemporaryDirectory() as directory:
        path = Path(directory) / "water.oview.json"
        save_project(session, path)
        reopened = load_project(path).document
    if reopened.records() != doc.records():
        raise RuntimeError("项目回读与原始修订或结果不一致")

    oxygen_id = initial.id_at(0)
    print(f"当前修订 {reopened.head.ref.revision}，氧原子在第 {reopened.head.index_of(oxygen_id) + 1} 行。")
    for dataset_id in result_ids:
        data = reopened.dataset(dataset_id)
        geometry = reopened.resolve(data.geometry)
        source_row = data.axes[0].ids.index(oxygen_id)
        print(f"{data.method}（合成样例）  修订 {geometry.ref.revision}，帧 {geometry.ref.frame_id}，"
              f"氧原子在第 {geometry.index_of(oxygen_id) + 1} 行，电荷 {data.values[source_row]:+.2f} e。")


if __name__ == "__main__":
    main()
