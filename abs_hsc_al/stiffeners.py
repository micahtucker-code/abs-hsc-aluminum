"""Internals, ABS HSC Rules July 2022, Part 3, Ch.2, Sec.4 (3-2-4), aluminum.

Inputs in mm for geometry; p kN/m2; s, l in m for the rule formulas.
US units (`units="US"` / a US material): in. for geometry, psi, s and l in ft; section properties in in2 / in3 / in4
(the `_cm2/_cm3/_cm4` result keys then hold in2/in3/in4).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .materials import AluminumMaterial, E_ALUMINUM
from . import units as UN
from .plating import PlateResult, critical_buckling

# 3-2-4/1.3.1 TABLE 1 (steel and aluminum column): fraction of sigma_y.
# For aluminum sigma_y is the WELDED yield (<= 0.7 ultimate).
SIGMA_A_FACTOR = {
    "bottom_long_slam": 0.65, "bottom_long_sea": 0.50,
    "side_long_slam": 0.60, "side_long_sea": 0.50,
    "deck_long_strength": 0.33, "deck_long_other": 0.40,
    "wet_deck_long": 0.75,
    "bottom_trans_slam": 0.80, "bottom_trans_sea": 0.60,
    "side_trans_slam": 0.80, "side_trans_sea": 0.60,
    "deck_trans_strength": 0.75, "deck_trans_other": 0.75,
    "wet_deck_trans": 0.75,
    "watertight_bulkhead": 0.85, "tank_bulkhead": 0.60,
    "superstructure_deckhouse": 0.70,
}

# 1.3.2 K4 aluminum: shell / deep tank members vs deck members
K4_SHELL, K4_DECK = 0.0021, 0.0018


@dataclass
class Section:
    """Stiffener cross section plus attached plate. All mm.

    profile: 'flat' (no flange), 'tee', or 'angle'."""
    profile: str
    hw: float  # web height (flange excluded)
    tw: float
    bf: float = 0.0
    tf: float = 0.0
    t_plate: float = 0.0
    b_eff: float = 0.0  # effective plate flange width
    units: str = "SI"

    def parts(self):
        """(area, centroid height above plate underside) for each part, mm."""
        p = [(self.b_eff * self.t_plate, self.t_plate / 2)]
        p.append((self.hw * self.tw, self.t_plate + self.hw / 2))
        if self.profile in ("tee", "angle") and self.bf > 0:
            p.append((self.bf * self.tf, self.t_plate + self.hw + self.tf / 2))
        return p

    def own_I(self):
        out = [self.b_eff * self.t_plate ** 3 / 12, self.tw * self.hw ** 3 / 12]
        if self.profile in ("tee", "angle") and self.bf > 0:
            out.append(self.bf * self.tf ** 3 / 12)
        return out

    @property
    def height(self) -> float:
        h = self.t_plate + self.hw
        if self.profile in ("tee", "angle") and self.bf > 0:
            h += self.tf
        return h

    def properties(self) -> dict:
        U = UN.get(self.units)
        parts = self.parts()
        A = sum(a for a, _ in parts)
        yb = sum(a * y for a, y in parts) / A
        I = sum(i + a * (y - yb) ** 2 for i, (a, y) in zip(self.own_I(), parts))
        c_top = self.height - yb
        return {
            "A_cm2": A / U.area_div,
            "I_cm4": I / U.inertia_div,
            "yb_mm": yb,
            "SM_plate_cm3": I / yb / U.mod_div,
            "SM_flange_cm3": I / c_top / U.mod_div,
            "SM_cm3": I / max(yb, c_top) / U.mod_div,  # governing (smaller) modulus
        }


def effective_plate_width(kind: str, spacing_mm: float, t_plate: float, span_m: float = 0.0, units: str = "SI") -> float:
    """3-1-2 effective flange: secondary min(s, 60 t); primary min(spacing, 0.33 l, 750 mm (30 in.))."""
    U = UN.get(units)
    if kind == "secondary":
        return min(spacing_mm, 60.0 * t_plate)
    if kind == "primary":
        return min(spacing_mm, 0.33 * span_m * U.small_per_big, U.eff_cap)
    raise ValueError("kind must be 'secondary' or 'primary'")


def sigma_a(mat: AluminumMaterial, member_case: str) -> float:
    return SIGMA_A_FACTOR[member_case] * mat.sigma_y_design


def required_SM(p: float, s_m: float, l_m: float, sa: float, no_end_attach_wt: bool = False, units: str = "SI") -> float:
    """3-2-4/1.3.1: SM = 83.3 p s l^2 / sigma_a (cm3);  144 p s l^2 / sigma_a (in3). +50% for stiffeners without
    end attachments on WT bulkheads."""
    sm = UN.get(units).SM_c * p * s_m * l_m ** 2 / sa
    return sm * 1.5 if no_end_attach_wt else sm


def required_I(p: float, s_m: float, l_m: float, deck: bool = False, units: str = "SI") -> float:
    """3-2-4/1.3.2: I = 260 p s l^3 / (K4 E) (cm4);  54 p s l^3 / (K4 E) (in4), aluminum."""
    U = UN.get(units)
    k4 = K4_DECK if deck else K4_SHELL
    return U.I_c * p * s_m * l_m ** 3 / (k4 * U.E)


def required_web_thickness(dw: float, p: float, s_m: float, l_m: float,
                           mat: AluminumMaterial, bottom_primary: bool = False) -> tuple[float, float, float]:
    """3-2-4/1.9.1. Returns (governing, proportion-based, shear-based) mm.
    Proportion: dw/50 sqrt(sigma_y/127.6 [18,500 psi]), sigma_y = unwelded yield (conservative reading).
    Shear: 1000 [144] p s l / (2 dw tau_a), tau_a = 0.5 tau_yw (0.75 for bottom primary)."""
    U = mat.U
    t1 = dw / 50.0 * math.sqrt(mat.sigma_y_unwelded / U.sigma_d)  # 127.6 N/mm2 (18,500 psi)
    tau_a = (0.75 if bottom_primary else 0.5) * mat.tau_yw
    t2 = U.web_shear_c * p * s_m * l_m / (2.0 * dw * tau_a)  # 1000 (SI), 144 (US)
    return max(t1, t2), t1, t2


def _c2(sigma_work: float, sy: float) -> float:
    """1.5.6 C2: 1 where sa > 0.8 sy; 0.8 sy/sa otherwise, sa not below 0.55 sy."""
    sa = max(sigma_work, 0.55 * sy)
    return 1.0 if sa > 0.8 * sy else 0.8 * sy / sa


def proportion_limit(profile: str, mat: AluminumMaterial, sigma_work: float | None = None) -> float:
    """1.5.6 max dw/tw. flat 0.5, built-up/angle/tee 1.5, bulb 0.85, each x sqrt(E/sy) x C2."""
    sy = mat.sigma_y_unwelded
    c2 = _c2(sigma_work if sigma_work is not None else 0.55 * sy, sy)
    coef = {"flat": 0.5, "tee": 1.5, "angle": 1.5, "bulb": 0.85}[profile]
    return coef * math.sqrt(mat.E / sy) * c2


def column_buckling(mat: AluminumMaterial, I_cm4: float, A_cm2: float, l_m: float) -> float:
    """3-2-4/1.5.1: sigma_E = E Ia / (c1 A l^2), c1 = 1000 (SI), 14.4 (US); then 1.5.3 sigma_c."""
    sE = mat.E * I_cm4 / (mat.U.c1_col * A_cm2 * l_m ** 2)
    return critical_buckling(sE, mat.sigma_y_unwelded)


def check_stiffener(
    mid: str, mat: AluminumMaterial, member_case: str, p: float, s_m: float, l_m: float,
    sec: Section, deck: bool = False, bottom_primary: bool = False,
    no_end_attach_wt: bool = False, sigma_compr: float | None = None,
) -> list[PlateResult]:
    """Runs SM, I, web thickness, web/flange proportion checks and optional column buckling."""
    U = mat.U
    us = U.name == "US"
    props = sec.properties()
    sa = sigma_a(mat, member_case)
    sm, lb, ps, ss, ar, md, iu = U.small, U.big, U.p, U.sig, U.area, U.mod, U.inertia
    dd = 4 if us else 2
    res: list[PlateResult] = []
    sm_req = required_SM(p, s_m, l_m, sa, no_end_attach_wt, U.name)
    res.append(PlateResult(mid, "section modulus", "3-2-4/1.3.1", sm_req,
                           props["SM_cm3"], md, {"sigma_a": sa, "p": p, "s": s_m, "l": l_m},
                           formula=f"SM = {U.SM_c:g} p s l^2 / sigma_a  [{md}]  (x1.5 for WT bulkhead stiffener without end attachments); sigma_a from TABLE 1",
                           working=f"p = {p:.{3 if us else 2}f} {ps}, s = {s_m:g} {lb}, l = {l_m:g} {lb}, sigma_a = {SIGMA_A_FACTOR[member_case]:g} x "
                                   f"{mat.sigma_y_design:.{0 if us else 1}f} = {sa:.{0 if us else 1}f} {ss};  SM = {sm_req:.{3 if us else 1}f} {md}. "
                                   f"Section (with {sec.b_eff:.{2 if us else 0}f} {sm} plate): A = {props['A_cm2']:.{3 if us else 2}f} {ar}, NA {props['yb_mm']:.{3 if us else 1}f} {sm} above plate underside, "
                                   f"I = {props['I_cm4']:.{3 if us else 1}f} {iu}, SM = {props['SM_cm3']:.{3 if us else 1}f} {md} (smaller of plate/flange side)"))
    i_req = required_I(p, s_m, l_m, deck, U.name)
    res.append(PlateResult(mid, "moment of inertia", "3-2-4/1.3.2", i_req,
                           props["I_cm4"], iu, {"K4": K4_DECK if deck else K4_SHELL},
                           formula=f"I = {U.I_c:g} p s l^3 / (K4 E)  [{iu}]",
                           working=f"K4 = {K4_DECK if deck else K4_SHELL:g}, E = {U.E:g};  I = {i_req:.{3 if us else 1}f} {iu}"))
    tw_req, t1, t2 = required_web_thickness(sec.hw, p, s_m, l_m, mat, bottom_primary)
    res.append(PlateResult(mid, "web thickness", "3-2-4/1.9.1", tw_req, sec.tw, sm,
                           {"proportion": t1, "shear": t2},
                           formula=f"t >= dw/50 sqrt(sigma_y/{U.sigma_d:g})  and  t >= {U.web_shear_c:g} p s l / (2 dw tau_a);  tau_a = 0.5 tau_yw (0.75 bottom primary)",
                           working=f"dw = {sec.hw:g} {sm}, sigma_y = {mat.sigma_y_unwelded:g} (unwelded): {t1:.{dd}f} {sm};  "
                                   f"tau_yw = {mat.tau_yw:.{0 if us else 1}f}: {t2:.{dd}f} {sm};  governing {tw_req:.{dd}f} {sm}"))
    lim = proportion_limit(sec.profile, mat, sigma_compr)
    ratio = sec.hw / sec.tw
    # reported as ratio vs limit: 'required' = actual dw/tw, 'provided' = limit
    res.append(PlateResult(mid, "web proportion dw/tw", "3-2-4/1.5.6", ratio, lim, "-", {},
                           formula="Limit check: dw/tw <= coef x sqrt(E/sigma_y) x C2 (coef 0.5 flat bar, 1.5 tee/angle, 0.85 bulb). Column 'Required' = actual ratio, 'Provided' = limit",
                           working=f"dw/tw = {sec.hw:g}/{sec.tw:g} = {ratio:.1f};  limit = {lim:.1f}"))
    if sec.profile in ("tee", "angle") and sec.bf > 0 and sec.tf > 0:
        flim = proportion_limit("tee", mat, sigma_compr) / 3.0  # outstanding flange: 0.5 vs 1.5 coefficient
        res.append(PlateResult(mid, "flange outstand proportion", "3-2-4/1.5.6(d)",
                               (sec.bf / 2 if sec.profile == "tee" else sec.bf) / sec.tf, flim, "-", {},
                               formula="Limit check: outstand/tf <= 0.5 sqrt(E/sigma_y) C2. 'Required' = actual ratio, 'Provided' = limit",
                               working=f"outstand/tf = {(sec.bf / 2 if sec.profile == 'tee' else sec.bf):g}/{sec.tf:g};  limit = {flim:.1f}"))
    if sigma_compr is not None:
        sc = column_buckling(mat, props["I_cm4"], props["A_cm2"], l_m)
        res.append(PlateResult(mid, "column buckling (1.2 x working)", "3-2-4/1.5.1,1.5.5",
                               1.2 * sigma_compr, sc, ss, {},
                               formula=f"sigma_E = E Ia / ({U.c1_col:g} A l^2); sigma_c per 1.5.3; need sigma_c >= 1.2 sigma_a",
                               working=f"Ia = {props['I_cm4']:.{3 if us else 1}f} {iu}, A = {props['A_cm2']:.{3 if us else 2}f} {ar}, l = {l_m:g} {lb};  sigma_c = {sc:.{0 if us else 1}f} {ss} vs 1.2 x {sigma_compr:g}"))
    return res
