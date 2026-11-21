"""Advisory checks on the geometry currently displayed in Design."""

from orcaview.core.models import Molecule
from orcaview.core.geometry import occupied_valences


# The editor has no atom-local formal charges. Include common charged centers
# such as ammonium and hydronium; leave transition-metal coordination open.
_COMMON_BOND_ORDER_LIMITS = {"H": 1, "B": 4, "C": 4, "N": 4, "O": 3, "F": 2}


def design_diagnostics(molecule: Molecule) -> tuple[str, ...]:
    """Report issues on a structurally valid snapshot without rejecting edits."""
    if not molecule.atoms:
        return ()
    issues = []
    try:
        molecule.validate()
    except ValueError as exc:
        issues.append(str(exc))

    # A close contact in a coordinate-only input is not an assigned bond.
    ambiguous = []
    totals = occupied_valences(molecule, molecule.bonds, ambiguous_donors=ambiguous)
    for candidates in ambiguous:
        sites = ", ".join(f"{molecule.atoms[i].element}{i + 1}" for i in candidates)
        issues.append(f"芳香环的加氢位置有歧义，请手动选择其中一个原子加氢：{sites}。")
    for index, (atom, total) in enumerate(zip(molecule.atoms, totals), 1):
        limit = _COMMON_BOND_ORDER_LIMITS.get(atom.element)
        if limit is not None and total > limit:
            issues.append(f"请检查 {atom.element}{index} 的成键：键级总和为 {total:g}，超出常见范围。")
    return tuple(issues)
