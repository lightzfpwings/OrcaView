"""Private attempt journal and read-only recovery of execution evidence."""

from dataclasses import asdict
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Tuple

from ._workspace import ATTEMPT_METADATA, INPUT_MANIFEST
from .records import AttemptRecord, TERMINAL_STATES


JOURNAL = "execution.json"
OUTPUT_LOG = "orca-output.log"


def _evidence_matches_state(report: dict) -> bool:
    if report["state"] != "succeeded":
        return True
    output = report.get("output")
    return (
        type(report.get("exit_code")) is int
        and report["exit_code"] == 0
        and report.get("normal_termination") is True
        and isinstance(output, dict)
        and isinstance(output.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", output["sha256"]) is not None
    )


def write_journal(record: AttemptRecord) -> None:
    metadata = record.directory / ATTEMPT_METADATA
    payload = asdict(record)
    payload.update({
        "schema_version": 1,
        "directory": str(record.directory),
        "executable": None if record.executable is None else str(record.executable),
    })
    for key in ("created_at", "started_at", "finished_at"):
        value = getattr(record, key)
        payload[key] = None if value is None else value.isoformat()

    temp = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=metadata, prefix=".execution-", delete=False
        ) as stream:
            temp = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, metadata / JOURNAL)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def recover_attempts(root: Path) -> Tuple[dict, ...]:
    if not root.is_dir():
        return ()
    reports = []
    for directory in sorted(root.iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            continue
        metadata = directory / ATTEMPT_METADATA
        if metadata.is_symlink() or not metadata.is_dir():
            continue
        journal = metadata / JOURNAL
        manifest = metadata / INPUT_MANIFEST
        if not journal.exists() and not journal.is_symlink() and not manifest.is_file():
            continue
        try:
            if journal.is_symlink() or not journal.is_file():
                raise ValueError("Missing regular attempt journal")
            with journal.open(encoding="utf-8") as stream:
                report = json.load(stream)
            if (not isinstance(report, dict) or report.get("schema_version") != 1
                    or report.get("attempt_id") != directory.name
                    or not isinstance(report.get("state"), str)):
                raise ValueError("Invalid attempt journal")
        except (OSError, ValueError):
            report = {"attempt_id": directory.name, "job_id": None,
                      "exit_code": None, "state": None}

        recorded = report["state"]
        report["recorded_state"] = recorded
        report["directory"] = str(directory)
        if recorded not in TERMINAL_STATES or not _evidence_matches_state(report):
            report["state"] = "needs_review"
        reports.append(report)
    return tuple(reports)
