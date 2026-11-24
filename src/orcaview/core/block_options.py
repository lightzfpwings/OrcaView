"""Typed, method- and job-specific overrides for ORCA's native input blocks."""

from dataclasses import dataclass
import math
import re
from typing import Union


@dataclass(frozen=True)
class BlockOverride:
    block: str
    key: str
    value: Union[int, float, bool, str]


def available_options(spec):
    from ._block_catalog import catalog_options
    from ._solver_block_catalog import solver_options
    from .methods import METHODS
    if not isinstance(spec.method, str) or spec.method not in METHODS:
        raise ValueError(f"Unknown computational method {spec.method!r}")
    if spec.job_type not in METHODS[spec.method].job_types:
        raise ValueError(f"{spec.method} does not support job type {spec.job_type!r}")
    from . import reaction_path
    from .solvation import solvation_block_options
    return (*catalog_options(spec), *solver_options(spec), *solvation_block_options(spec), *reaction_path.options(spec))


def _checked_value(option, value):
    name = f"%{option.block}.{option.key}"
    if option.kind == "bool":
        if type(value) is not bool:
            raise ValueError(f"{name} requires true or false")
        return value
    if option.kind == "choice":
        if not isinstance(value, str) or value not in option.choices:
            raise ValueError(f"Allowed values for {name}: " + ", ".join(option.choices))
        return value
    if option.kind == "int":
        if type(value) is not int or not -2**31 <= value < 2**31:
            raise ValueError(f"{name} requires a 32-bit integer")
    elif option.kind == "float":
        if type(value) not in (int, float):
            raise ValueError(f"{name} requires a finite real number")
        try:
            value = float(value)
        except OverflowError:
            raise ValueError(f"{name} is outside the floating-point range") from None
        if not math.isfinite(value):
            raise ValueError(f"{name} requires a finite real number")
    else:
        raise ValueError(f"Unknown field type for {name}")
    if option.minimum is not None and (value < option.minimum or
                                        (option.minimum_exclusive and value == option.minimum)):
        relation = "greater than" if option.minimum_exclusive else "greater than or equal to"
        raise ValueError(f"{name} must be {relation} {option.minimum}")
    if option.maximum is not None and (value > option.maximum or
                                        (option.maximum_exclusive and value == option.maximum)):
        relation = "less than" if option.maximum_exclusive else "less than or equal to"
        raise ValueError(f"{name} must be {relation} {option.maximum}")
    return value


def parse_option_value(option, text):
    """Convert one GUI/CLI input value. Persisted records are checked without coercing strings."""
    name = f"%{option.block}.{option.key}"
    if not isinstance(text, str) or not text.isprintable():
        raise ValueError(f"{name} requires a single-line parameter value")
    token = text.strip()
    if option.kind == "bool":
        value = {"true": True, "false": False}.get(token.casefold())
    elif option.kind == "choice":
        value = next((v for v in option.choices if token.casefold() == v.casefold()), None)
    elif option.kind == "int":
        if not re.fullmatch(r"[+-]?[0-9]+", token):
            raise ValueError(f"{name} requires an integer")
        try:
            value = int(token)
        except ValueError:
            raise ValueError(f"Value too large for {name}") from None
    elif option.kind == "float":
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", token):
            raise ValueError(f"{name} requires a decimal number; scientific notation is supported")
        value = float(token)
    else:
        raise ValueError(f"Unknown field type for {name}")
    return _checked_value(option, value)


def validated_block_values(spec):
    """Return typed values in catalog order so equivalent input yields the same snapshot."""
    if not isinstance(spec.block_options, tuple):
        raise ValueError("Input block settings must use an immutable tuple")
    if not spec.block_options:
        return {}
    from ._block_catalog import validate_common_combinations
    from ._solver_block_catalog import validate_solver_combinations
    catalog = {(o.block, o.key): o for o in available_options(spec)}
    values = {}
    for override in spec.block_options:
        if not isinstance(override, BlockOverride) or not all(
                isinstance(field, str) for field in (override.block, override.key)):
            raise ValueError("Input block settings require a block name, field name and value")
        key = override.block, override.key
        if key not in catalog:
            raise ValueError(f"{spec.method} / {spec.job_type} does not support a manual %{override.block}.{override.key} setting")
        if key in values:
            raise ValueError(f"Duplicate setting %{override.block}.{override.key}")
        values[key] = _checked_value(catalog[key], override.value)
    validate_common_combinations(spec, values)
    validate_solver_combinations(spec, values)
    from . import reaction_path
    reaction_path.validate(values)
    return {key: values[key] for key in catalog if key in values}
