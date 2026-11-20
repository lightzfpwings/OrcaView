"""Run M2 transactions without Qt. Result values are synthetic fixtures only."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from orcaview.application.document import MoleculeDocument
from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.models import Atom, Bond, CalculationSpec, Molecule
from orcaview.core.provenance import Provenance
from orcaview.core.results import DatasetAxis, ResultDataset
from orcaview.editing import (AddAtoms, CoordinateDefinition, DeleteAtoms, EditorService,
                              GeometryEditCommand, ReorderAtoms, ReplaceElement,
                              SetDistance, SetElectronicState, measure)
from orcaview.selection import SelectionService


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    document = MoleculeDocument.from_molecule(Molecule(
        "M2 water geometry fixture", (Atom("O", 0, 0, 0), Atom("H", 0.96, 0, 0),
                                      Atom("H", -0.24, 0.93, 0)),
        (Bond(0, 1), Bond(0, 2)),
    ))
    root = document.head
    oxygen, hydrogen, deleted_h = root.atom_ids
    frame = document.add_frame(root.ref, "synthetic-step", root.molecule, root.atom_ids,
                               Provenance("synthetic_fixture", "m2.example", "1"))
    data = ResultDataset("atomic_charge", frame.ref, Provenance("synthetic_fixture"),
                         "float64", (3,), "e", (-0.8, 0.4, 0.4),
                         (DatasetAxis("atom", frame.atom_ids),), quality=("synthetic-fixture",))
    document.add_dataset(data)
    selection = SelectionService(root).select((deleted_h, oxygen))
    editor = EditorService(document, selection)

    def execute(operation):
        return editor.commit(editor.preview(GeometryEditCommand(editor.expected, operation)))

    before = document.records()
    preview = editor.preview(GeometryEditCommand(editor.expected, AddAtoms((Atom("He", 4, 0, 0),))))
    require(preview.mapping.target_ids[-1] is None, "预览提前分配了新增原子 ID")
    editor.cancel(preview)
    require(document.records() == before, "预览或取消改变了文档")
    print("预览/取消：文档、原子 ID 和历史保持不变。")

    deleted = execute(DeleteAtoms((deleted_h,)))
    require(deleted.electronic_state_error is not None, "未提示删除后的电子态不相容")
    require(deleted.snapshot.molecule.bonds == (Bond(0, 1),), "删除未清理显式键")
    restored = editor.undo()
    require((restored.snapshot.molecule, restored.snapshot.atom_ids) == (root.molecule, root.atom_ids),
            "撤销未完整恢复原始状态")
    require(restored.selection.atom_ids == selection.atom_ids, "撤销未恢复有序选择")
    editor.redo()
    execute(SetElectronicState(0, 2))
    print("删除→撤销→重做：原 ID、显式键、电子态及选择往返正确；OH 自旋由命令显式改为二重态。")

    added = execute(AddAtoms((Atom("He", 4, 0, 0),)))
    new_id = added.snapshot.atom_ids[-1]
    require(new_id not in root.atom_ids, "新增原子复用了历史 ID")
    execute(ReplaceElement(new_id, "Ne"))
    reordered = execute(ReorderAtoms(document.head.atom_ids[::-1]))
    require(reordered.mapping.source_to_target == (2, 1, 0), "重排映射错误")
    print(f"添加/替换/重排：新原子拥有独立 ID；旧行→新行映射 {reordered.mapping.source_to_target}。")

    distance = CoordinateDefinition(editor.expected, "distance", (oxygen, hydrogen))
    exact = execute(SetDistance(distance, 1.1, (hydrogen,), (oxygen, new_id)))
    measured = measure(exact.snapshot, CoordinateDefinition(exact.snapshot.ref, "distance", (oxygen, hydrogen)))
    require(abs(measured - 1.1) < 1e-10, "精确距离编辑未满足目标")
    print(f"精确距离：O—H = {measured:.6f} Å，仅移动显式指定的 H。")

    with TemporaryDirectory(prefix="orcaview-m2-") as directory:
        project = Path(directory) / "m2.oview.json"
        save_project(Session.from_document(document, CalculationSpec(), ""), project)
        reopened = load_project(project).document
        require(reopened.records() == document.records(), "项目重开没有保留完整文档历史")
        require(reopened.resolve(reopened.dataset(data.dataset_id).geometry) == frame,
                "旧结果被误绑到编辑头")
        fresh_editor = EditorService(reopened)
        require(not fresh_editor.undo_entries and not fresh_editor.redo_entries, "命令栈不应隐式持久化")
    print("保存重开：全部修订和原子 ID 保留，合成结果仍绑定原始帧；新编辑服务从空命令栈开始。")
    require(not any(name.split(".")[0] in ("PySide6", "vtk", "chem_traversal") for name in sys.modules),
            "无 Qt 示例加载了可选界面或执行依赖")
    print("以上数值为合成演示；未运行 ORCA、Traversal 或 Multiwfn。")


if __name__ == "__main__":
    main()
