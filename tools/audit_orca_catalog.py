"""Exercise each structured method/job and its offered RI, spin-reference and solvent selections.

Run PYTHONPATH=src python3 tools/audit_orca_catalog.py. This is an input-generation
check on a representative molecule, independent of the ORCA executable.
"""
from collections import Counter
from dataclasses import replace

from orcaview.application.session import Session
from orcaview.core.block_options import available_options
from orcaview.core.integrals import basis_options, integral_options
from orcaview.core.methods import (
    ACTIVE_SPACE_METHODS, EXCITED_STATE_METHODS, METHODS, REFERENCE_FUNCTIONAL_METHODS, reference_options,
)
from orcaview.core._state_methods import ROCIS_METHODS, SPIN_FLIP_METHODS
from orcaview.core.models import CalculationSpec
from orcaview.core.solvation import solvation_options
from orcaview.orca.input import render_input


def audit():
    water = Session().molecule
    contexts = 0
    selections = 0
    errors = []
    for method, preset in METHODS.items():
        basis = (basis_options(method) or ("def2-SVP",))[0]
        params = {}
        if method in ACTIVE_SPACE_METHODS:
            params.update(active_electrons=2, active_orbitals=2)
        if method in EXCITED_STATE_METHODS:
            params["nroots"] = 2
        if method in REFERENCE_FUNCTIONAL_METHODS:
            params["reference_functional"] = "B3LYP"
        for job in preset.job_types:
            contexts += 1
            for ri in integral_options(method, job):
                for model in solvation_options(method, job):
                    for reference in reference_options(method, job):
                        triplet = method in (*ROCIS_METHODS, *SPIN_FLIP_METHODS) or reference in ("ROHF", "ROKS")
                        molecule = replace(water, multiplicity=3) if triplet else water
                        spec = CalculationSpec(method=method, basis=basis, job_type=job, wavefunction=reference,
                                               integral_approximation=ri, solvation_model=model,
                                               solvent=None if model == "Gas" else "water", **params)
                        selections += 1
                        try:
                            options = available_options(spec)
                            keys = [(opt.block.lower(), opt.key.lower()) for opt in options]
                            if len(keys) != len(set(keys)):
                                raise ValueError("duplicate structured field")
                            if job == "SP" and any(block == "geom" for block, _ in keys):
                                raise ValueError("geometry optimizer field is active in a single point")
                            text = render_input(molecule, spec)
                            headers = Counter(s.lower().split()[0] for s in text.splitlines() if s.startswith("%"))
                            if any(n > 1 for n in headers.values()):
                                raise ValueError(f"duplicate native blocks: {headers}")
                            if job == "SP" and "%geom" in headers:
                                raise ValueError("geometry optimizer block in a single point")
                        except ValueError as exc:
                            errors.append((method, job, ri, reference, model, str(exc)))
    print(f"{len(METHODS)} presets, {contexts} method/job combinations, {selections} input combinations")
    if errors:
        for error in errors[:40]:
            print(*error, sep=" | ")
        raise SystemExit(f"{len(errors)} errors")


if __name__ == "__main__":
    audit()
