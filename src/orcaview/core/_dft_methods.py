"""ORCA 6.1.1 ground-state methods selectable with a simple input keyword.

The DFT manual's tables 3.1, 3.2, 3.4, 3.6, 3.8 and 3.9 specify the
keywords. Sections 3.4.2 (VV10), 3.9.5 (RI-MP2 gradients) and 4.6
(vibrational frequencies) specify the derivative profiles.
https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/DensityFunctionalTheory.html
"""

DFT_METHOD_GROUPS = (
    ("Hartree–Fock", (
        ("HF", "standard"),
    )),
    ("局域密度近似（LDA）", (
        ("LDA", "standard"),  # ORCA uses VWN5 by default.
        ("VWN3", "standard"),
        ("PWLDA", "standard"),
        ("HFS", "standard"),
    )),
    ("广义梯度近似（GGA）", (
        ("PBE", "standard"),
        ("BP86", "standard"),
        ("BLYP", "standard"),
        ("OLYP", "standard"),
        ("GLYP", "standard"),
        ("XLYP", "standard"),
        ("PW91", "standard"),
        ("MPWPW", "standard"),
        ("MPWLYP", "standard"),
        ("RPBE", "standard"),
        ("REVPBE", "standard"),
        ("RPW86PBE", "standard"),
        ("PWP", "standard"),
    )),
    ("动能密度泛函（meta-GGA）", (
        ("TPSS", "standard"),
        ("REVTPSS", "standard"),
        ("SCANFUNC", "standard"),  # SCAN alone is a surface-scan keyword.
        ("RSCAN", "standard"),
        ("R2SCAN", "standard"),
        ("M06L", "standard"),
        ("B97M-V", "numeric-freq"),
        ("B97M-D3BJ", "standard"),
        ("B97M-D4", "standard"),
    )),
    ("全局杂化 GGA", (
        ("B3LYP", "standard"),
        ("B3LYP/G", "standard"),  # Gaussian VWN3 convention.
        ("PBE0", "standard"),
        ("B1LYP", "standard"),
        ("O3LYP", "standard"),
        ("X3LYP", "standard"),
        ("B1P86", "standard"),
        ("B3P86", "standard"),
        ("B3PW91", "standard"),
        ("PW1PW", "standard"),
        ("MPW1PW", "standard"),
        ("MPW1LYP", "standard"),
        ("REVPBE0", "standard"),
        ("REVPBE38", "standard"),
        ("BHANDHLYP", "standard"),
    )),
    ("全局杂化 meta-GGA", (
        ("M06", "standard"),
        ("M062X", "standard"),
        ("PW6B95", "standard"),
        ("TPSSH", "standard"),
        ("TPSS0", "standard"),
        ("R2SCANH", "standard"),
        ("R2SCAN0", "standard"),
        ("R2SCAN50", "standard"),
    )),
    ("范围分离杂化泛函", (
        ("CAM-B3LYP", "standard"),
        ("LC-BLYP", "standard"),
        ("LC-PBE", "standard"),
        ("WB97", "standard"),
        ("WB97X", "standard"),
        ("WB97X-V", "numeric-freq"),
        ("WB97X-D3", "standard"),
        ("WB97X-D3BJ", "standard"),
        ("WB97X-D4", "standard"),
        ("WB97X-D4REV", "standard"),
        ("WB97M-V", "numeric-freq"),
        ("WB97M-D3BJ", "standard"),
        ("WB97M-D4", "standard"),
        ("WB97M-D4REV", "standard"),
        ("WR2SCAN", "standard"),
    )),
    ("全局双杂化泛函", (
        ("B2PLYP", "double-hybrid"),
        ("mPW2PLYP", "double-hybrid"),
        ("B2GP-PLYP", "double-hybrid"),
        ("B2K-PLYP", "double-hybrid"),
        ("B2T-PLYP", "double-hybrid"),
        ("B2NC-PLYP", "double-hybrid"),
        ("PWPB95", "double-hybrid"),
        ("PBE-QIDH", "double-hybrid"),
        ("PBE0-DH", "double-hybrid"),
        ("DSD-BLYP/2013", "double-hybrid"),
        ("DSD-PBEP86/2013", "double-hybrid"),
        ("DSD-PBEB95", "double-hybrid"),
        ("REVDSD-PBEP86/2021", "double-hybrid"),
        ("REVDSD-PBEP86-D4/2021", "double-hybrid"),
        ("REVDOD-PBEP86/2021", "double-hybrid"),
        ("REVDOD-PBEP86-D4/2021", "double-hybrid"),
        ("R2SCAN-CIDH", "double-hybrid"),
        ("R2SCAN-QIDH", "double-hybrid"),
        ("R2SCAN0-2", "double-hybrid"),
        ("R2SCAN0-DH", "double-hybrid"),
    )),
    ("范围分离双杂化泛函", (
        ("RSX-QIDH", "double-hybrid"),
        ("RSX-0DH", "double-hybrid"),
        ("WB2PLYP", "double-hybrid"),
        ("WB2GP-PLYP", "double-hybrid"),
        ("WB88PP86", "double-hybrid"),
        ("WPBEPP86", "double-hybrid"),
    )),
)

# Single-point profiles for methods added after the original project format.
# The two historical DSD parameterizations require D3BJ on the simple line.
DSD_D3BJ = {"DSD-BLYP-D3BJ": "DSD-BLYP", "DSD-PBEP86-D3BJ": "DSD-PBEP86"}
EXTRA_DFT_GROUPS = (
    ("原生双杂化泛函（单点）", tuple((name, "sp-aux") for name in (
        "PR2SCAN50", "PR2SCAN69", "KPR2SCAN", "WB97X-2", "WPR2SCAN50", *DSD_D3BJ,
    ))),
)

# §3.3.5 recommends the block form even for parents without a DLPNO-
# prefixed simple keyword. KPR2SCAN needs regularized MP2 (§3.9.18),
# for which the documented algorithms are conventional and RI-MP2.
DLPNO_DOUBLE_HYBRIDS = {
    "DLPNO-" + parent: parent for family, entries in DFT_METHOD_GROUPS + EXTRA_DFT_GROUPS
    if "双杂化" in family for parent, _ in entries if parent != "KPR2SCAN"
}
DLPNO_DFT_GROUP = (("DLPNO 双杂化泛函（单点）", tuple(
    (name, "sp-aux") for name in DLPNO_DOUBLE_HYBRIDS
)),)

# These are names users may enter. Only the canonical keyword is emitted.
DFT_METHOD_ALIASES = {
    "DSD-BLYP D3BJ": "DSD-BLYP-D3BJ", "DSD-PBEP86 D3BJ": "DSD-PBEP86-D3BJ",
    "Pr²SCAN50": "PR2SCAN50", "Pr²SCAN69": "PR2SCAN69", "κPr²SCAN50": "KPR2SCAN",
    "ωPr²SCAN50": "WPR2SCAN50", "ωB97X-2": "WB97X-2",
    "BP": "BP86",
    "LSD": "LDA",
    "VWN": "LDA",
    "VWN5": "LDA",
    "PW-LDA": "PWLDA",
    "SCAN": "SCANFUNC",
    "r²SCAN": "R2SCAN",
    "r²SCANh": "R2SCANH",
    "r²SCAN0": "R2SCAN0",
    "r²SCAN50": "R2SCAN50",
    "M06-L": "M06L",
    "M06-2X": "M062X",
    "B97M-D3(BJ)": "B97M-D3BJ",
    "WB97X-D3(BJ)": "WB97X-D3BJ",
    "WB97M-D3(BJ)": "WB97M-D3BJ",
    "ωB97": "WB97",
    "ωB97X": "WB97X",
    "ωB97X-V": "WB97X-V",
    "ωB97M-V": "WB97M-V",
    "ωB97X-D3": "WB97X-D3",
    "ωB97X-D3(BJ)": "WB97X-D3BJ",
    "ωB97M-D3(BJ)": "WB97M-D3BJ",
    "ωB97X-D4": "WB97X-D4",
    "ωB97M-D4": "WB97M-D4",
    "ωB2PLYP": "WB2PLYP",
    "ωB2GP-PLYP": "WB2GP-PLYP",
}
