"""Explicit CLI updates from the same verified release channel as the desktop."""

from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from orcaview import __version__
from orcaview.application.macos_update import current_macos_installation, install_macos
from orcaview.application.update_download import (
    UpdateDownloadError, current_portable_installation, download_update, install_portable,
    prepare_portable_update, schedule_portable_update,
)
from orcaview.application.updates import UpdateError, check_for_update


def register(sub):
    update = sub.add_parser("update", help="Check for or install an official OrcaView update")
    commands = update.add_subparsers(dest="update_action", required=True)
    commands.add_parser("check", help="Report the newest eligible release and verified asset as JSON")
    download = commands.add_parser("download", help="Download and verify the current platform's package")
    download.add_argument("directory", type=Path)
    install = commands.add_parser("install", help="Install the verified application into a selected directory")
    install.add_argument("directory", type=Path)
    replace = commands.add_parser("replace-current", help="Replace this packaged installation without reopening it")
    for command in (install, replace):
        command.add_argument("--archive", type=Path,
                             help="Reuse a local package after checking it against the official release metadata")
    update.set_defaults(handler=run_update)


def _install(asset, archive, action, target):
    if asset.name.endswith(".dmg"):
        path = install_macos(asset, archive, target)
    elif action == "install":
        path = install_portable(asset, archive, target)
    else:
        prepared = prepare_portable_update(asset, archive, target)
        try:
            schedule_portable_update(prepared, relaunch=False)
        except BaseException:
            prepared.discard()
            raise
        return {"status": "scheduled", "path": str(prepared.target), "backup": str(prepared.backup),
                "error_file": str(prepared.staged.parent / "update-error.txt")}
    return {"status": "installed", "path": str(path)}


def _update(args):
    action = args.update_action
    release = check_for_update(__version__)
    if release is None:
        return {"status": "current", "installed_version": __version__}
    if action == "check":
        return {"status": "available", "installed_version": __version__, **asdict(release)}
    if release.asset is None:
        raise ValueError("This release has no verifiable installer for this system.")
    asset = release.asset
    if action == "download":
        path = download_update(asset, args.directory.expanduser())
        return {"status": "downloaded", "version": release.version, "path": str(path), "sha256": asset.sha256}
    if action == "replace-current":
        target = current_macos_installation() if asset.name.endswith(".dmg") else current_portable_installation()
        if target is None:
            raise ValueError("This command requires a packaged OrcaView installation. Use update install DIRECTORY.")
    else:
        target = args.directory.expanduser()
    if args.archive is not None:
        result = _install(asset, args.archive.expanduser(), action, target)
    else:
        with TemporaryDirectory(prefix="orcaview-download-") as temp:
            result = _install(asset, download_update(asset, Path(temp)), action, target)
    return {**result, "version": release.version}


def run_update(args):
    try:
        report = _update(args)
    except (UpdateError, UpdateDownloadError) as exc:
        raise ValueError(str(exc)) from exc
    print(json.dumps(report, ensure_ascii=False))
    return 0
