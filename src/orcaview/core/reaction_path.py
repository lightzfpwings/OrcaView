"""Intrinsic reaction coordinate settings, ORCA 6.1.1 §4.4."""

from ._block_catalog import BlockOption
from .solvation import uses_numerical_frequencies


def options(spec):
    if spec.job_type != "IRC":
        return ()
    algorithms = ("calc_numfreq",) if uses_numerical_frequencies(spec) else ("calc_anfreq", "calc_numfreq")
    return (
        BlockOption("irc", "MaxIter", "Maximum IRC steps", "int", 1),
        BlockOption("irc", "Direction", "Path direction", "choice", choices=("both", "forward", "backward", "down")),
        BlockOption("irc", "InitHess", "Initial Hessian algorithm", "choice", choices=algorithms),
        BlockOption("irc", "hessMode", "Hessian mode for initial displacement (from 0)", "int", 0),
        BlockOption("irc", "Init_Displ_DE", "Initial displacement definition", "choice", choices=("DE", "length")),
        BlockOption("irc", "Scale_Init_Displ", "Initial displacement length (a.u.)", "float", 0, minimum_exclusive=True),
        BlockOption("irc", "DE_Init_Displ", "Initial displacement energy difference (mEh)", "float", 0, minimum_exclusive=True),
        BlockOption("irc", "Scale_Displ_SD", "Steepest descent step length factor", "float", 0, minimum_exclusive=True),
        BlockOption("irc", "Adapt_Scale_Displ", "Adapt step length along path", "bool"),
        BlockOption("irc", "SD_ParabolicFit", "Parabolic fit on steepest descent step", "bool"),
        BlockOption("irc", "Interpolate_only", "Restrict parabolic fit to interpolation", "bool"),
        BlockOption("irc", "Do_SD_Corr", "Correct steepest descent step", "bool"),
        BlockOption("irc", "Scale_Displ_SD_Corr", "Correction step length factor", "float", 0, minimum_exclusive=True),
        BlockOption("irc", "SD_Corr_ParabolicFit", "Parabolic fit on correction step", "bool"),
        BlockOption("irc", "TolRMSG", "RMS gradient threshold (a.u.)", "float", 0, minimum_exclusive=True),
        BlockOption("irc", "TolMaxG", "Maximum gradient threshold (a.u.)", "float", 0, minimum_exclusive=True),
    )


def validate(values):
    fields = {key: v for (block, key), v in values.items() if block == "irc"}
    if fields.get("Direction") == "down" and fields.keys() & {
            "InitHess", "hessMode", "Init_Displ_DE", "Scale_Init_Displ", "DE_Init_Displ"}:
        raise ValueError("IRC down follows the negative gradient and cannot use an initial Hessian displacement")
    length = fields.get("Init_Displ_DE", "DE") == "length"
    if (length and "DE_Init_Displ" in fields) or (not length and "Scale_Init_Displ" in fields):
        raise ValueError("The IRC initial displacement parameters do not match the chosen DE / length mode")
    if fields.get("Do_SD_Corr") is False and fields.keys() & {"Scale_Displ_SD_Corr", "SD_Corr_ParabolicFit"}:
        raise ValueError("IRC correction parameters require an enabled correction step")
    initial_fit = fields.get("SD_ParabolicFit", True)
    correction_fit = fields.get("Do_SD_Corr", True) and fields.get("SD_Corr_ParabolicFit", True)
    if "Interpolate_only" in fields and not (initial_fit or correction_fit):
        raise ValueError("Interpolate_only requires a parabolic fit for the descent or correction step")


def generated_options(spec, values):
    if spec.job_type != "IRC" or not uses_numerical_frequencies(spec):
        return values
    if values.get(("irc", "Direction")) == "down" or ("irc", "InitHess") in values:
        return values
    return {**values, ("irc", "InitHess"): "calc_numfreq"}
