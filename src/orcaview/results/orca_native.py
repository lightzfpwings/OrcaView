"""Inspect and publish one existing ORCA output using M1 document contracts."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from orcaview.application.document import GeometryLookupError, MoleculeDocument
from orcaview.core._validation import Versioned
from orcaview.core.models import Molecule
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.core.results import DatasetAxis, ResultDataset
from orcaview.core.snapshots import GeometryRef, GeometrySnapshot
from orcaview.orca._native_output import NativeOutputEvidence, OutputIssue, parse_native_output


_PRODUCER = "orcaview.orca.native-output"
_PARSER_VERSION = "1"
_COORDINATE_UNIT = "angstrom"

DocumentRecords = Tuple[Tuple[GeometrySnapshot, ...], Tuple[ResultDataset, ...]]


@dataclass(frozen=True)
class OrcaOutputInspection(Versioned):
    source_path: Path
    artifact: Optional[ArtifactRef]
    evidence: Optional[NativeOutputEvidence]
    target: Optional[GeometryRef]
    atom_ids: Optional[Tuple[str, ...]]
    issues: Tuple[OutputIssue, ...]

    @property
    def importable(self) -> bool:
        return self.artifact is not None and self.evidence is not None and not self.issues


@dataclass(frozen=True)
class OrcaImportResult(Versioned):
    inspection: OrcaOutputInspection
    document: MoleculeDocument
    frame: GeometrySnapshot
    datasets: Tuple[ResultDataset, ...]
    base_records: Optional[DocumentRecords] = None


class OrcaImportError(ValueError):
    """Publication failed. `issues` contains stable codes and source locations."""

    def __init__(self, issues: Tuple[OutputIssue, ...]):
        self.issues = issues
        super().__init__("；".join(issue.message for issue in issues))


def _read_source(path):
    if not path.is_file():
        raise OSError("来源需要是可读取的普通文件")
    return path.read_bytes()


def _molecule(path, evidence):
    return Molecule(path.stem.strip() or "ORCA", evidence.atoms,
                    charge=evidence.charge, multiplicity=evidence.multiplicity)


def _match_revision(document, target, evidence):
    if target.frame_id is not None:
        return None, OutputIssue("target_is_frame", "请指定实际帧所属的不可变修订")
    try:
        reference = document.resolve(target)
    except GeometryLookupError:
        return None, OutputIssue("target_unavailable", "指定修订不在所给文档中")

    molecule = reference.molecule
    if (molecule.charge, molecule.multiplicity) != (evidence.charge, evidence.multiplicity):
        return None, OutputIssue("electronic_state_mismatch", "输出的电荷或多重度与指定修订不一致",
                                 evidence.charge_line)
    if tuple(a.element for a in molecule.atoms) != tuple(a.element for a in evidence.atoms):
        return None, OutputIssue("atom_order_mismatch", "输出的原子数或元素顺序与指定修订不一致",
                                 evidence.geometry_line)
    if molecule.atoms != evidence.atoms:
        return None, OutputIssue("coordinates_mismatch", "输出的有序 Å 坐标与指定修订不完全一致",
                                 evidence.geometry_line)
    if len(set(evidence.atoms)) != len(evidence.atoms):
        return None, OutputIssue("ambiguous_atom_mapping", "同元素原子具有完全相同的坐标，无法确认对应身份",
                                 evidence.geometry_line)
    return reference.atom_ids, None


def _inspect_bytes(path, raw, artifact, document, target):
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        issue = OutputIssue("unsupported_encoding", "只支持 ASCII 或 UTF-8 的 ORCA 输出")
        return OrcaOutputInspection(path, artifact, None, target, None, (issue,))

    evidence = parse_native_output(decoded)
    issues = evidence.issues
    atom_ids = None
    if evidence.importable and target is not None:
        atom_ids, conflict = _match_revision(document, target, evidence)
        if conflict is not None:
            issues += (conflict,)
    return OrcaOutputInspection(path, artifact, evidence, target, atom_ids, issues)


def inspect_orca_bytes(path, raw, *, document=None, target=None):
    """Inspect the same byte snapshot used for file-level spectroscopy and properties."""
    if (document is None) != (target is None):
        raise ValueError("关联已有文档需要同时指定文档和完整修订引用")
    artifact = ArtifactRef.from_bytes(raw, "orca-out", str(path))
    return _inspect_bytes(path, raw, artifact, document, target)


def inspect_orca_output(path: Path, *, document: Optional[MoleculeDocument] = None,
                        target: Optional[GeometryRef] = None) -> OrcaOutputInspection:
    """Inspect one chosen file and optionally verify one explicitly chosen revision."""
    if (document is None) != (target is None):
        raise ValueError("关联已有文档需要同时指定文档和完整修订引用")
    source = Path(path).absolute()
    try:
        source = source.resolve(strict=True)
        raw = _read_source(source)
    except (OSError, RuntimeError) as exc:
        issue = OutputIssue("source_unavailable", f"无法读取 ORCA 输出：{exc}")
        return OrcaOutputInspection(source, None, None, target, None, (issue,))
    return inspect_orca_bytes(source, raw, document=document, target=target)


def _provenance(report, **field_locations):
    evidence = report.evidence
    locations = dict(
        version_line=evidence.version_line,
        geometry_line=evidence.geometry_line,
        charge_line=evidence.charge_line,
        multiplicity_line=evidence.multiplicity_line,
        scf_line=evidence.scf_line,
        termination_line=evidence.termination_line,
        **field_locations,
    )
    parameters = (
        ("orca_version", evidence.program_version),
        ("task_type", "SP"),
        ("coordinate_unit", _COORDINATE_UNIT),
        ("normal_termination", "observed"),
        ("scf_convergence", "observed"),
        ("optimization_convergence", "unknown"),
    ) + tuple((key, str(value)) for key, value in locations.items() if value is not None)
    return Provenance("orca-native-import", _PRODUCER, _PARSER_VERSION, (report.artifact,), parameters)


def _publish(report, candidate):
    evidence = report.evidence
    molecule = _molecule(report.source_path, evidence)
    geometry_source = _provenance(report)
    if candidate is None:
        candidate = MoleculeDocument.from_molecule(molecule, geometry_source, _COORDINATE_UNIT)
        base = candidate.head.ref
        atom_ids = candidate.head.atom_ids
    else:
        base, atom_ids = report.target, report.atom_ids

    frame = candidate.add_frame(base, _frame_id(report), molecule, atom_ids, geometry_source, _COORDINATE_UNIT)
    energy = ResultDataset(
        "energy", frame.ref, _provenance(report, energy_line=evidence.energy_line),
        "float64", (), "hartree", (evidence.energy_hartree,), quality=("orca-final-single-point-energy",),
    )
    charge_issue = evidence.mulliken_issue
    charges = ResultDataset(
        "mulliken-charge", frame.ref,
        _provenance(report, mulliken_line=evidence.mulliken_line,
                    mulliken_issue=charge_issue.code if charge_issue is not None else None),
        "float64", (len(frame.atom_ids),), "e", evidence.mulliken_charges,
        axes=(DatasetAxis("atom", frame.atom_ids),), missing_reason=evidence.mulliken_missing_reason,
        method="Mulliken",
    )
    for dataset in (energy, charges):
        candidate.add_dataset(dataset)
    return candidate, frame, (energy, charges)


def _frame_id(report):
    return f"orca-out:{report.artifact.sha256}:1"


def commit_orca_output(inspection: OrcaOutputInspection, *,
                       document: Optional[MoleculeDocument] = None) -> OrcaImportResult:
    """Recheck inspected bytes and publish a standalone or staged document."""
    if not inspection.importable:
        raise OrcaImportError(inspection.issues)
    if (inspection.target is None) != (document is None):
        raise OrcaImportError((OutputIssue("target_unavailable", "提交时需要使用与检查一致的关联模式"),))

    source = inspection.source_path
    try:
        raw = _read_source(source)
    except OSError as exc:
        raise OrcaImportError((OutputIssue("source_unavailable", f"无法重新读取 ORCA 输出：{exc}"),)) from exc
    artifact = inspection.artifact
    actual = ArtifactRef.from_bytes(raw, "orca-out", str(source))
    if artifact.sha256 != actual.sha256:
        raise OrcaImportError((OutputIssue("source_changed", "ORCA 输出内容自检查后已改变，请重新检查"),))
    if (artifact.path_hint, artifact.format) != (actual.path_hint, actual.format):
        raise OrcaImportError((OutputIssue("source_changed", "ORCA 输出路径或格式与检查记录不一致"),))

    base_records = document.records() if document is not None else None
    try:
        candidate = MoleculeDocument.restore(*base_records) if base_records is not None else None
    except ValueError as exc:
        raise OrcaImportError((OutputIssue("publication_failed", f"无法复制关联文档：{exc}"),)) from exc
    report = _inspect_bytes(source, raw, artifact, candidate, inspection.target)
    if not report.importable:
        raise OrcaImportError(report.issues)
    if report.atom_ids != inspection.atom_ids:
        raise OrcaImportError((OutputIssue("atom_mapping_changed", "指定修订的原子身份与检查记录不一致"),))

    if base_records is not None and any(
        snapshot.ref.revision == report.target.revision and snapshot.ref.frame_id == _frame_id(report)
        for snapshot in base_records[0]
    ):
        raise OrcaImportError((OutputIssue("already_imported", "此修订已导入相同 ORCA 输出的实际帧"),))
    try:
        candidate, frame, datasets = _publish(report, candidate)
    except ValueError as exc:
        raise OrcaImportError((OutputIssue("publication_failed", f"无法发布 ORCA 输出结果：{exc}"),)) from exc
    return OrcaImportResult(report, candidate, frame, datasets, base_records)
