"""Shared validation for the lightweight scientific contracts."""

import math
from typing import ClassVar


class Versioned:
    contract_version: ClassVar[int] = 1


def integer(value, label, minimum=None):
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}")


def finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite real number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} is outside the floating-point range") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} cannot be NaN or infinite")
    return number


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")


def require_tuple(value, label):
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be an immutable tuple")


def identifiers(values, label):
    require_tuple(values, label)
    for value in values:
        nonempty(value, label)
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must be unique")
