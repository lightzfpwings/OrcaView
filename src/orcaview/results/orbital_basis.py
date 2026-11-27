"""Normalized Cartesian and real solid-harmonic Gaussians in Molden AO order."""

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
import math

from orcaview.core.units import BOHR_IN_ANGSTROM


_CARTESIAN = (
    ("",), ("x", "y", "z"), ("xx", "yy", "zz", "xy", "xz", "yz"),
    ("xxx", "yyy", "zzz", "xyy", "xxy", "xxz", "xzz", "yzz", "yyz", "xyz"),
    ("xxxx", "yyyy", "zzzz", "xxxy", "xxxz", "xyyy", "yyyz", "xzzz", "yzzz",
     "xxyy", "xxzz", "yyzz", "xxyz", "xyyz", "xyzz"),
)


def _odd_factorial(power):
    return math.prod(range(1, 2 * power, 2))


def _solid_harmonic(l, m):
    # Expand (x+iy)^m r^(l-m) P_l^(m)(z/r), using the mth derivative
    # of Legendre's polynomial. Real and imaginary parts are the two tesseral AOs.
    f = math.factorial
    norm = math.sqrt((2 if m else 1) * f(l - m) / f(l + m)) / 2**l
    terms = defaultdict(complex)
    for k in range((l - m) // 2 + 1):
        z_power = l - 2*k - m
        legendre = norm * (-1)**k * f(2*l - 2*k) / (f(k) * f(l-k) * f(z_power))
        for a in range(k + 1):
            for b in range(k - a + 1):
                c = k - a - b
                radial = legendre * f(k) / (f(a) * f(b) * f(c))
                for j in range(m + 1):
                    powers = (2*a + m-j, 2*b + j, 2*c + z_power)
                    terms[powers] += radial * math.comb(m, j) * 1j**j
    return terms


@lru_cache(maxsize=None)
def angular_functions(l, spherical, orca):
    if l < 2 or not spherical:
        if l >= len(_CARTESIAN):
            raise ValueError("Cartesian Molden shells above g are unsupported.")
        functions = []
        for label in _CARTESIAN[l]:
            powers = tuple(label.count(axis) for axis in "xyz")
            factor = math.sqrt(_odd_factorial(l) / math.prod(_odd_factorial(n) for n in powers))
            functions.append(((powers, factor),))
        return tuple(functions)
    functions = []
    for m in range(l + 1):
        terms = _solid_harmonic(l, m)
        # orca_2mkl retains ORCA's phases for the +/-3 and +/-4 components.
        sign = -1 if orca and m in (3, 4) else 1
        functions.append(tuple((p, sign*v.real) for p, v in terms.items() if v.real))
        if m:
            functions.append(tuple((p, sign*v.imag) for p, v in terms.items() if v.imag))
    return tuple(functions)


@dataclass(frozen=True)
class GaussianShell:
    center: tuple
    primitives: tuple
    functions: tuple

    @classmethod
    def from_molden(cls, atom, l, rows, spherical, orca):
        # ORCA writes primitive normalization into the contraction coefficients.
        # Remove its exponent dependence, then normalize the radial contraction by
        # its analytic overlap. Angular normalization is relative to x^l.
        power = .75 + .5*l
        weights = [(a, c / a**power if orca else c) for a, c in rows]
        norm2 = math.fsum(c*d * (2*math.sqrt(a*b)/(a+b))**(l+1.5)
                          for a, c in weights for b, d in weights)
        if not math.isfinite(norm2) or norm2 <= 0:
            raise ValueError("Invalid Molden Gaussian contraction norm.")
        scale = (2 / math.pi)**.75 * 2**l / math.sqrt(_odd_factorial(l)*norm2)
        primitives = tuple((a, scale * c * a**power) for a, c in weights)
        center = tuple(v / BOHR_IN_ANGSTROM for v in (atom.x, atom.y, atom.z))
        return cls(center, primitives, angular_functions(l, spherical, orca))


def orbital_expansion(shells, coefficients):
    """Contract a single MO into one angular polynomial per occupied basis shell."""
    expansion = []
    offset = 0
    for shell in shells:
        polynomial = defaultdict(float)
        for function in shell.functions:
            coefficient = coefficients[offset]
            offset += 1
            if coefficient:
                for powers, factor in function:
                    polynomial[powers] += coefficient * factor
        terms = tuple((powers, value) for powers, value in polynomial.items() if value)
        if terms:
            expansion.append((shell.center, shell.primitives, terms))
    return tuple(expansion)


def orbital_value(expansion, x, y, z):
    """Signed MO amplitude at one Cartesian point in bohr, in bohr^(-3/2)."""
    total = 0.
    for (cx, cy, cz), primitives, terms in expansion:
        dx, dy, dz = x-cx, y-cy, z-cz
        r2 = dx*dx + dy*dy + dz*dz
        radial = sum(c * math.exp(-a*r2) for a, c in primitives)
        total += radial * sum(v * dx**i * dy**j * dz**k for (i, j, k), v in terms)
    return total
