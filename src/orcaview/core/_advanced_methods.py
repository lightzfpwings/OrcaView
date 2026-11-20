"""Additional energy models and simple LibXC keywords in ORCA 6.1.1, chapters 3 and 5."""

from ._dft_methods import DLPNO_DOUBLE_HYBRIDS, DSD_D3BJ
from ._wavefunction_methods import NDO_BLOCK

def _group(names, profile):
    return tuple((name, profile) for name in names.split())


def _libxc(names, profile):
    return tuple((f"LibXC({name})", profile) for name in names.split())


LIBXC_PURE = (
    "PWLDA VWN5 B97-D B97-D3 B97-D4 BLYP BPBE BPW91 BVWN GLYP KT2 KT3 MPWLYP MPWPW OPBE "
    "OLYP RPW86PBE PW86PBE PW91 PBE RPBE REVPBE XLYP B97M-V B97M-D3BJ B97M-D4 M06L MN15L "
    "MTASK-LDA MTASK-SCAN REVTM R2SCAN RSCAN SCAN TASK-CCALDA TASK-CC TASK-LDA TASK-SCAN "
    "TM TPSS"
)

LIBXC_HYBRID = (
    "HFLDA BHANDHLYP B1LYP B1PW91 B1PW B1PBE B3PW91 B3LYP B3LYP/G B3LYPS BLYP35 B97 "
    "CAM-B3LYP CASE21 G1LYP HSE03 HSE12 HSE12S HSESOL KMLYP LB07 LC-BLYP MPW1LYP MPW1PW "
    "PBE0 PBE38 PBE50 PW91_0 PW1PW REVPBE0 REVPBE38 WHPBE0 WB97 WB97X WB97X-D3 WB97X-V "
    "WB97X-D3BJ WB97X-D4 WB97X-D4REV GAS22 M05 M052X M06 M062X M06SX MN15 LC-TMLYP PW6B95 "
    "R2SCANH R2SCAN0 R2SCAN38 R2SCAN50 SCAN0 TPSS0 TPSSH WB97M-V WB97M-D3BJ WB97M-D4 "
    "WB97M-D4REV"
)

LIBXC_DOUBLE = (
    "B2PLYP B2GP-PLYP B2T-PLYP B2K-PLYP B2NC-PLYP DSD-PBEB95-D3 DSD-PBEB95-D4 MPW2-PLYP "
    "PWPB95 PBE0-DH PBE0-2 PBE-QIDH PR2SCAN50 PR2SCAN69 SOS1-R2SCAN0-DH SOS1-R2SCAN-CIDH "
    "SOS1-R2SCAN-QIDH SOS1-R2SCAN0-2"
)

D4 = (
    "HF BLYP BPBE BP86 BPW91 GLYP LB94 MPWLYP MPWPW OLYP OPBE PBE RPBE REVPBE PW86PBE "
    "RPW86PBE PW91 PW91P86 SCAN B1LYP B3LYP "
    "XLYP B97BECKE TPSS revTPSS BHANDHLYP B1P B3P86 B1PW91 B3PW91 O3LYP REVPBE0 REVPBE38 "
    "PBE0 PWP1 PW1PW mPW1PW mPW1LYP PW6B95 TPSSh TPSS0 X3LYP M06L M06 wB97 wB97X B97M-D4 "
    "CAM-B3LYP LC-BLYP B2PLYP B2GP-PLYP mPW2PLYP PWPB95 B97-D RSCAN r2SCAN r2SCANh r2SCAN0 "
    "r2SCAN50 wB97X-D4rev wB97M-D4rev wR2SCAN r2SCAN0-DH r2SCAN-CIDH r2SCAN-QIDH r2SCAN0-2 "
    "Pr2SCAN50 kPr2SCAN50 wPr2SCAN50 Pr2SCAN69 revDSD-PBEP86/2021 revDOD-PBEP86/2021 "
    "LRC-PBE"
)

D3BJ = (
    "HF BP86 BLYP REVPBE B97-D PBE RPBE RPW86PBE B3LYP BHANDHLYP TPSS TPSS0 PBE0 REVPBE38 "
    "PW6B95 B2PLYP mPWLYP OLYP BPBE OPBE B3PW91 REVPBE0 TPSSh CAM-B3LYP B2GP-PLYP PWPB95 "
    "SCAN RSCAN R2SCAN R2SCANh R2SCAN0 R2SCAN50 WR2SCAN r2SCAN0-DH r2SCAN-CIDH r2SCAN-QIDH "
    "r2SCAN0-2 Pr2SCAN50 kPr2SCAN50 wPr2SCAN50 Pr2SCAN69 revDSD-PBEP86/2021 "
    "revDOD-PBEP86/2021 DSD-BLYP DSD-BLYP/2013 DSD-PBEB95 DSD-PBEP86 DSD-PBEP86/2013 "
    "B97M-D3BJ wB97X-D3BJ wB97M-D3BJ wB97X-2 PBE0DH PBE02 PBE-QIDH"
)

D3ZERO = (
    "BLYP BP86 B97-D REVPBE PBE RPBE TPSS B3LYP PBE0 PW6B95 TPSS0 B2PLYP B2GP-PLYP PWPB95 "
    "mPWLYP BPBE BHANDHLYP TPSSh REVPBE0 REVPBE38 RPW86PBE B3PW91 M06L M06 M062X wB97X-D3 "
    "CAM-B3LYP SCAN wB97X-2 PBE0DH PBE02 PBE-QIDH"
)

_AUTOCI_GRAD = "CID CISD CCD CCSD CCSD[T] CCSD(T) CEPA(0) MP2 MP3 MP4 MP4(SDQ)"
_AUTOCI_ENERGY = "CISDT CCSDT CC2 QCISD"
_AUTOCI_UHF = "CCSDTQ CCSDT-1 CCSDT-2 CCSDT-3 CCSDT-4 CC3 MP5".split()
_AUTOCI = tuple(("AUTOCI-" + name, profile) for names, profile in (
    (_AUTOCI_GRAD.split(), "numeric-freq"), (_AUTOCI_ENERGY.split(), "sp"), (_AUTOCI_UHF, "sp")
) for name in names)

_F12 = "F12-MP2 CCSD-F12 CCSD(T)-F12 QCISD-F12 QCISD(T)-F12"
_F12_RI = (
    "F12-RI-MP2 F12/D-RI-MP2 F12-DLPNO-MP2 F12/D-DLPNO-MP2 CCSD-F12/RI CCSD-F12D/RI "
    "CCSD(T)-F12/RI CCSD(T)-F12D/RI QCISD-F12/RI QCISD(T)-F12/RI RI-CEPA/1-F12 "
    "DLPNO-CCSD-F12 DLPNO-CCSD-F12/D DLPNO-CCSD(T)-F12 DLPNO-CCSD(T)-F12/D "
    "DLPNO-CCSD(T1)-F12 DLPNO-CCSD(T1)-F12/D"
)
_MRCC = "CCSDT CCSDTQ CCSDTQP CCSD(T) CCSD[T] CCSD(T)_L CC3 CCSDT-1a CCSDT-1b CISDT"
# Each CBS protocol delegates the pair of orbital bases to ORCA (§3.10.8).
_CBS_BASES = {
    "2/3,cc": ("cc-pVDZ", "cc-pVTZ"), "3/4,cc": ("cc-pVTZ", "cc-pVQZ"),
    "2/3,aug-cc": ("aug-cc-pVDZ", "aug-cc-pVTZ"), "3/4,aug-cc": ("aug-cc-pVTZ", "aug-cc-pVQZ"),
    "2/3,def2": ("def2-SVP", "def2-TZVPP"), "3/4,def2": ("def2-TZVPP", "def2-QZVPP"),
}
CBS_PROTOCOLS = {f"{method}-CBS({pair})": (method, pair) for method in ("HF", "MP2", "CCSD", "CCSD(T)")
                 for pair in _CBS_BASES}


def check_extrapolation_basis(name, molecule):
    if name in CBS_PROTOCOLS:
        from .integrals import validate_basis_system
        for basis in _CBS_BASES[CBS_PROTOCOLS[name][1]]:
            validate_basis_system(basis, molecule)


ADVANCED_GROUPS = (
    ("LibXC 纯泛函", _libxc(LIBXC_PURE, "sp")),
    ("LibXC 杂化泛函", _libxc(LIBXC_HYBRID, "sp")),
    ("LibXC 双杂化泛函", _libxc(LIBXC_DOUBLE, "sp-aux")),
    ("显式相关 F12", _group(_F12, "sp") + _group(_F12_RI, "sp-aux")),
    ("自动生成单参考关联 AUTOCI", _AUTOCI),
    ("高阶关联 MRCC（外部程序）", tuple(("MRCC-" + m, "sp") for m in _MRCC.split())),
    ("解析密度泛函 ADFT", _group("ADFT(XAlpha) ADFT(HF) ADFT(CC)", "numeric-freq")),
    ("随机相位近似 RPA", (("RPAC(PBE)", "sp-aux"),)),
    ("全组态相互作用", (("FCI", "sp"),)),
    ("完备基组极限 CBS 外推", tuple((name, "fixed-sp") for name in CBS_PROTOCOLS)),
    ("外部 xTB 与力场", _group("GFN0-xTB GFN1-xTB GFN2-xTB GFN-FF", "semiempirical")),
    ("分子内团簇近似 CIM", _group("CIM-RI-MP2 CIM-DLPNO-MP2 CIM-DLPNO-CCSD(T)", "sp-aux")
     + _group("CIM-CCSD(T)", "sp")),
)

ADVANCED_ALIASES = {
    "RIMP2": "RI-MP2", "MP2RI": "RI-MP2",
    "SCS-RI-MP2": "RI-SCS-MP2", "SCS-RIMP2": "RI-SCS-MP2",
    "SOS-RI-MP2": "RI-SOS-MP2", "SOS-RIMP2": "RI-SOS-MP2",
    "SCS-DLPNO-MP2": "DLPNO-SCS-MP2", "SOS-DLPNO-MP2": "DLPNO-SOS-MP2",
    "OO-RIMP2": "OO-RI-MP2", "OO-MP2RI": "OO-RI-MP2",
    "OO-SCS-RI-MP2": "OO-RI-SCS-MP2", "OO-SCS-RIMP2": "OO-RI-SCS-MP2",
    "OO-SOS-RI-MP2": "OO-RI-SOS-MP2", "OO-SOS-RIMP2": "OO-RI-SOS-MP2",
    "MP2-F12/D-RI": "F12/D-RI-MP2", "F12D-RI-MP2": "F12/D-RI-MP2",
    "MP2-F12D-RI": "F12/D-RI-MP2", "RI-MP2-F12D": "F12/D-RI-MP2",
    "F12D-DLPNO-MP2": "F12/D-DLPNO-MP2", "DLPNO-MP2-F12D": "F12/D-DLPNO-MP2",
    "XTB0": "GFN0-xTB", "XTB1": "GFN1-xTB", "GFN-xTB": "GFN1-xTB",
    "XTB2": "GFN2-xTB", "XTB": "GFN2-xTB", "XTBFF": "GFN-FF",
    "ADFT": "ADFT(XAlpha)", "MP2-F12": "F12-MP2", "RI-MP2-F12": "F12-RI-MP2",
    "MP2-F12-RI": "F12-RI-MP2", "RI-MP2-F12/D": "F12/D-RI-MP2",
    "DLPNO-MP2-F12": "F12-DLPNO-MP2", "DLPNO-MP2-F12/D": "F12/D-DLPNO-MP2",
}

# Table 3.15–3.17 are parameters for specific parent functionals.
_DISPERSION = {k: frozenset(s.upper().split()) for k, s in
               (("D3BJ", D3BJ), ("D3ZERO", D3ZERO), ("D4", D4))}
_EXPLICIT_DISPERSION = {"B97-D", "B97-D3", "B3LYP/G", "B2GP-PLYP-D3", "HF-3c"}

def dispersion_options(name):
    if name in _EXPLICIT_DISPERSION or name.endswith(("-D3", "-D4", "-D4REV", "-D3BJ", "-V")):
        return ("Auto",)
    parent = {"SCANFUNC": "SCAN"}.get(name, name.upper())
    return ("Auto", *(option for option, parents in _DISPERSION.items() if parent in parents))


def advanced_input(name, multiplicity):
    if name in NDO_BLOCK:
        return "", ("%method", "  Method " + NDO_BLOCK[name], "end")
    if name in DLPNO_DOUBLE_HYBRIDS:
        parent = DLPNO_DOUBLE_HYBRIDS[name]
        keyword = DSD_D3BJ[parent] + " D3BJ" if parent in DSD_D3BJ else parent
        return keyword, ("%mp2", "  DLPNO true", "end")
    if name in DSD_D3BJ:
        return DSD_D3BJ[name] + " D3BJ", ()
    if name in CBS_PROTOCOLS:
        method, pair = CBS_PROTOCOLS[name]
        return f"{method} Extrapolate({pair}) TightSCF Conv", ()
    if name in ("F12-DLPNO-MP2", "F12/D-DLPNO-MP2") and multiplicity != 1:
        raise ValueError(f"{name} 要求限制性闭壳层参考态")
    if name.startswith("CIM-"):
        if multiplicity != 1:
            raise ValueError("CIM 要求闭壳层单重参考态")
        return name[4:] + " CIM", ()
    if name == "FCI":
        return "HF", ("%casscf", "  DoFCI true", f"  mult {multiplicity}", "  nroots 1", "end")
    if name.startswith("MRCC-"):
        if multiplicity != 1:
            raise ValueError("外部 MRCC 接口只支持闭壳层单重参考态")
        return "HF Conv", ("%mrcc", f'  method "{name[5:]}"', "end")
    if name.startswith("ADFT("):
        return name + " XFit/3", ()
    if name == "RPAC(PBE)":
        return "PBE RPAC", ()
    if name.startswith("AUTOCI-") and name[7:] in _AUTOCI_UHF:
        return "UHF " + name, ()
    return name, ()

