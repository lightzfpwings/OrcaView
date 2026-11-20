"""Geometry and source information returned by desktop structure readers."""

from dataclasses import dataclass
from typing import Tuple

from orcaview.core.models import Molecule
from orcaview.core.provenance import ArtifactRef


class PeriodicStructureError(ValueError):
    """The input requires a decision about discarding its periodic boundary."""


@dataclass(frozen=True)
class StructureRecord:
    molecule: Molecule
    source_unit: str = "angstrom"
    unit_source: str = "format"
    generated_3d: bool = False
    removed_periodicity: bool = False
    auxiliary_sources: Tuple[ArtifactRef, ...] = ()
