"""ORCA orbital-set identity and sidecar names, independent of the GBW binary layout."""

from pathlib import Path


ORCA_ORBITAL_SUFFIXES = {
    ".gbw": "mo", ".qro": "qro", ".unso": "unso", ".uno": "uno", ".uco": "uco",
    ".loc": "localized", ".nat": "natural", ".mp2nat": "natural", ".mdcinat": "natural",
}
ORBITAL_SET_LABELS = {
    "mo": "Molecular orbitals", "qro": "Quasi-restricted orbitals (QRO)",
    "unso": "Natural spin-density orbitals (UNSO)", "uno": "Unrestricted natural orbitals (UNO)",
    "uco": "Unrestricted corresponding orbitals (UCO)", "localized": "Localized orbitals",
    "natural": "Natural orbitals",
}


def orbital_kind(path):
    if path is None:
        return "mo"
    name = Path(path).name.lower()
    for ending in (".molden.input", ".molden", ".mld", ".gbw"):
        if name.endswith(ending):
            name = name[:-len(ending)]
            break
    return ORCA_ORBITAL_SUFFIXES.get(Path(name).suffix, "mo")


def molden_destination(path):
    # Different ORCA orbital sets often share a directory and a basename.
    if path.suffix.lower() == ".gbw":
        return path.with_suffix(".molden.input")
    return path.with_name(path.name + ".molden.input")
