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
            raise ValueError("A wavefunction file must have a SHA-256 digest")
        if not isinstance(self.geometry, GeometryRef) or not isinstance(self.provenance, Provenance):
            raise ValueError("The wavefunction must reference a geometry and provenance")
        if not isinstance(self.geometry_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.geometry_sha256):
            raise ValueError("A canonical geometry SHA-256 digest is required")
        identifiers(self.atom_ids, "Wavefunction source-row atom ID")
        if not self.atom_ids:
            raise ValueError("The wavefunction must map at least one atom")
        if self.source_unit is not None and self.source_unit not in LENGTH_UNITS:
            raise ValueError("Source coordinate units must be angstrom or bohr")
        for name in ("basis_convention", "spin_type"):
            if getattr(self, name) is not None:
                nonempty(getattr(self, name), name)
        for name in ("has_basis", "has_orbitals", "has_occupations", "has_ecp", "has_state_data", "periodic"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise ValueError(f"{name} must be a boolean or None")
        if self.densities is not None:
            identifiers(self.densities, "Verified density types")


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
        integer(self.feature_version, "Capability version", 1)
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
        nonempty(self.capability_id, "Analysis capability ID")
        nonempty(self.density, "Requested density")
        integer(self.feature_version, "Capability version", 1)
        if not isinstance(self.wavefunction, WavefunctionRef):
            raise ValueError("An analysis request must reference a wavefunction")
        if self.resources is not None and not isinstance(self.resources, ResourceBudget):
            raise ValueError("Analysis resources must use ResourceBudget")
        require_tuple(self.parameters, "Analysis parameters")
        for item in self.parameters:
            if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[1], str):
                raise ValueError("Analysis parameters must be (name, string value) pairs")
        identifiers(tuple(key for key, _ in self.parameters), "Analysis parameter name")


@dataclass(frozen=True)
class AnalysisTaskRecord(Versioned):
    """Pre-engine record for a fixture or an unavailable operation."""

    request: AnalysisRequest
    status: str
    error: Optional[ErrorInfo] = None
    task_id: str = field(default_factory=new_id)

    def __post_init__(self):
        nonempty(self.task_id, "Analysis task ID")
        if not isinstance(self.request, AnalysisRequest):
            raise ValueError("The analysis record is missing its request")
        if self.status == "unavailable" and isinstance(self.error, ErrorInfo):
            return
        if self.status == "synthetic-fixture" and self.error is None:
            return
        raise ValueError("The analysis status conflicts with its error evidence. Only unavailable and synthetic records are supported")


@dataclass(frozen=True)
class AnalysisResult(Versioned):
    """A non-execution result envelope carrying shared M1 payloads."""

    task: AnalysisTaskRecord
    datasets: Tuple[ResultDataset, ...]

    def __post_init__(self):
        if not isinstance(self.task, AnalysisTaskRecord) or self.task.status != "synthetic-fixture":
            raise ValueError("Only synthetic analysis records are supported for this result")
        require_tuple(self.datasets, "Analysis datasets")
        if not self.datasets or any(not isinstance(item, ResultDataset) for item in self.datasets):
            raise ValueError("The analysis result must contain shared datasets")
        identifiers(tuple(item.dataset_id for item in self.datasets), "Analysis dataset ID")
        request = self.task.request
        for item in self.datasets:
            if (item.geometry != request.wavefunction.geometry or item.density != request.density
                    or "synthetic-fixture" not in item.quality
                    or request.wavefunction.artifact not in item.provenance.parents):
                raise ValueError("The dataset geometry, density, source file or quality flag does not match the sample request")
