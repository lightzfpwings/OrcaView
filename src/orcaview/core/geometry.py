"""仅用于可视化的距离连键，不进行价态、芳香性或键级感知。"""

import math
from typing import Tuple

from .elements import COVALENT_RADII
from .models import Bond, Molecule


def infer_bonds(molecule: Molecule) -> Tuple[Bond, ...]:
    molecule.validate_structure()
    bonds = []
    for i, first in enumerate(molecule.atoms):
        for j in range(i + 1, len(molecule.atoms)):
            second = molecule.atoms[j]
            distance = math.sqrt((first.x - second.x) ** 2 + (first.y - second.y) ** 2 + (first.z - second.z) ** 2)
            cutoff = 1.20 * (COVALENT_RADII.get(first.element, 0.85) + COVALENT_RADII.get(second.element, 0.85))
            if 0.1 < distance <= cutoff:
                bonds.append(Bond(i, j))
    return tuple(bonds)
