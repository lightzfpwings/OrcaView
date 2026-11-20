"""Adapt explicitly synthetic data to the shared analysis result payload."""

from typing import Optional, Tuple

from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.core.results import DatasetAxis, Number, ResultDataset
from orcaview.core.snapshots import GeometrySnapshot

from .capabilities import HIRSHFELD_CHARGE, check_capability
from .contracts import AnalysisRequest, AnalysisResult, AnalysisTaskRecord


def adapt_hirshfeld_fixture(request: AnalysisRequest, snapshot: GeometrySnapshot, fixture: ArtifactRef,
                            values: Optional[Tuple[Optional[Number], ...]], *,
                            missing_reason: Optional[str] = None) -> AnalysisResult:
    """Wrap caller-supplied synthetic values in wavefunction source order. No I/O."""
    checked = check_capability(request, snapshot)
    problems = tuple(issue for issue in checked.issues if issue.code != "internal_engine_unavailable")
    if problems:
        raise ValueError("。".join(f"{issue.reason} ({issue.code})" for issue in problems))
    if checked.capability != HIRSHFELD_CHARGE:
        raise ValueError("该适配器只接受 Hirshfeld 电荷能力")
    if not isinstance(fixture, ArtifactRef) or fixture.format != "orcaview.synthetic-json" or fixture.sha256 is None:
        raise ValueError("合成分析样例必须显式提供带 SHA-256 的 orcaview.synthetic-json 产物")

    source = request.wavefunction
    parents = {}
    for ref in (source.artifact, fixture, *source.provenance.parents):
        existing = parents.setdefault(ref.artifact_id, ref)
        if existing != ref:
            raise ValueError("同一来源文件 ID 对应了不同产物")

    task = AnalysisTaskRecord(request, "synthetic-fixture")
    parameters = (
        ("synthetic_fixture", "true"),
        ("task_id", task.task_id),
        ("capability_id", request.capability_id),
        ("feature_version", str(request.feature_version)),
        ("wavefunction_sha256", source.artifact.sha256),
        ("geometry_sha256", source.geometry_sha256),
        ("density", request.density),
        ("source_kind", source.provenance.kind),
        ("source_unit", source.source_unit),
        ("basis_convention", source.basis_convention),
        ("spin_type", source.spin_type),
    )
    parameters += tuple((key, value) for key, value in (
        ("source_producer", source.provenance.producer),
        ("source_producer_version", source.provenance.producer_version),
    ) if value is not None)
    parameters += tuple((f"request.{key}", value) for key, value in request.parameters)
    parameters += tuple((f"source.{key}", value) for key, value in source.provenance.parameters)
    provenance = Provenance("analysis-fixture", "orcaview.analysis.hirshfeld-fixture", "1",
                            tuple(parents.values()), parameters)
    dataset = ResultDataset(
        kind=HIRSHFELD_CHARGE.result_kind,
        geometry=snapshot.ref,
        provenance=provenance,
        dtype=HIRSHFELD_CHARGE.dtype,
        shape=(len(source.atom_ids),),
        unit=HIRSHFELD_CHARGE.unit,
        values=values,
        axes=(DatasetAxis("atom", source.atom_ids),),
        missing_reason=missing_reason,
        method=HIRSHFELD_CHARGE.method,
        density=request.density,
        quality=("synthetic-fixture",),
        data_version=1,
    )
    return AnalysisResult(task, (dataset,))
