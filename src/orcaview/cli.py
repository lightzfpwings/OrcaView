"""Core commands run independently of the optional Qt interface."""

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

from orcaview import __version__
from orcaview import cli_design, cli_project, cli_render, cli_results, cli_settings, cli_update
from orcaview.cli_calculation import approximation_flags, block_options
from orcaview.core.block_options import available_options, validated_block_values
from orcaview.core.integrals import auxiliary_options, basis_options, integral_options
from orcaview.core.methods import (ACTIVE_SPACE_METHODS, ALL_JOBS, ELECTRON_CHANNEL_METHODS, EXCITED_STATE_METHODS, METHODS,
                                   METHOD_GROUPS, REFERENCE_FUNCTIONAL_METHODS, RESPONSE_FUNCTIONALS,
                                   canonical_method, dispersion_options, frozen_core_options, pno_options,
                                   reference_options)
from orcaview.core.models import CalculationSpec
from orcaview.core.solvation import MODELS, SOLVENTS, solvation_options
from orcaview.orca.output import parse_output


def main(argv=None) -> int:
    # Preserve CSV line endings and Unicode labels in Unix and Windows pipelines.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8", newline="")
    if hasattr(sys.stdin, "reconfigure") and not sys.stdin.isatty() and sys.stdin.encoding.lower() != "utf-8":
        sys.stdin.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="orcaview", description="OrcaView · ORCA molecular workbench")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    manual = sub.add_parser("manual", help="Look up an ORCA 6.1.1 manual section and its PDF page")
    manual.add_argument("query", nargs="*", help="Section number, method or keyword")
    methods = sub.add_parser("methods", help="List methods or show available basis sets and approximations for a method")
    methods.add_argument("method", nargs="?")
    methods.add_argument("--job", choices=ALL_JOBS, default="SP")
    methods.add_argument("--basis")
    methods.add_argument("--ri", "--integral-approximation", dest="ri", default="Auto")
    methods.add_argument("--blocks", action="store_true", help="List input block fields available for this method and job")
    approximation_flags(methods)
    gui = sub.add_parser("gui", help="Start the desktop application (requires the optional GUI dependencies)")
    cli_render.add_gui_options(gui)
    gui.set_defaults(handler=cli_render.launch_gui)
    for commands in (cli_project, cli_design, cli_results, cli_render, cli_settings, cli_update):
        commands.register(sub)
    inspect = sub.add_parser("inspect", help="Read a single-job output summary without running ORCA")
    inspect.add_argument("output", type=Path)
    inspect.add_argument("--job", choices=ALL_JOBS, default="SP")
    args = parser.parse_args(argv)
    try:
        if hasattr(args, "handler"):
            return args.handler(args)
        if args.command == "manual":
            from orcaview.core.manual import lookup, PDF_URL, WEB_ROOT
            for number, title, path, page, _ in lookup(" ".join(args.query)):
                print(f"{number}  {title}\n  {WEB_ROOT}{path}\n  {PDF_URL}#page={page}")
            return 0
        if args.command == "methods":
            if args.method is None:
                if args.blocks:
                    raise ValueError("--blocks requires a method, for example orcaview methods B3LYP --blocks")
                for family, names in METHOD_GROUPS.items():
                    print(f"{family}  " + ", ".join(names))
            else:
                from orcaview.core.integrals import grid_options, scalar_options
                name = canonical_method(args.method)
                bases = basis_options(name)
                basis = args.basis if args.basis is not None else (bases or ("def2-SVP",))[0]
                if args.job not in METHODS[name].job_types or args.ri not in integral_options(name, args.job):
                    raise ValueError(f"{name} does not support the selected job and integral options")
                if not bases and args.basis is not None:
                    raise ValueError(f"{name} uses a built-in basis set. Omit --basis")
                models = solvation_options(name, args.job)
                if args.solvation not in models or (args.solvent is not None and args.solvent.lower() not in SOLVENTS.get(args.solvation, ())):
                    raise ValueError("Incompatible method, job, solvent model or solvent name")
                print("Solvent model  " + ", ".join(models))
                if args.solvation in SOLVENTS:
                    print("Solvent  " + ", ".join(SOLVENTS[args.solvation]))
                spec = CalculationSpec(method=name, job_type=args.job, basis=basis, integral_approximation=args.ri,
                                       nroots=5 if name in EXCITED_STATE_METHODS else None,
                                       solvation_model=args.solvation, solvent=args.solvent,
                                       dispersion=args.dispersion, pno_preset=args.pno_preset, wavefunction=args.wavefunction,
                                       frozen_core=args.frozen_core, relativity=args.relativity, integration_grid=args.grid)
                if args.overrides:
                    spec = replace(spec, block_options=block_options(spec, args.overrides))
                    validated_block_values(spec)
                slots = auxiliary_options(name, basis, args.ri, spec.block_options)
                for label, choices in (("Job", METHODS[name].job_types), ("Orbital basis set", bases or ("Built-in",)),
                                       ("Integrals", integral_options(name, args.job)), *slots.items(),
                                       ("Dispersion", dispersion_options(name)), ("PNO", pno_options(name)),
                                       ("Reference wavefunction", reference_options(name, args.job)), ("Frozen core", frozen_core_options(name)),
                                       ("Grid", grid_options(name, args.ri)), ("Relativity", scalar_options(name, basis))):
                    print(f"{label}  " + ", ".join(choices))
                if name in ACTIVE_SPACE_METHODS:
                    print("Active space  --active-electrons and --active-orbitals")
                if name in EXCITED_STATE_METHODS:
                    print("Number of roots  --nroots")
                if name in REFERENCE_FUNCTIONAL_METHODS:
                    print("Reference functional  " + ", ".join(RESPONSE_FUNCTIONALS))
                if name in ELECTRON_CHANNEL_METHODS:
                    print("Open-shell electron channel  --electron-channel alpha or beta")
                if args.blocks:
                    for value, choices in ((args.dispersion, dispersion_options(name)), (args.pno_preset, pno_options(name)),
                                           (args.wavefunction, reference_options(name, args.job)), (args.frozen_core, frozen_core_options(name)),
                                           (args.relativity, scalar_options(name, basis)), (args.grid, grid_options(name, args.ri))):
                        if value not in choices:
                            raise ValueError(f"{name} does not support {value!r}. Choices: " + ", ".join(choices))
                    for option in available_options(spec):
                        value = " / ".join(option.choices) if option.kind == "choice" else option.kind
                        print(f"%{option.block}.{option.key}  {value}  {option.label}")
            return 0
        if args.command == "inspect":
            result = parse_output(args.output.read_text(encoding="utf-8", errors="replace"), args.job)
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            return 0
        parser.print_help()
        return 0
    except (ValueError, OSError) as exc:
        print("OrcaView: {}".format(exc), file=sys.stderr)
        return 2

