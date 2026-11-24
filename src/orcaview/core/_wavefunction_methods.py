"""ORCA 6.1.1 simple-input methods from manual sections 3.5, 3.6, 3.9 and 3.10.

https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/semiempirical.html
https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/3cmethods.html
https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/MP2.html
https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mdci.html
"""


OTHER_METHOD_GROUPS = (
    ("3c composite methods", (
        ("HF-3c", "fixed"),
        ("B97-3c", "fixed"),
        ("r2SCAN-3c", "fixed"),
        ("PBEh-3c", "fixed"),
        ("B3LYP-3c", "fixed"),
        ("wB97X-3c", "fixed"),
    )),
    ("Semiempirical NDDO", (
        ("MNDO", "semiempirical"),
        ("AM1", "semiempirical"),
        ("PM3", "semiempirical"),
    )),
    ("Native xTB", (
        ("Native-GFN1-xTB", "semiempirical"),
        ("Native-GFN2-xTB", "semiempirical"),
        ("Native-spGFN1-xTB", "semiempirical"),
        ("Native-spGFN2-xTB", "semiempirical"),
    )),
    ("Perturbation theory", (
        ("MP2", "numeric-freq"),
        ("SCS-MP2", "numeric-freq"),
        ("RI-MP2", "mp2-aux"),
        ("RI-SCS-MP2", "mp2-aux"),
        ("RI-SOS-MP2", "mp2-aux"),
        ("OO-RI-MP2", "mp2-aux"),
        ("OO-RI-SCS-MP2", "mp2-aux"),
        ("OO-RI-SOS-MP2", "mp2-aux"),
        # The UHF implementation of DLPNO-MP2 only supplies energies.
        ("DLPNO-MP2", "sp-aux"),
        ("DLPNO-SCS-MP2", "sp-aux"),
        ("DLPNO-SOS-MP2", "sp-aux"),
        ("MP3", "sp"),
        ("SCS-MP3", "sp"),
    )),
    ("Coupled cluster", (
        ("CCSD", "sp"),
        ("CCSD(T)", "sp"),
        ("RI-CCSD", "sp-aux"),
        ("RI-CCSD(T)", "sp-aux"),
        ("pCCSD/1a", "sp"),
        ("pCCSD/2a", "sp"),
        ("DLPNO-CCSD", "sp-aux"),
        ("DLPNO-CCSD(T)", "sp-aux"),
        ("DLPNO-CCSD(T1)", "sp-aux"),
        ("DLPNO-pCCSD/1a", "sp-aux"),
    )),
    ("Configuration interaction and electron-pair methods", (
        ("CISD", "sp"),
        ("QCISD", "sp"),
        ("QCISD(T)", "sp"),
        ("DLPNO-CISD", "sp-aux"),
        ("DLPNO-QCISD", "sp-aux"),
        ("ACPF", "sp"),
        ("NACPF", "sp"),
        ("AQCC", "sp"),
        ("CEPA/1", "sp"),
        ("CEPA/2", "sp"),
        ("CEPA/3", "sp"),
        ("NCEPA/1", "sp"),
        ("NCEPA/2", "sp"),
        ("NCEPA/3", "sp"),
        ("CPF/1", "sp"),
        ("CPF/2", "sp"),
        ("CPF/3", "sp"),
        ("NCPF/1", "sp"),
        ("NCPF/2", "sp"),
        ("NCPF/3", "sp"),
    )),
)

# §3.5.1 tables 3.22–3.23. CNDO/INDO require %method selectors.
# The spectroscopic S parameterizations are restricted to fixed nuclei.
NDO_BLOCK = {f"{name}/{variant}": f"{name}_{variant}" for name in ("CNDO", "INDO")
             for variant in ("1", "2", "S")}
EXTRA_NDO_GROUPS = (("Semiempirical CNDO, INDO and ZNDDO", tuple(
    (name, "semiempirical-sp" if name.endswith("/S") else "semiempirical")
    for name in (*NDO_BLOCK, "ZINDO/1", "ZINDO/2", "ZINDO/S", "ZNDDO/1", "ZNDDO/2")
)),)

# §3.10.2 lists RHF and UHF references. The RI simple keywords additionally
# select KC_RI, which is unavailable for UHF (§3.10.14).
RI_CANONICAL_CC = ("RI-CCSD", "RI-CCSD(T)")
CANONICAL_MDCI = frozenset(name for family, entries in OTHER_METHOD_GROUPS
                           if family in ("Coupled cluster", "Configuration interaction and electron-pair methods")
                           for name, _ in entries if not name.startswith("DLPNO-"))

# The 6.1.1 manual lists the 3c ranges individually in section 3.6.
# The original GFN1 and GFN2 parameter sets cover elements through Rn.
# https://doi.org/10.1021/acs.jctc.7b00118
# https://doi.org/10.1021/acs.jctc.8b01176
METHOD_MAX_Z = {
    "ADFT(HF)": 36,
    "ADFT(CC)": 30,
    "GFN0-xTB": 86, "GFN1-xTB": 86, "GFN2-xTB": 86, "GFN-FF": 86,
    "HF-3c": 94,
    "B97-3c": 94,
    "r2SCAN-3c": 103,
    "PBEh-3c": 94,
    "B3LYP-3c": 94,
    "wB97X-3c": 86,
    "Native-GFN1-xTB": 86,
    "Native-GFN2-xTB": 86,
    "Native-spGFN1-xTB": 86,
    "Native-spGFN2-xTB": 86,
}

# A conservative common subset of the published MNDO, AM1 and PM3
# parameters. Section 3.5.1 describes ORCA's main-group implementation.
_NDDO_ELEMENTS = frozenset("H C N O F Si P S Cl Br I".split())
METHOD_ELEMENTS = {
    "MNDO": _NDDO_ELEMENTS,
    "AM1": _NDDO_ELEMENTS,
    "PM3": _NDDO_ELEMENTS,
}

