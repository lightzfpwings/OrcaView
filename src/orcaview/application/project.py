"""Atomic project snapshots, with side-by-side migration of schema 1 documents."""

from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile

from orcaview import (
    ADVANCED_PROJECT_SCHEMA_VERSION, DOCUMENT_PROJECT_SCHEMA_VERSION, LEGACY_PROJECT_SCHEMA_VERSION,
    BLOCK_PROJECT_SCHEMA_VERSION, PROJECT_SCHEMA_VERSION, __version__,
    SOLVATION_PROJECT_SCHEMA_VERSION, STATE_PROJECT_SCHEMA_VERSION,
)
from orcaview.core.methods import PATH_JOBS
from orcaview.core.provenance import ArtifactRef
from orcaview.core.snapshots import GeometryRef
from orcaview.orca.input import render_input
from ._project_format import (
    check_fields, has_advanced_settings, has_calculation_parameters, read_calculation,
    read_document, read_log_report, read_molecule, write_calculation,
)
from .session import Session


def _payload(session, target):
    spec = session.calculation
    spec.validate()
    if not isinstance(session.source_path, str):
        raise ValueError("项目来源路径必须是字符串")
    document = session.tracked_document
    if session.log_report is not None:
        version = PROJECT_SCHEMA_VERSION
    elif spec.solvation_model != "Gas" or spec.job_type in PATH_JOBS:
        version = SOLVATION_PROJECT_SCHEMA_VERSION
    elif spec.block_options:
        version = BLOCK_PROJECT_SCHEMA_VERSION
    elif has_advanced_settings(spec):
        version = ADVANCED_PROJECT_SCHEMA_VERSION
    elif has_calculation_parameters(spec):
        version = STATE_PROJECT_SCHEMA_VERSION
    elif document is not None:
        version = DOCUMENT_PROJECT_SCHEMA_VERSION
    else:
        version = LEGACY_PROJECT_SCHEMA_VERSION
    if (version != LEGACY_PROJECT_SCHEMA_VERSION and session.legacy_project_path is not None
            and target.resolve() == session.legacy_project_path):
        raise ValueError("迁移需要另存到新路径，以保留原 schema 1 项目")

    payload = {"schema_version": version, "software_version": __version__, "source_path": session.source_path,
               "calculation": write_calculation(spec, version)}
    if version == LEGACY_PROJECT_SCHEMA_VERSION:
        session.molecule.validate()
        payload["molecule"] = asdict(session.molecule)
    else:
        if document is None:
            # Reject an invalid first parameterized save before allocating document IDs.
            render_input(session.molecule, spec)
            snapshots, datasets = session.document.records()
        else:
            snapshots, datasets = document.records()
            head = next(s for s in reversed(snapshots) if s.ref.frame_id is None)
            if version >= STATE_PROJECT_SCHEMA_VERSION:
                render_input(head.molecule, spec)
            else:
                head.molecule.validate()
        payload.update(
            contract_version=GeometryRef.contract_version,
            document={"coordinate_unit": "angstrom", "snapshots": [asdict(s) for s in snapshots],
                      "datasets": [asdict(d) for d in datasets]},
        )
        if session.log_report is not None:
            if session.document.artifact(session.log_report.source.artifact_id) != session.log_report.source:
                raise ValueError("项目的日志与结构来源不一致")
            payload["log_report"] = asdict(session.log_report)
    return payload


def _write(session, path, *, replace):
    target = Path(path)
    payload = _payload(session, target)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(target.parent),
                                         prefix=".orcaview-", suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, target)
            temporary = None
        else:
            # Atomically create only if the migration destination is still unused.
            os.link(temporary, target)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def save_project(session: Session, path: Path) -> None:
    """Write the earliest schema that represents the selected method and settings."""
    _write(session, path, replace=True)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"项目包含重复字段：{key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"项目中包含非有限数值：{value}")


def load_project(path: Path) -> Session:
    """Load without following path hints, regenerating IDs or changing the source file."""
    source = Path(path).resolve()
    raw = source.read_bytes()
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if not isinstance(data, dict):
        raise ValueError("项目根节点必须是对象")
    version = data.get("schema_version")
    if type(version) is not int or version not in (
            LEGACY_PROJECT_SCHEMA_VERSION, DOCUMENT_PROJECT_SCHEMA_VERSION,
            STATE_PROJECT_SCHEMA_VERSION, ADVANCED_PROJECT_SCHEMA_VERSION, BLOCK_PROJECT_SCHEMA_VERSION,
            SOLVATION_PROJECT_SCHEMA_VERSION, PROJECT_SCHEMA_VERSION):
        raise ValueError("不支持此项目版本；需要显式迁移")
    common = {"schema_version", "software_version", "calculation", "source_path"}
    extra = {"molecule"} if version == LEGACY_PROJECT_SCHEMA_VERSION else {"contract_version", "document"}
    if version == PROJECT_SCHEMA_VERSION:
        extra.add("log_report")
    check_fields(data, common | extra, "项目")
    if not isinstance(data["software_version"], str) or not isinstance(data["source_path"], str):
        raise ValueError("软件版本和来源路径必须是字符串")
    spec = read_calculation(data["calculation"], version)
    if version == LEGACY_PROJECT_SCHEMA_VERSION:
        molecule = read_molecule(data["molecule"])
        molecule.validate()
        artifact = ArtifactRef.from_bytes(raw, "orcaview.schema1", str(source))
        return Session.from_schema1(molecule, spec, data["source_path"], artifact, data["software_version"])
    if type(data["contract_version"]) is not int or data["contract_version"] != GeometryRef.contract_version:
        raise ValueError("不支持此公共契约版本")
    document = read_document(data["document"])
    if version >= STATE_PROJECT_SCHEMA_VERSION:
        render_input(document.head.molecule, spec)
    else:
        document.head.molecule.validate()
    session = Session.from_document(document, spec, data["source_path"])
    if version == PROJECT_SCHEMA_VERSION:
        report = read_log_report(data["log_report"])
        if document.artifact(report.source.artifact_id) != report.source:
            raise ValueError("项目的日志与结构来源不一致")
        session.log_report = report
    return session


def migrate_project(source: Path, destination: Path) -> Session:
    """Promote a legacy file to schema 2, keeping both the original and any existing destination."""
    session = load_project(source)
    if session.legacy_project_path is None:
        raise ValueError("迁移来源必须是 schema 1 项目")
    _ = session.document  # Allocate IDs once before choosing the schema 2 wire format.
    _write(session, destination, replace=False)
    return session
