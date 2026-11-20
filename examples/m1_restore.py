"""Demonstrate the M1 history protocol; the M2 editor owns the actual undo stack."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.models import Bond
from orcaview.core.provenance import Provenance
from orcaview.core.results import DatasetAxis, ResultDataset


def main():
    session = Session()
    document = session.document
    # Explicit bonds and electronic state are part of the historical molecule.
    root = document.head
    before = document.publish_revision(
        root.ref, replace(root.molecule, bonds=(Bond(0, 1), Bond(0, 2))), root.atom_ids,
    )
    frame = document.add_frame(before.ref, "synthetic-result", before.molecule,
                               before.atom_ids, Provenance("fixture", "m1.restore-example", "1"))
    data = ResultDataset(
        "atomic_charge", frame.ref, Provenance("fixture"), "float64", (3,), "e",
        (-0.8, 0.4, 0.4), (DatasetAxis("atom", frame.atom_ids),),
        quality=("synthetic-fixture",),
    )
    document.add_dataset(data)
    # Simulate M2 deleting H2 and updating its bonds/electronic state.
    after = document.publish_revision(
        before.ref, replace(before.molecule, atoms=before.molecule.atoms[:2],
                            bonds=(Bond(0, 1),), multiplicity=2), before.atom_ids[:2],
    )
    undone = document.restore_revision(after.ref, before.ref)
    if (undone.molecule, undone.atom_ids) != (before.molecule, before.atom_ids):
        raise RuntimeError("撤销没有完整恢复历史修订")

    with TemporaryDirectory(prefix="orcaview-m1-restore-") as directory:
        project = Path(directory) / "restore.oview.json"
        save_project(session, project)
        reopened = load_project(project).document
        if reopened.records() != document.records():
            raise RuntimeError("恢复历史没有正确保存重开")
        # M2 stores the original before/after refs; redo appends yet another revision.
        redone = reopened.restore_revision(reopened.head.ref, after.ref)
        restored = reopened.restore_revision(redone.ref, before.ref)
        save_project(Session.from_document(reopened, session.calculation, ""), project)
        if load_project(project).document.records() != reopened.records():
            raise RuntimeError("重做与再次撤销没有正确保存重开")

    if reopened.resolve(reopened.dataset(data.dataset_id).geometry) != frame:
        raise RuntimeError("历史结果被错误绑定到编辑头")
    print(f"删除：修订 {after.ref.revision}，{len(after.atom_ids)} 个原子。")
    print(f"撤销：修订 {undone.ref.revision}，原有 ID、坐标、键和电子态完整恢复。")
    print(f"保存重开后重做：修订 {redone.ref.revision}；再次撤销：修订 {restored.ref.revision}。")
    print(f"合成结果仍指向修订 {frame.ref.revision} / 帧 {frame.ref.frame_id}。")


if __name__ == "__main__":
    main()
