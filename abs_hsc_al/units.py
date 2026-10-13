"""Unit systems: SI (the Rule's primary units) and US customary (the Rule's bracketed US values).

Every constant that the ABS HSC Rules print differently for the US system is held here, so the formulas in the
other modules read their constants from one audited place (see tests/test_units.py and RULE_REFERENCE.md).
The Rule's US constants are in several places rounded and NOT exact conversions of the SI ones; the US path uses
the Rule's printed values, and where the Rule gives no US value (or an inconsistent one) the constant is derived
by exact conversion and flagged in `NOTES`.

Native units of each system (what every length / stress / pressure number means when units = "US"):

    quantity                          SI              US
    -------------------------------   -------------   ---------------
    craft lengths, breadths, drafts   m               ft
    plate / web / flange sizes, s     mm              in
    pressure                          kN/m2           psi
    stress, modulus                   N/mm2           psi
    displacement (hull girder)        tonnes          long tons
    displacement (pressures, cross)   kg              lb  (long tons x 2240)
    section area / modulus / inertia  cm2 / cm3 / cm4 in2 / in3 / in4
    hull girder SM / I                cm2-m / cm2-m2  in2-ft / in2-ft2
    bending moment / shear force      kN-m / kN       Ltf-ft / Ltf
    cross-structure Mtb, Mtt / Qt     kN-m / kN       ft-lbf / lbf

The JSON input keeps its key names in both systems (s_mm, t_mm, l_m, SM_deck_cm3 ...); with "units": "US" the
numbers are read in the US column above.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# --- exact conversion factors (used only for converting inputs between systems and for derived constants) ---
FT_PER_M = 1.0 / 0.3048
IN_PER_MM = 1.0 / 25.4
PSI_PER_NMM2 = 1000000.0 / 6894.757293168  # 1 N/mm2 = 1e6 Pa
PSI_PER_KPA = 1000.0 / 6894.757293168  # kN/m2 = kPa
LBF_PER_KN = 1000.0 / 4.4482216152605
LTON_PER_TONNE = 1000.0 / 1016.0469088  # tonne -> long ton
LB_PER_LTON = 2240.0
KG_PER_LB = 0.45359237
TF_PER_KN = 1.0 / 9.80665


@dataclass(frozen=True)
class UnitSystem:
    name: str
    # ---- labels -------------------------------------------------------------------------------------------
    big: str  # m / ft
    small: str  # mm / in
    p: str  # pressure
    sig: str  # stress
    area: str
    mod: str
    inertia: str
    sm_hg: str
    i_hg: str
    moment: str
    force: str
    shear_hg: str  # hull girder shear stress unit
    disp: str  # hull girder displacement unit
    disp_p: str  # displacement unit in the pressure formulas
    rho: str  # weight density
    area_big: str  # 'm2' / 'ft2'
    # ---- geometry scale: small -> section units ------------------------------------------------------------
    small_per_big: float  # mm per m / in per ft
    area_div: float  # mm2 -> cm2 (100) / in2 (1)
    mod_div: float  # mm3 -> cm3 (1e3) / in3 (1)
    inertia_div: float  # mm4 -> cm4 (1e4) / in4 (1)
    sm_hg_per_mod: float  # section modulus (cm3 / in3) -> Rule hull-girder unit (cm2-m / in2-ft)
    i_hg_per_inertia: float  # cm4 / in4 -> cm2-m2 / in2-ft2
    # ---- 3-2-2 pressures -----------------------------------------------------------------------------------
    delta_to_load: float  # displacement (tonnes / long tons) -> kg / lb
    N1: float
    N1_wd: float  # wet deck equation (3-2-2/3.5)
    N2: float
    N3: float
    KN: float
    H_a: float
    H_b: float
    AR_pr: float  # AR = AR_pr * delta(kg/lb) / d  (cm2 / in2)
    L24: float
    L30_hs: float
    L30_fore: float
    L61: float
    L80_cf: float
    CF_a: float
    Hs_a: float
    Hs_min_add: float  # D + 1.22 m / D + 4 ft
    fore_c: float  # 0.28 / 0.92
    fore_L: float  # 0.6 / 0.33
    wd_V1_a_short: float
    wd_V1_b_short: float
    wd_V1_a_long: float
    wd_V1_a_long_printed: float
    wd_V1_b_long: float
    wd_55: float
    deck_fwd: tuple
    deck_encl: tuple
    deck_accom: float
    deck_rho_min: float
    deck_rho_div: float
    T4_L_lo: float
    T4_L_hi: float
    T4: dict
    tank_rhog_min: float
    FD_table: tuple
    h13: dict
    # ---- 3-2-3 / 3-2-4 -------------------------------------------------------------------------------------
    E: float
    plate_div: float  # t = s sqrt(p k / (plate_div sigma_a))
    min_t: dict  # location -> (a, b, floor) in small length units
    SM_c: float
    I_c: float
    c1_col: float
    sigma_d: float
    web_shear_c: float
    eff_cap: float  # primary member effective width cap 750 mm / 30 in
    # ---- 3-2-1 hull girder ---------------------------------------------------------------------------------
    C1_a: float
    C1_L: float
    C1_off: float
    C1_div: float
    C2: float
    K3_div: float
    Cb_L_lo: float
    Cb_L_hi: float
    Cb_calc_c: float  # Cb = delta / (1.025 L B d)  <->  35 delta / (L B d)
    q5_n: float
    Q0_n: float
    k1: float
    k2: float
    fp: float
    C3: float
    AR_hg: float
    ncg_table: tuple
    shear_allow_n: float
    k_wave: float
    C4: float
    K1_cat: float
    K2_cat: float
    # ---- section calculator / misc ---------------------------------------------------------------------------
    shear_web_deg: float = 45.0


_TABLE4_SI = {"front_plating": (24.1, 37.9), "front_stiffeners": (24.1, 24.1), "side_aft_plating": (10.3, 13.8),
              "side_aft_stiffeners": (10.3, 10.3), "top_forward": (6.9, 8.6), "top_aft": (3.4, 6.9)}
_TABLE4_US = {"front_plating": (3.5, 5.50), "front_stiffeners": (3.5, 3.5), "side_aft_plating": (1.5, 2.0),
              "side_aft_stiffeners": (1.5, 1.5), "top_forward": (1.0, 1.25), "top_aft": (0.5, 1.0)}

SI = UnitSystem(
    name="SI", big="m", small="mm", p="kN/m2", sig="N/mm2", area="cm2", mod="cm3", inertia="cm4", sm_hg="cm2-m",
    i_hg="cm2-m2", moment="kN-m", force="kN", shear_hg="kN/cm2", disp="t", disp_p="kg", rho="kN/m3", area_big="m2",
    small_per_big=1000.0, area_div=100.0, mod_div=1e3, inertia_div=1e4, sm_hg_per_mod=1.0 / 100.0, i_hg_per_inertia=1.0 / 1e4,
    delta_to_load=1000.0, N1=0.1, N1_wd=0.1, N2=0.0078, N3=9.8, KN=0.256, H_a=0.0172, H_b=3.653, AR_pr=6.95,
    L24=24.0, L30_hs=30.0, L30_fore=30.0, L61=61.0, L80_cf=80.0, CF_a=0.0125, Hs_a=0.083, Hs_min_add=1.22,
    fore_c=0.28, fore_L=0.6,
    wd_V1_a_short=4.0, wd_V1_b_short=1.0, wd_V1_a_long=5.0, wd_V1_a_long_printed=5.0, wd_V1_b_long=1.0, wd_55=55.0,
    deck_fwd=(0.20, 7.6), deck_encl=(0.10, 6.1), deck_accom=5.0, deck_rho_min=7.04, deck_rho_div=1.0,
    T4_L_lo=12.2, T4_L_hi=30.5, T4=_TABLE4_SI, tank_rhog_min=10.05,
    FD_table=((250, 0.85), (500, 0.75), (750, 0.60), (1000, 0.50), (1250, 0.40)),
    h13={"high-speed": 4.0, "coastal": 2.5, "riverine": 0.5, "crewboat": 3.35},
    E=6.9e4, plate_div=1000.0,
    min_t={"bottom": (0.70, 1.0, 4.0), "side": (0.62, 1.0, 3.5), "strength_deck": (0.62, 1.0, 3.5),
           "lower_deck_or_bulkhead": (0.52, 1.0, 3.5)},
    SM_c=83.3, I_c=260.0, c1_col=1000.0, sigma_d=127.6, web_shear_c=1000.0, eff_cap=750.0,
    C1_a=0.044, C1_L=90.0, C1_off=300.0, C1_div=100.0, C2=0.01, K3_div=2.36, Cb_L_lo=35.0, Cb_L_hi=61.0, Cb_calc_c=1.0 / 1.025,
    q5_n=115.0, Q0_n=635.0, k1=110.0, k2=190.0, fp=17.5, C3=1.25, AR_hg=0.697,
    ncg_table=((180.0, 3.0), (400.0, 2.0), (1200.0, 1.0)), shear_allow_n=11.0, k_wave=30.0, C4=4.9, K1_cat=2.5, K2_cat=1.25,
)

US = UnitSystem(
    name="US", big="ft", small="in", p="psi", sig="psi", area="in2", mod="in3", inertia="in4", sm_hg="in2-ft",
    i_hg="in2-ft2", moment="Ltf-ft", force="Ltf", shear_hg="Ltf/in2", disp="LT", disp_p="lb", rho="lb/ft3", area_big="ft2",
    small_per_big=12.0, area_div=1.0, mod_div=1.0, inertia_div=1.0, sm_hg_per_mod=1.0 / 12.0, i_hg_per_inertia=1.0 / 144.0,
    delta_to_load=LB_PER_LTON, N1=0.069, N1_wd=0.00442, N2=0.0016, N3=0.44, KN=0.463, H_a=0.0172, H_b=11.98, AR_pr=1.61,
    L24=79.0, L30_hs=100.0, L30_fore=98.0, L61=200.0, L80_cf=262.0, CF_a=0.00381, Hs_a=0.083, Hs_min_add=4.0,
    fore_c=0.92, fore_L=0.33,
    # 3-2-2/3.5: V1 = 7.24 h/sqrt(L) + 3.28 ft/s (L < 200 ft); for L >= 200 ft the Rule prints 16.4 h/sqrt(L) + 3.28,
    # which does not follow from the SI 5 h/sqrt(L) + 1 (that converts to 9.06); the consistent value is the default.
    wd_V1_a_short=7.24, wd_V1_b_short=3.28, wd_V1_a_long=9.06, wd_V1_a_long_printed=16.4, wd_V1_b_long=3.28,
    wd_55=55.0 * PSI_PER_KPA / FT_PER_M,  # no US constant is printed for this equation: converted (2.43)
    deck_fwd=(0.0088, 1.10), deck_encl=(0.0044, 0.88), deck_accom=0.71, deck_rho_min=44.8, deck_rho_div=144.0,
    T4_L_lo=40.0, T4_L_hi=100.0, T4=_TABLE4_US, tank_rhog_min=0.44,
    FD_table=((9.75, 0.85), (16.75, 0.75), (29.5, 0.60), (39.25, 0.50), (49.25, 0.40)),
    h13={"high-speed": 13.0, "coastal": 8.5, "riverine": 1.75, "crewboat": 11.0},
    E=1.0e7, plate_div=1.0,
    min_t={"bottom": (0.015, 0.04, 0.16), "side": (0.013, 0.04, 0.14), "strength_deck": (0.013, 0.04, 0.14),
           "lower_deck_or_bulkhead": (0.011, 0.04, 0.14)},
    SM_c=144.0, I_c=54.0, c1_col=14.4, sigma_d=18500.0, web_shear_c=144.0, eff_cap=30.0,
    C1_a=0.0134, C1_L=295.0, C1_off=984.0, C1_div=328.0, C2=1.44e-4, K3_div=1.30, Cb_L_lo=115.0, Cb_L_hi=200.0, Cb_calc_c=35.0,
    q5_n=17000.0, Q0_n=92000.0, k1=1.026, k2=1.772, fp=11.33, C3=0.125, AR_hg=25.0,
    ncg_table=((177.0, 3.0), (394.0, 2.0), (1181.0, 1.0)), shear_allow_n=7.122, k_wave=0.2797, C4=0.5, K1_cat=0.255, K2_cat=0.1275,
)

SYSTEMS = {"SI": SI, "US": US}


def get(name: str | None) -> UnitSystem:
    key = (name or "SI").upper()
    if key not in SYSTEMS:
        raise ValueError(f"units must be 'SI' or 'US', not {name!r}")
    return SYSTEMS[key]


def fmt_len(x: float, u: UnitSystem, small: bool = False) -> str:
    return f"{x:g} {u.small if small else u.big}"


# Items where the Rule's printed US text is inconsistent, ambiguous or absent (shown in the report and the README).
NOTES = [
    "3-2-2/3.5.2 (wet deck, L >= 61 m): the Rule gives one constant (55) for all unit systems; for US it is converted (2.43 psi per ft/s).",
    "3-2-2/3.5 V1 for L >= 200 ft is printed as 16.4 h1/3/sqrt(L) + 3.28 ft/s; the SI expression 5 h1/3/sqrt(L) + 1 m/s converts to 9.06. "
    "9.06 is used unless 'v1_printed_us' is set.",
    "3-2-2/3.3.3 (multi-hull fore-end pressure): the US line prints 0.28 where 3-2-2/1.3.3 prints 0.92; 0.92 is dimensionally consistent and is used.",
    "3-2-2/1.1.3 TABLE 2 (FD minimum): 500 mm is printed as 16.75 in. (19.7 in. by conversion); the printed value is used.",
    "US constants rounded by the Rule (N1 0.069, qa 17000/sigma, 0.015/0.013/0.011 in minimum-thickness coefficients, "
    "C2 1.44e-4, k 0.2797 ...) do not convert exactly from the SI ones, so SI and US results for the same craft differ by a few percent.",
]


# ------------------------------------------------------------------------------------------------------------------
# Input conversion (SI <-> US) for the GUI selector and the CLI
# ------------------------------------------------------------------------------------------------------------------
# kind -> factor SI -> US
_F = {
    "len": FT_PER_M,  # m -> ft
    "small": IN_PER_MM,  # mm -> in
    "area_mm2": IN_PER_MM ** 2,
    "inertia_mm4": IN_PER_MM ** 4,
    "stress": PSI_PER_NMM2,
    "p": PSI_PER_KPA,
    "rho": LBF_PER_KN / FT_PER_M ** 3,  # kN/m3 -> lb/ft3
    "rho_g": PSI_PER_KPA / FT_PER_M,  # kN/m3 -> psi/ft (liquid weight in tank pressures)
    "disp": LTON_PER_TONNE,
    "cm2": 1.0 / 6.4516,
    "cm3": 1.0 / 16.387064,
    "cm4": 1.0 / 41.62314256,
    "sm_hg": (1.0 / 6.4516) * FT_PER_M,  # cm2-m -> in2-ft
    "moment": TF_PER_KN * (1.0 / 1.0160469088) * FT_PER_M,  # kN-m -> Ltf-ft
    "force": 1.0 / (9.80665 * 1.0160469088),  # kN -> Ltf
}

_VESSEL_LEN = ("L", "Lw", "B", "Bw", "D", "d", "B_cl")
_PLATE_SMALL = ("s_mm", "l_mm", "t_mm")
_STIFF_SMALL = ("spacing_mm", "hw_mm", "tw_mm", "bf_mm", "tf_mm", "t_plate_mm")
_SPEC_LEN = ("y", "ha", "h", "h2")
_SECTION_SMALL = ("y1", "z1", "y2", "z2", "t_mm", "z_mm", "deck_z_mm", "base_z_mm", "shear_level_z_mm", "spacing_mm", "hw_mm",
                  "tw_mm", "bf_mm", "tf_mm")


def _sig(x: float, n: int) -> float:
    if x == 0 or not math.isfinite(x):
        return x
    return round(x, n - 1 - int(math.floor(math.log10(abs(x)))))


def _conv(v, f, n):
    return _sig(v * f, n) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


def _pressure_spec(spec, f, n):
    if isinstance(spec, (int, float)) and not isinstance(spec, bool):
        return _conv(spec, f["p"], n)
    s = dict(spec)
    if "value" in s:
        s["value"] = _conv(s["value"], f["p"], n)
    for k in _SPEC_LEN:
        if k in s:
            s[k] = _conv(s[k], f["len"], n)
    if "W" in s:
        s["W"] = _conv(s["W"], f["p"], n)
    if "rho" in s:
        s["rho"] = _conv(s["rho"], f["rho"], n)
    if "rho_g" in s:
        s["rho_g"] = _conv(s["rho_g"], f["rho_g"], n)
    return s


def _section(sec: dict, f, n) -> dict:
    out = dict(sec)
    for k in ("deck_z_mm", "base_z_mm", "shear_level_z_mm"):
        if k in out:
            out[k] = _conv(out[k], f["small"], n)
    mem = []
    for m in sec.get("members", []):
        m = dict(m)
        for k in ("y1", "z1", "y2", "z2", "t_mm", "z_mm"):
            if k in m:
                m[k] = _conv(m[k], f["small"], n)
        if "area_mm2" in m:
            m["area_mm2"] = _conv(m["area_mm2"], f["area_mm2"], n)
        if "I_mm4" in m:
            m["I_mm4"] = _conv(m["I_mm4"], f["inertia_mm4"], n)
        if "stiffeners" in m:
            s = dict(m["stiffeners"])
            for k in ("spacing_mm", "hw_mm", "tw_mm", "bf_mm", "tf_mm"):
                if k in s:
                    s[k] = _conv(s[k], f["small"], n)
            m["stiffeners"] = s
        mem.append(m)
    if "members" in sec:
        out["members"] = mem
    if "dxf" in sec:
        d = dict(sec["dxf"])
        def _layer(v):
            if not isinstance(v, dict):
                return v
            v = dict(v)
            for k in ("t_mm", "length_mm"):
                if k in v:
                    v[k] = _conv(v[k], f["small"], n)
            return v
        d["layers"] = {k: _layer(v) for k, v in d.get("layers", {}).items()}
        d["segments"] = [[s[0]] + [_conv(x, f["small"], n) for x in s[1:]] for s in d.get("segments", [])]
        if isinstance(d.get("meta"), dict):
            meta = dict(d["meta"])
            if "bbox" in meta:
                meta["bbox"] = [_conv(x, f["small"], n) for x in meta["bbox"]]
            d["meta"] = meta
        out["dxf"] = d
    return out


def convert_inputs(data: dict, to: str, round_sig: int = 6) -> dict:
    """Return a copy of an input document converted to the unit system `to` ('SI' or 'US').

    The document's own "units" key says what it is now (default SI). Dimensionless values, angles and the
    Rule-figure factors are untouched. Alloy-library materials keep their reference and only the thickness converts
    (the library returns the Rule's own values for the system in use); explicit material strengths are converted."""
    to = get(to).name
    now = get(data.get("units")).name
    out = json_copy(data)
    if now == to:
        out["units"] = to
        return out
    if now == "US":  # US -> SI: invert the factors
        f = {k: 1.0 / v for k, v in _F.items()}
    else:
        f = dict(_F)
    n = round_sig
    out["units"] = to
    v = out.get("vessel")
    if v:
        for k in _VESSEL_LEN:
            if k in v:
                v[k] = _conv(v[k], f["len"], n)
        if "delta_t" in v:
            v["delta_t"] = _conv(v["delta_t"], f["disp"], n)
    m = out.get("material")
    if m:
        if "alloy" in m:
            if "thickness_mm" in m:
                m["thickness_mm"] = _conv(m["thickness_mm"], f["small"], n)
        else:
            for k in ("sigma_y_unwelded", "sigma_u_unwelded", "sigma_y_welded", "sigma_u_welded"):
                if k in m:
                    m[k] = _conv(m[k], f["stress"], n)
    for pl in out.get("plates", []):
        for k in _PLATE_SMALL:
            if k in pl:
                pl[k] = _conv(pl[k], f["small"], n)
        if "loads" in pl:
            pl["loads"] = {c: _pressure_spec(s, f, n) for c, s in pl["loads"].items()}
        if "buckling" in pl and "sigma_work" in pl["buckling"]:
            pl["buckling"]["sigma_work"] = _conv(pl["buckling"]["sigma_work"], f["stress"], n)
    for st in out.get("stiffeners", []):
        for k in _STIFF_SMALL:
            if k in st:
                st[k] = _conv(st[k], f["small"], n)
        if "l_m" in st:
            st["l_m"] = _conv(st["l_m"], f["len"], n)
        if "sigma_compr" in st and st["sigma_compr"] is not None:
            st["sigma_compr"] = _conv(st["sigma_compr"], f["stress"], n)
        if "load" in st:
            st["load"] = _pressure_spec(st["load"], f, n)
    if out.get("section"):
        out["section"] = _section(out["section"], f, n)
    hg = out.get("hull_girder")
    if hg:
        for k, kind in (("SM_deck_cm3", "cm3"), ("SM_bottom_cm3", "cm3"), ("I_cm4", "cm4"), ("Mswh_kNm", "moment"), ("Msws_kNm", "moment")):
            if k in hg:
                hg[k] = _conv(hg[k], f[kind], n)
    hs = out.get("hull_shear")
    if hs:
        for k, kind in (("m_cm3", "cm3"), ("ts_mm", "small"), ("I_cm4", "cm4")):
            if k in hs:
                hs[k] = _conv(hs[k], f[kind], n)
        for st in hs.get("stations", []):
            if "Fsw_kN" in st:
                st["Fsw_kN"] = _conv(st["Fsw_kN"], f["force"], n)
    cs = out.get("cross_structure")
    if cs:
        if "SMt_cm2m" in cs:
            cs["SMt_cm2m"] = _conv(cs["SMt_cm2m"], f["sm_hg"], n)
        if "At_cm2" in cs:
            cs["At_cm2"] = _conv(cs["At_cm2"], f["cm2"], n)
        if cs.get("section"):
            cs["section"] = _section(cs["section"], f, n)
        for e in cs.get("elements", []):
            for k in ("x_m", "span_m"):
                if k in e:
                    e[k] = _conv(e[k], f["len"], n)
            for k, kind in (("I_cm4", "cm4"), ("SM_cm3", "cm3"), ("Aw_cm2", "cm2"), ("E_Nmm2", "stress")):
                if k in e:
                    e[k] = _conv(e[k], f[kind], n)
    return out


def json_copy(x):
    import json
    return json.loads(json.dumps(x))
