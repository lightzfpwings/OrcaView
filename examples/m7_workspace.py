"""在 OrcaView 桌面工作区查看已有结果及其绑定的结构。

PYTHONPATH=src python examples/m7_workspace.py
PYTHONPATH=src python examples/m7_workspace.py --orca examples/m5_orca/water-sp.out --kind energy
"""

import argparse
import os
from pathlib import Path
import sys

from orcaview.application.project import load_project
from orcaview.gui.result_demo import build_result_demo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--orca", type=Path, help="导入一份 M5 支持的 ORCA 单点输出")
    source.add_argument("--project", type=Path, help="打开含有结果的 OrcaView 项目")
    parser.add_argument("--kind", help="显示指定类型的首个数据集，例如 energy 或 mulliken-charge")
    parser.add_argument("--screenshot", type=Path, help="将当前窗口保存为 PNG 后退出")
    args = parser.parse_args()

    if args.screenshot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        if args.orca:
            from orcaview.gui.result_import import read_native_session
            session = read_native_session(args.orca)
            dataset_id = None
        elif args.project:
            session = load_project(args.project)
            dataset_id = None
        else:
            session, dataset_id = build_result_demo()
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    datasets = session.document.records()[1]
    if not datasets:
        parser.error("项目缺少已绑定的数据集")
    if args.kind:
        data = next((item for item in datasets if item.kind == args.kind), None)
        if data is None:
            parser.error("此项目可用的数据类型为 " + ", ".join(sorted({item.kind for item in datasets})))
    else:
        data = session.document.dataset(dataset_id) if dataset_id else datasets[0]

    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("OrcaView")
    app.setFont(QFont("Arial", 12))
    window = MainWindow()
    window.open_result_session(session, data.dataset_id, mark_dirty=args.project is None)
    window.show()
    if args.screenshot is None:
        return app.exec()

    app.processEvents()
    actual_frame = window.foundation_panel.selected_snapshot
    if actual_frame.ref != data.geometry:
        raise RuntimeError("工作区显示的几何与所选结果不一致")
    if not window.grab().save(str(args.screenshot), "PNG"):
        parser.error(f"无法保存截图 {args.screenshot}")
    print(f"{data.kind} ({data.unit})，{data.provenance.producer or data.provenance.kind}，"
          f"结果修订 {actual_frame.ref.revision}，编辑修订 {session.document.head.ref.revision}")
    print(args.screenshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
