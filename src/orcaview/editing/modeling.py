"""Prepare a modeling command for one immutable editing revision."""

from .commands import AddHydrogens, OptimizeCoordinates, SetSketchLayout
from .hydrogens import missing_hydrogens
from .hydrogen_bonds import optimize_hydrogen_bonds
from .optimization import clean_sketch, optimize_structure


def modeling_operation(snapshot, mode, **options):
    molecule = snapshot.molecule
    if mode == "HB":
        return optimize_hydrogen_bonds(snapshot, **options)
    if mode == "H":
        added, perceived = missing_hydrogens(molecule)
        return AddHydrogens(tuple((snapshot.atom_ids[i], atom) for i, atom in added), perceived)
    if mode == "2D":
        return SetSketchLayout(clean_sketch(molecule, snapshot.sketch_xy))
    if mode == "3D":
        result = optimize_structure(molecule, mode)
        xyz = tuple((atom.x, atom.y, atom.z) for atom in result.molecule.atoms)
        implicit = not (molecule.bonds or molecule.bonds_explicit)
        return OptimizeCoordinates(result.method, xyz, result.molecule.bonds if implicit else None)
    raise ValueError("Unknown modeling operation")
