"""Length boundaries for molecular coordinates. Molecule always stores Å."""

from ._validation import finite_number

# 2022 CODATA, https://physics.nist.gov/cuu/pdf/wallet_2022.pdf
BOHR_IN_ANGSTROM = 0.529177210544
LENGTH_UNITS = ("angstrom", "bohr")


def convert_length(value: float, source: str, target: str) -> float:
    if source not in LENGTH_UNITS or target not in LENGTH_UNITS:
        raise ValueError("长度单位必须是 angstrom 或 bohr")
    number = finite_number(value, "长度")
    if source == target:
        return number
    result = number * BOHR_IN_ANGSTROM if source == "bohr" else number / BOHR_IN_ANGSTROM
    return finite_number(result, "转换后的长度")
