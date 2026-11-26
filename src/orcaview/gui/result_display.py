"""Presentation of immutable scientific results and their source evidence."""

from pathlib import PurePath
import re

from orcaview.i18n import tr

from orcaview.orca.log_properties import property_series_key


# The M5 handwritten ORCA fixture carries ordinary parser provenance. Match the
# artifact bytes pinned in examples/m5_orca/manifest.json, even after a rename.
_M5_FIXTURE_SHA256 = "b6df1c4779938d9d33c35d593c364e84ca1da2d2f94d93e912557840d3690e66"


def log_filename(report):
    return PurePath((report.source.path_hint or "").replace("\\", "/")).name or report.source.format


def report_text(source):
    """Localize parser-generated labels without changing a saved report or its grouping keys."""
    translated = tr(source)
    if translated != source:
        return translated
    if " · " in source:
        return " · ".join(report_text(part) for part in source.split(" · "))
    for pattern, template in (("Job (\\d+)", "Job {value}"), ("Line (\\d+)", "Line {value}"),
                              ("Optimization step (\\d+)", "Optimization step {value}"),
                              ("(\\S+) correlation energy", "{value} correlation energy")):
        match = re.fullmatch(pattern, source)
        if match:
            return tr(template, value=match[1])
    for prefix in ("Multiplicity", "Irreducible representation", "Root", "State", "Rotational constants", "Static polarizability", "Dipole moment"):
        if source.startswith(prefix + " "):
            return tr(prefix) + " " + source[len(prefix) + 1:]
    # Optical titles combine the spectrum name, gauge and optional moment convention.
    if source.startswith(("UV–visible absorption (", "Electronic circular dichroism (CD) (")) and source.endswith(")"):
        name, _, qualifiers = source[:-1].rpartition(" (")
        detail = tr(", ").join(tr(part) for part in qualifiers.split(", "))
        return tr("{label} ({suffix})", label=tr(name), suffix=detail)
    return source


def log_overview_status(report):
    if report.source.sha256 == _M5_FIXTURE_SHA256:
        return report_text(report.status) + "\n" + tr("Source type  ") + tr("Synthetic example")
    return report_text(report.status)


def _file_suffix(name):
    return next((end for end in (".oview.json", ".molden.input") if name.lower().endswith(end)),
                PurePath(name).suffix)


def display_file_name(path, fallback):
    if not path:
        return fallback
    name = PurePath(str(path).replace("\\", "/")).name
    suffix = _file_suffix(name)
    return name[:-len(suffix)] if suffix else name


def _file_type(path, file_format):
    name = (path or "").replace("\\", "/").lower()
    suffix = _file_suffix(name)
    if file_format in ("orca-out", "orca-output"):
        label = "ORCA log file" if suffix == ".log" else "ORCA output file"
    else:
        labels = {
            "xyz": "XYZ coordinate file", "mol": "MDL MOL structure file", "sdf": "SDF structure file",
            "mol2": "Tripos MOL2 structure file", "pdb": "PDB structure file", "smi": "SMILES notation",
            "inchi": "InChI identifier", "cdxml": "ChemDraw structure file", "cml": "CML structure file",
            "cif": "CIF crystal structure file", "poscar": "VASP structure file",
            "gaussian-input": "Gaussian input file", "orca-input": "ORCA input file",
            "qchem-input": "Q-Chem input file", "nwchem-input": "NWChem input file",
            "molden": "Molden wavefunction file", "gaussian-fchk": "Gaussian formatted checkpoint file",
            "wfn": "WFN wavefunction file", "wfx": "WFX wavefunction file", "mwfn": "MWFN wavefunction file",
            "orca-gbw": "ORCA GBW wavefunction file", "orcaview-project": "OrcaView project file",
            "orcaview.schema1": "OrcaView project file", "orcaview.synthetic-json": "JSON sample file",
        }
        label = labels.get(file_format, file_format)
        if file_format == "unknown":
            label = {".xyz": "XYZ coordinate file", ".oview.json": "OrcaView project file"}.get(
                suffix, tr("{format} file", format=suffix[1:].upper()) if suffix else "Unknown")
    return tr("{label} ({suffix})", label=tr(label), suffix=suffix) if suffix else tr(label)


def source_file_details(artifacts, *, input_path="", project_path=""):
    """Describe recorded files without opening paths or inventing missing addresses."""
    files = [(item.path_hint, item.format) for item in artifacts]
    if not files and input_path:
        files = [(input_path, "unknown")]
    if not files and project_path:
        files = [(project_path, "orcaview-project")]
    if not files:
        return tr("File path  {path}\nFile type  {type}", path=tr("None"), type=tr("None"))
    return "\n\n".join(tr("File path  {path}\nFile type  {type}", path=path or tr("Not recorded"), type=_file_type(path, fmt))
                        for path, fmt in dict.fromkeys(files))


def log_property_series(report):
    groups = {}
    for prop in report.properties:
        groups.setdefault(property_series_key(prop), []).append(prop)
    return tuple(tuple(sorted(values, key=lambda p: p.line, reverse=True)) for values in groups.values())


def log_reference_snapshot(snapshots, source):
    """Prefer a printed frame over the project's initially imported revision."""
    revision = None
    for snapshot in reversed(snapshots):
        origin = snapshot.provenance
        if origin.kind not in ("orca-native-import", "orca-log-geometry"):
            continue
        if not any(p.format == source.format and p.sha256 == source.sha256 for p in origin.parents):
            continue
        if snapshot.ref.frame_id is not None:
            return snapshot
        revision = snapshot
    return revision


def matched_energy_lines(datasets, source):
    """Only merge a geometry-bound energy with the exact line in the same artifact."""
    matches = {}
    for data in datasets:
        if ("orca-final-single-point-energy" not in data.quality or not source.sha256
                or not any(parent.sha256 == source.sha256 for parent in data.provenance.parents)):
            continue
        line = dict(data.provenance.parameters).get("energy_line", "")
        if line.isdecimal():
            matches[int(line)] = data
    return matches


POPULATION_NAMES = {
    "mulliken-electrons": "Mulliken electron population", "mulliken-charge": "Mulliken charge",
    "mulliken-spin": "Mulliken spin population",
    "loewdin-electrons": "Löwdin electron population", "loewdin-charge": "Löwdin charge",
    "loewdin-spin": "Löwdin spin population",
    "hirshfeld-electrons": "Hirshfeld electron population", "hirshfeld-charge": "Hirshfeld charge",
    "hirshfeld-spin": "Hirshfeld spin population",
    "mbis-electrons": "MBIS electron population", "mbis-charge": "MBIS charge", "mbis-spin": "MBIS spin population",
    "chelpg-charge": "CHELPG charge", "atomic_charge": "Atomic charge",
}


def dataset_name(data):
    if data.kind == "energy" and "orca-final-single-point-energy" in data.quality:
        return tr("Single-point energy")
    if data.kind == "energy":
        return tr("Energy")
    return tr(POPULATION_NAMES[data.kind]) if data.kind in POPULATION_NAMES else data.method or data.kind


def result_summary(data):
    name = dataset_name(data)
    if data.shape == () and data.array_ref is None:
        value = data.values[0] if data.values is not None else None
        return f"{name}    {(tr('Missing') if value is None else value)} {data.unit}"
    return f"{name}   ·   {data.unit}"


def frame_name(frame):
    if frame.startswith("orca-out:"):
        frame = tr("ORCA frame ") + frame[len("orca-out:"):][:8]
    return frame


def geometry_name(ref):
    revision = tr("Revision {revision}", revision=ref.revision)
    return revision + " / " + frame_name(ref.frame_id) if ref.frame_id is not None else revision


def _is_fixture(origin):
    return (origin.kind == "fixture" or dict(origin.parameters).get("synthetic_fixture") == "true"
            or any(parent.format == "orca-out" and parent.sha256 == _M5_FIXTURE_SHA256
                   for parent in origin.parents))


def source_label(snapshot, data):
    origin = data.provenance if data is not None else snapshot.provenance
    if _is_fixture(origin) or (data is not None and "synthetic-fixture" in data.quality):
        return tr("Synthetic example")
    if origin.kind == "orca-native-import":
        return tr("ORCA output import")
    if origin.kind == "orca-log-geometry":
        return tr("ORCA log geometry")
    labels = {"created": "Project structure", "history-restore": "Restore revision", "edit": "Edited revision"}
    return tr(labels[origin.kind]) if origin.kind in labels else origin.kind


def describe(snapshot, data):
    origin = data.provenance if data is not None else snapshot.provenance
    producer = " ".join(part for part in (origin.producer, origin.producer_version) if part)
    lines = []
    if data is not None:
        lines.append(result_summary(data))
        fields = (("Method", data.method), ("Density", data.density), ("Spin", data.spin), ("State", data.state_id))
        tags = [f"{tr(label)}  {value}" for label, value in fields if value]
        if tags:
            lines.append("    ·    ".join(tags))
        if data.quality:
            lines.append(tr("Quality flags  ") + ", ".join(data.quality))
        if data.missing_reason:
            lines.append(tr("Reason for missing value  ") + data.missing_reason)
        if data.array_ref is not None:
            lines.append(tr("External array not loaded"))
        if data.shape and (len(data.shape) != 1 or data.axes[0].kind != "atom"):
            lines.append(tr("Only metadata are shown for this axis type"))
    else:
        molecule = snapshot.molecule
        lines.extend((molecule.name, tr("Charge  {charge}    ·    Multiplicity  {multiplicity}", charge=molecule.charge, multiplicity=molecule.multiplicity),
                      tr("Source coordinate unit  {unit}", unit=snapshot.source_unit)))
    lines.append(tr("Source type  ") + source_label(snapshot, data))
    parameters = dict(origin.parameters)
    if parameters.get("population_formula") == "ZA - q" and parameters.get("nuclear_charge_line"):
        lines.append(tr("Electron population = printed nuclear charge ZA − atomic charge. ZA is on line {line}.",
                        line=parameters["nuclear_charge_line"]))
    elif parameters.get("population_column"):
        lines.append(tr("Printed column  {column}", column=parameters["population_column"]))
    population_line = parameters.get("population_line") or parameters.get("mulliken_line")
    if population_line:
        lines.append(tr("Source line  ") + population_line)
    if "orca_version" in parameters:
        lines.append("ORCA " + parameters["orca_version"])
    if origin.parents:
        filenames = [PurePath(parent.path_hint.replace("\\", "/")).name if parent.path_hint else parent.format
                     for parent in origin.parents]
        lines.append(tr("Source file  ") + ", ".join(filenames))
    if producer:
        lines.append(tr("Record source  ") + producer)

    return "\n".join(lines)
