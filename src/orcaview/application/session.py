"""Single-document session with independent scientific data and view state."""

from dataclasses import InitVar, dataclass, replace
from pathlib import Path
from typing import Optional

from orcaview import __version__
from orcaview.application.document import MoleculeDocument, StaleRevisionError
from orcaview.core.models import CalculationSpec, Molecule
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.io.xyz import parse_xyz, parse_xyz_record
from orcaview.orca.input import render_input


DEMO_XYZ = """3
Water | geometry demonstration only
O  0.000000  0.000000  0.000000
H  0.758602  0.000000  0.586541
H -0.758602  0.000000  0.586541
"""


@dataclass(init=False)
class Session:
    """Legacy molecule access and an opt-in, identity-preserving document."""

    molecule: Molecule
    calculation: CalculationSpec
    source_path: str
    # Preserve the three-field dataclass projection. replace() carries a branch of the history.
    tracked_document: InitVar[Optional[MoleculeDocument]]
    _origin: InitVar[Optional[Provenance]] = None
    legacy_project_path: InitVar[Optional[Path]] = None
    log_report: InitVar[object] = None

    def __init__(self, molecule: Optional[Molecule] = None, calculation: Optional[CalculationSpec] = None,
                 source_path: str = "", *, tracked_document: Optional[MoleculeDocument] = None,
                 _origin: Optional[Provenance] = None, legacy_project_path: Optional[Path] = None, log_report=None):
        if not isinstance(source_path, str):
            raise ValueError("The source path must be a string")
        self.calculation = calculation if calculation is not None else CalculationSpec()
        self.source_path = source_path
        self._document: Optional[MoleculeDocument] = None
        self._origin = _origin
        self.legacy_project_path = legacy_project_path
        self.log_report = log_report
        if tracked_document is None:
            self._molecule = molecule if molecule is not None else parse_xyz(DEMO_XYZ, name="Water")
        else:
            self._document = MoleculeDocument.restore(*tracked_document.records())
            self._molecule = self._document.head.molecule
            if molecule is not None:
                self.molecule = molecule

    @property
    def tracked_document(self) -> Optional[MoleculeDocument]:
        return self._document

    @property
    def document(self) -> MoleculeDocument:
        if self._document is None:
            origin = self._origin
            if origin is None and self.source_path.strip():
                origin = Provenance("unverified-source", parents=(ArtifactRef("unknown", self.source_path),))
            self._document = MoleculeDocument.from_molecule(self._molecule, origin)
        return self._document

    @property
    def molecule(self) -> Molecule:
        return self._molecule if self._document is None else self._document.head.molecule

    @molecule.setter
    def molecule(self, value: Molecule) -> None:
        if self._document is None:
            if self._origin is not None and value != self._molecule:
                self._origin = replace(self._origin, kind="legacy-edit")
            self._molecule = value
            return
        base = self._document.head
        if value == base.molecule:
            return
        # Bare replacement has no atom map. Only unchanged rows can retain the old ordering.
        ids = base.atom_ids if value.atoms == base.molecule.atoms else (None,) * len(value.atoms)
        self._document.publish_revision(base.ref, value, ids, Provenance("legacy-replacement"))

    @classmethod
    def from_document(cls, document: MoleculeDocument, calculation: CalculationSpec, source_path: str):
        session = cls(document.head.molecule, calculation, source_path)
        session._document = document
        return session

    @classmethod
    def from_schema1(cls, molecule: Molecule, calculation: CalculationSpec, source_path: str,
                     project: ArtifactRef, software_version: str):
        session = cls(molecule, calculation, source_path)
        session.legacy_project_path = Path(project.path_hint)
        parents = (project, ArtifactRef("unknown", source_path)) if source_path.strip() else (project,)
        session._origin = Provenance("schema1-import", "orcaview.project", __version__, parents,
                                     (("source_software_version", software_version),))
        return session

    def open_xyz(self, path: Path) -> None:
        path = Path(path)
        source = path.resolve()
        raw = source.read_bytes()
        record = parse_xyz_record(raw.decode("utf-8"), name=path.stem)
        artifact = ArtifactRef.from_bytes(raw, "xyz", str(source))
        origin = Provenance("import", "orcaview.io.xyz", __version__, (artifact,),
                            (("unit_source", record.unit_source),))
        document = MoleculeDocument.from_molecule(record.molecule, origin, source_unit=record.source_unit)
        self._document = document
        self._molecule = record.molecule
        self._origin = None
        self.legacy_project_path = None
        self.log_report = None
        self.source_path = str(source)

    def apply_settings(self, calculation: CalculationSpec, charge: int, multiplicity: int) -> str:
        """Validate a preview before committing settings to the same document."""
        document = self._document
        base = document.head if document is not None else None
        previous = self._molecule if base is None else base.molecule
        molecule = replace(previous, charge=charge, multiplicity=multiplicity)
        text = render_input(molecule, calculation)
        if base is None:
            self.molecule = molecule
        elif molecule != previous:
            document.publish_revision(base.ref, molecule, base.atom_ids, Provenance("electronic-state"))
        elif document.head.ref != base.ref:
            raise StaleRevisionError("The geometry changed during the preview")
        self.calculation = calculation
        return text

    def input_text(self, charge: int = None, multiplicity: int = None) -> str:
        base = self.molecule
        molecule = replace(
            base,
            charge=base.charge if charge is None else charge,
            multiplicity=base.multiplicity if multiplicity is None else multiplicity,
        )
        return render_input(molecule, self.calculation)

    def apply_input_preview(self, text, *, expected=None):
        """Commit a validated text edit to the same geometry history as the inspector."""
        from orcaview.orca.preview import parse_preview

        document = self.tracked_document
        base = document.head if document is not None else None
        if expected is not None and (base is None or expected != base.ref):
            raise StaleRevisionError("Geometry changed while the input preview was being edited")
        original = self.molecule if base is None else base.molecule
        molecule, mapping, calculation, normalized = parse_preview(text, original, self.calculation)
        if molecule != original:
            if document is None:
                document = self.document
                base = document.head
            ids = tuple(base.atom_ids[i] if i is not None else None for i in mapping)
            document.publish_revision(base.ref, molecule, ids, Provenance("input-preview-edit"))
        elif base is not None and document.head.ref != base.ref:
            raise StaleRevisionError("Geometry changed while the input preview was being edited")
        self.calculation = calculation
        return normalized

