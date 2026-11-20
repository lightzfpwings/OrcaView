"""Backend-independent analysis contracts and capability inspection."""

from .capabilities import ANALYSIS_CAPABILITIES, HIRSHFELD_CHARGE, CapabilityCheck, check_capability
from .contracts import AnalysisCapability, AnalysisRequest, AnalysisResult, AnalysisTaskRecord, WavefunctionRef
from .service import adapt_hirshfeld_fixture

__all__ = [
    "ANALYSIS_CAPABILITIES",
    "HIRSHFELD_CHARGE",
    "AnalysisCapability",
    "AnalysisRequest",
    "AnalysisResult",
    "AnalysisTaskRecord",
    "CapabilityCheck",
    "WavefunctionRef",
    "adapt_hirshfeld_fixture",
    "check_capability",
]
