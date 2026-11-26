"""Immutable contracts shared by modules. All coordinates are in angstroms."""

from dataclasses import dataclass
from typing import Optional, Tuple

from ._validation import finite_number, integer as _integer
from .block_options import BlockOverride, available_options, validated_block_values
from .elements import ATOMIC_NUMBERS
from .integrals import BASES, orbital_and_aux_keywords
from .methods import ALL_JOBS, METHODS, dispersion_options, frozen_core_options, pno_options, reference_options
from ._state_methods import validate_parameters
from .solvation import validate_solvation


SUPPORTED_METHODS = tuple(METHODS)
SUPPORTED_BASES = BASES
SCF_CONVERGENCE = ("SloppySCF", "LooseSCF", "NormalSCF", "MediumSCF", "StrongSCF", "TightSCF", "VeryTightSCF", "ExtremeSCF")

BOND_STYLES = {
    1: ("plain", "hydrogen_bond", "coordinate", "coordinate_arrow", "wedge", "hashed_wedge", "hollow_wedge",
        "wavy", "bold", "hashed", "wavy_wedge"),
    2: ("plain", "aromatic", "crossed", "bold", "dashed"),
    3: ("plain", "partial_triple"),
}
COORDINATE_STYLES = ("coordinate", "coordinate_arrow")
DIRECTIONAL_STYLES = (*COORDINATE_STYLES, "wedge", "hashed_wedge", "hollow_wedge", "wavy_wedge")


def validate_bond_style(order, style):
    _integer(order, "Bond order", 1)
    if order not in BOND_STYLES:
        raise ValueError("This version accepts only bond orders 1, 2 and 3")
    if style not in BOND_STYLES[order]:
        raise ValueError("The bond style does not match the selected bond order.")


@dataclass(frozen=True)
class Atom:
    """Element symbols are case-sensitive. Coordinates are in angstroms."""

    element: str
    x: float
    y: float
    z: float

    def validate(self) -> None:
        if not isinstance(self.element, str) or self.element not in ATOMIC_NUMBERS:
            raise ValueError(f"Unsupported element symbol: {self.element!r}")
        for coordinate in (self.x, self.y, self.z):
            finite_number(coordinate, "Atomic coordinates")


@dataclass(frozen=True)
class Bond:
    """Indices are zero based. For directional bonds, a is the donor or narrow end."""

    a: int
    b: int
    order: int = 1
    style: str = "plain"

    @property
    def is_covalent(self):
        """Whether the edge connects atoms in the chemical topology."""
        return self.style != "hydrogen_bond"

    @property
    def valence_order(self):
        if not self.is_covalent:
            return 0
        if self.style in ("aromatic", "partial_triple"):
            return self.order - .5
        return self.order

    def valence_at(self, endpoint):
        # A donor supplies a lone pair without consuming an extra covalent valence.
        if self.style in COORDINATE_STYLES and endpoint == self.a:
            return 0
        return self.valence_order


@dataclass(frozen=True)
class Molecule:
    name: str
    atoms: Tuple[Atom, ...]
    bonds: Tuple[Bond, ...] = ()
    charge: int = 0
    multiplicity: int = 1
    # An intentionally empty bond table must survive editing, saving and reopening.
    bonds_explicit: bool = False

    @property
    def electron_count(self) -> int:
        return sum(ATOMIC_NUMBERS[atom.element] for atom in self.atoms) - self.charge

    def validate_structure(self, *, allow_empty: bool = False) -> None:
        """Validate the topology. Only an editable draft may have no atoms."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("The molecule name must be a nonempty string")
        if not self.atoms and not allow_empty:
            raise ValueError("A molecule requires at least one atom")
        if not isinstance(self.atoms, tuple) or not isinstance(self.bonds, tuple):
            raise ValueError("atoms and bonds must be immutable tuples")
        if type(self.bonds_explicit) is not bool:
            raise ValueError("The explicit connectivity flag must be a boolean.")
        for atom in self.atoms:
            if not isinstance(atom, Atom):
                raise ValueError("atoms must contain Atom objects")
            atom.validate()
        seen = set()
        for bond in self.bonds:
            if not isinstance(bond, Bond):
                raise ValueError("bonds must contain Bond objects")
            _integer(bond.a, "Bond start", 0)
            _integer(bond.b, "Bond end", 0)
            validate_bond_style(bond.order, bond.style)
            if bond.a >= len(self.atoms) or bond.b >= len(self.atoms) or bond.a == bond.b:
                raise ValueError("A bond must connect two distinct valid atoms")
            if not bond.is_covalent and (self.atoms[bond.a].element, self.atoms[bond.b].element).count("H") != 1:
                raise ValueError("A hydrogen bond requires an explicit H and an acceptor atom.")
            key = tuple(sorted((bond.a, bond.b)))
            if key in seen:
                raise ValueError("A bond cannot be defined twice for the same atom pair")
            seen.add(key)

    def validate(self) -> None:
        self.validate_structure()
        _integer(self.charge, "Total charge")
        _integer(self.multiplicity, "Spin multiplicity", 1)
        electrons = self.electron_count
        unpaired = self.multiplicity - 1
        if electrons < 0:
            raise ValueError("The total charge gives a negative electron count")
        if unpaired > electrons or (electrons - unpaired) % 2:
            raise ValueError("Electron count and spin multiplicity are incompatible. Check total charge and multiplicity.")


@dataclass(frozen=True)
class CalculationSpec:
    """ORCA 6.1 input options. The user must assess the suitability of advanced methods."""

    method: str = "B3LYP"
    basis: str = "def2-SVP"
    job_type: str = "SP"
    cores: int = 16
    maxcore_mb: int = 4096
    active_electrons: Optional[int] = None
    active_orbitals: Optional[int] = None
    nroots: Optional[int] = None
    reference_functional: Optional[str] = None
    integral_approximation: str = "Auto"
    aux_j: Optional[str] = None
    aux_jk: Optional[str] = None
    aux_c: Optional[str] = None
    cabs: Optional[str] = None
    pno_preset: str = "Auto"
    integration_grid: str = "Auto"
    relativity: str = "Auto"
    dispersion: str = "Auto"
    electron_channel: Optional[str] = None
    wavefunction: str = "Auto"
    frozen_core: str = "Auto"
    block_options: Tuple[BlockOverride, ...] = ()
    solvation_model: str = "Gas"
    solvent: Optional[str] = None
    scf_convergence: str = "Auto"
    input_comments: Tuple[str, ...] = ()

    @property
    def peak_maxcore_per_process(self) -> int:
        """Largest configured per-process MaxCore among the successive ORCA modules."""
        return max((self.maxcore_mb, *(item.value for item in self.block_options
                                      if item.key.casefold() == "maxcore")))

    def validate(self) -> None:
        if self.scf_convergence not in ("Auto", *SCF_CONVERGENCE):
            raise ValueError("Unknown SCF convergence preset")
        if not isinstance(self.input_comments, tuple) or any(
                not isinstance(note, str) or not note or "#" in note or not note.isprintable()
                for note in self.input_comments):
            raise ValueError("Input comments must be individual printable lines without a # delimiter")
        if not isinstance(self.method, str) or self.method not in METHODS:
            raise ValueError(f"Unknown computational method {self.method!r}")
        if self.job_type not in ALL_JOBS:
            raise ValueError("Unknown job type. Available: " + ", ".join(ALL_JOBS))
        if self.job_type not in METHODS[self.method].job_types:
            allowed = ", ".join(METHODS[self.method].job_types)
            raise ValueError(f"The current {self.method} template supports these job types: {allowed}")
        _integer(self.cores, "CPU core count", 1)
        _integer(self.maxcore_mb, "Memory per core in MB", 1)
        validate_parameters(self.method, self.active_electrons, self.active_orbitals,
                            self.nroots, self.reference_functional, self.electron_channel)
        orbital_and_aux_keywords(self)
        if self.pno_preset not in pno_options(self.method):
            raise ValueError(f"{self.method} does not support PNO threshold {self.pno_preset!r}")
        if self.dispersion not in dispersion_options(self.method):
            raise ValueError(f"{self.method} does not support dispersion setting {self.dispersion!r}")
        if self.wavefunction not in reference_options(self.method):
            raise ValueError(f"{self.method} does not support the selected reference wavefunction")
        if self.wavefunction in ("ROHF", "ROKS") and self.job_type != "SP":
            raise ValueError("The restricted open-shell reference template supports single-point energies only")
        if self.frozen_core not in frozen_core_options(self.method):
            raise ValueError(f"{self.method} does not support the selected frozen-core setting")
        validate_solvation(self)
        validated_block_values(self)
        if self.scf_convergence != "Auto":
            if not any((o.block, o.key) == ("scf", "Convergence") for o in available_options(self)):
                raise ValueError("The selected method does not offer an SCF convergence preset")
            if any((o.block, o.key) == ("scf", "Convergence") for o in self.block_options):
                raise ValueError("SCF convergence is already set by the method or the %scf block")
