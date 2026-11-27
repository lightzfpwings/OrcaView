from pathlib import Path
from importlib.metadata import distribution
import sys
import sysconfig

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
pyinstaller = distribution("PyInstaller")
bootloader_license = next(pyinstaller.locate_file(p) for p in pyinstaller.files if p.name == "COPYING.txt")
ffmpeg = distribution("imageio-ffmpeg")
ffmpeg_license = next(ffmpeg.locate_file(p) for p in ffmpeg.files if p.name == "LICENSE")
repo = source.parent
notices = [
    (str(repo / "LICENSE"), "ThirdParty/OrcaView"),
    (str(repo / "THIRD_PARTY_NOTICES.md"), "ThirdParty"),
    (str(packaging_dir / "DEPENDENCY_LICENSES.txt"), "ThirdParty"),
    (str(Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"), "ThirdParty/CPython"),
    (str(bootloader_license), "ThirdParty/PyInstaller"),
    (str(ffmpeg_license), "ThirdParty/imageio-ffmpeg"),
    (str(repo / "packaging/licenses/wgpu-native-MIT.txt"), "ThirdParty/wgpu-native"),
]
for package in ("numpy", "wgpu", "rendercanvas", "cffi", "pycparser", "rubicon-objc"):
    dist = distribution(package)
    metadata = next(path for path in dist.files if path.name == "METADATA")
    notices.append((str(dist.locate_file(metadata.parent / "licenses")), f"ThirdParty/{package}"))

analysis = Analysis(
    [str(packaging_dir / "launcher.py")],
    pathex=[str(source)],
    datas=[(str(source / "orcaview" / "gui" / "assets" / "orcaview.png"), "orcaview/gui/assets"),
           (str(source / "orcaview" / "gui" / "assets" / "*.svg"), "orcaview/gui/assets"),
           (str(babel_data), "openbabel/share/openbabel"), *copy_metadata("openbabel"), *notices],
    binaries=[(str(babel_plugins / "*.so"), "openbabel/lib/openbabel/3.2.0")],
    hiddenimports=[*collect_submodules("orcaview"), "openbabel.openbabel", "openbabel._openbabel"],
)
# pip records the local install URL even when the wheel is byte-identical to PyPI.
analysis.datas = [entry for entry in analysis.datas
                  if entry[0] != "openbabel-3.2.0.dist-info/direct_url.json" and not entry[0].endswith(".qm")]
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
        "CFBundleDevelopmentRegion": "en",
        "CFBundleLocalizations": ["en"],
        "NSHighResolutionCapable": True,
    },
)
