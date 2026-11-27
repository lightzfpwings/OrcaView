"""Install the same user-facing molecular examples into every desktop release."""

from pathlib import Path
import shutil

from release_language import check_release_text


def install_examples(root: Path, destination: Path):
    examples = root / "examples"
    logs = root / "artifacts/public/validation/results-0.1.0a12"
    files = {
        "Orbitals/water-homo.cube": examples / "orbitals/water-homo.cube",
        "water.xyz": examples / "water.xyz",
        "benzene.xyz": examples / "benzene.xyz",
        "water-sp.out": examples / "m5_orca/water-sp.out",
        "water-opt-freq.out": root / "artifacts/public/validation/ORCA-6.1.1-macOS-arm64/optfreq/job.out",
        "water-raman.out": logs / "raman/water.out",
        "water-nmr.out": logs / "nmr/water-shield.out",
        "peroxide-uv-cd.out": logs / "tdcd/peroxide.out",
        "hydroxyl-populations.out": examples / "populations/hydroxyl.out",
    }
    for name in ("water.gjf", "ethanol-2d.mol", "crystal.cif"):
        files[f"Structure-import/{name}"] = examples / "structure_import" / name
    for molecule in ("water", "OH"):
        for suffix in (".inp", ".molden.input"):
            name = molecule + suffix
            files[f"Orbitals/{name}"] = examples / "orbitals" / name
    native = examples / "native_methods"
    for source in sorted(native.rglob("*")):
        if source.suffix in (".inp", ".xyz") and source.is_file():
            files[f"ORCA-inputs/{source.relative_to(native).as_posix()}"] = source

    for name, source in files.items():
        check_release_text(name, name)
        check_release_text(source.read_text(encoding="utf-8"), name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
