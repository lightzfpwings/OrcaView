"""Freeze and verify an ORCA input bundle without Qt or an ORCA process."""

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from orcaview.application.session import Session
from orcaview.core.models import CalculationSpec
from orcaview.orca.input import InputCompanionFile, InputSnapshot, freeze_input


def stage_example(snapshot: InputSnapshot, directory: Path) -> None:
    """Minimal consumer for a fresh directory allocated to one attempt."""
    files = [(snapshot.main_input_path, snapshot.input_bytes, snapshot.input_sha256)]
    files.extend((file.relative_path, file.content, file.sha256) for file in snapshot.companions)
    for relative_path, content, expected in files:
        path = directory / relative_path
        with path.open("xb") as stream:
            stream.write(content)
        observed = sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            raise ValueError(f"Staged input digest mismatch: {relative_path}")
        print(f"{relative_path} sha256={observed}")


def main() -> None:
    source = Path(__file__).with_name("water.xyz")
    session = Session()
    session.open_xyz(source)
    head = session.document.head
    spec = CalculationSpec(cores=1)
    inline = freeze_input(head, spec)
    external_xyz = InputCompanionFile.from_path("external_xyz", "water.xyz", source)
    external = freeze_input(head, spec, companions=(external_xyz,))

    print(f"ORCA {external.target_orca_version} target and input contract v{external.contract_version}")
    print(f"Source revision {head.ref.revision} with zero-based atom indices {list(external.atom_indices.values())}")
    print(f"Inline XYZ has {len(inline.companions)} companion files")
    print(f"External XYZ has {len(external.companions)} companion file")
    print(f"Bundle digest {external.content_digest}")
    with TemporaryDirectory(prefix="orcaview-m3-") as attempt:
        stage_example(external, Path(attempt))
    print("Verified the staged bytes without running ORCA.")


if __name__ == "__main__":
    main()
