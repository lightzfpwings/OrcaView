"""Describe and check planned features without loading any analysis backend."""

from dataclasses import dataclass
from typing import Optional, Tuple

from orcaview.core.snapshots import GeometrySnapshot
from orcaview.core.tasks import ErrorInfo

from .contracts import AnalysisCapability, AnalysisRequest


HIRSHFELD_CHARGE = AnalysisCapability(
    capability_id="hirshfeld-charge",
    feature_version=1,
    formats=("molden",),
    densities=("total",),
    required_metadata=("source_unit", "basis_convention", "has_basis", "has_orbitals",
                       "has_occupations", "spin_type", "has_ecp", "densities", "periodic"),
    result_kind="hirshfeld-charge",
    method="Hirshfeld",
    dtype="float64",
    unit="e",
)
ANALYSIS_CAPABILITIES = (HIRSHFELD_CHARGE,)


@dataclass(frozen=True)
class CapabilityCheck:
    capability: Optional[AnalysisCapability]
    issues: Tuple[ErrorInfo, ...]

    @property
    def available(self) -> bool:
        return self.capability is not None and not self.issues


def check_capability(request: AnalysisRequest, snapshot: GeometrySnapshot) -> CapabilityCheck:
    """Check the producer's declared metadata against a historical or current snapshot."""
    if not isinstance(request, AnalysisRequest) or not isinstance(snapshot, GeometrySnapshot):
        raise ValueError("能力检查需要 AnalysisRequest 和 GeometrySnapshot")
    versions = tuple(item for item in ANALYSIS_CAPABILITIES if item.capability_id == request.capability_id)
    if not versions:
        return CapabilityCheck(None, (ErrorInfo("unknown_capability", "未登记此分析功能"),))
    capability = next((item for item in versions if item.feature_version == request.feature_version), None)
    if capability is None:
        return CapabilityCheck(None, (ErrorInfo("feature_version_unsupported", "未登记此功能版本"),))

    source = request.wavefunction
    issues = []
    file_evidence = (source.artifact,)
    if (source.geometry, source.geometry_sha256) != (snapshot.ref, snapshot.content_hash):
        issues.append(ErrorInfo("geometry_mismatch", "波函数与选定几何的完整引用或摘要不符", evidence=file_evidence))
    if set(source.atom_ids) != set(snapshot.atom_ids):
        issues.append(ErrorInfo("atom_mapping_mismatch", "源文件原子行必须逐一对应选定几何的原子 ID",
                                evidence=file_evidence))
    if source.periodic is True:
        issues.append(ErrorInfo("periodic_unsupported", "分子分析不支持周期输入", evidence=file_evidence))
    if source.artifact.format not in capability.formats:
        issues.append(ErrorInfo("input_unsupported", "此功能仅登记 Molden 候选输入", evidence=file_evidence))

    unknown = tuple(name for name in capability.required_metadata if getattr(source, name) is None)
    if unknown:
        issues.append(ErrorInfo("metadata_missing", "尚未核对 " + ", ".join(unknown), evidence=file_evidence))
    absent = tuple(name for name in ("has_basis", "has_orbitals", "has_occupations")
                   if getattr(source, name) is False)
    if absent:
        issues.append(ErrorInfo("input_unsupported", "缺少所需输入 " + ", ".join(absent), evidence=file_evidence))
    if source.has_ecp is True:
        issues.append(ErrorInfo("input_unsupported", "本交付范围尚未核验 ECP/EDF 输入", evidence=file_evidence))
    if source.basis_convention not in (None, "spherical", "cartesian", "mixed"):
        issues.append(ErrorInfo("input_unsupported", "未登记该基组表示约定", evidence=file_evidence))
    if source.spin_type not in (None, "restricted", "unrestricted"):
        issues.append(ErrorInfo("input_unsupported", "未登记该轨道自旋表示", evidence=file_evidence))
    if (request.density not in capability.densities
            or (source.densities is not None and request.density not in source.densities)):
        issues.append(ErrorInfo("input_unsupported", "请求的密度超出功能范围，或源文件缺少该密度",
                                evidence=file_evidence))
    if request.resources is not None and request.resources.processes != 1:
        issues.append(ErrorInfo("resource_unsupported", "单次分析只接受一个 worker 进程的预算"))
    issues.append(ErrorInfo("internal_engine_unavailable", "当前构建未提供内部数值库与 worker"))
    return CapabilityCheck(capability, tuple(issues))
