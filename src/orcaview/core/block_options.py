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
        raise ValueError(f"未收录计算方法 {spec.method!r}")
    if spec.job_type not in METHODS[spec.method].job_types:
        raise ValueError(f"{spec.method} 不支持作业 {spec.job_type!r}")
    from . import reaction_path
    from .solvation import solvation_block_options
    return (*catalog_options(spec), *solver_options(spec), *solvation_block_options(spec), *reaction_path.options(spec))


def _checked_value(option, value):
    name = f"%{option.block}.{option.key}"
    if option.kind == "bool":
        if type(value) is not bool:
            raise ValueError(f"{name} 需要 true 或 false")
        return value
    if option.kind == "choice":
        if not isinstance(value, str) or value not in option.choices:
            raise ValueError(f"{name} 可选 " + "、".join(option.choices))
        return value
    if option.kind == "int":
        if type(value) is not int or not -2**31 <= value < 2**31:
            raise ValueError(f"{name} 需要 32 位整数")
    elif option.kind == "float":
        if type(value) not in (int, float):
            raise ValueError(f"{name} 需要有限实数")
        try:
            value = float(value)
        except OverflowError:
            raise ValueError(f"{name} 超出浮点范围") from None
        if not math.isfinite(value):
            raise ValueError(f"{name} 需要有限实数")
    else:
        raise ValueError(f"{name} 未识别的字段类型")
    if option.minimum is not None and (value < option.minimum or
                                        (option.minimum_exclusive and value == option.minimum)):
        relation = "大于" if option.minimum_exclusive else "大于或等于"
        raise ValueError(f"{name} 需要{relation} {option.minimum}")
    if option.maximum is not None and (value > option.maximum or
                                        (option.maximum_exclusive and value == option.maximum)):
        relation = "小于" if option.maximum_exclusive else "小于或等于"
        raise ValueError(f"{name} 需要{relation} {option.maximum}")
    return value


def parse_option_value(option, text):
    """Convert one GUI/CLI input value. Persisted records are checked without coercing strings."""
    name = f"%{option.block}.{option.key}"
    if not isinstance(text, str) or not text.isprintable():
        raise ValueError(f"{name} 需要单行参数值")
    token = text.strip()
    if option.kind == "bool":
        value = {"true": True, "false": False}.get(token.casefold())
    elif option.kind == "choice":
        value = next((v for v in option.choices if token.casefold() == v.casefold()), None)
    elif option.kind == "int":
        if not re.fullmatch(r"[+-]?[0-9]+", token):
            raise ValueError(f"{name} 需要整数")
        try:
            value = int(token)
        except ValueError:
            raise ValueError(f"{name} 数值过大") from None
    elif option.kind == "float":
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", token):
            raise ValueError(f"{name} 需要十进制数值，可使用科学计数法")
        value = float(token)
    else:
        raise ValueError(f"{name} 未识别的字段类型")
    return _checked_value(option, value)


def validated_block_values(spec):
    """Return typed values in catalog order so equivalent input yields the same snapshot."""
    if not isinstance(spec.block_options, tuple):
        raise ValueError("输入块设置必须使用不可变 tuple")
    if not spec.block_options:
        return {}
    from ._block_catalog import validate_common_combinations
    from ._solver_block_catalog import validate_solver_combinations
    catalog = {(o.block, o.key): o for o in available_options(spec)}
    values = {}
    for override in spec.block_options:
        if not isinstance(override, BlockOverride) or not all(
                isinstance(field, str) for field in (override.block, override.key)):
            raise ValueError("输入块设置需要块名、字段名和参数值")
        key = override.block, override.key
        if key not in catalog:
            raise ValueError(f"{spec.method} / {spec.job_type} 不支持手动设置 %{override.block}.{override.key}")
        if key in values:
            raise ValueError(f"重复设置 %{override.block}.{override.key}")
        values[key] = _checked_value(catalog[key], override.value)
    validate_common_combinations(spec, values)
    validate_solver_combinations(spec, values)
    from . import reaction_path
    reaction_path.validate(values)
    return {key: values[key] for key in catalog if key in values}
