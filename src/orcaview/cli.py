"""Core commands run independently of the optional Qt interface."""

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

from orcaview import __version__
from orcaview.application.session import Session
from orcaview.core.block_options import BlockOverride, available_options, parse_option_value, validated_block_values
from orcaview.core.integrals import auxiliary_options, basis_options, integral_options
from orcaview.core.methods import (ACTIVE_SPACE_METHODS, ALL_JOBS, ELECTRON_CHANNEL_METHODS, EXCITED_STATE_METHODS, METHODS,
                                   METHOD_GROUPS, REFERENCE_FUNCTIONAL_METHODS, RESPONSE_FUNCTIONALS,
                                   canonical_method, dispersion_options, frozen_core_options, pno_options,
                                   reference_options)
from orcaview.core.models import CalculationSpec
from orcaview.core.solvation import MODELS, SOLVENTS, solvation_options
from orcaview.orca.output import parse_output


def _cli_block_options(spec, arguments):
    choices = {f"{o.block}.{o.key}".casefold(): o for o in available_options(spec)}
    overrides = []
    for argument in arguments:
        path, equals, value = argument.partition("=")
        if not equals:
            raise ValueError("Use --set block.parameter=value, for example scf.MaxIter=250")
        option = choices.get(path.strip().removeprefix("%").casefold())
        if option is None:
            raise ValueError(f"{spec.method} / {spec.job_type} does not support setting {path!r} manually")
        overrides.append(BlockOverride(option.block, option.key, parse_option_value(option, value)))
    return tuple(overrides)


def _approximation_flags(parser):
    parser.add_argument("--set", dest="overrides", action="append", default=[], metavar="BLOCK.KEY=VALUE",
                        help="Set an input parameter. Repeat for additional parameters, e.g. --set scf.MaxIter=250")
    parser.add_argument("--pno-preset", default="Auto")
    parser.add_argument("--dispersion", default="Auto")
    parser.add_argument("--grid", "--integration-grid", dest="grid", default="Auto")
    parser.add_argument("--relativity", default="Auto")
    parser.add_argument("--wavefunction", default="Auto")
    parser.add_argument("--frozen-core", default="Auto")
    parser.add_argument("--solvation", choices=("Gas", *MODELS), default="Gas", help="Implicit solvent model")
    parser.add_argument("--solvent", help="Solvent name, e.g. water")


def main(argv=None) -> int:
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
    _approximation_flags(methods)
    gui = sub.add_parser("gui", help="Start the desktop application (requires the optional GUI dependencies)")
    gui.add_argument("--screenshot", type=Path, help=argparse.SUPPRESS)
    preview = sub.add_parser("preview", help="Validate a molecule and write ORCA input to standard output")
    preview.add_argument("xyz", nargs="?", type=Path)
    preview.add_argument("--job", choices=ALL_JOBS, default="SP")
    preview.add_argument("--method", default="B3LYP", help="Calculation method. Run orcaview methods for the full list")
    preview.add_argument("--basis", help="Orbital basis set (defaults to cc-pVDZ-F12 for F12 or def2-SVP otherwise)")
    preview.add_argument("--ri", "--integral-approximation", dest="ri", default="Auto")
    for slot in ("aux-j", "aux-jk", "aux-c", "cabs"):
        preview.add_argument("--" + slot, help="Choose an auxiliary basis set. Run orcaview methods METHOD for compatible choices")
    _approximation_flags(preview)
    preview.add_argument("--electron-channel", choices=("alpha", "beta"), help="Open-shell IP/EA-EOM spin channel")
    preview.add_argument("--active-electrons", type=int, help="Active electrons for multireference methods")
    preview.add_argument("--active-orbitals", type=int, help="Active orbitals for multireference methods")
    preview.add_argument("--nroots", type=int, help="Number of roots for vertical excitations (default: 5)")
    preview.add_argument("--reference-functional", help="Reference functional for TD-DFT / TDA-DFT (default: B3LYP)")
    preview.add_argument("--charge", type=int, default=0)
    preview.add_argument("--multiplicity", type=int, default=1)
    preview.add_argument("--cores", type=int, default=4)
    preview.add_argument("--maxcore", type=int, default=1000, help="Memory per core in MB")
    inspect = sub.add_parser("inspect", help="Read a single-job output summary without running ORCA")
    inspect.add_argument("output", type=Path)
    inspect.add_argument("--job", choices=ALL_JOBS, default="SP")
    args = parser.parse_args(argv)
    try:
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
                    spec = replace(spec, block_options=_cli_block_options(spec, args.overrides))
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
        if args.command == "gui":
            try:
                from orcaview.gui.main_window import launch
            except ModuleNotFoundError as exc:
                if exc.name and exc.name.startswith("PySide6"):
                    print("Install the GUI dependencies first: python3 -m pip install \".[gui]\"", file=sys.stderr)
                    return 2
                raise
            return launch(args.screenshot)
        if args.command == "preview":
            method = canonical_method(args.method)
            if args.basis is not None and not METHODS[method].uses_orbital_basis:
                raise ValueError(f"{method} uses a built-in basis set. Omit --basis")
            session = Session()
            if args.xyz:
                session.open_xyz(args.xyz)
            session.molecule = replace(session.molecule, charge=args.charge, multiplicity=args.multiplicity)
            nroots = args.nroots
            if nroots is None and method in EXCITED_STATE_METHODS:
                nroots = 5
            functional = args.reference_functional
            if functional is not None:
                functional = canonical_method(functional)
            elif method in REFERENCE_FUNCTIONAL_METHODS:
                functional = "B3LYP"
            session.calculation = CalculationSpec(
                method=method, basis=args.basis if args.basis is not None else (basis_options(method) or ("def2-SVP",))[0],
                job_type=args.job, cores=args.cores, maxcore_mb=args.maxcore,
                active_electrons=args.active_electrons, active_orbitals=args.active_orbitals,
                nroots=nroots, reference_functional=functional,
                integral_approximation=args.ri, aux_j=args.aux_j, aux_jk=args.aux_jk, aux_c=args.aux_c,
                cabs=args.cabs, pno_preset=args.pno_preset, dispersion=args.dispersion,
                integration_grid=args.grid, relativity=args.relativity, electron_channel=args.electron_channel,
                wavefunction=args.wavefunction, frozen_core=args.frozen_core,
                solvation_model=args.solvation, solvent=args.solvent,
            )
            if args.overrides:
                overrides = _cli_block_options(session.calculation, args.overrides)
                session.calculation = replace(session.calculation, block_options=overrides)
            print(session.input_text(), end="")
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

