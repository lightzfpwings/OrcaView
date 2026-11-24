"""Plot stick spectra from ORCA's printed transition positions and strengths."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import math
import unicodedata

from orcaview.orca.log_spectra import SpectrumTable


_WN = "cm⁻¹"
_OPTICAL_UNITS = ("nm", "eV", _WN)
# h*c/e in eV nm, from the exact defining SI constants.
_HC = 6.62607015e-34 * 299792458 / 1.602176634e-19 * 1e9
_LABELS = {"nm": "Wavelength", "eV": "Energy", _WN: "Wavenumber"}
_STRENGTHS = {"ir": "IR intensity (km/mol)", "raman": "Raman activity (Å⁴/amu)",
              "uvvis": "Oscillator strength", "cd": "Rotatory strength (10⁻⁴⁰ cgs)"}


@dataclass(frozen=True)
class StickSpectrum:
    peaks: tuple[tuple[float, float], ...]
    unit: str
    units: tuple[str, ...]
    x_label: str
    y_label: str
    default_fwhm: float
    reversed_axis: bool


def _unit(label):
    # Units are independent of historical project language and column order.
    text = unicodedata.normalize("NFKC", label).strip().casefold()
    return text.rpartition("(")[2].removesuffix(")").strip().replace("−", "-")


def _finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def _convert(position, source, destination):
    if source == destination:
        return position
    if source == "eV":
        return _HC / position if destination == "nm" else position * (1e7 / _HC)
    if source == "nm":
        return (_HC if destination == "eV" else 1e7) / position
    return 1e7 / position if destination == "nm" else position * (_HC / 1e7)


def stick_spectrum(table: SpectrumTable, unit: str | None = None) -> StickSpectrum | None:
    """Use printed coordinates preferentially; convert missing optical axes when possible.

    A frequency list, an NMR shielding/J table, and an already sampled curve do
    not carry stick intensities for this plot. Leave them to their own viewers.
    """
    if table.kind not in _STRENGTHS:
        return None
    optical = table.kind in ("uvvis", "cd")
    units = _OPTICAL_UNITS if optical else (_WN,)
    unit = units[0] if unit is None else unit
    if unit not in units:
        raise ValueError("Unsupported spectrum axis unit.")
    column_units = tuple(_unit(c) for c in table.columns)
    axis = {}
    for name, token in (("eV", "ev"), (_WN, "cm-1"), ("nm", "nm")):
        if token in column_units:
            axis[name] = column_units.index(token)
    if not axis:
        return None
    y_token = {"ir": "km/mol", "raman": "å4/amu", "cd": "10-40 cgs"}.get(table.kind)
    if y_token is not None:
        if y_token not in column_units:
            return None
        y = column_units.index(y_token)
    else:
        # ORCA places the dimensionless oscillator strength immediately after
        # wavelength in both its State and Transition layouts (including old projects).
        y = next((i for i, name in enumerate(table.columns)
                  if name.casefold() == "oscillator strength" or name.casefold().startswith("fosc")), None)
        if y is None:
            if "nm" not in axis:
                return None
            y = axis["nm"] + 1
    preferred = [unit, *(name for name in axis if name != unit)]
    peaks = []
    for row in table.rows:
        if y >= len(row) or not _finite(row[y]):
            continue
        for name in preferred:
            i = axis.get(name)
            if i is None or i >= len(row) or not _finite(row[i]) or (optical and row[i] <= 0):
                continue
            position = _convert(row[i], name, unit)
            if math.isfinite(position):
                peaks.append((position, row[y]))
                break
    if not peaks:
        return None
    width = {"nm": 10.0, "eV": 0.25, _WN: 2000.0 if optical else 20.0}[unit]
    return StickSpectrum(tuple(peaks), unit, units, _LABELS[unit], _STRENGTHS[table.kind],
                         width, table.kind == "ir")


def spectrum_range(peaks, fwhm):
    """Choose display limits that include the outermost line centers and their wings."""
    if not _finite(fwhm) or fwhm <= 0 or not peaks:
        raise ValueError("Provide spectral lines and a positive finite FWHM.")
    low = min(x for x, _ in peaks)
    high = max(x for x, _ in peaks)
    padding = max(4 * fwhm, 0.025 * (high - low), math.ulp(low), math.ulp(high))
    bounds = (low - padding, high + padding)
    if not all(map(math.isfinite, bounds)) or not math.isfinite(bounds[1] - bounds[0]):
        raise ValueError("Spectrum limits exceed the available numeric range.")
    return bounds


def broaden_spectrum(peaks, fwhm, *, shape="gaussian", mix=0.5, normalize=False,
                     x_range=None, points=1201):
    """Sum unit-height lines scaled by the printed (signed) stick strengths.

    FWHM uses the selected x-axis units. The pseudo-Voigt is the linear combination
    of Gaussian and Lorentzian profiles with a common FWHM and Lorentzian fraction
    `mix`. Normalization divides the completed curve by its maximum absolute value.
    The base grid gains local samples when narrow peaks would otherwise disappear.
    """
    if not _finite(fwhm) or fwhm <= 0:
        raise ValueError("FWHM must be positive and finite.")
    if shape not in ("gaussian", "lorentzian", "pseudo-voigt"):
        raise ValueError("Choose a Gaussian, Lorentzian or pseudo-Voigt line shape.")
    if not _finite(mix) or not 0 <= mix <= 1:
        raise ValueError("The Lorentzian fraction must be between zero and one.")
    if type(points) is not int or not 2 <= points <= 20001:
        raise ValueError("Choose between 2 and 20001 sampling points.")
    peaks = tuple(peaks)
    if not all(_finite(x) and _finite(y) for x, y in peaks):
        raise ValueError("Spectrum positions and strengths must be finite.")
    if not peaks:
        return ()
    low, high = spectrum_range(peaks, fwhm) if x_range is None else x_range
    if not (_finite(low) and _finite(high) and low < high and math.isfinite(high - low)):
        raise ValueError("The spectrum limits must be finite and increasing.")
    # Exactly coincident transitions add algebraically before convolution. Keep
    # the original individual sticks for the table, overlay and export.
    summed = {}
    for center, strength in peaks:
        summed.setdefault(center, []).append(strength)
    try:
        active = [(x, y) for x, values in summed.items() if (y := math.fsum(values))]
    except OverflowError as exc:
        raise ValueError("The summed spectrum exceeds the available numeric range.") from exc
    step = (high - low) / (points - 1)
    grid = [low + i * step for i in range(points - 1)] + [high]
    lorentz = {"gaussian": 0.0, "lorentzian": 1.0, "pseudo-voigt": mix}[shape]
    if step > fwhm / 5:
        # Retain peak centers and both half-height positions even at a wide zoom.
        # Each added point is clipped to the requested horizontal range.
        offsets = [fwhm * (i / 8) for i in range(-24, 25)]
        radius = 3 * fwhm
        # Trace a Lorentzian's slow tails through the next base grid interval;
        # connecting the last core sample straight to that node exaggerates them.
        while lorentz and radius < step:
            radius *= 1.5
            offsets.extend((-radius, radius))
        anchors = set(grid)
        for center, _ in active:
            if low - radius <= center <= high + radius:
                local = (center + offset for offset in offsets)
                anchors.update(x for x in local if low <= x <= high)
                if len(anchors) > 100_000:
                    raise ValueError("Too many narrow peaks to resolve. Choose a smaller x range or a larger FWHM.")
        grid = sorted(anchors)
    result = [0.0] * len(grid)
    gaussian_constant = -4 * math.log(2)
    # Refuse an impractically dense interactive plot before spending minutes
    # in the GUI thread. Gaussian support is local; Lorentzian wings span the
    # whole grid, including lines whose centers are outside the selected range.
    work = 0
    for center, _ in active:
        start = bisect_left(grid, center - 16 * fwhm)
        stop = bisect_right(grid, center + 16 * fwhm)
        work += (len(grid) if lorentz else 0) + (stop - start if lorentz < 1 else 0)
        if work > 12_000_000:
            raise ValueError("Spectrum sampling is too dense. Narrow the x range or use fewer sampling points.")
    for center, strength in active:
        if lorentz:
            for i, x in enumerate(grid):
                z = 2 * ((x - center) / fwhm)
                result[i] += (lorentz * strength) / (1 + z * z)
        if lorentz < 1:
            # At 16 FWHM the Gaussian is below 10^-308 of its peak height.
            start = bisect_left(grid, center - 16 * fwhm)
            stop = bisect_right(grid, center + 16 * fwhm)
            height = (1 - lorentz) * strength
            for i in range(start, stop):
                z = (grid[i] - center) / fwhm
                result[i] += height * math.exp(gaussian_constant * z * z)
    if not all(map(math.isfinite, result)):
        raise ValueError("The summed spectrum exceeds the available numeric range.")
    if normalize:
        maximum = max(map(abs, result))
        if maximum:
            result = [y / maximum for y in result]
    return tuple(zip(grid, result))
