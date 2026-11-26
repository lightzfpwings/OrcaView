"""One-dimensional NMR positions and signed scalar couplings from printed ORCA tables."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
import math
import unicodedata

from orcaview.results.broadening import StickSpectrum, stick_spectrum


@dataclass(frozen=True)
class ShieldingSpectrum(StickSpectrum):
    element: str
    reference: float | None


def _column_unit(table):
    if table.kind == "nmr" and len(table.columns) >= 3:
        # The headers in older saved projects may be translated.
        return unicodedata.normalize("NFKC", table.columns[2]).rpartition("(")[2].rstrip(")").strip().casefold()
    return ""


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def coupling_pairs(table):
    if _column_unit(table) != "hz":
        return ()
    return tuple((str(row[0]), str(row[1]), row[2]) for row in table.rows
                 if len(row) >= 3 and _finite(row[2]))


def _shieldings(table):
    if _column_unit(table) == "ppm":
        for row in table.rows:
            if len(row) >= 3 and isinstance(row[1], str) and row[1].strip() and _finite(row[2]):
                yield row[1].strip(), row[2]


def shielding_elements(table):
    return tuple(sorted({element for element, _ in _shieldings(table)}, key=lambda e: (e != "H", e)))


def plot_source(table, unit=None, *, element=None, reference=None):
    """Use one count per printed nucleus; equal positions add within the selected element."""
    if _column_unit(table) != "ppm":
        if element is not None or reference is not None:
            raise ValueError("Element and reference apply only to an NMR shielding table.")
        return stick_spectrum(table, unit)
    if unit not in (None, "ppm"):
        raise ValueError("The NMR axis unit is ppm.")
    if reference is not None and not _finite(reference):
        raise ValueError("Enter a finite reference shielding in ppm.")
    elements = shielding_elements(table)
    if not elements:
        return None
    element = element.strip().capitalize() if element is not None else elements[0]
    if element not in elements:
        raise ValueError(f"No printed shielding for {element}. Available elements: {', '.join(elements)}.")
    # Keep decimal positions from the ORCA printout and user reference exact before CSV/plot conversion.
    ref = Decimal(str(reference)) if reference is not None else None
    positions = Counter(shielding if ref is None else float(ref - Decimal(str(shielding)))
                        for symbol, shielding in _shieldings(table) if symbol == element)
    if not all(math.isfinite(x) for x in positions):
        raise ValueError("Spectrum limits exceed the available numeric range.")
    return ShieldingSpectrum(tuple(sorted(positions.items())), "ppm", ("ppm",),
                             "Isotropic shielding σ" if reference is None else "Chemical shift δ",
                             "Nucleus count", .05, reference is not None, element, reference)


def default_shape(source):
    return "lorentzian" if isinstance(source, ShieldingSpectrum) else "gaussian"
