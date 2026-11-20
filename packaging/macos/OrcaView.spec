from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_submodules, copy_metadata, get_package_paths

packaging_dir = Path(SPECPATH)
source = packaging_dir.parents[1] / "src"
sys.path.insert(0, str(source))
from orcaview import __version__
from packaging.version import Version

babel = Path(get_package_paths("openbabel")[1])
# Open Babel discovers its format and force-field plug-ins with dlopen.
# Preserve the wheel's relative directories for both discovery and signing.
babel_plugins = babel / "lib" / "openbabel" / "3.2.0"
if not babel_plugins.is_dir():
    raise RuntimeError("The macOS trial build requires the official openbabel 3.2.0 wheel.")
babel_data = babel / "share" / "openbabel"

analysis = Analysis(
    [str(packaging_dir / "launcher.py")],
    pathex=[str(source)],
    datas=[(str(source / "orcaview" / "gui" / "assets" / "orcaview.png"), "orcaview/gui/assets"),
           (str(source / "orcaview" / "languages" / "*.json"), "orcaview/languages"),
           (str(babel_data), "openbabel/share/openbabel"), *copy_metadata("openbabel")],
    binaries=[(str(babel_plugins / "*.so"), "openbabel/lib/openbabel/3.2.0")],
    hiddenimports=[*collect_submodules("orcaview"), "openbabel.openbabel", "openbabel._openbabel"],
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive, analysis.scripts, [],
    exclude_binaries=True,
    name="OrcaView",
    console=False,
    target_arch="arm64",
)
distribution = COLLECT(executable, analysis.binaries, analysis.datas, name="OrcaView")
app = BUNDLE(
    distribution,
    name="OrcaView.app",
    icon=str(packaging_dir / "OrcaView.icns"),
    bundle_identifier="org.orcaview.desktop",
    version=__version__,
    info_plist={
        "CFBundleShortVersionString": Version(__version__).base_version,
        "CFBundleVersion": __version__,
        "NSHighResolutionCapable": True,
    },
)
