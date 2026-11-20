"""Lightweight metadata and result envelopes for molecular analysis."""

from dataclasses import dataclass, field
import re
from typing import Optional, Tuple

from orcaview.core._validation import Versioned, identifiers, integer, nonempty, require_tuple
from orcaview.core.provenance import ArtifactRef, Provenance, new_id
from orcaview.core.results import ResultDataset
from orcaview.core.snapshots import GeometryRef
from orcaview.core.tasks import ErrorInfo, ResourceBudget
from orcaview.core.units import LENGTH_UNITS


@dataclass(frozen=True)
class WavefunctionRef(Versioned):
    """Importer-supplied evidence, with atom IDs in source-file row order."""

    artifact: ArtifactRef
    geometry: GeometryRef
    geometry_sha256: str
    atom_ids: Tuple[str, ...]
    provenance: Provenance
    source_unit: Optional[str] = None
    basis_convention: Optional[str] = None
    has_basis: Optional[bool] = None
    has_orbitals: Optional[bool] = None
    has_occupations: Optional[bool] = None
    spin_type: Optional[str] = None
    has_ecp: Optional[bool] = None
    densities: Optional[Tuple[str, ...]] = None
    has_state_data: Optional[bool] = None
    periodic: Optional[bool] = None

    def __post_init__(self):
        if not isinstance(self.artifact, ArtifactRef) or self.artifact.sha256 is None:
            raise ValueError("波函数文件必须具有 SHA-256")
        if not isinstance(self.geometry, GeometryRef) or not isinstance(self.provenance, Provenance):
            raise ValueError("波函数必须绑定几何和来源")
        if not isinstance(self.geometry_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.geometry_sha256):
            raise ValueError("需要规范几何 SHA-256")
        identifiers(self.atom_ids, "波函数源行原子 ID")
        if not self.atom_ids:
            raise ValueError("波函数必须映射至少一个原子")
        if self.source_unit is not None and self.source_unit not in LENGTH_UNITS:
            raise ValueError("源坐标单位必须是 angstrom 或 bohr")
        for name in ("basis_convention", "spin_type"):
            if getattr(self, name) is not None:
                nonempty(getattr(self, name), name)
        for name in ("has_basis", "has_orbitals", "has_occupations", "has_ecp", "has_state_data", "periodic"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise ValueError(f"{name} 必须是布尔值或 None")
        if self.densities is not None:
            identifiers(self.densities, "已核对的密度类型")


@dataclass(frozen=True)
class AnalysisCapability(Versioned):
    """Input and output contract for a versioned feature."""

    capability_id: str
    feature_version: int
    formats: Tuple[str, ...]
    densities: Tuple[str, ...]
    required_metadata: Tuple[str, ...]
    result_kind: str
    method: str
    dtype: str
    unit: str

    def __post_init__(self):
        integer(self.feature_version, "功能版本", 1)
        for name in ("capability_id", "result_kind", "method", "dtype", "unit"):
            nonempty(getattr(self, name), name)
        for name in ("formats", "densities", "required_metadata"):
            identifiers(getattr(self, name), name)


@dataclass(frozen=True)
class AnalysisRequest(Versioned):
    capability_id: str
    wavefunction: WavefunctionRef
    density: str
    feature_version: int = 1
    parameters: Tuple[Tuple[str, str], ...] = ()
    resources: Optional[ResourceBudget] = None

    def __post_init__(self):
        nonempty(self.capability_id, "分析功能 ID")
        nonempty(self.density, "请求密度")
        integer(self.feature_version, "功能版本", 1)
        if not isinstance(self.wavefunction, WavefunctionRef):
            raise ValueError("分析请求必须引用波函数")
        if self.resources is not None and not isinstance(self.resources, ResourceBudget):
            raise ValueError("分析资源必须使用 ResourceBudget")
        require_tuple(self.parameters, "分析参数")
        for item in self.parameters:
            if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[1], str):
                raise ValueError("分析参数必须是（名称，字符串值）对")
        identifiers(tuple(key for key, _ in self.parameters), "分析参数名称")


@dataclass(frozen=True)
class AnalysisTaskRecord(Versioned):
    """Pre-engine record for a fixture or an unavailable operation."""

    request: AnalysisRequest
    status: str
    error: Optional[ErrorInfo] = None
    task_id: str = field(default_factory=new_id)

    def __post_init__(self):
        nonempty(self.task_id, "分析任务 ID")
        if not isinstance(self.request, AnalysisRequest):
            raise ValueError("分析记录缺少请求")
        if self.status == "unavailable" and isinstance(self.error, ErrorInfo):
            return
        if self.status == "synthetic-fixture" and self.error is None:
            return
        raise ValueError("分析任务状态与错误证据不符，当前仅支持不可用与合成样例记录")


@dataclass(frozen=True)
class AnalysisResult(Versioned):
    """A non-execution result envelope carrying shared M1 payloads."""

    task: AnalysisTaskRecord
    datasets: Tuple[ResultDataset, ...]

    def __post_init__(self):
        if not isinstance(self.task, AnalysisTaskRecord) or self.task.status != "synthetic-fixture":
            raise ValueError("当前分析结果只接受合成样例记录")
        require_tuple(self.datasets, "分析数据集")
        if not self.datasets or any(not isinstance(item, ResultDataset) for item in self.datasets):
            raise ValueError("分析结果必须包含公共数据集")
        identifiers(tuple(item.dataset_id for item in self.datasets), "分析数据集 ID")
        request = self.task.request
        for item in self.datasets:
            if (item.geometry != request.wavefunction.geometry or item.density != request.density
                    or "synthetic-fixture" not in item.quality
                    or request.wavefunction.artifact not in item.provenance.parents):
                raise ValueError("数据集的几何、密度、源文件或质量标记与样例请求不符")
