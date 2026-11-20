"""Emit independent analytic and integration references for two Molden fixtures."""

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Fixture:
    path: str
    sha256: str
    center: tuple[float, float, float]
    exponent: float
    electrons: int
    spin_electrons: int


FIXTURES = (
    Fixture(
        "helium-closed.molden",
        "6126c3671c992939227355c4ec44dd167060f4c6a34b60100cf9841bebab2732",
        (0.0, 0.0, 0.0),
        0.75,
        electrons=2,
        spin_electrons=0,
    ),
    Fixture(
        "hydrogen-open.molden",
        "c25fa59aebc1903b088bb8b87631af7a91dadbaeb08eda8ddd44093fa2a3de72",
        (0.4, -0.3, 0.2),
        1.125,
        electrons=1,
        spin_electrons=1,
    ),
)

POINTS_BOHR = (
    (0.0, 0.0, 0.0),
    (0.4, -0.3, 0.2),
    (0.7, -0.8, 0.6),
    (-0.5, 1.2, 0.9),
    (2.5, 3.0, -3.5),
)


def gaussian_value(amplitude, exponent, displacement):
    radius_squared = math.fsum(component**2 for component in displacement)
    return amplitude * math.exp(-exponent * radius_squared)


def gaussian_fields(amplitude, exponent, displacement):
    value = gaussian_value(amplitude, exponent, displacement)
    curvature = -2.0 * exponent
    gradient = [curvature * component * value for component in displacement]
    hessian = [
        [
            (curvature * int(row == column) + curvature**2 * x * y) * value
            for column, y in enumerate(displacement)
        ]
        for row, x in enumerate(displacement)
    ]
    return {
        "value": value,
        "gradient": gradient,
        "hessian": hessian,
        "laplacian": math.fsum(hessian[axis][axis] for axis in range(3)),
    }


def verify_derivatives(amplitude, exponent, displacement, fields):
    step = 0.0001

    def shifted(*offsets):
        point = list(displacement)
        for axis, amount in offsets:
            point[axis] += amount
        return gaussian_value(amplitude, exponent, point)

    for row in range(3):
        plus = shifted((row, step))
        minus = shifted((row, -step))
        gradient = (plus - minus) / (2.0 * step)
        if abs(gradient - fields["gradient"][row]) > 1e-7:
            raise ValueError("Analytic gradient differs from central finite difference")
        diagonal = (plus - 2.0 * fields["value"] + minus) / step**2
        if abs(diagonal - fields["hessian"][row][row]) > 1e-6:
            raise ValueError("Analytic diagonal Hessian differs from central finite difference")
        for column in range(row):
            mixed = (
                shifted((row, step), (column, step))
                - shifted((row, step), (column, -step))
                - shifted((row, -step), (column, step))
                + shifted((row, -step), (column, -step))
            ) / (4.0 * step**2)
            if abs(mixed - fields["hessian"][row][column]) > 1e-6:
                raise ValueError("Analytic mixed Hessian differs from central finite difference")


def radial_integral(amplitude, exponent):
    """Composite Simpson integration of a one-center field over a radius-10 sphere."""
    panels = 4096
    spacing = 10.0 / panels

    def weighted_value(index):
        radius = index * spacing
        weight = 1 if index in (0, panels) else 4 if index % 2 else 2
        return weight * radius**2 * gaussian_value(amplitude, exponent, (radius, 0.0, 0.0))

    return (4.0 * math.pi / 3.0) * spacing * math.fsum(
        weighted_value(index) for index in range(panels + 1)
    )


def reference(fixture):
    source = Path(__file__).with_name(fixture.path)
    if hashlib.sha256(source.read_bytes()).hexdigest() != fixture.sha256:
        raise ValueError(f"Fixture SHA-256 mismatch for {fixture.path}")

    alpha = fixture.exponent
    orbital_amplitude = (2.0 * alpha / math.pi) ** 0.75
    density_amplitude = fixture.electrons * orbital_amplitude**2
    spin_amplitude = fixture.spin_electrons * orbital_amplitude**2
    fields = {
        "spatial_orbital": (orbital_amplitude, alpha),
        "total_density": (density_amplitude, 2.0 * alpha),
        "spin_density": (spin_amplitude, 2.0 * alpha),
    }
    points = []
    for position in POINTS_BOHR:
        displacement = tuple(value - center for value, center in zip(position, fixture.center))
        sample = {"position_bohr": position}
        for name, (amplitude, exponent) in fields.items():
            sample[name] = gaussian_fields(amplitude, exponent, displacement)
            verify_derivatives(amplitude, exponent, displacement, sample[name])
        points.append(sample)

    integrals = {
        "orbital_norm_squared": radial_integral(orbital_amplitude**2, 2.0 * alpha),
        "total_electrons": radial_integral(density_amplitude, 2.0 * alpha),
        "alpha_minus_beta_electrons": radial_integral(spin_amplitude, 2.0 * alpha),
    }
    for name, expected in (
        ("orbital_norm_squared", 1.0),
        ("total_electrons", fixture.electrons),
        ("alpha_minus_beta_electrons", fixture.spin_electrons),
    ):
        if abs(integrals[name] - expected) > 1e-12:
            raise ValueError(f"Unexpected quadrature result for {fixture.path}: {name}")
    return {
        "source": fixture.path,
        "sha256": fixture.sha256,
        "center_bohr": fixture.center,
        "exponent_bohr_inverse_squared": alpha,
        "points": points,
        "integrals": integrals,
    }


if __name__ == "__main__":
    print(json.dumps(
        {
            "source_kind": "synthetic-analytic-reference",
            "axes": ["x", "y", "z"],
            "fixtures": [reference(fixture) for fixture in FIXTURES],
        },
        indent=2,
        allow_nan=False,
    ))
