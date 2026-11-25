"""Desktop display and background image commands. Importing this module does not load Qt."""

import argparse
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from orcaview.appearance import MODEL_LABELS, AppearanceStore, read_palette


def _rotation(value):
    axis, separator, angle = value.lower().partition(":")
    if axis not in ("x", "y", "z") or not separator:
        raise argparse.ArgumentTypeError("Use AXIS:DEGREES, for example y:-30")
    try:
        degrees = float(angle)
    except ValueError:
        raise argparse.ArgumentTypeError("Rotation requires a finite angle in degrees") from None
    if not math.isfinite(degrees):
        raise argparse.ArgumentTypeError("Rotation requires a finite angle in degrees")
    return axis, degrees


def _view_options(parser):
    parser.add_argument("--finite", action="store_true", help="Import a periodic cell as a finite structure")
    parser.add_argument("--labels", action="store_true", help="Show element symbols and atom numbers in 3D")
    parser.add_argument("--rotate", type=_rotation, action="append", default=[], metavar="AXIS:DEGREES",
                        help="Rotate about a screen axis, e.g. y:-30. Repeat in the desired order")
    parser.add_argument("--zoom", type=float, default=1, help="3D magnification, 0.3 to 4 (default: 1)")
    parser.add_argument("--pan", type=float, nargs=2, metavar=("X", "Y"), default=(0, 0),
                        help="Shift the 3D view by logical pixels, positive right and down")
    parser.add_argument("--model", choices=MODEL_LABELS)
    parser.add_argument("--atom-scale", type=float)
    parser.add_argument("--bond-scale", type=float)
    parser.add_argument("--bond-distance-factor", type=float)
    colors = parser.add_mutually_exclusive_group()
    colors.add_argument("--palette", help="ID of an installed color pack, or default")
    colors.add_argument("--color-pack", type=Path, help="Use a local palette JSON file for this command")


def add_gui_options(gui):
    gui.add_argument("input", type=Path, nargs="?", help="Structure, project or ORCA output to open")
    gui.add_argument("--workspace", choices=("input", "design", "result"))
    gui.add_argument("--screenshot", type=Path, help="Write a desktop screenshot offscreen, then exit")
    gui.add_argument("--window-size", type=int, nargs=2, metavar=("WIDTH", "HEIGHT"))
    gui.add_argument("--bottom-tab", choices=("input", "summary", "log"))
    gui.add_argument("--show-panel", action="append", choices=("navigation", "inspector", "bottom"), default=[])
    gui.add_argument("--hide-panel", action="append", choices=("navigation", "inspector", "bottom"), default=[])
    gui.add_argument("--select", nargs="+", type=int, metavar="ATOM", help="Select 1-based atom numbers in the active page")
    gui.add_argument("--rotation-step", type=float, help="Set the desktop rotation button increment in degrees")
    selected = gui.add_mutually_exclusive_group()
    selected.add_argument("--dataset", help="Open the result dataset with this ID")
    selected.add_argument("--snapshot", help="Open the result geometry with this snapshot ID")
    _view_options(gui)


def register(sub):
    parser = sub.add_parser("render", help="Export a structure image in the background (PNG, JPG, BMP, PDF)")
    parser.add_argument("input", type=Path, help="Structure, ORCA output or project")
    parser.add_argument("output", type=Path, help="Image filename; the extension selects the format")
    parser.add_argument("--view", choices=("3d", "2d"), default="3d")
    parser.add_argument("--snapshot", help="Export the specified project snapshot ID (default: current geometry)")
    parser.add_argument("--width", type=int, default=800, help="Logical view width before resolution scaling")
    parser.add_argument("--height", type=int, default=600, help="Logical view height before resolution scaling")
    parser.add_argument("--scale", type=int, default=1, choices=range(1, 9), help="Output pixels per logical pixel")
    parser.add_argument("--canvas-width", type=int, help="Final image width, centered around the scaled view")
    parser.add_argument("--canvas-height", type=int, help="Final image height, centered around the scaled view")
    parser.add_argument("--transparent", action="store_true", help="Export PNG or PDF with a transparent background")
    _view_options(parser)
    parser.set_defaults(handler=render)


def render(args):
    from orcaview.cli_io import check_output
    check_output(args.input, args.output)
    return run_offscreen("structure", args)


def _worker_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--render-worker"], os.environ.copy()
    env = os.environ.copy()
    if sys.flags.isolated:
        return [sys.executable, "-I", "-m", "orcaview.cli_render"], env
    source = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (source, env.get("PYTHONPATH"))))
    return [sys.executable, "-B", "-m", "orcaview.cli_render"], env


def _qt_worker(operation, args=None, *, timeout=None):
    # A broken platform plugin can abort inside native QApplication initialization.
    # Probe/display and offscreen work never initialize an unverified Qt backend in the CLI process.
    command, env = _worker_command()
    if operation != "probe":
        env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM"] = "1"
    values = {} if args is None else {k: v for k, v in vars(args).items() if not callable(v)}
    return subprocess.run(command + [operation], env=env, input=json.dumps(values, default=os.fspath).encode("utf-8"),
                          capture_output=True, timeout=timeout)


def run_offscreen(operation, args):
    timeout = float(os.environ.get("ORCAVIEW_RENDER_TIMEOUT", "300"))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("ORCAVIEW_RENDER_TIMEOUT must be a positive number of seconds")
    try:
        result = _qt_worker(operation, args, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ValueError(f"Background rendering timed out after {timeout:g} seconds") from None
    if result.returncode:
        # Native loader messages can contain many platform plugin paths; keep the actionable first line.
        error = result.stdout.decode("utf-8", "replace").strip()
        if not error:
            detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
            error = "The offscreen renderer could not complete the image"
            if detail:
                error += ": " + detail[0]
        raise ValueError(error)
    return 0


def _desktop_candidate():
    if os.environ.get("ORCAVIEW_HEADLESS", "").lower() in ("1", "yes", "true", "on"):
        return False
    backend = os.environ.get("QT_QPA_PLATFORM", "").split(";")[0].split(":")[0].lower()
    if backend in ("offscreen", "minimal", "minimalegl", "vnc"):
        return False
    if sys.platform.startswith("linux"):
        if backend == "xcb":
            return bool(os.environ.get("DISPLAY"))
        if backend.startswith("wayland"):
            return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("WAYLAND_SOCKET"))
        return bool(backend or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
                    or os.environ.get("WAYLAND_SOCKET"))
    if sys.platform == "darwin":
        if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY") or os.environ.get("SSH_CLIENT"):
            return False
        try:
            return os.stat("/dev/console").st_uid == os.getuid()
        except OSError:
            return False
    return True


def launch_gui(args):
    if args.screenshot:
        from orcaview.cli_io import check_output
        if args.input:
            check_output(args.input, args.screenshot)
        return run_offscreen("screenshot", args)
    if not _desktop_candidate():
        return 0
    try:
        if _qt_worker("probe", timeout=8).returncode:
            return 0
    except (subprocess.TimeoutExpired, OSError):
        return 0
    from orcaview.gui.main_window import launch
    return launch(configure=lambda window: _configure_window(window, args))


def _appearance(args, store):
    fields = {k: getattr(args, k) for k in ("model", "atom_scale", "bond_scale", "bond_distance_factor")
              if getattr(args, k) is not None}
    if args.palette is not None:
        if args.palette not in store.palettes():
            raise ValueError(f"Unknown color pack: {args.palette}")
        fields["palette_id"] = args.palette
    settings = replace(store.load(), **fields)
    colors = read_palette(args.color_pack).colors if args.color_pack else store.overrides(settings.palette_id)
    return settings, colors


def _camera(view, args):
    from PySide6.QtCore import QPointF

    if not .3 <= args.zoom <= 4 or not all(map(math.isfinite, args.pan)):
        raise ValueError("Use a zoom from 0.3 to 4 and finite pan offsets")
    for axis, degrees in args.rotate:
        view.rotate_view(axis, degrees)
    view.zoom = args.zoom
    view._pan = QPointF(*args.pan)
    view.labels = args.labels
    view.update()


def _configure_window(window, args):
    from orcaview.cli_io import load_session

    page = {"input": window.input_page, "design": window.design_panel, "result": window.foundation_panel}
    selected_result = args.dataset is not None or args.snapshot is not None
    if selected_result and (not args.input or args.workspace not in (None, "result")):
        raise ValueError("To select a result, open an input file in the Result workspace")
    if args.input:
        path = Path(args.input)
        session = load_session(path, finite=args.finite, calculation=window.default_calculation)
        project = str(path) if path.suffix.lower() == ".json" else None
        if project is None and session.log_report is not None and not session.molecule.atoms:
            if selected_result:
                raise ValueError("This log contains no bound molecular dataset or geometry")
            if args.workspace in ("input", "design"):
                raise ValueError("The log contains results only. Open it in the Result workspace")
            window._show_log_only(path, session.log_report)
        else:
            if session.log_report is not None or session.document.records()[1]:
                window.open_result_session(session, mark_dirty=False, project_path=project, opened_path=path, message="")
            else:
                window.session = session
                window._load_controls(project_path=project, opened_path=path)
                window.workspace_tabs.setCurrentWidget(window.input_page if session.molecule.atoms else window.design_panel)
    if selected_result:
        window.workspace_tabs.setCurrentWidget(page["result"])
        result = window.foundation_panel
        if args.dataset is not None:
            result.view_dataset(args.dataset)
        else:
            result.view_geometry(_snapshot(window.session.document, args.snapshot).ref)
    elif args.workspace is not None:
        window.workspace_tabs.setCurrentWidget(page[args.workspace])
    _layout(window, args)
    settings, colors = _appearance(args, window.appearance_store)
    window.appearance = settings
    window.labels_action.setChecked(args.labels)
    for view in window._viewports:
        view.set_appearance(settings, colors)
        _camera(view, args)
    window.design_panel.canvas.set_element_colors(colors)
    if args.select:
        indices = [n - 1 for n in args.select]
        view = window._active_viewport()
        if (not view.molecule or len(set(indices)) != len(indices)
                or any(i < 0 or i >= len(view.molecule.atoms) for i in indices)):
            raise ValueError("Select distinct atom numbers present in the current geometry")
        if view is window.design_panel.viewport:
            window.design_panel._select(indices)
        else:
            if len(indices) > 2:
                raise ValueError("Input and Result workspaces support selecting up to two atoms")
            view.selected = indices
            view.selection_changed.emit(indices)
            view.update()


def _layout(window, args):
    if args.window_size:
        w, h = args.window_size
        if not window.minimumWidth() <= w <= 16_384 or not window.minimumHeight() <= h <= 16_384 or w * h > 32_000_000:
            raise ValueError(f"Window size must be at least {window.minimumWidth()} x {window.minimumHeight()} "
                             "and fit the image export size limits")
        window.resize(w, h)
    docks = {"navigation": window.tree_dock, "inspector": window.inspector_dock, "bottom": window.bottom_dock}
    if set(args.show_panel).intersection(args.hide_panel):
        raise ValueError("A panel cannot be both shown and hidden")
    for name in args.hide_panel:
        docks[name].hide()
    for name in args.show_panel:
        docks[name].show()
    if args.bottom_tab:
        tabs = {"input": window.input_preview, "summary": window.output_summary, "log": window.log}
        window.tabs.setCurrentWidget(tabs[args.bottom_tab])
    if args.rotation_step is not None:
        if not window.rotation_angle.minimum() <= args.rotation_step <= window.rotation_angle.maximum():
            raise ValueError("Rotation button step must be between 0 and 360 degrees")
        window.rotation_angle.setValue(args.rotation_step)


def _snapshot(document, snapshot_id):
    if snapshot_id is None:
        return document.head
    for snapshot in document.records()[0]:
        if snapshot.ref.snapshot_id == snapshot_id:
            return snapshot
    raise ValueError(f"Unknown geometry snapshot: {snapshot_id}")


def _render_structure(args):
    from orcaview.cli_io import load_session
    from orcaview.gui.structure_export import save_structure_image, validate_structure_size

    fmt = Path(args.output).suffix.lstrip(".")
    width = args.width * args.scale if args.canvas_width is None else args.canvas_width
    height = args.height * args.scale if args.canvas_height is None else args.canvas_height
    validate_structure_size(args.width, args.height, "PDF")
    validate_structure_size(width, height, fmt, scale=args.scale)
    session = load_session(Path(args.input), finite=args.finite)
    snapshot = _snapshot(session.document, args.snapshot)
    if not snapshot.molecule.atoms:
        raise ValueError("The selected geometry contains no atoms to render")
    settings, colors = _appearance(args, AppearanceStore())
    if args.view == "2d":
        if (args.rotate or args.zoom != 1 or any(args.pan) or args.model or args.labels or
                any(v is not None for v in (args.atom_scale, args.bond_scale, args.bond_distance_factor))):
            raise ValueError("Model, 3D camera, sizing, inference and atom label options require --view 3d")
        from orcaview.gui.design_canvas import DesignCanvas

        view = DesignCanvas()
        view.setMinimumSize(1, 1)
        view.resize(args.width, args.height)
        view.set_element_colors(colors)
        view.set_molecule(snapshot.sketch_molecule(), fit=True, independent_sketch=snapshot.sketch_xy is not None)
    else:
        from orcaview.gui.viewport import MoleculeViewport

        view = MoleculeViewport()
        view.setMinimumSize(1, 1)
        view.resize(args.width, args.height)
        view.set_appearance(settings, colors)
        view.set_molecule(snapshot.molecule)
        _camera(view, args)
    save_structure_image(view, args.output, fmt, width, height, transparent=args.transparent, scale=args.scale)


def worker_main(argv):
    try:
        operation, = argv
        args = argparse.Namespace(**json.load(sys.stdin.buffer))
        windows_fonts = None
        if sys.platform == "win32" and operation != "probe":
            from PySide6.QtCore import QStandardPaths

            # The Windows offscreen backend discovers fonts in a directory.
            windows_fonts = os.environ.get("QT_QPA_FONTDIR") or QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.FontsLocation)
            os.environ["QT_QPA_FONTDIR"] = windows_fonts
        from PySide6.QtWidgets import QApplication
        app = QApplication(["OrcaView"])
        app.setApplicationName("OrcaView")
        if operation == "probe":
            return 0 if app.primaryScreen() else 1
        if app.platformName() != "offscreen":
            raise ValueError("The Qt offscreen platform is unavailable")
        if windows_fonts:
            from PySide6.QtGui import QFontDatabase

            # Qt 6.8 scans TTF and OTF, but many Windows CJK fonts are collections.
            for collection in Path(windows_fonts).glob("*.ttc"):
                QFontDatabase.addApplicationFont(str(collection))
        if operation == "screenshot":
            from orcaview.gui.main_window import launch
            return launch(args.screenshot, configure=lambda window: _configure_window(window, args))
        from orcaview.gui.language_settings import load_interface_language
        from orcaview.gui.typography import interface_font
        app.setFont(interface_font(load_interface_language(app)))
        if operation == "structure":
            _render_structure(args)
        elif operation == "spectrum":
            from orcaview.cli_results import render_spectrum_image
            render_spectrum_image(args)
        else:
            raise ValueError("Unknown image operation")
        return 0
    except (ImportError, OSError, ValueError) as exc:
        message = str(exc)
        if isinstance(exc, ImportError):
            message = f"The Qt renderer could not be loaded ({exc}). Install OrcaView's gui extra or a desktop package."
        sys.stdout.buffer.write(message.encode("utf-8", "replace"))
        return 2


if __name__ == "__main__":
    raise SystemExit(worker_main(sys.argv[1:]))
