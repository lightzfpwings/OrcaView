"""Install the same user-facing molecular examples into every desktop release."""

from pathlib import Path
import shutil


def install_examples(root: Path, destination: Path):
    examples = root / "examples"
    logs = root / "artifacts/public/validation/results-0.1.0a12"
    files = {
        "water.xyz": examples / "water.xyz",
        "benzene.xyz": examples / "benzene.xyz",
        "water-sp.out": examples / "m5_orca/water-sp.out",
        "water-raman.out": logs / "raman/water.out",
        "water-nmr.out": logs / "nmr/water-shield.out",
        "peroxide-uv-cd.out": logs / "tdcd/peroxide.out",
    }
    for name in ("water.gjf", "ethanol-2d.mol", "crystal.cif"):
        files[f"文件导入/{name}"] = examples / "structure_import" / name
    native = examples / "native_methods"
    for source in sorted(native.rglob("*")):
        if source.suffix in (".inp", ".xyz") and source.is_file():
            files[f"原生计算输入/{source.relative_to(native).as_posix()}"] = source

    for name, source in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
