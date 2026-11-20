"""Built-in basis keywords from ORCA 6.1.1 tables 2.12–2.37.

Each row groups entries with identical element coverage and potential or
Hamiltonian. Gaps in coverage are significant. Keep library data independent
of the combinations supported by the molecular input builder.
"""

from .elements import ATOMIC_NUMBERS


def atomic_numbers(symbols):
    numbers = set()
    for item in symbols.split():
        ends = item.split("-")
        first, last = ATOMIC_NUMBERS[ends[0]], ATOMIC_NUMBERS[ends[-1]]
        numbers.update(range(first, last + 1))
    return frozenset(numbers)


# (element ranges, potential/Hamiltonian, space-separated library names)
_GROUPS = (
    # Table 2.12
    ("H-I", "all-electron", "STO-3G"),
    ("H-Cs", "all-electron", "3-21G"),
    ("H-Ar", "all-electron", "3-21GSP 4-22GSP"),
    ("H-Zn", "all-electron",
     "6-31G 6-31G** 6-31G(d) 6-31G(d,p) 6-31G(2d) 6-31G(2d,p) 6-31G(2d,2p) 6-31G(2df) "
     "6-31G(2df,2p) 6-31G(2df,2pd) 6-31+G** 6-31+G(d) 6-31+G(d,p) 6-31+G(2d) 6-31+G(2d,p) "
     "6-31+G(2d,2p) 6-31+G(2df) 6-31+G(2df,2p) 6-31+G(2df,2pd) 6-31++G** 6-31++G(d,p) "
     "6-31++G(2d,p) 6-31++G(2d,2p) 6-31++G(2df,2p) 6-31++G(2df,2pd)"),
    ("H-Kr", "all-electron", "6-31G* 6-31+G*"),
    ("Sc-Cu", "all-electron", "m6-31G m6-31G*"),
    ("H-Br", "all-electron",
     "6-311G 6-311G* 6-311G** 6-311G(d) 6-311G(d,p) 6-311G(2d) 6-311G(2d,p) 6-311G(2d,2p) "
     "6-311G(2df) 6-311G(2df,2p) 6-311G(2df,2pd) 6-311G(3df) 6-311G(3df,3pd) 6-311+G* 6-311+G** "
     "6-311+G(d) 6-311+G(d,p) 6-311+G(2d) 6-311+G(2d,p) 6-311+G(2d,2p) 6-311+G(2df) "
     "6-311+G(2df,2p) 6-311+G(2df,2pd) 6-311+G(3df) 6-311+G(3df,2p) 6-311+G(3df,3pd) 6-311++G** "
     "6-311++G(d,p) 6-311++G(2d,p) 6-311++G(2d,2p) 6-311++G(2df,2p) 6-311++G(2df,2pd) "
     "6-311++G(3df,3pd)"),
    # Table 2.13
    ("H-Kr", "all-electron", "SV SV(P) SVP TZV TZV(P) TZVP TZVPP QZVP QZVPP"),
    ("H-Lr", "def-ECP", "def-SV(P) def-SVP def-TZVP def-TZVPP"),
    ("Fr-Lr", "def-ECP", "ma-def-TZVP"),
    ("H-I", "all-electron", "old-SV old-SV(P) old-SVP old-TZV old-TZV(P) old-TZVP old-TZVPP"),
    # Table 2.14
    ("H-Rn", "def2-ECP",
     "def2-SVP def2-SV(P) def2-TZVP def2-TZVP(-f) def2-TZVPP def2-QZVP def2-QZVPP def2-SVPD "
     "def2-TZVPD def2-TZVPPD def2-QZVPD def2-QZVPPD ma-def2-SVP ma-def2-SV(P) ma-def2-mSVP "
     "ma-def2-TZVP ma-def2-TZVP(-f) ma-def2-TZVPP ma-def2-QZVPP"),
    # Table 2.15
    ("H-Rn", "dhf-ECP", "dhf-SV(P) dhf-SVP dhf-TZVP dhf-TZVPP dhf-QZVP dhf-QZVPP"),
    ("H-Rn", "dhf-ECP-2c", "dhf-SVP-2c dhf-TZVP-2c dhf-TZVPP-2c dhf-QZVP-2c dhf-QZVPP-2c"),
    # Table 2.16
    ("H-Ca Ga-Kr", "all-electron", "pc-0 aug-pc-0"),
    ("H-Kr", "all-electron",
     "pc-1 pc-2 pc-3 pc-4 aug-pc-1 aug-pc-2 aug-pc-3 aug-pc-4 pcseg-0 pcseg-1 pcseg-2 pcseg-3 "
     "pcseg-4 aug-pcseg-0 aug-pcseg-1 aug-pcseg-2 aug-pcseg-3 aug-pcseg-4 pcSseg-0 pcSseg-1 "
     "pcSseg-2 pcSseg-3 pcSseg-4 aug-pcSseg-0 aug-pcSseg-1 aug-pcSseg-2 aug-pcSseg-3 "
     "aug-pcSseg-4"),
    ("H-He B-Ne Al-Ar", "all-electron",
     "pcJ-0 pcJ-1 pcJ-2 pcJ-3 pcJ-4 aug-pcJ-0 aug-pcJ-1 aug-pcJ-2 aug-pcJ-3 aug-pcJ-4"),
    ("H He B-Ne Al-Ar", "all-electron",
     "pcH-1 pcH-2 pcH-3 pcH-4 aug-pcH-1 aug-pcH-2 aug-pcH-3 aug-pcH-4"),
    ("Li-Ar", "all-electron", "pcX-1 pcX-2 pcX-3 pcX-4 aug-pcX-1 aug-pcX-2 aug-pcX-3 aug-pcX-4"),
    # Table 2.17
    ("H-Og", "all-electron",
     "HGBS-5 HGBS-7 HGBS-9 HGBSP1-5 HGBSP1-7 HGBSP1-9 HGBSP2-5 HGBSP2-7 HGBSP2-9 HGBSP3-5 "
     "HGBSP3-7 HGBSP3-9 AHGBS-5 AHGBS-7 AHGBS-9 AHGBSP1-5 AHGBSP1-7 AHGBSP1-9 AHGBSP2-5 "
     "AHGBSP2-7 AHGBSP2-9 AHGBSP3-5 AHGBSP3-7 AHGBSP3-9"),
    # Table 2.18
    ("H-Xe", "all-electron", "Sapporo-DZP-2012 Sapporo-TZP-2012 Sapporo-QZP-2012"),
    # Table 2.19
    ("H Li-Sr", "all-electron", "Partridge-1"),
    ("H Li-Kr", "all-electron", "Partridge-2"),
    ("H Li-Zn", "all-electron", "Partridge-3"),
    ("Sc-Zn", "all-electron", "Partridge-4"),
    # Table 2.20
    ("H Li-Og", "CRENBL-ECP", "CRENBL"),
    # Table 2.21
    ("Na-La Hf-Bi", "HayWadt", "LANL08"),
    ("Sc-Cu Y-Ag La Hf-Au", "HayWadt", "LANL08(f) LANL2TZ(f)"),
    ("H Li-La Hf-Bi U-Pu", "HayWadt", "LANL2DZ"),
    ("Sc-Zn Y-Cd La Hf-Hg", "HayWadt", "LANL2TZ"),
    # Table 2.22
    ("H-Ar Ca-Kr", "all-electron", "cc-pVDZ cc-pVQZ cc-pV5Z cc-pwCVQZ cc-pwCV5Z"),
    ("H-Ar Ca-Kr Y Ag Au", "all-electron", "cc-pVTZ"),
    ("H-He Be-Ne Al-Ar", "all-electron", "cc-pV6Z"),
    ("H-Ar Sc-Kr", "all-electron", "aug-cc-pVDZ aug-cc-pVQZ aug-cc-pV5Z aug-cc-pwCVQZ aug-cc-pwCV5Z"),
    ("H-Ar Sc-Kr Ag Au", "all-electron", "aug-cc-pVTZ aug-cc-pwCVTZ"),
    ("H-He B-Ne Al-Ar", "all-electron", "aug-cc-pV6Z cc-pCV6Z aug-cc-pCV6Z"),
    ("Na-Ar", "all-electron", "cc-pVD(+d)Z cc-pVT(+d)Z cc-pVQ(+d)Z cc-pV5(+d)Z"),
    ("Al-Ar", "all-electron",
     "aug-cc-pVD(+d)Z aug-cc-pVT(+d)Z aug-cc-pVQ(+d)Z aug-cc-pV5(+d)Z aug-cc-pV6(+d)Z"),
    ("H-Ar", "all-electron",
     "apr-cc-pV(Q+d)Z may-cc-pV(T+d)Z may-cc-pV(Q+d)Z jun-cc-pV(D+d)Z jun-cc-pV(T+d)Z "
     "jun-cc-pV(Q+d)Z jul-cc-pV(D+d)Z jul-cc-pV(T+d)Z jul-cc-pV(Q+d)Z maug-cc-pV(D+d)Z "
     "maug-cc-pV(T+d)Z maug-cc-pV(Q+d)Z haV(T+d)Z haV(Q+d)Z haV(5+d)Z"),
    ("H-Ar Ca Ga-Kr", "all-electron", "cc-pCVDZ cc-pCVTZ cc-pCVQZ cc-pCV5Z cc-pwCVDZ"),
    ("H-Ar Ga-Kr", "all-electron", "aug-cc-pCVDZ aug-cc-pCVTZ aug-cc-pCVQZ aug-cc-pCV5Z aug-cc-pwCVDZ"),
    ("H-Ar Ca-Kr Ag Au", "all-electron", "cc-pwCVTZ"),
    ("Ca Cu-Kr Sr-Xe Ba Hf-Rn Ra U", "SK-MCDHF-RSC",
     "cc-pVDZ-PP cc-pVTZ-PP cc-pVQZ-PP cc-pwCVDZ-PP cc-pwCVTZ-PP cc-pwCVQZ-PP"),
    ("Ca Cu-Kr Sr-Xe Ba Hf-Rn Ra", "SK-MCDHF-RSC",
     "cc-pV5Z-PP aug-cc-pVDZ-PP aug-cc-pVTZ-PP aug-cc-pVQZ-PP aug-cc-pV5Z-PP cc-pwCV5Z-PP "
     "aug-cc-pwCVDZ-PP aug-cc-pwCVTZ-PP aug-cc-pwCVQZ-PP aug-cc-pwCV5Z-PP"),
    ("Ca Sr Ba Ra", "SK-MCDHF-RSC",
     "cc-pCVDZ-PP cc-pCVTZ-PP cc-pCVQZ-PP cc-pCV5Z-PP aug-cc-pCVDZ-PP aug-cc-pCVTZ-PP "
     "aug-cc-pCVQZ-PP aug-cc-pCV5Z-PP"),
    ("H B-F Al-Cl Sc-Zn Se", "all-electron", "aug-cc-pVTZ-J"),
    # Table 2.23
    ("H-Ar", "all-electron", "cc-pVDZ-F12 cc-pVTZ-F12 cc-pVQZ-F12"),
    ("Li-Ar", "all-electron", "cc-pCVDZ-F12 cc-pCVTZ-F12 cc-pCVQZ-F12"),
    ("Ga-Kr In-Xe Tl-Rn", "SK-MCDHF-RSC", "cc-pVDZ-PP-F12 cc-pVTZ-PP-F12 cc-pVQZ-PP-F12"),
    # Table 2.24
    ("H-Ar Sc-Zn", "all-electron",
     "ANO-SZ ANO-pVDZ ANO-pVTZ ANO-pVQZ ANO-pV5Z ANO-pV6Z aug-ANO-pVDZ aug-ANO-pVTZ aug-ANO-pVQZ "
     "aug-ANO-pV5Z saug-ANO-pVDZ saug-ANO-pVTZ saug-ANO-pVQZ saug-ANO-pV5Z"),
    # Table 2.25
    ("H Li B-Ne Al-Cl", "all-electron", "D95 D95p"),
    ("H B-F", "all-electron", "EPR-II EPR-III"),
    ("H B-F Al-Cl", "all-electron", "IGLO-II IGLO-III"),
    ("H-Th Pu-Am Cf-Lr", "all-electron", "UGBS"),
    ("Sc-Zn", "all-electron", "CP CP(PPP)"),
    ("Sc-Cu", "all-electron", "Wachters+f"),
    ("H-Ar", "all-electron", "W1-mtsmall W1-DZ W1-TZ W1-QZ W1-Opt"),
    ("H-Ca", "all-electron", "MINI MINIS"),
    ("H-Na Al-K", "all-electron", "MIDI"),
    ("H-Lr", "def-ECP", "MINIX"),
    ("H-Lr", "def2-ECP+def-ECP", "def2-mSVP def2-mTZVP def2-mTZVPP"),
    ("H-Rn", "vDZP-ECP", "vDZP"),
    # Table 2.26
    ("H-Kr", "DKH2", "DKH-SV(P) DKH-SVP DKH-TZV(P) DKH-TZVP DKH-TZVPP DKH-QZVP DKH-QZVPP"),
    ("H-Kr", "ZORA", "ZORA-SV(P) ZORA-SVP ZORA-TZV(P) ZORA-TZVP ZORA-TZVPP ZORA-QZVP ZORA-QZVPP"),
    ("H-I", "DKH2", "old-DKH-SV(P) old-DKH-SVP old-DKH-TZV(P) old-DKH-TZVP old-DKH-TZVPP"),
    ("H-I", "ZORA", "old-ZORA-SV(P) old-ZORA-SVP old-ZORA-TZV(P) old-ZORA-TZVP old-ZORA-TZVPP"),
    # Table 2.27
    ("H-Kr", "DKH2",
     "DKH-def2-SVP DKH-def2-SV(P) DKH-def2-TZVP DKH-def2-TZVP(-f) DKH-def2-TZVPP DKH-def2-QZVPP "
     "ma-DKH-def2-SVP ma-DKH-def2-SV(P) ma-DKH-def2-TZVP ma-DKH-def2-TZVP(-f) ma-DKH-def2-TZVPP "
     "ma-DKH-def2-QZVPP"),
    ("H-Kr", "ZORA",
     "ZORA-def2-SVP ZORA-def2-SV(P) ZORA-def2-TZVP ZORA-def2-TZVP(-f) ZORA-def2-TZVPP "
     "ZORA-def2-QZVPP ma-ZORA-def2-SVP ma-ZORA-def2-SV(P) ma-ZORA-def2-TZVP "
     "ma-ZORA-def2-TZVP(-f) ma-ZORA-def2-TZVPP ma-ZORA-def2-QZVPP"),
    # Table 2.28
    ("Hf-Hg", "DKH2", "SARC-DKH-SVP"),
    ("Rb-Rn Ac-Lr", "DKH2", "SARC-DKH-TZVP SARC-DKH-TZVPP"),
    ("Hf-Hg", "ZORA", "SARC-ZORA-SVP"),
    ("Rb-Rn Ac-Lr", "ZORA", "SARC-ZORA-TZVP SARC-ZORA-TZVPP"),
    # Table 2.29
    ("La-Lu", "DKH2", "SARC2-DKH-QZV SARC2-DKH-QZVP"),
    ("La-Lu", "ZORA", "SARC2-ZORA-QZV SARC2-ZORA-QZVP"),
    # Table 2.30
    ("H-Rn", "X2C",
     "x2c-SV(P)all x2c-SVPall x2c-TZVPall x2c-TZVPPall x2c-QZVPall x2c-QZVPPall x2c-SV(P)all-s "
     "x2c-SVPall-s x2c-TZVPall-s x2c-TZVPPall-s x2c-QZVPall-s x2c-QZVPPall-s"),
    ("H-Rn", "SO-X2C",
     "x2c-SV(P)all-2c x2c-SVPall-2c x2c-TZVPall-2c x2c-TZVPPall-2c x2c-QZVPall-2c "
     "x2c-QZVPPall-2c x2c-QZVPall-2c-s x2c-QZVPPall-2c-s"),
    # Table 2.31
    ("K-Rn", "DKH3", "Sapporo-DKH3-DZP-2012 Sapporo-DKH3-TZP-2012 Sapporo-DKH3-QZP-2012"),
    # Table 2.32
    ("H-Ar Sc-Kr", "DKH2", "cc-pVDZ-DK cc-pV5Z-DK aug-cc-pVDZ-DK aug-cc-pV5Z-DK"),
    ("H-Ar Sc-Kr Y-Xe Hf-Rn", "DKH2", "cc-pVTZ-DK aug-cc-pVTZ-DK"),
    ("H-Ar Sc-Kr In-Xe Tl-Rn", "DKH2", "cc-pVQZ-DK aug-cc-pVQZ-DK"),
    ("U", "DKH3", "cc-pVDZ-DK3 cc-pVTZ-DK3 cc-pVQZ-DK3 cc-pwCVDZ-DK3 cc-pwCVTZ-DK3 cc-pwCVQZ-DK3"),
    ("H-Be Na-Mg Ca-Zn", "DKH2", "cc-pwCVDZ-DK cc-pwCV5Z-DK"),
    ("H-Be Na-Mg Ca-Zn Y-Xe Hf-Rn", "DKH2", "cc-pwCVTZ-DK"),
    ("H-Be Na-Mg Ca-Zn In-Xe Tl-Rn", "DKH2", "cc-pwCVQZ-DK"),
    ("H-Be Na-Mg Sc-Zn", "DKH3", "aug-cc-pwCVDZ-DK"),
    ("H-Be Na-Mg Sc-Zn Y-Xe Hf-Rn", "DKH2", "aug-cc-pwCVTZ-DK"),
    ("H-Be Na-Mg Sc-Zn In-Xe Tl-Rn", "DKH2", "aug-cc-pwCVQZ-DK"),
    ("H-Be Na-Mg Sc-Zn", "DKH2", "aug-cc-pwCV5Z-DK"),
    # Table 2.33
    ("H-Cm", "DKH2", "ANO-RCC-Full ANO-RCC-DZP ANO-RCC-TZP ANO-RCC-QZP"),
    # Table 2.34
    ("H-Lr", "fit", "def2/J def2-mTZVP/J def2-mTZVPP/J"),
    ("H-Rn", "fit", "x2c/J"),
    ("H-Rn Ac-Lr", "fit", "SARC/J"),
    # Table 2.35
    ("H-Rn", "fit", "def2/JK"),
    ("H-Ra Th-Lr", "fit", "def2/JKsmall"),
    ("H B-F Al-Cl Ga-Br", "fit",
     "cc-pVTZ/JK cc-pVQZ/JK cc-pV5Z/JK aug-cc-pVTZ/JK aug-cc-pVQZ/JK aug-cc-pV5Z/JK"),
    ("La-Lu", "fit", "SARC2-DKH-QZV/JK SARC2-DKH-QZVP/JK SARC2-ZORA-QZV/JK SARC2-ZORA-QZVP/JK"),
    # Table 2.36
    ("H-Rn", "fit", "def2-SVP/C def2-TZVP/C def2-TZVPP/C def2-QZVPP/C"),
    ("H-La Hf-Rn", "fit", "def2-SVPD/C def2-TZVPD/C def2-TZVPPD/C def2-QZVPPD/C"),
    ("H-Ar Ga-Kr", "fit", "cc-pVDZ/C cc-pV5Z/C"),
    ("H-Ar Sc-Kr", "fit", "cc-pVTZ/C cc-pVQZ/C"),
    ("H-He B-Ne Al-Ar", "fit", "cc-pV6Z/C aug-cc-pV6Z/C"),
    ("H-He Be-Ne Mg-Ar Ga-Kr", "fit", "aug-cc-pVDZ/C"),
    ("H-He Be-Ne Mg-Ar Sc-Kr", "fit", "aug-cc-pVTZ/C aug-cc-pVQZ/C"),
    ("H-Ne Al-Ar Ga-Kr", "fit", "aug-cc-pV5Z/C"),
    ("H-He B-Ne Al-Ar Ga-Kr", "fit", "cc-pwCVDZ/C cc-pwCVQZ/C aug-cc-pwCVDZ/C aug-cc-pwCVQZ/C"),
    ("H-He B-Ne Al-Ar Sc-Kr", "fit", "cc-pwCVTZ/C aug-cc-pwCVTZ/C"),
    ("H-Ne Al-Ar", "fit", "cc-pwCV5Z/C aug-cc-pwCV5Z/C"),
    ("Cu-Kr Y-Xe Hf-Rn", "fit",
     "cc-pVDZ-PP/C cc-pVTZ-PP/C cc-pVQZ-PP/C aug-cc-pVDZ-PP/C aug-cc-pVTZ-PP/C aug-cc-pVQZ-PP/C "
     "cc-pwCVDZ-PP/C cc-pwCVTZ-PP/C cc-pwCVQZ-PP/C aug-cc-pwCVDZ-PP/C aug-cc-pwCVTZ-PP/C "
     "aug-cc-pwCVQZ-PP/C"),
    ("H-Ar", "fit", "cc-pVDZ-F12-MP2Fit cc-pVTZ-F12-MP2Fit cc-pVQZ-F12-MP2Fit"),
    ("Ga-Kr In-Xe Tl-Rn", "fit", "cc-pVDZ-PP-F12-MP2Fit cc-pVTZ-PP-F12-MP2Fit cc-pVQZ-PP-F12-MP2Fit"),
    ("Li-Ar", "fit", "cc-pCVDZ-F12-MP2Fit cc-pCVTZ-F12-MP2Fit cc-pCVQZ-F12-MP2Fit"),
    # Table 2.37
    ("H B-Ne Al-Ar", "fit", "cc-pVDZ-F12-CABS cc-pVTZ-F12-CABS cc-pVQZ-F12-CABS"),
    ("H-Ar", "fit", "cc-pVDZ-F12-OptRI cc-pVTZ-F12-OptRI cc-pVQZ-F12-OptRI"),
    ("Ga-Kr In-Xe Tl-Rn", "fit", "cc-pVDZ-PP-F12-OptRI cc-pVTZ-PP-F12-OptRI cc-pVQZ-PP-F12-OptRI"),
    ("Cu-Zn Ag-Cd Au-Hg", "fit",
     "aug-cc-pVDZ-PP-OptRI aug-cc-pVTZ-PP-OptRI aug-cc-pVQZ-PP-OptRI aug-cc-pV5Z-PP-OptRI "
     "aug-cc-pwCVDZ-PP-OptRI aug-cc-pwCVTZ-PP-OptRI aug-cc-pwCVQZ-PP-OptRI "
     "aug-cc-pwCV5Z-PP-OptRI"),
    ("Li-Ar", "fit", "cc-pCVDZ-F12-OptRI cc-pCVTZ-F12-OptRI cc-pCVQZ-F12-OptRI"),
)

ORBITAL_COVERAGE = {}
FITTING_COVERAGE = {}
BASIS_POTENTIALS = {}
BASIS_HAMILTONIANS = {}
for elements, category, keywords in _GROUPS:
    coverage = atomic_numbers(elements)
    for name in keywords.split():
        if category == "fit":
            FITTING_COVERAGE[name] = coverage
            continue
        ORBITAL_COVERAGE[name] = coverage
        if category in ("ZORA", "DKH2", "DKH3", "X2C", "SO-X2C"):
            BASIS_HAMILTONIANS[name] = category
        elif category != "all-electron":
            BASIS_POTENTIALS[name] = category
