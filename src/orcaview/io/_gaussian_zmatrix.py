"""Place Gaussian Z-matrix centers from bond, angle and signed torsion."""

import math
import re

from ..core.symmetry import _cross
from ._quantum_geometry import atom, number


_VARIABLE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def _variables(text):
    variables = {}
    for line in text.splitlines():
        line = line.split("!", 1)[0].strip()
        if not line or line.lower().rstrip(":") in ("variables", "constants"):
            continue
        fields = line.replace("=", " ").split()
        if len(fields) != 2 or not _VARIABLE.fullmatch(fields[0]):
            break  # following sections may contain basis or other calculation data
        key = fields[0].lower()
        try:
            value = number(fields[1])
        except ValueError:
            break
        if key in variables:
            raise ValueError(f"Gaussian Z 矩阵变量重复定义：{key}")
        variables[key] = value
    return variables


def _value(token, variables):
    try:
        value = number(token)
    except ValueError:
        key = token.lstrip("+-").lower()
        if key not in variables or not re.fullmatch(r"[-+]?[A-Za-z][A-Za-z0-9_]*", token):
            raise ValueError(f"Gaussian Z 矩阵需要数值或已定义变量：{token}") from None
        value = -variables[key] if token.startswith("-") else variables[key]
    if not math.isfinite(value):
        raise ValueError(f"Gaussian Z 矩阵数值必须有限：{token}")
    return value


def _reference(token, labels):
    if token.isdigit():
        index = int(token) - 1
        if index in range(len(labels)):
            return index
    else:
        matches = [i for i, label in enumerate(labels) if label == token.lower()]
        if len(matches) == 1:
            return matches[0]
    raise ValueError(f"Gaussian Z 矩阵需要唯一、已经定义的参考原子：{token}")


def _direction(a, b):
    delta = tuple(y - x for x, y in zip(a, b))
    norm = math.hypot(*delta)
    if norm == 0 or not math.isfinite(norm):
        raise ValueError("Gaussian Z 矩阵的参考原子重合或无法定义方向")
    return tuple(v / norm for v in delta)


def _place(refs, values, degrees):
    if not refs:
        return (0., 0., 0.)
    origin, radius = refs[0], values[0]
    if radius <= 0:
        raise ValueError("Gaussian Z 矩阵键长必须大于零")
    if len(refs) == 1:
        return origin[0], origin[1], origin[2] + radius
    theta = math.radians(values[1]) if degrees else values[1]
    if not 0 <= theta <= math.pi:
        raise ValueError("Gaussian Z 矩阵键角应在 0 到 180° 之间")
    axis = _direction(origin, refs[1])
    # For the third center the first two lie along z; choose the xz plane.
    seed = _direction(refs[1], refs[2]) if len(refs) == 3 else (1., 0., 0.)
    normal = _cross(axis, seed)
    norm = math.hypot(*normal)
    if norm <= 1e-12:
        raise ValueError("Gaussian Z 矩阵的参考原子共线，无法定义二面角，请指定哑原子 X")
    normal = tuple(v / norm for v in normal)
    tangent = _cross(normal, axis)
    phi = values[2] if len(values) == 3 else 0.
    if degrees:
        phi = math.radians(phi)
    # The requested torsion is measured from the new center towards the
    # third reference about the directed central bond (refs[0] → refs[1]).
    return tuple(origin[i] + radius * (math.cos(theta) * axis[i] + math.sin(theta) *
                 (math.cos(phi) * tangent[i] - math.sin(phi) * normal[i])) for i in range(3))


def z_matrix_atoms(rows, definitions, unit, degrees):
    variables = _variables(definitions)
    atoms, centers, labels = [], [], []
    for index, row in enumerate(rows):
        expected = 1 + 2 * min(index, 3)
        if index >= 3 and len(row) == 8 and row[-1] == "0":
            row = row[:-1]  # explicit dihedral format code
        if len(row) != expected:
            raise ValueError("Gaussian Z 矩阵需要键长、键角、二面角及各自的参考原子；暂不支持双键角格式")
        label = re.fullmatch(r"([A-Za-z]{1,2})\d*|(\d+)", row[0])
        if not label:
            raise ValueError(f"无法识别 Gaussian Z 矩阵原子：{row[0]}")
        refs = [_reference(token, labels) for token in row[1::2]]
        if len(refs) != len(set(refs)):
            raise ValueError("Gaussian Z 矩阵的参考原子必须互异")
        xyz = _place([centers[i] for i in refs], [_value(t, variables) for t in row[2::2]], degrees)
        centers.append(xyz)
        labels.append(row[0].lower())
        element = label[1] or label[2]
        if element.lower() != "x":
            atoms.append(atom(element, list(map(str, xyz)), unit))
    return atoms
