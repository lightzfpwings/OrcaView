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
    for pattern, template in ((r"作业 (\d+)", "作业 {value}"), (r"第 (\d+) 行", "第 {value} 行"),
                              (r"优化第 (\d+) 步", "优化第 {value} 步"),
                              (r"(\S+) 相关能", "{value} 相关能")):
        match = re.fullmatch(pattern, source)
        if match:
            return tr(template, value=match[1])
    for prefix in ("多重度", "不可约表示", "根", "态", "转动常数", "静态极化率", "偶极矩"):
        if source.startswith(prefix + " "):
            return tr(prefix) + " " + source[len(prefix) + 1:]
    # Optical titles combine the spectrum name, gauge and optional moment convention.
    if source.startswith(("紫外–可见吸收（", "电子圆二色谱 CD（")) and source.endswith("）"):
        name, _, qualifiers = source[:-1].partition("（")
        detail = tr("，").join(tr(part) for part in qualifiers.split("，"))
        return tr("{label}（{suffix}）", label=tr(name), suffix=detail)
    return source


def log_overview_status(report):
    if report.source.sha256 == _M5_FIXTURE_SHA256:
        return report_text(report.status) + "\n" + tr("来源类型  ") + tr("合成样例")
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
        label = "ORCA 日志文件" if suffix == ".log" else "ORCA 输出文件"
    else:
        labels = {
            "xyz": "XYZ 坐标文件", "mol": "MDL MOL 结构文件", "sdf": "SDF 结构文件",
            "mol2": "Tripos MOL2 结构文件", "pdb": "PDB 结构文件", "smi": "SMILES 分子表示",
            "inchi": "InChI 分子标识", "cdxml": "ChemDraw 结构文件", "cml": "CML 结构文件",
            "cif": "CIF 晶体结构文件", "poscar": "VASP 结构文件",
            "gaussian-input": "Gaussian 输入文件", "orca-input": "ORCA 输入文件",
            "qchem-input": "Q-Chem 输入文件", "nwchem-input": "NWChem 输入文件",
            "molden": "Molden 波函数文件", "gaussian-fchk": "Gaussian 格式化检查点文件",
            "wfn": "WFN 波函数文件", "wfx": "WFX 波函数文件", "mwfn": "MWFN 波函数文件",
            "orca-gbw": "ORCA GBW 波函数文件", "orcaview-project": "OrcaView 项目文件",
            "orcaview.schema1": "OrcaView 项目文件", "orcaview.synthetic-json": "JSON 样例文件",
        }
        label = labels.get(file_format, file_format)
        if file_format == "unknown":
            label = {".xyz": "XYZ 坐标文件", ".oview.json": "OrcaView 项目文件"}.get(
                suffix, tr("{format} 文件", format=suffix[1:].upper()) if suffix else "未知")
    return tr("{label}（{suffix}）", label=tr(label), suffix=suffix) if suffix else tr(label)


def source_file_details(artifacts, *, input_path="", project_path=""):
    """Describe recorded files without opening paths or inventing missing addresses."""
    files = [(item.path_hint, item.format) for item in artifacts]
    if not files and input_path:
        files = [(input_path, "unknown")]
    if not files and project_path:
        files = [(project_path, "orcaview-project")]
    if not files:
        return tr("文件地址  {path}\n文件类型  {type}", path=tr("无"), type=tr("无"))
    return "\n\n".join(tr("文件地址  {path}\n文件类型  {type}", path=path or tr("未记录"), type=_file_type(path, fmt))
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


def dataset_name(data):
    if data.kind == "energy" and "orca-final-single-point-energy" in data.quality:
        return tr("单点能")
    names = {
        "energy": "能量",
        "mulliken-charge": "Mulliken 电荷",
        "mulliken-spin": "Mulliken 自旋布居",
        "loewdin-charge": "Löwdin 电荷",
        "loewdin-spin": "Löwdin 自旋布居",
        "hirshfeld-charge": "Hirshfeld 电荷",
        "hirshfeld-spin": "Hirshfeld 自旋布居",
        "atomic_charge": "原子电荷",
    }
    return tr(names[data.kind]) if data.kind in names else data.method or data.kind


def result_summary(data):
    name = dataset_name(data)
    if data.shape == () and data.array_ref is None:
        value = data.values[0] if data.values is not None else None
        return f"{name}    {tr('缺失') if value is None else value} {data.unit}"
    return f"{name}   ·   {data.unit}"


def frame_name(frame):
    if frame.startswith("orca-out:"):
        frame = tr("ORCA 帧 ") + frame[len("orca-out:"):][:8]
    return frame


def geometry_name(ref):
    revision = tr("修订 {revision}", revision=ref.revision)
    return revision + " / " + frame_name(ref.frame_id) if ref.frame_id is not None else revision


def _is_fixture(origin):
    return (origin.kind == "fixture" or dict(origin.parameters).get("synthetic_fixture") == "true"
            or any(parent.format == "orca-out" and parent.sha256 == _M5_FIXTURE_SHA256
                   for parent in origin.parents))


def source_label(snapshot, data):
    origin = data.provenance if data is not None else snapshot.provenance
    if _is_fixture(origin) or (data is not None and "synthetic-fixture" in data.quality):
        return tr("合成样例")
    if origin.kind == "orca-native-import":
        return tr("ORCA 输出导入")
    if origin.kind == "orca-log-geometry":
        return tr("ORCA 日志结构")
    labels = {"created": "项目结构", "history-restore": "恢复修订", "edit": "编辑修订"}
    return tr(labels[origin.kind]) if origin.kind in labels else origin.kind


def describe(snapshot, data):
    origin = data.provenance if data is not None else snapshot.provenance
    producer = " ".join(part for part in (origin.producer, origin.producer_version) if part)
    lines = []
    if data is not None:
        lines.append(result_summary(data))
        fields = (("方法", data.method), ("密度", data.density), ("自旋", data.spin), ("态", data.state_id))
        tags = [f"{tr(label)}  {value}" for label, value in fields if value]
        if tags:
            lines.append("    ·    ".join(tags))
        if data.quality:
            lines.append(tr("质量标记  ") + "，".join(data.quality))
        if data.missing_reason:
            lines.append(tr("缺失原因  ") + data.missing_reason)
        if data.array_ref is not None:
            lines.append(tr("外部数组尚未加载"))
        if data.shape and (len(data.shape) != 1 or data.axes[0].kind != "atom"):
            lines.append(tr("此轴类型仅展示元数据"))
    else:
        molecule = snapshot.molecule
        lines.extend((molecule.name, tr("电荷  {charge}    ·    多重度  {multiplicity}", charge=molecule.charge, multiplicity=molecule.multiplicity),
                      tr("源坐标单位  {unit}", unit=snapshot.source_unit)))
    lines.append(tr("来源类型  ") + source_label(snapshot, data))
    parameters = dict(origin.parameters)
    population_line = parameters.get("population_line") or parameters.get("mulliken_line")
    if population_line:
        lines.append(tr("来源行  ") + population_line)
    if "orca_version" in parameters:
        lines.append("ORCA " + parameters["orca_version"])
    if origin.parents:
        filenames = [PurePath(parent.path_hint.replace("\\", "/")).name if parent.path_hint else parent.format
                     for parent in origin.parents]
        lines.append(tr("来源文件  ") + "，".join(filenames))
    if producer:
        lines.append(tr("记录来源  ") + producer)

    return "\n".join(lines)
