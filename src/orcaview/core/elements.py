"""Atomic numbers, radii and colors used to display atoms."""

_SYMBOLS = (
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn "
    "Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce "
    "Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn "
    "Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og"
).split()
ATOMIC_NUMBERS = {symbol: index + 1 for index, symbol in enumerate(_SYMBOLS)}

# Open Babel 3.2, OBElements::GetVdwRad (angstroms, in atomic-number order).
# Keep the GUI's space-filling projection independent of the native worker.
VDW_RADII = dict(zip(_SYMBOLS, (
    1.10, 1.40, 1.81, 1.53, 1.92, 1.70, 1.55, 1.52, 1.47, 1.54,
    2.27, 1.73, 1.84, 2.10, 1.80, 1.80, 1.75, 1.88, 2.75, 2.31,
    2.30, 2.15, 2.05, 2.05, 2.05, 2.05, 2.00, 2.00, 2.00, 2.10,
    1.87, 2.11, 1.85, 1.90, 1.83, 2.02, 3.03, 2.49, 2.40, 2.30,
    2.15, 2.10, 2.05, 2.05, 2.00, 2.05, 2.10, 2.20, 2.20, 1.93,
    2.17, 2.06, 1.98, 2.16, 3.43, 2.68, 2.50, 2.48, 2.47, 2.45,
    2.43, 2.42, 2.40, 2.38, 2.37, 2.35, 2.33, 2.32, 2.30, 2.28,
    2.27, 2.25, 2.20, 2.10, 2.05, 2.00, 2.00, 2.05, 2.10, 2.05,
    1.96, 2.02, 2.07, 1.97, 2.02, 2.20, 3.48, 2.83, 2.00, 2.40,
    2.00, 2.30, 2.00, 2.00, 2.00, 2.00, 2.00, 2.00, 2.00, 2.00,
    2.00, 2.00, 2.00, 2.00, 2.00, 2.00, 2.00, 2.00, 2.00, 2.00,
    2.00, 2.00, 2.00, 2.00, 2.00, 2.00, 2.00, 2.00,
)))

# Radii in angstroms are for display, independent of bond order.
COVALENT_RADII = {
    "H": 0.31, "He": 0.28, "Li": 1.28, "Be": 0.96, "B": 0.84,
    "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "Ne": 0.58,
    "Na": 1.66, "Mg": 1.41, "Al": 1.21, "Si": 1.11, "P": 1.07,
    "S": 1.05, "Cl": 1.02, "K": 2.03, "Ca": 1.76, "Fe": 1.32,
    "Co": 1.26, "Ni": 1.24, "Cu": 1.32, "Zn": 1.22,
    "Br": 1.20, "I": 1.39, "Pt": 1.36, "Au": 1.36,
}
ELEMENT_COLORS = {
    "H": "#F3F3EE", "C": "#586770", "N": "#4E80D1", "O": "#D75147",
    "F": "#4ADE80", "Cl": "#22C55E", "Br": "#A16207", "I": "#A855F7",
    "P": "#F97316", "S": "#EAB308", "Fe": "#D97706",
}
