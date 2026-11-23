"""Planar sketch cleanup and local, topology-preserving molecular mechanics."""

from dataclasses import dataclass, replace
import json
import math
from statistics import median

from orcaview.core.geometry import display_bonds
from orcaview.core.models import Atom, Molecule
from orcaview.io.babel_geometry import build_obmol, geometry_payload
from orcaview.io.babel_structure import run_babel_worker


@dataclass(frozen=True)
class OptimizationResult:
    molecule: Molecule
    method: str


def _calculate_points(molecule, mode):
    payload = geometry_payload(molecule)
    payload["infer_orders"] = not molecule.bonds and not molecule.bonds_explicit
    if not payload["bonds"]:
        raise ValueError("结构优化需要至少一条化学键")
    if mode == "3D" and (molecule.charge != 0 or molecule.multiplicity != 1):
        raise ValueError("三维力场优化当前支持中性单重态结构")
    response = run_babel_worker(json.dumps(payload, allow_nan=False).encode(), "optimize-" + mode.lower())
    rows = response.get("atoms", [])
    methods = ("gen2D",) if mode == "2D" else ("MMFF94", "UFF")
    if response.get("method") not in methods or not isinstance(rows, list) or len(rows) != len(molecule.atoms):
        raise ValueError("Open Babel 返回的原子映射或优化方法无效")
    points = []
    for source, row in zip(molecule.atoms, rows):
        if not isinstance(row, (list, tuple)) or len(row) != 4 or row[0] != source.element:
            raise ValueError("Open Babel 返回的原子映射或优化方法无效")
        xyz = row[1:]
        if not all(type(v) in (int, float) and math.isfinite(v) for v in xyz):
            raise ValueError("Open Babel 返回无效坐标")
        points.append(xyz)
    return points, response


def _zigzag_chain(molecule):
    """Draw a plain, unbranched single-bond backbone in the usual extended zigzag."""
    count = len(molecule.atoms)
    if count < 4 or len(molecule.bonds) != count - 1 or any(
        atom.element not in ("C", "N", "O", "S") for atom in molecule.atoms
    ):
        return None
    neighbors = [[] for _ in molecule.atoms]
    for bond in molecule.bonds:
        if bond.order != 1 or bond.style != "plain":
            return None
        neighbors[bond.a].append(bond.b)
        neighbors[bond.b].append(bond.a)
    ends = [i for i, adjacent in enumerate(neighbors) if len(adjacent) == 1]
    if len(ends) != 2 or any(len(adjacent) not in (1, 2) for adjacent in neighbors):
        return None
    points = [None] * count
    previous, current = None, ends[0]
    for step in range(count):
        points[current] = (step * 1.5 * math.sqrt(3) / 2, (step % 2) * .75)
        following = next((i for i in neighbors[current] if i != previous), None)
        if following is None:
            # A separate ring can coexist with a shorter path.
            return points if step == count - 1 else None
        previous, current = current, following


def clean_sketch(molecule: Molecule, sketch_xy=None):
    """Depict the chemical graph in two dimensions, retaining its position on the page."""
    molecule.validate_structure()
    points = _zigzag_chain(molecule)
    if points is None:
        xyz, _ = _calculate_points(molecule, "2D")
        points = [(x, y) for x, y, _ in xyz]
    reference = sketch_xy if sketch_xy is not None else tuple((a.x, a.y) for a in molecule.atoms)
    if len(reference) != len(points):
        raise ValueError("二维草图坐标与原子数不一致")
    ox, oy = _center(reference)
    cx, cy = _center(points)
    centered = [(x - cx, y - cy) for x, y in points]
    # Best-fit rotation in the drawing plane. Reflection would invert wedge stereochemistry.
    dot = cross = 0.
    for (x, y), (rx, ry) in zip(centered, reference):
        dot += x * (rx - ox) + y * (ry - oy)
        cross += x * (ry - oy) - y * (rx - ox)
    angle = math.atan2(cross, dot)
    cos, sin = math.cos(angle), math.sin(angle)
    layout = tuple((ox + cos * x - sin * y, oy + sin * x + cos * y) for x, y in centered)
    if all(math.dist(p, q) < 1e-9 for p, q in zip(layout, reference)):
        return reference
    return layout


def optimize_structure(molecule: Molecule, mode: str, plane: str = "XY") -> OptimizationResult:
    """Return a detached geometry; the editor uses clean_sketch for drawing-only edits."""
    if mode not in ("2D", "3D") or plane not in ("XY", "XZ", "YZ"):
        raise ValueError("请选择有效的结构优化方式和投影平面")
    points, response = _calculate_points(molecule, mode)
    if mode == "2D":
        axes = tuple("XYZ".index(axis) for axis in plane)
        planar = []
        for x, y, _ in points:
            point = [0., 0., 0.]
            point[axes[0]], point[axes[1]] = x, y
            planar.append(point)
        points = planar
    # Keep the viewport centered on the edited object. Discard any arbitrary
    # translation introduced by the native builder or 2D depiction engine.
    old_center = _center([(a.x, a.y, a.z) for a in molecule.atoms])
    new_center = _center(points)
    atoms = tuple(Atom(atom.element, *(v - n + o for v, n, o in zip(point, new_center, old_center)))
                  for atom, point in zip(molecule.atoms, points))
    bonds = display_bonds(molecule)
    if not molecule.bonds and not molecule.bonds_explicit:
        orders = response.get("orders")
        if (not isinstance(orders, list) or len(orders) != len(bonds)
                or any(type(order) is not int or order not in (1, 2, 3) for order in orders)):
            raise ValueError("Open Babel 无法建立当前连接表")
        bonds = tuple(replace(bond, order=order) for bond, order in zip(bonds, orders))
    result = replace(molecule, atoms=atoms, bonds=bonds, bonds_explicit=True)
    result.validate_structure()
    return OptimizationResult(result, response["method"])


def _center(points):
    return tuple(sum(axis) / len(points) for axis in zip(*points))


def _point(atom):
    return atom.GetX(), atom.GetY(), atom.GetZ()


def _plane_axes(points):
    """For coplanar points, drop the coordinate with the largest normal component."""
    offsets = [tuple(v - o for v, o in zip(point, points[0])) for point in points]
    a, b, c = max(offsets, key=lambda v: math.hypot(*v))
    normals = [(b * z - c * y, c * x - a * z, a * y - b * x) for x, y, z in offsets]
    normal = max(normals, key=lambda v: math.hypot(*v))
    length = math.hypot(*normal)
    if length < 1e-9:  # Collinear; retain the axis carrying the largest extent.
        drop = min(range(3), key=lambda i: abs((a, b, c)[i]))
    else:
        if any(abs(sum(v * n for v, n in zip(offset, normal))) > 1e-5 * length for offset in offsets):
            return None
        drop = max(range(3), key=lambda i: abs(normal[i]))
    return tuple(i for i in range(3) if i != drop)


def _perceive_stereo(mol, ob, axes):
    if axes is None:
        mol.SetDimension(3)
        ob.StereoFrom3D(mol, True)
    else:
        # Open Babel reads planar stereochemistry from the XY projection.
        u, v = axes
        for atom in ob.OBMolAtomIter(mol):
            xyz = _point(atom)
            atom.SetVector(xyz[u], xyz[v], 0.)
        mol.SetDimension(2)
        ob.StereoFrom2D(mol, None, True)
    facade = ob.OBStereoFacade(mol)
    configs = {}
    for atom in ob.OBMolAtomIter(mol):
        idx = atom.GetId()
        if facade.HasTetrahedralStereo(idx):
            cfg = facade.GetTetrahedralStereo(idx).GetConfig()
            if cfg.specified and cfg.winding != ob.OBStereo.UnknownWinding:
                configs["tetra", idx] = cfg
    for bond in ob.OBMolBondIter(mol):
        idx = bond.GetId()
        if not bond.IsCisOrTrans() and facade.HasCisTransStereo(idx):
            cfg = facade.GetCisTransStereo(idx).GetConfig()
            if cfg.specified:
                configs["alkene", idx] = cfg
    return configs


def _minimize(mol, ob):
    # Supply implicit hydrogens in the calculation copy for all-atom force
    # fields. Only the input atom IDs are returned to the editor.
    if not mol.AddHydrogens():
        raise ValueError("Open Babel 无法补全力场所需的氢")
    for name in ("MMFF94", "UFF"):
        field = ob.OBForceField.FindForceField(name)
        if field is None or not field.Setup(mol):
            continue
        initial = field.Energy()
        field.ConjugateGradients(500, 1e-6)
        final = field.Energy()
        if (not math.isfinite(initial) or not math.isfinite(final)
                or final > initial + 1e-6 or not field.GetCoordinates(mol)):
            raise ValueError("Open Babel 力场未能得到有效的低能结构")
        return name
    raise ValueError("Open Babel 力场缺少当前结构的参数")


def _prepare_graph(payload, operation, ob):
    work = build_obmol(payload, ob, layout_only=(operation == "optimize-2d"))
    if payload["infer_orders"]:
        # XYZ and quantum outputs describe Cartesian atoms without bond orders.
        # Perceive unsaturation on the supplied edges before moving any atom.
        work.SetDimension(3)
        work.PerceiveBondOrders()
    bonds = [work.GetBond(a + 1, b + 1) for a, b, order in payload["bonds"]]
    if len(bonds) != work.NumBonds() or any(bond is None for bond in bonds):
        raise ValueError("Open Babel 无法建立当前连接表")
    orders = [bond.GetBondOrder() for bond in bonds]
    neutral_valence_limit = {5: 3, 6: 4, 7: 3, 8: 2, 9: 1}
    for atom in ob.OBMolAtomIter(work):
        if operation == "optimize-3d":
            # The editor has no per-atom charge model. Refuse recognized ionic
            # valences, including neutral zwitterions with a quaternary N.
            max_valence = neutral_valence_limit.get(atom.GetAtomicNum())
            if atom.GetFormalCharge() or (max_valence is not None and atom.GetExplicitValence() > max_valence):
                raise ValueError("当前结构需要原子形式电荷，无法可靠地进行力场优化")
        ob.OBAtomAssignTypicalImplicitHydrogens(atom)
    return work, orders


def _draw_2d(work, ob):
    draw = ob.OBOp.FindType("gen2D")
    if draw is None or not draw.Do(work):
        raise ValueError("Open Babel 无法生成二维草图")
    lengths = [bond.GetLength() for bond in ob.OBMolBondIter(work)]
    if not lengths or min(lengths) < 1e-6:
        raise ValueError("Open Babel 无法生成二维草图")
    scale = 1.5 / median(lengths)
    for atom in ob.OBMolAtomIter(work):
        atom.SetVector(atom.GetX() * scale, atom.GetY() * scale, 0.)


def _seed_3d(work, points, ob, planar, stereo):
    # Seed each planar fragment independently to keep their relative
    # placement. Separate() preserves original OBAtom IDs.
    protected_atoms = {idx if kind == "tetra" else work.GetBondById(idx).GetBeginAtom().GetId()
                       for kind, idx in stereo}
    for fragment in work.Separate():
        if fragment.NumAtoms() == 1:
            atom = fragment.GetAtom(1)
            work.GetAtomById(atom.GetId()).SetVector(*points[atom.GetId()])
            continue
        atoms = list(ob.OBMolAtomIter(fragment))
        ids = [a.GetId() for a in atoms]
        reference = None
        if not planar:
            # After explicit H placement a flat saturated ring is no longer an
            # all-planar molecule. Minimizing this sketch as-is can trap its
            # heavy atoms at the planar saddle (e.g. cyclohexane).
            if (not protected_atoms.isdisjoint(ids)
                    or not any(a.GetHyb() == 3 and a.MemberOfRingSize() >= 4 for a in atoms)
                    or _plane_axes([points[a.GetId()] for a in atoms if a.GetAtomicNum() > 1]) is None):
                continue
            reference = ob.OBMol(fragment)
        if not ob.OBBuilder().Build(fragment):
            raise ValueError("Open Babel 无法生成三维初始构象")
        if reference is not None:
            alignment = ob.OBAlign(reference, fragment, True, False)
            if alignment.Align():
                alignment.UpdateCoords(fragment)
        coords = [_point(fragment.GetAtomById(i)) for i in ids]
        center = _center(coords)
        target = _center([points[i] for i in ids])
        for idx, point in zip(ids, coords):
            work.GetAtomById(idx).SetVector(*(p - c + t for p, c, t in zip(point, center, target)))
    work.SetDimension(3)


def optimize_worker(payload, operation):
    """Called only in the native subprocess. The atom IDs index input rows."""
    from openbabel import openbabel as ob
    work, orders = _prepare_graph(payload, operation, ob)
    if operation == "perceive-orders":
        return {"orders": orders}
    points = [row[1:] for row in payload["atoms"]]
    axes = _plane_axes(points)
    original = ob.OBMol(work)
    expected = _perceive_stereo(work, ob, axes)
    wedge_centers = {bond.GetBeginAtom().GetId() for bond in ob.OBMolBondIter(work)
                     if bond.IsWedge() or bond.IsHash()}
    if operation == "optimize-2d":
        if any(kind == "tetra" and idx not in wedge_centers for kind, idx in expected):
            raise ValueError("二维草图无法保留当前四面体手性，请使用三维优化")
        _draw_2d(work, ob)
        method = "gen2D"
    else:
        # UFF tables cover H through Lr. Beyond that, the native implementation
        # can silently reuse an unrelated parameter type while reporting success.
        if any(atom.GetAtomicNum() > 103 for atom in ob.OBMolAtomIter(work)):
            raise ValueError("Open Babel 力场缺少当前结构的参数")
        _seed_3d(work, points, ob, axes is not None, expected)
        method = _minimize(work, ob)
    output = ob.OBMol(original)
    for atom in ob.OBMolAtomIter(output):
        updated = work.GetAtomById(atom.GetId())
        if updated is None or updated.GetAtomicNum() != atom.GetAtomicNum():
            raise ValueError("Open Babel 返回的原子映射或优化方法无效")
        atom.SetVector(*_point(updated))
    if operation == "optimize-3d" and axes is not None:
        # A newly built conformer has an arbitrary spatial orientation. Keep
        # the same visible orientation using every input atom and fixed IDs.
        alignment = ob.OBAlign(original, output, True, False)
        if alignment.Align():
            alignment.UpdateCoords(output)
    rows = []
    for atom in ob.OBMolAtomIter(output):
        xyz = _point(atom)
        if not all(math.isfinite(value) for value in xyz):
            raise ValueError("Open Babel 返回无效坐标")
        rows.append((ob.GetSymbol(atom.GetAtomicNum()), *xyz))
    observed = _perceive_stereo(output, ob, (0, 1) if operation == "optimize-2d" else None)
    if any(key not in observed or observed[key] != cfg for key, cfg in expected.items()):
        raise ValueError("优化会改变原有立体化学，已保留原结构")
    return {"atoms": rows, "method": method, "orders": orders}
