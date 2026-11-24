"""Strict decoders for the JSON wire format. No paths are followed while decoding."""

from dataclasses import asdict, fields

from orcaview import (ADVANCED_PROJECT_SCHEMA_VERSION, BLOCK_PROJECT_SCHEMA_VERSION, BOND_STYLE_PROJECT_SCHEMA_VERSION,
                      EMPTY_DRAFT_PROJECT_SCHEMA_VERSION, SKETCH_PROJECT_SCHEMA_VERSION, SOLVATION_PROJECT_SCHEMA_VERSION,
                      STATE_PROJECT_SCHEMA_VERSION, TOPOLOGY_PROJECT_SCHEMA_VERSION)
from orcaview.core.block_options import BlockOverride
from orcaview.core._state_methods import EARLIER_RESPONSE_FUNCTIONALS
from orcaview.core.methods import EARLIER_METHODS, PATH_JOBS
from orcaview.core.models import Atom, Bond, CalculationSpec, Molecule
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.core.results import DatasetAxis, ResultDataset
from orcaview.core.snapshots import GeometryRef, GeometrySnapshot
from .document import MoleculeDocument


def check_fields(record, names, label):
    if not isinstance(record, dict) or record.keys() != set(names):
        raise ValueError(f"{label} has missing or unknown fields")
    return record


def _fields_for(record, cls):
    return check_fields(record, (f.name for f in fields(cls)), cls.__name__)


def _array(value):
    if not isinstance(value, list):
        raise ValueError("Project array fields must be JSON arrays")
    return value


def read_molecule(record, version):
    keys = [f.name for f in fields(Molecule) if version >= TOPOLOGY_PROJECT_SCHEMA_VERSION or f.name != "bonds_explicit"]
    data = dict(check_fields(record, keys, "Molecule"))
    data["atoms"] = tuple(Atom(**_fields_for(a, Atom)) for a in _array(data["atoms"]))
    if not data["atoms"] and version < EMPTY_DRAFT_PROJECT_SCHEMA_VERSION:
        raise ValueError("A molecule requires at least one atom")
    bond_fields = ("a", "b", "order", "style") if version >= BOND_STYLE_PROJECT_SCHEMA_VERSION else ("a", "b", "order")
    data["bonds"] = tuple(Bond(**check_fields(b, bond_fields, "Bond")) for b in _array(data["bonds"]))
    return Molecule(**data)


def trim_molecule_fields(record, version):
    if version < BOND_STYLE_PROJECT_SCHEMA_VERSION:
        for bond in record["bonds"]:
            del bond["style"]
    if version < TOPOLOGY_PROJECT_SCHEMA_VERSION:
        del record["bonds_explicit"]


_BASE_CALCULATION_FIELDS = ("method", "basis", "job_type", "cores", "maxcore_mb")
_PARAMETER_FIELDS = ("active_electrons", "active_orbitals", "nroots", "reference_functional")
_ADVANCED_FIELDS = ("integral_approximation", "aux_j", "aux_jk", "aux_c", "cabs", "dispersion",
                    "integration_grid", "pno_preset", "relativity", "electron_channel", "wavefunction", "frozen_core")


def has_advanced_settings(spec):
    return (spec.method not in EARLIER_METHODS or spec.basis not in ("def2-SVP", "def2-TZVP", "def2-TZVPP")
            or (spec.reference_functional is not None and spec.reference_functional not in EARLIER_RESPONSE_FUNCTIONALS)
            or any(getattr(spec, key) != getattr(CalculationSpec, key) for key in _ADVANCED_FIELDS))


def has_calculation_parameters(spec):
    return any(getattr(spec, key) is not None for key in _PARAMETER_FIELDS)


def _calculation_fields(version):
    if version >= SOLVATION_PROJECT_SCHEMA_VERSION:
        return _BASE_CALCULATION_FIELDS + _PARAMETER_FIELDS + _ADVANCED_FIELDS + ("solvation_model", "solvent")
    if version >= ADVANCED_PROJECT_SCHEMA_VERSION:
        return _BASE_CALCULATION_FIELDS + _PARAMETER_FIELDS + _ADVANCED_FIELDS
    if version == STATE_PROJECT_SCHEMA_VERSION:
        return _BASE_CALCULATION_FIELDS + _PARAMETER_FIELDS
    return _BASE_CALCULATION_FIELDS


def write_calculation(spec, version):
    record = {key: getattr(spec, key) for key in _calculation_fields(version)}
    if version >= BLOCK_PROJECT_SCHEMA_VERSION:
        record["block_options"] = [asdict(option) for option in spec.block_options]
    return record


def read_calculation(record, version):
    keys = _calculation_fields(version)
    if version >= BLOCK_PROJECT_SCHEMA_VERSION:
        data = dict(check_fields(record, (*keys, "block_options"), "Calculation settings"))
        data["block_options"] = tuple(BlockOverride(**_fields_for(item, BlockOverride))
                                      for item in _array(data["block_options"]))
    else:
        data = check_fields(record, keys, "Calculation settings")
    spec = CalculationSpec(**data)
    spec.validate()
    if version < SOLVATION_PROJECT_SCHEMA_VERSION and spec.job_type in PATH_JOBS:
        raise ValueError("Reaction path jobs require schema 6")
    if version < ADVANCED_PROJECT_SCHEMA_VERSION and has_advanced_settings(spec):
        raise ValueError("These calculation settings require schema 4")
    if version == STATE_PROJECT_SCHEMA_VERSION and not has_calculation_parameters(spec):
        raise ValueError("Schema 3 requires calculation settings with method parameters")
    return spec


def _artifact(record):
    return ArtifactRef(**_fields_for(record, ArtifactRef))


def read_log_report(record):
    from orcaview.orca.log_report import LogProperty, LogReport, SpectrumTable
    data = _fields_for(record, LogReport)
    props = tuple(LogProperty(**_fields_for(p, LogProperty)) for p in _array(data["properties"]))
    tables = []
    for table in _array(data["spectra"]):
        fields = dict(_fields_for(table, SpectrumTable))
        fields["columns"] = tuple(_array(fields["columns"]))
        fields["rows"] = tuple(tuple(_array(row)) for row in _array(fields["rows"]))
        tables.append(SpectrumTable(**fields))
    return LogReport(_artifact(data["source"]), props, tuple(tables), data["status"])


def _provenance(record):
    data = dict(_fields_for(record, Provenance))
    data["parents"] = tuple(_artifact(a) for a in _array(data["parents"]))
    data["parameters"] = tuple(tuple(_array(p)) for p in _array(data["parameters"]))
    return Provenance(**data)


def _ref(record):
    return GeometryRef(**_fields_for(record, GeometryRef))


def _snapshot(record, version):
    keys = (f.name for f in fields(GeometrySnapshot) if version >= SKETCH_PROJECT_SCHEMA_VERSION or f.name != "sketch_xy")
    data = dict(check_fields(record, keys, "GeometrySnapshot"))
    expected_hash = data.pop("content_hash")
    data["ref"] = _ref(data["ref"])
    if data["parent"] is not None:
        data["parent"] = _ref(data["parent"])
    data["molecule"] = read_molecule(data["molecule"], version)
    data["atom_ids"] = tuple(_array(data["atom_ids"]))
    if data.get("sketch_xy") is not None:
        data["sketch_xy"] = tuple(tuple(_array(point)) for point in _array(data["sketch_xy"]))
    data["provenance"] = _provenance(data["provenance"])
    snapshot = GeometrySnapshot(**data)
    if snapshot.content_hash != expected_hash:
        raise ValueError("Geometry content hash verification failed")
    return snapshot


def _axis(record):
    data = dict(_fields_for(record, DatasetAxis))
    if data["ids"] is not None:
        data["ids"] = tuple(_array(data["ids"]))
    return DatasetAxis(**data)


def _dataset(record):
    data = dict(_fields_for(record, ResultDataset))
    data["geometry"] = _ref(data["geometry"])
    data["provenance"] = _provenance(data["provenance"])
    data["axes"] = tuple(_axis(axis) for axis in _array(data["axes"]))
    data["shape"] = tuple(_array(data["shape"]))
    data["quality"] = tuple(_array(data["quality"]))
    if data["array_ref"] is not None:
        data["array_ref"] = _artifact(data["array_ref"])
    if data["values"] is not None:
        data["values"] = tuple(_array(data["values"]))
    return ResultDataset(**data)


def read_document(record, version):
    check_fields(record, ("coordinate_unit", "snapshots", "datasets"), "Document")
    if record["coordinate_unit"] != "angstrom":
        raise ValueError("Project coordinates must be in angstroms")
    return MoleculeDocument.restore(
        tuple(_snapshot(s, version) for s in _array(record["snapshots"])),
        tuple(_dataset(d) for d in _array(record["datasets"])),
    )
