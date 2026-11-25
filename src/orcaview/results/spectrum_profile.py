"""Shared spectrum plotting parameters, sampling and CSV export."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from io import StringIO

from orcaview.results.broadening import StickSpectrum, broaden_spectrum, spectrum_range


@dataclass
class PlotStyle:
    reverse: bool
    layers: str = "both"
    grid: bool = True
    normalized: bool = False
    color: str = "#365987"
    stroke_width: float = 2.0


@dataclass
class PlotProfile:
    source: StickSpectrum
    curve: tuple[tuple[float, float], ...]
    limits: tuple[float, float]
    shape: str
    fwhm: float
    mix: float
    peak_height: float
    points: int = 1201

    @classmethod
    def setup(cls, source, shape, fwhm, mix, limits=None, points=1201):
        if limits is None:
            limits = spectrum_range(source.peaks, fwhm)
            if len(source.units) > 1:
                limits = max(0.0, limits[0]), limits[1]
        return cls(source, (), limits, shape, fwhm, mix, 0., points)

    def scale(self, style):
        if style.normalized and self.peak_height:
            return self.peak_height
        return 1.0

    def sampled(self):
        curve = broaden_spectrum(self.source.peaks, self.fwhm, shape=self.shape, mix=self.mix,
                                 x_range=self.limits, points=self.points)
        return replace(self, curve=curve, peak_height=max((abs(y) for _, y in curve), default=0.0))


def spectrum_csv(source, curve=None, *, scale=1.0, normalized=False):
    """Keep printed stick values verbatim; scale only the sampled curve."""
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow([f"{source.x_label} ({source.unit})",
                     "Relative height" if curve is not None and normalized else source.y_label])
    writer.writerows(source.peaks if curve is None else ((x, y / scale) for x, y in curve))
    return stream.getvalue()
