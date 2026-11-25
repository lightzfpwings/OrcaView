"""Calculation options shared by input preview, project creation and execution."""

import argparse
from dataclasses import fields, replace

from orcaview.core.block_options import BlockOverride, available_options, parse_option_value
from orcaview.core.integrals import basis_options
from orcaview.core.methods import ALL_JOBS, EXCITED_STATE_METHODS, METHODS, REFERENCE_FUNCTIONAL_METHODS, canonical_method
from orcaview.core.models import CalculationSpec
from orcaview.core.solvation import MODELS


def block_options(spec, arguments):
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


def approximation_flags(parser, *, inherit=False):
    default = argparse.SUPPRESS if inherit else "Auto"
    parser.add_argument("--set", dest="overrides", action="append", default=[], metavar="BLOCK.KEY=VALUE",
                        help="Set an input parameter; repeat for additional fields")
    for name in ("pno-preset", "dispersion", "relativity", "wavefunction", "frozen-core"):
        parser.add_argument("--" + name, default=default)
    parser.add_argument("--grid", "--integration-grid", dest="integration_grid" if inherit else "grid", default=default)
    parser.add_argument("--solvation", dest="solvation_model" if inherit else "solvation", choices=("Gas", *MODELS),
                        default=argparse.SUPPRESS if inherit else "Gas")
    parser.add_argument("--solvent", default=argparse.SUPPRESS if inherit else None)


def calculation_flags(parser):
    parser.add_argument("--edit-input", metavar="FILE", help="Apply an edited inline ORCA preview (use - for stdin) before command-line overrides")
    parser.add_argument("--job", dest="job_type", choices=ALL_JOBS, default=argparse.SUPPRESS)
    parser.add_argument("--method", default=argparse.SUPPRESS, help="Run 'orcaview methods' for supported methods")
    parser.add_argument("--basis", default=argparse.SUPPRESS)
    parser.add_argument("--ri", "--integral-approximation", dest="integral_approximation", default=argparse.SUPPRESS)
    for name in ("aux-j", "aux-jk", "aux-c", "cabs", "reference-functional"):
        parser.add_argument("--" + name, default=argparse.SUPPRESS)
    parser.add_argument("--scf-convergence", default=argparse.SUPPRESS)
    parser.add_argument("--electron-channel", choices=("alpha", "beta"), default=argparse.SUPPRESS)
    for name in ("active-electrons", "active-orbitals", "nroots", "charge", "multiplicity"):
        parser.add_argument("--" + name, type=int, default=argparse.SUPPRESS)
    parser.add_argument("--cores", type=int, default=argparse.SUPPRESS,
                        help=f"Number of ORCA processes (new jobs default to {CalculationSpec.cores})")
    parser.add_argument("--maxcore", dest="maxcore_mb", type=int, default=argparse.SUPPRESS,
                        help=f"Memory in MB per ORCA process (new jobs default to {CalculationSpec.maxcore_mb})")
    approximation_flags(parser, inherit=True)
    parser.add_argument("--reset-calculation", action="store_true", help="Start from default calculation settings")
    parser.add_argument("--clear-blocks", action="store_true", help="Clear saved block overrides before applying --set")


def configure(session, args):
    spec = CalculationSpec() if args.reset_calculation else session.calculation
    changes = {f.name: getattr(args, f.name) for f in fields(spec) if hasattr(args, f.name)}
    if "method" in changes:
        method = changes["method"] = canonical_method(changes["method"])
        if method != spec.method:
            # Method-dependent defaults match the desktop controls for a fresh method.
            for key in ("basis", "nroots", "reference_functional", "active_electrons", "active_orbitals",
                        "electron_channel", "aux_j", "aux_jk", "aux_c", "cabs"):
                changes.setdefault(key, None)
            if changes["basis"] is None:
                changes["basis"] = (basis_options(method) or ("def2-SVP",))[0]
    method = changes.get("method", spec.method)
    if hasattr(args, "basis") and not METHODS[method].uses_orbital_basis:
        raise ValueError(f"{method} uses a built-in basis set. Omit --basis")
    if method in EXCITED_STATE_METHODS and changes.get("nroots", spec.nroots) is None:
        changes["nroots"] = 5
    if changes.get("reference_functional"):
        changes["reference_functional"] = canonical_method(changes["reference_functional"])
    elif method in REFERENCE_FUNCTIONAL_METHODS and not changes.get("reference_functional", spec.reference_functional):
        changes["reference_functional"] = "B3LYP"
    if changes.get("solvation_model") == "Gas":
        changes.setdefault("solvent", None)
    spec = replace(spec, **changes)
    if args.clear_blocks:
        spec = replace(spec, block_options=())
    if args.overrides:
        overrides = block_options(spec, args.overrides)
        replaced = {(item.block, item.key) for item in overrides}
        keep = tuple(item for item in spec.block_options if (item.block, item.key) not in replaced)
        spec = replace(spec, block_options=keep + overrides)
    charge = getattr(args, "charge", session.molecule.charge)
    multiplicity = getattr(args, "multiplicity", session.molecule.multiplicity)
    return spec, charge, multiplicity
