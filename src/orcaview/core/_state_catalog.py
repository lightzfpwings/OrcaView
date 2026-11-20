"""ORCA 6.1.1 state-method presets, grouped by the scientific output."""

# Label, basis profile. "sp-aux" requests a matching correlation fitting basis.
_CAS = (
    ("CASSCF", "sp"), ("CASCI", "sp"),
    ("ICE-CASSCF", "sp"), ("ICE-CASCI", "sp"), ("DMRG-CASSCF", "sp"), ("DMRG-CASCI", "sp"),
)
# Tables 3.47–3.49 specify the literal simple keywords. The CI variants
# diagonalize the linearized Hamiltonian of a state-averaged reference.
_MCPDFT = ("tLDA", "tPBE", "tPBE0", "ctLDA", "ctPBE", "ctPBE0")
_SRDFT = ("srLDA", "srPBE", "srPBE0", "sr-ctLDA", "sr-ctPBE", "sr-ctPBE0")
_CI_DFT = tuple("CI-" + name for name in (*_MCPDFT[3:], *_SRDFT))
CASDFT_METHODS = _MCPDFT + _SRDFT + _CI_DFT
_SA_CAS = ("SA-CASSCF", "SA-SC-NEVPT2", "QD-SC-NEVPT2")
MULTIROOT_CAS_METHODS = _SA_CAS + _CI_DFT
MCRPA_METHODS = ("MCRPA", "MCTDA")
_CAS_PT = (
    ("SC-NEVPT2", "sp"), ("RI-NEVPT2", "sp-aux"),
    ("FIC-NEVPT2", "sp"), ("DLPNO-NEVPT2", "sp-aux"),
    ("CASPT2", "sp"), ("RI-CASPT2", "sp-aux"),
    ("CASPT2K", "sp"), ("RI-CASPT2K", "sp-aux"),
    ("DCD-CAS(2)", "sp"), ("RI-DCD-CAS(2)", "sp-aux"),
)
_CAS_AUTOCI = (
    ("FIC-MRCI", "sp"), ("FIC-CEPA(0)", "sp"), ("FIC-ACPF", "sp"),
    ("FIC-AQCC", "sp"), ("FIC-DDCI3", "sp"), ("FIC-MRCC", "sp"),
    ("FIC-NEVPT3", "sp"), ("FIC-NEVPT4(SD)", "sp"),
)
_MRCI_NAMES = "MRCI MRCI+Q MRACPF MRAQCC MRDDCI1 MRDDCI2 MRDDCI3 MRDDCI1+Q MRDDCI2+Q MRDDCI3+Q SORCI".split()
_UNCONTRACTED = tuple((name, "sp") for name in _MRCI_NAMES) + tuple(
    ("RI-" + name, "sp-aux") for name in _MRCI_NAMES)
MREOM_METHODS = ("MR-EOM", "MR-EOM-T|Td", "MR-EOM-T|Td|SXD", "MR-EOM-MRPT")
ROCIS_METHODS = ("ROCIS", "RI-ROCIS", "ROCIS/DFT", "RI-ROCIS/DFT")
_MREOM = tuple((name, "sp") for name in MREOM_METHODS)
_ROCIS = tuple((name, "sp-aux" if name.startswith("RI-") else "sp") for name in ROCIS_METHODS)
_RESPONSE = (
    ("TD-DFT", "sp"), ("TDA-DFT", "sp"), ("CIS", "sp"), ("TD-HF", "sp"),
    ("CIS(D)", "sp-aux"), ("SCS-CIS(D)", "sp-aux"),
    ("SF-CIS", "sp"), ("SF-TDA-BHANDHLYP", "sp"),
    ("ZINDO/S-CIS", "semiempirical-sp"),
)
# §§3.3.5 and 5.6.9. A literal SCS/SOS prefix identifies one fitted
# functional. ORCA applies its four excited-state coefficients itself.
_DH_REFERENCES = (
    "B2PLYP", "B2GP-PLYP", "PBE-QIDH", "PBE0-DH", "WB2PLYP", "WB2GP-PLYP",
    "WB88PP86", "WPBEPP86", "RSX-QIDH", "RSX-0DH",
    "SCS/SOS-B2PLYP21", "SCS-PBE-QIDH", "SOS-PBE-QIDH", "SCS-B2GP-PLYP21",
    "SOS-B2GP-PLYP21", "SCS/SOS-WB2PLYP", "SCS-WB2GP-PLYP", "SOS-WB2GP-PLYP",
    "SCS-RSX-QIDH", "SOS-RSX-QIDH", "SCS-WB88PP86", "SOS-WB88PP86",
    "SCS-WPBEPP86", "SOS-WPBEPP86",
)
DOUBLE_HYBRID_RESPONSE = {
    prefix + "-" + functional: functional for prefix in ("TD", "TDA") for functional in _DH_REFERENCES
}
_CORRELATED_EE = (
    ("EOM-CCSD", "sp"), ("STEOM-CCSD", "sp"),
    ("EOM-CCSD(2)", "sp"), ("STEOM-CCSD(2)", "sp"),
    ("ADC2", "sp-aux"), ("IH-FSMR-CCSD", "sp"),
    ("bt-PNO-EOM-CCSD", "sp-aux"), ("bt-PNO-STEOM-CCSD", "sp-aux"),
    ("STEOM-DLPNO-CCSD", "sp-aux"),
)
_IONIZATION = (
    ("IP-EOM-CCSD", "sp"), ("IP-ADC2", "sp-aux"), ("bt-PNO-IP-EOM-CCSD", "sp-aux"),
    ("IP-EOM-DLPNO-CCSD", "sp-aux"),
)
_ATTACHMENT = (
    ("EA-EOM-CCSD", "sp"), ("EA-ADC2", "sp-aux"), ("bt-PNO-EA-EOM-CCSD", "sp-aux"),
    ("EA-EOM-DLPNO-CCSD", "sp-aux"),
)

STATE_METHOD_GROUPS = (
    ("多参考活性空间", _CAS),
    ("态平均与准简并活性空间", tuple((name, "sp") for name in _SA_CAS)),
    ("多组态线性响应", tuple((name, "sp-aux") for name in MCRPA_METHODS)),
    ("多参考密度泛函（CASDFT）", tuple((name, "sp") for name in CASDFT_METHODS)),
    ("多参考微扰", _CAS_PT),
    ("内收缩多参考 CI / CC 与高阶微扰", _CAS_AUTOCI),
    ("未收缩多参考 CI（MRCI）", _UNCONTRACTED),
    ("多参考运动方程（MR-EOM）", _MREOM),
    ("垂直电子激发能", _RESPONSE),
    ("双杂化 TD/TDA 激发能", tuple((name, "sp-aux") for name in DOUBLE_HYBRID_RESPONSE)),
    ("高自旋限制性开壳层 CI（ROCIS）", _ROCIS),
    ("耦合簇与 ADC 垂直激发能", _CORRELATED_EE),
    ("垂直电离能（IP）", _IONIZATION),
    ("垂直电子附着能（EA）", _ATTACHMENT),
)
ACTIVE_SPACE_METHODS = (tuple(name for name, _ in _CAS + _CAS_PT + _CAS_AUTOCI + _UNCONTRACTED + _MREOM)
                        + CASDFT_METHODS + _SA_CAS + MCRPA_METHODS)
RESPONSE_METHODS = tuple(name for name, _ in _RESPONSE) + tuple(DOUBLE_HYBRID_RESPONSE)
MDCI_METHODS = tuple(name for name, _ in _CORRELATED_EE + _IONIZATION + _ATTACHMENT)
EXCITED_STATE_METHODS = (RESPONSE_METHODS + MDCI_METHODS + MREOM_METHODS + ROCIS_METHODS
                         + MULTIROOT_CAS_METHODS + MCRPA_METHODS)
REFERENCE_FUNCTIONAL_METHODS = ("TD-DFT", "TDA-DFT")
ELECTRON_CHANNEL_METHODS = (
    "IP-EOM-CCSD", "EA-EOM-CCSD", "bt-PNO-IP-EOM-CCSD", "bt-PNO-EA-EOM-CCSD",
)
CLOSED_SHELL_METHODS = (
    "ADC2", "IP-ADC2", "EA-ADC2", "EOM-CCSD(2)", "STEOM-CCSD(2)",
    "IH-FSMR-CCSD", "STEOM-DLPNO-CCSD", "IP-EOM-DLPNO-CCSD", "EA-EOM-DLPNO-CCSD",
    "CIS(D)", "SCS-CIS(D)", *DOUBLE_HYBRID_RESPONSE,
)
SPIN_FLIP_METHODS = ("SF-CIS", "SF-TDA-BHANDHLYP")
STATE_METHOD_ALIASES = {
    "MR-EOM-CC": "MR-EOM", "DMRG": "DMRG-CASSCF",
    "EE-EOM-CCSD": "EOM-CCSD", "ADC(2)": "ADC2", "IP-ADC(2)": "IP-ADC2",
    "EA-ADC(2)": "EA-ADC2", "TDHF": "TD-HF", "CASPT2-K": "CASPT2K",
    "RI-CASPT2-K": "RI-CASPT2K", "DLPNO-STEOM-CCSD": "STEOM-DLPNO-CCSD",
    "PC-NEVPT2": "FIC-NEVPT2", "NEVPT2": "SC-NEVPT2", "ICE-SCF": "ICE-CASSCF",
}
