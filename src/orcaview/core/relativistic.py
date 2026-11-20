"""Matched scalar-relativistic basis and Hamiltonian pairs from ORCA 6.1.1.

Section 2.7 also catalogs DKH3 and two-component contractions. Section 2.12
implements DKH1/2, ZORA and scalar X2C for molecular input.
"""

from ._basis_library import BASIS_HAMILTONIANS, ORBITAL_COVERAGE


SCALAR_BASES = {
    name: (model, ORBITAL_COVERAGE[name])
    for name, model in BASIS_HAMILTONIANS.items()
    if model in ("DKH2", "ZORA", "X2C")
}
