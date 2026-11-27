"""An affine volumetric lattice with Cartesian positions in angstroms."""

from dataclasses import dataclass
from functools import cached_property
import math


def _cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])


@dataclass(frozen=True)
class VolumeGrid:
    shape: tuple
    origin: tuple
    steps: tuple

    def __post_init__(self):
        if len(self.shape) != 3 or min(self.shape) < 2:
            raise ValueError("A 3D grid requires at least two points along each axis.")
        scale = math.prod(math.hypot(*step) for step in self.steps)
        if not math.isfinite(scale) or not math.isfinite(self.determinant) or abs(self.determinant) <= 1e-12*scale:
            raise ValueError("The volume grid axes must be linearly independent.")

    @cached_property
    def determinant(self):
        a, b, c = self.steps
        return sum(x*y for x, y in zip(a, _cross(b, c)))

    @cached_property
    def reciprocal(self):
        a, b, c = self.steps
        return tuple(tuple(x/self.determinant for x in v) for v in (_cross(b, c), _cross(c, a), _cross(a, b)))

    def point(self, x, y, z):
        return tuple(o + x*a + y*b + z*c for o, a, b, c in zip(self.origin, *self.steps))
