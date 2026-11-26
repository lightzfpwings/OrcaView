"""Read scientific results and export spectra without an interactive desktop."""

import argparse
import csv
from dataclasses import asdict
from io import StringIO
import json
from pathlib import Path
import re

from orcaview.gui.result_display import log_property_series, source_label
from orcaview.results.nmr import coupling_pairs, default_shape, plot_source
from orcaview.results.optimization import optimization_runs
from orcaview.results.spectrum_profile import PlotProfile, PlotStyle, spectrum_csv


def register(sub):
    results = sub.add_parser("results", help="Inspect result history, geometry, datasets and source evidence")
    results.add_argument("input", type=Path, help="OrcaView project, ORCA log or structure")
    select = results.add_mutually_exclusive_group()
    select.add_argument("--geometry", metavar="SELECTOR", help="Geometry number, snapshot ID or frame ID")
    select.add_argument("--dataset", metavar="SELECTOR", help="Dataset number, ID or unique kind")
    select.add_argument("--properties", action="store_true", help="All printed calculation properties")
    select.add_argument("--property", metavar="SERIES", help="Property series number or unique label")
    select.add_argument("--optimization", action="store_true", help="Printed geometry optimization steps and energies")
    select.add_argument("--normal-modes", action="store_true", help="Vibrational frequencies, reference atoms and displacement vectors")
    select.add_argument("--evidence", action="store_true", help="Recorded sources, paths and checksums")
    select.add_argument("--all", action="store_true", help="Full JSON with all snapshots, datasets and log tables")
    results.add_argument("--format", choices=("json", "csv", "tsv"), default="json")
    results.add_argument("-o", "--output", type=Path, help="Write to a file (default: standard output)")
    results.add_argument("--finite", action="store_true", help="Use the finite structure of a periodic input")
    results.set_defaults(handler=_results)

    spectrum = sub.add_parser("spectrum", help="List spectra or export a printed table, sticks, curve or PNG")
    spectrum.add_argument("input", type=Path, help="ORCA log or OrcaView project containing a log")
    spectrum.add_argument("--table", metavar="NUMBER_OR_KIND", help="One-based table number, unique kind or title")
    spectrum.add_argument("--format", choices=("table", "sticks", "curve", "png"),
                          help="CSV table, printed sticks, sampled curve, or offscreen PNG")
    spectrum.add_argument("-o", "--output", type=Path, help="Output path (required for PNG)")
    spectrum.add_argument("--unit", choices=("nm", "eV", "cm-1", "cm⁻¹", "ppm"))
    spectrum.add_argument("--element", help="Element for an NMR plot (defaults to H when present)")
    spectrum.add_argument("--reference-ppm", type=float, help="Reference shielding for that element, for δ = σref − σ")
    spectrum.add_argument("--shape", choices=("gaussian", "lorentzian", "pseudo-voigt"),
                          help="Line shape (NMR defaults to Lorentzian, other spectra to Gaussian)")
    spectrum.add_argument("--fwhm", type=float, help="Full width at half maximum in the selected axis unit")
    spectrum.add_argument("--mix", type=float, default=.5, help="Lorentzian fraction for pseudo-Voigt (0–1)")
    spectrum.add_argument("--points", type=int, default=1201, help="Base sampling grid (2–20001)")
    spectrum.add_argument("--range", nargs=2, type=float, metavar=("LOW", "HIGH"),
                          help="Set the x-axis limits in the selected unit")
    spectrum.add_argument("--normalize", action="store_true", help="Normalize by the largest absolute curve height")
    spectrum.add_argument("--reverse", action=argparse.BooleanOptionalAction, default=None,
                          help="Reverse the plotted x-axis (default follows spectrum type)")
    spectrum.add_argument("--grid", action=argparse.BooleanOptionalAction, default=True)
    spectrum.add_argument("--layers", choices=("both", "curve", "sticks"), default="both")
    spectrum.add_argument("--color", default=PlotStyle.color, help="Curve color in #RRGGBB")
    spectrum.add_argument("--stroke-width", type=float, default=PlotStyle.stroke_width,
                          help="Curve width in logical pixels (0.5–6)")
    spectrum.set_defaults(handler=_spectrum)


def _pick(items, selector, keys, name):
    if selector is None:
        if len(items) == 1:
            return items[0]
        raise ValueError(f"Select one of the {len(items)} {name} entries by number.")
    if selector.isascii() and selector.isdecimal():
        position = int(selector)
        if 1 <= position <= len(items):
            return items[position - 1]
    matches = [item for item in items if selector in keys(item)]
    if len(matches) != 1:
        raise ValueError(f"Expected one {name} matching {selector!r}, found {len(matches)}. Use its listed number.")
    return matches[0]


def _delimited(columns, rows, delimiter=","):
    stream = StringIO(newline="")
    writer = csv.writer(stream, delimiter=delimiter)
    writer.writerow(columns)
    writer.writerows(rows)
    return stream.getvalue()


def pick_dataset(datasets, selector, geometry=None):
    # Older projects can retain the native import's missing Mulliken record
    # alongside a measured charge column for the same frame. Both keep their IDs.
    measured = {d.geometry for d in datasets if d.kind == selector and d.values is not None}
    def keys(d):
        if geometry is not None and d.geometry != geometry:
            return ()
        if (d.kind == "mulliken-charge" and d.values is None and d.missing_reason
                and d.provenance.kind == "orca-native-import" and d.geometry in measured):
            return (d.dataset_id,)
        return d.dataset_id, d.kind
    return _pick(datasets, selector, keys, "dataset")


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _spectrum_entries(report):
    return [{"number": index, "kind": table.kind, "title": table.title, "source_line": table.source_line,
             "rows": len(table.rows), "columns": table.columns}
            for index, table in enumerate(report.spectra, 1)] if report else []


def _evidence(report, snapshots, datasets):
    sources = {}
    if report:
        sources[report.source.artifact_id] = report.source
    for record in (*snapshots, *datasets):
        for source in record.provenance.parents:
            sources[source.artifact_id] = source
    for data in datasets:
        if data.array_ref:
            sources[data.array_ref.artifact_id] = data.array_ref
    return [asdict(source) for source in sources.values()]


def _inventory(snapshots, datasets, report, series):
    return {
        "geometries": [{"number": n, **asdict(s.ref), "atoms": len(s.atom_ids),
                        "geometry_sha256": s.content_hash, "source_type": source_label(s, None)} for n, s in enumerate(snapshots, 1)],
        "datasets": [{"number": n, "id": d.dataset_id, "kind": d.kind, "unit": d.unit, "shape": d.shape,
                      "geometry": asdict(d.geometry), "missing_reason": d.missing_reason}
                     for n, d in enumerate(datasets, 1)],
        "status": report.status if report else None,
        "source": asdict(report.source) if report else None,
        "properties": [{"number": n, **asdict(group[0]), "observations": len(group)}
                       for n, group in enumerate(series, 1)],
        "spectra": _spectrum_entries(report),
        "optimizations": [{"number": n, "job": run.job, "points": len(run.points)}
                          for n, run in enumerate(optimization_runs(report), 1)],
        "normal_mode_groups": [{"number": n, "title": group.title, "source_line": group.source_line,
                                "modes": len(group.modes), "atoms": len(group.atoms)}
                               for n, group in enumerate(report.normal_modes, 1)] if report else [],
    }


def _atomic_table(snapshot, dataset=None):
    columns = ["atom", "id", "element", "x (angstrom)", "y (angstrom)", "z (angstrom)"]
    values = {}
    if dataset:
        columns.extend([f"value ({dataset.unit})", "value_status"])
        values = dict(zip(dataset.axes[0].ids, dataset.values or [None] * len(dataset.axes[0].ids)))
    rows = []
    for index, (identity, atom) in enumerate(zip(snapshot.atom_ids, snapshot.molecule.atoms), 1):
        row = [index, identity, atom.element, atom.x, atom.y, atom.z]
        if dataset:
            value = values.get(identity)
            if identity not in values:
                status = "off-axis"
            elif dataset.array_ref:
                status = "not loaded"
            else:
                status = "missing" if value is None else "available"
            row.extend([value, status])
        rows.append(row)
    return columns, rows


def _results(args):
    from orcaview.cli_io import check_output, load_session, write_text

    check_output(args.input, args.output)
    session = load_session(args.input, finite=args.finite)
    snapshots, datasets = session.document.records()
    report = session.log_report
    # A standalone log's empty draft is a storage container, not a measured geometry.
    if report and len(snapshots) == 1 and not snapshots[0].atom_ids:
        snapshots = ()
    series = log_property_series(report) if report else ()
    table = None
    if args.geometry is not None:
        snapshot = _pick(snapshots, args.geometry, lambda s: (s.ref.snapshot_id, s.ref.frame_id), "geometry")
        payload = asdict(snapshot)
        payload["source_type"] = source_label(snapshot, None)
        table = _atomic_table(snapshot)
    elif args.dataset is not None:
        data = pick_dataset(datasets, args.dataset)
        snapshot = session.document.resolve(data.geometry)
        payload = asdict(data)
        payload["source_type"] = source_label(snapshot, data)
        if len(data.axes) == 1 and data.axes[0].kind == "atom":
            table = _atomic_table(snapshot, data)
        else:
            table = (("flat_index", f"value ({data.unit})"), enumerate(data.values or (), 1))
        if args.format == "json" and len(data.axes) == 1 and data.axes[0].kind == "atom":
            payload["atoms"] = [dict(zip(table[0], row)) for row in table[1]]
    elif args.properties or args.property is not None:
        props = (report.properties if report else ()) if args.properties else _pick(
            series, args.property, lambda group: (group[0].label,), "property series")
        columns = ("group", "label", "context", "value", "unit", "line")
        table = (columns, (tuple(getattr(p, field) for field in columns) for p in props))
        payload = {"source": asdict(report.source) if report else None, "properties": [asdict(p) for p in props]}
    elif args.optimization:
        runs = optimization_runs(report)
        if not runs:
            raise ValueError("This report contains no geometry optimization cycle energies.")
        if args.format == "json":
            payload = {"source": asdict(report.source), "energy_unit": "Eh", "runs": [asdict(run) for run in runs]}
        else:
            columns = ("run", "job", "step", "energy_Eh", "source_line", "scf_warning")
            table = columns, ((n, run.job, "final" if p.step is None else p.step, p.energy, p.line, p.scf_warning)
                              for n, run in enumerate(runs, 1) for p in run.points)
    elif args.normal_modes:
        if not report or not report.normal_modes:
            raise ValueError("No complete normal-mode displacement vectors with matching coordinates were found.")
        if args.format == "json":
            payload = {"source": asdict(report.source), "coordinate_unit": "angstrom", "frequency_unit": "cm-1",
                       "groups": [asdict(group) for group in report.normal_modes]}
        else:
            columns = ("group", "mode", "frequency_cm-1", "atom", "element", "x_angstrom", "y_angstrom", "z_angstrom",
                       "dx", "dy", "dz", "geometry_line", "frequency_line", "vector_line")
            table = columns, ((n, mode.index, mode.frequency, atom_no, atom.element, atom.x, atom.y, atom.z, *vector,
                               group.geometry_line, group.frequency_line, mode.source_line)
                              for n, group in enumerate(report.normal_modes, 1) for mode in group.modes
                              for atom_no, (atom, vector) in enumerate(zip(group.atoms, mode.displacements), 1))
    elif args.evidence:
        payload = _evidence(report, snapshots, datasets)
        columns = ("artifact_id", "format", "path_hint", "sha256")
        table = (columns, (tuple(source[c] for c in columns) for source in payload))
    elif args.all:
        payload = {"geometries": [asdict(s) for s in snapshots], "datasets": [asdict(d) for d in datasets],
                   "log_report": asdict(report) if report else None}
    else:
        payload = _inventory(snapshots, datasets, report, series)

    if args.format == "json":
        text = _json(payload)
    elif table is not None:
        text = _delimited(*table, delimiter="," if args.format == "csv" else "\t")
    else:
        raise ValueError("Select a geometry, dataset, property table, optimization, normal modes or source evidence for CSV/TSV output.")
    write_text(args.output, text)
    return 0


def _selected_spectrum(args, report):
    if not report or not report.spectra:
        raise ValueError("This file contains no printed spectrum tables.")
    return _pick(report.spectra, args.table, lambda t: (t.kind, t.title), "spectrum")


def _spectrum_source(table, args):
    source = plot_source(table, "cm⁻¹" if args.unit == "cm-1" else args.unit,
                         element=args.element, reference=args.reference_ppm)
    if source is None:
        if coupling_pairs(table):
            raise ValueError("Choose --format png for a signed J plot or --format table for the printed nucleus pairs.")
        raise ValueError("This table has no printed stick strengths. Choose --format table to export its columns.")
    return source


def _profile(source, args):
    width = source.default_fwhm if args.fwhm is None else args.fwhm
    return PlotProfile.setup(source, args.shape or default_shape(source), width, args.mix, args.range, args.points).sampled()


def _spectrum(args):
    from orcaview.cli_io import check_output, load_session, write_text

    check_output(args.input, args.output)
    kind = args.format
    if kind is None and args.output and args.output.suffix.lower() == ".png":
        kind = "png"
    if kind in (None, "table") and (args.element is not None or args.reference_ppm is not None):
        raise ValueError("Choose --format sticks, curve or png to plot NMR positions. The table contains the raw values.")
    if kind == "png":
        if args.output is None or str(args.output) == "-":
            raise ValueError("PNG export requires --output FILE.")
        from orcaview.cli_render import run_offscreen
        return run_offscreen("spectrum", args)
    report = load_session(args.input).log_report
    if args.table is None and kind is None:
        text = _json(_spectrum_entries(report))
    else:
        table = _selected_spectrum(args, report)
        if kind is None or kind == "table":
            text = _delimited(table.columns, table.rows)
        else:
            source = _spectrum_source(table, args)
            if kind == "curve":
                profile = _profile(source, args)
                scale = profile.peak_height if args.normalize and profile.peak_height else 1.0
                text = spectrum_csv(source, profile.curve, normalized=args.normalize, scale=scale)
            else:
                text = spectrum_csv(source)
    write_text(args.output, text)
    return 0


def render_spectrum_image(args):
    """Called in a Qt worker configured for offscreen drawing."""
    from orcaview.cli_io import load_session
    from orcaview.gui.nmr_couplings import CouplingFigure
    from orcaview.gui.result_display import report_text
    from orcaview.gui.spectrum_plot import SpectrumFigure, save_spectrum_figure
    from orcaview.gui.spectrum_preview_export import save_spectrum_png

    table = _selected_spectrum(args, load_session(Path(args.input)).log_report)
    pairs = coupling_pairs(table)
    if pairs:
        if (any(value is not None for value in (args.element, args.reference_ppm, args.unit, args.shape, args.fwhm,
                                                args.range, args.reverse)) or args.normalize or args.layers != "both"
                or args.points != 1201 or args.mix != .5 or args.color != PlotStyle.color
                or args.stroke_width != PlotStyle.stroke_width):
            raise ValueError("The J plot shows printed values by nucleus pair. Its appearance option is --[no-]grid.")
        figure = CouplingFigure(report_text(table.title), pairs)
        figure.grid = args.grid
        save_spectrum_png(args.output, figure)
        return 0
    source = _spectrum_source(table, args)
    if not re.fullmatch(r"#[\da-fA-F]{6}", args.color, re.ASCII):
        raise ValueError("The curve color must use #RRGGBB.")
    if not .5 <= args.stroke_width <= 6:
        raise ValueError("The curve width must be between 0.5 and 6 pixels.")
    figure = SpectrumFigure()
    figure.title = report_text(table.title)
    figure.profile = _profile(source, args)
    figure.style = PlotStyle(reverse=source.reversed_axis if args.reverse is None else args.reverse,
                             layers=args.layers, grid=args.grid, normalized=args.normalize,
                             color=args.color, stroke_width=args.stroke_width)
    save_spectrum_figure(figure, args.output, "png")
    return 0
