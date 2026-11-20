"""Shared validation for the lightweight scientific contracts."""

import math
from typing import ClassVar


class Versioned:
    contract_version: ClassVar[int] = 1


def integer(value, label, minimum=None):
    if type(value) is not int:
        raise ValueError(f"{label} 必须是整数")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} 必须不小于 {minimum}")


def finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} 必须是有限实数")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} 超出浮点范围") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} 不能是 NaN 或无穷大")
    return number


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空字符串")


def require_tuple(value, label):
    if not isinstance(value, tuple):
        raise ValueError(f"{label} 必须使用不可变 tuple")


def identifiers(values, label):
    require_tuple(values, label)
    for value in values:
        nonempty(value, label)
    if len(set(values)) != len(values):
        raise ValueError(f"{label} 不能重复")
