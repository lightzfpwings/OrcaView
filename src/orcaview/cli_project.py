"""Batch project import, input generation and local ORCA execution."""

from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

from orcaview.application.project import migrate_project, save_project
from orcaview.application.session import Session
from orcaview.cli_calculation import calculation_flags, configure
from orcaview.cli_io import check_output, load_session, write_bytes, write_text
from orcaview.core.models import Atom, Molecule
from orcaview.io.xyz import write_xyz


def register(sub):
    resources = sub.add_parser("resources", help="Show new-job defaults and the recommendation for this host in JSON")
    resources.set_defaults(handler=_resources)
    preview = sub.add_parser("preview", help="Generate ORCA input from a structure or saved project")
    preview.add_argument("input", nargs="?", type=Path, help="Default: built-in water")
    preview.add_argument("-o", "--output", type=Path, help="Write UTF-8 input instead of stdout")
    preview.add_argument("--finite", action="store_true")
    calculation_flags(preview)
    preview.set_defaults(handler=_preview)
    project = sub.add_parser("project", help="Import, create, configure or convert a project (or export XYZ)")
    source = project.add_mutually_exclusive_group()
    source.add_argument("input", nargs="?", type=Path)
    source.add_argument("--new", choices=("empty", "carbon", "water"))
    source.add_argument("--demo", choices=("m1", "m6"), help="Built-in synthetic example")
    project.add_argument("-o", "--output", required=True, type=Path)
    project.add_argument("--finite", action="store_true")
    project.add_argument("--format", choices=("project", "xyz"), help="Inferred from output extension by default")
    calculation_flags(project)
    project.set_defaults(handler=_project)
    migrate = sub.add_parser("migrate", help="Migrate a schema 1 project to a new side-by-side project")
    migrate.add_argument("source", type=Path)
    migrate.add_argument("destination", type=Path)
    migrate.set_defaults(handler=_migrate)
    native = sub.add_parser("native-input", help="Read or write independent UTF-8 ORCA input, preserving exact line endings")
    native.add_argument("input", nargs="?", default="-", help="Read a .inp file or '-' for standard input")
    native.add_argument("-o", "--output", default="-", help="Write a .inp file or '-' for standard output")
    native.set_defaults(handler=_native_input)
    run = sub.add_parser("run", help="Execute a frozen input with an explicitly selected local ORCA (POSIX)")
    run.add_argument("input", type=Path)
    run.add_argument("--orca", required=True, type=Path, help="Absolute path to the ORCA executable")
    run.add_argument("--workdir", required=True, type=Path, help="Directory for isolated attempts and their logs")
    run.add_argument("--timeout", type=float, help="Execution timeout in seconds")
    run.add_argument("--finite", action="store_true")
    run.add_argument("--external-xyz", type=Path)
    run.add_argument("--initial-gbw", type=Path)
    calculation_flags(run)
    run.set_defaults(handler=_run)
    attempts = sub.add_parser("attempts", help="Read recorded execution statuses from a local workspace")
    attempts.add_argument("workdir", type=Path)
    attempts.set_defaults(handler=_attempts)


def _resources(args):
    from orcaview.core.resource_defaults import TARGET_CORES, TARGET_MAXCORE_MB, detect_resources
    host = detect_resources()
    cores, maxcore = host.recommend()
    print(json.dumps({"cpu_limit": host.cpu_limit, "available_memory_mb": host.memory_mb,
                      "target": {"cores": TARGET_CORES, "maxcore_mb": TARGET_MAXCORE_MB},
                      "recommended": {"cores": cores, "maxcore_mb": maxcore, "total_mb": cores * maxcore}},
                     indent=2))
    return 0


def _job_session(args):
    if getattr(args, "demo", None) == "m6":
        from orcaview.gui.result_demo import build_result_demo
        session, _ = build_result_demo()
        return session
    if getattr(args, "demo", None) == "m1":
        from orcaview.gui.foundation_demo import build_foundation_demo
        return build_foundation_demo()
    if args.input:
        return load_session(args.input, finite=args.finite)
    if getattr(args, "new", "water") == "water":
        return Session()
    atoms = (Atom("C", 0., 0., 0.),) if args.new == "carbon" else ()
    return Session(molecule=Molecule("New molecule", atoms, bonds_explicit=True))


def _preview(args):
    check_output(args.input, args.output)
    session = _job_session(args)
    spec, charge, multiplicity = configure(session, args)
    write_text(args.output, session.apply_settings(spec, charge, multiplicity))
    return 0


def _project(args):
    format_name = args.format or ("xyz" if args.output.suffix.lower() == ".xyz" else "project")
    if not (args.input and args.input.suffix.lower() == ".json" and format_name == "project"
            and args.input.resolve() == args.output.resolve()):
        check_output(args.input, args.output)
    session = _job_session(args)
    spec, charge, multiplicity = configure(session, args)
    if (session.calculation, session.molecule.charge, session.molecule.multiplicity) != (spec, charge, multiplicity):
        if session.molecule.atoms:
            session.apply_settings(spec, charge, multiplicity)
        else:
            spec.validate()
            session.molecule = replace(session.molecule, charge=charge, multiplicity=multiplicity)
            session.calculation = spec
    if format_name == "xyz":
        write_text(args.output, write_xyz(session.molecule))
    else:
        if str(args.output) == "-":
            raise ValueError("Provide a file path for the project.")
        save_project(session, args.output)
    return 0


def _migrate(args):
    migrate_project(args.source, args.destination)
    return 0


def _native_input(args):
    check_output(None if args.input == "-" else args.input, args.output)
    raw = sys.stdin.buffer.read() if args.input == "-" else Path(args.input).read_bytes()
    raw.decode("utf-8")
    if args.output == "-":
        sys.stdout.buffer.write(raw)
    else:
        write_bytes(args.output, raw)
    return 0


def _run(args):
    from orcaview.core.tasks import ResourceBudget
    from orcaview.execution import LocalOrcaRunner
    from orcaview.orca.input import InputCompanionFile, freeze_input

    session = _job_session(args)
    spec, charge, multiplicity = configure(session, args)
    session.apply_settings(spec, charge, multiplicity)
    companions = tuple(InputCompanionFile.from_path(role, path.name, path)
                       for role, path in (("external_xyz", args.external_xyz), ("initial_gbw", args.initial_gbw)) if path)
    snapshot = freeze_input(session.document.head, spec, companions=companions)
    runner = LocalOrcaRunner(args.workdir, budget=ResourceBudget(spec.cores, 1, spec.peak_maxcore_per_process * spec.cores))
    try:
        started = runner.start(snapshot, args.orca, timeout_seconds=args.timeout)
        try:
            result = runner.wait(started.attempt_id)
        except KeyboardInterrupt:
            runner.cancel(started.attempt_id)
            runner.wait(started.attempt_id)
            return 130
        report = asdict(result)
        # The full version probe can include the complete ORCA banner. The attempt journal retains it.
        report.pop("version_output")
        print(json.dumps(report, default=str, ensure_ascii=False, indent=2))
        return 0 if result.state == "succeeded" else 1
    finally:
        runner.close()


def _attempts(args):
    from orcaview.execution._journal import recover_attempts
    print(json.dumps(recover_attempts(args.workdir), ensure_ascii=False, indent=2))
    return 0
