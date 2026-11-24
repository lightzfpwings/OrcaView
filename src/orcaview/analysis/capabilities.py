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
        raise ValueError("Capability checks require an AnalysisRequest and a GeometrySnapshot")
    versions = tuple(item for item in ANALYSIS_CAPABILITIES if item.capability_id == request.capability_id)
    if not versions:
        return CapabilityCheck(None, (ErrorInfo("unknown_capability", "This analysis capability is not registered"),))
    capability = next((item for item in versions if item.feature_version == request.feature_version), None)
    if capability is None:
        return CapabilityCheck(None, (ErrorInfo("feature_version_unsupported", "This capability version is not registered"),))

    source = request.wavefunction
    issues = []
    file_evidence = (source.artifact,)
    if (source.geometry, source.geometry_sha256) != (snapshot.ref, snapshot.content_hash):
        issues.append(ErrorInfo("geometry_mismatch", "The wavefunction reference or digest does not match the selected geometry", evidence=file_evidence))
    if set(source.atom_ids) != set(snapshot.atom_ids):
        issues.append(ErrorInfo("atom_mapping_mismatch", "Source atom rows must match the selected geometry's atom IDs in order",
                                evidence=file_evidence))
    if source.periodic is True:
        issues.append(ErrorInfo("periodic_unsupported", "Molecular analysis does not support periodic inputs", evidence=file_evidence))
    if source.artifact.format not in capability.formats:
        issues.append(ErrorInfo("input_unsupported", "Only Molden candidate inputs are registered for this capability", evidence=file_evidence))

    unknown = tuple(name for name in capability.required_metadata if getattr(source, name) is None)
    if unknown:
        issues.append(ErrorInfo("metadata_missing", "Not yet verified: " + ", ".join(unknown), evidence=file_evidence))
    absent = tuple(name for name in ("has_basis", "has_orbitals", "has_occupations")
                   if getattr(source, name) is False)
    if absent:
        issues.append(ErrorInfo("input_unsupported", "Missing required input: " + ", ".join(absent), evidence=file_evidence))
    if source.has_ecp is True:
        issues.append(ErrorInfo("input_unsupported", "ECP/EDF inputs have not been validated for this release", evidence=file_evidence))
    if source.basis_convention not in (None, "spherical", "cartesian", "mixed"):
        issues.append(ErrorInfo("input_unsupported", "This basis representation convention is not registered", evidence=file_evidence))
    if source.spin_type not in (None, "restricted", "unrestricted"):
        issues.append(ErrorInfo("input_unsupported", "This orbital spin representation is not registered", evidence=file_evidence))
    if (request.density not in capability.densities
            or (source.densities is not None and request.density not in source.densities)):
        issues.append(ErrorInfo("input_unsupported", "The requested density is unsupported or absent from the source",
                                evidence=file_evidence))
    if request.resources is not None and request.resources.processes != 1:
        issues.append(ErrorInfo("resource_unsupported", "An analysis is limited to a single worker process"))
    issues.append(ErrorInfo("internal_engine_unavailable", "This build does not include the internal numerical library and worker"))
    return CapabilityCheck(capability, tuple(issues))
