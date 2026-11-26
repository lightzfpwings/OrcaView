"""Geometry and source information returned by desktop structure readers."""

from dataclasses import dataclass
from typing import Optional, Tuple

from orcaview.core.models import Molecule
from orcaview.core.polymer_backbone import validate_backbone_links, validate_polymer_roles
from orcaview.core.provenance import ArtifactRef


_BACKBONE_ELEMENTS = {
    "protein": {"N": "N", "CA": "C", "C": "C"},
    "dna": {"P": "P", "O5'": "O", "C5'": "C", "C4'": "C", "C3'": "C", "O3'": "O"},
}


def polymer_atom_role(polymer, atom_name, element):
    """Identify the continuous backbone path from an archive or template atom ID."""
    name = atom_name.strip().upper().replace("*", "'").replace("′", "'")
    return "B" if _BACKBONE_ELEMENTS[polymer].get(name) == element else "S"


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
    # In molecule order: backbone, polymer side atom, or other component.
    polymer_roles: str = ""
    backbone_links: Optional[Tuple[Tuple[int, int], ...]] = None

    def __post_init__(self):
        validate_polymer_roles(self.polymer_roles, len(self.molecule.atoms))
        validate_backbone_links(self.backbone_links, self.polymer_roles)
