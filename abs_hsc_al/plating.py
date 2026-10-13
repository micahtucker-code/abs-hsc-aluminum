"""Plating, ABS HSC Rules July 2022, Part 3, Ch.2, Sec.3 (3-2-3), aluminum.

SI units: mm, N/mm2, kN/m2. US units (`units="US"`): in., psi, psi, with the Rule's US constants from units.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .materials import AluminumMaterial, E_ALUMINUM
from . import units as UN

# 3-2-3/1.3.1 TABLE 1: (l/s, k). Linear interpolation, k = 0.500 for l/s > 2.
_K_TABLE = [
    (1.0, 0.308), (1.1, 0.348), (1.2, 0.383), (1.3, 0.412), (1.4, 0.436),
    (1.5, 0.454), (1.6, 0.468), (1.7, 0.479), (1.8, 0.487), (1.9, 0.493),
    (2.0, 0.497),
]

# 3-2-3/1.3.1 TABLE 2: design stress as a fraction of sigma_y (aluminum).
DESIGN_STRESS_FACTOR = {
    "bottom_slam": 0.90,
    "bottom_hydro": 0.55,
    "waterjet_tunnel_slam": 0.60,
    "waterjet_tunnel_hydro": 0.55,
    "side_slam": 0.90,
    "side_hydro": 0.55,
    "above_bulkhead_deck_slam": 0.90,
    "above_bulkhead_deck_hydro": 0.55,
    "strength_deck": 0.60,
    "lower_deck": 0.60,
    "wet_deck": 0.90,
    "superstructure_deck": 0.60,
    "deep_tank_bulkhead": 0.60,
    "watertight_bulkhead": 0.95,
    "superstructure_or_deckhouse": 0.60,
}

# 3-2-3/1.3.3 minimum thickness (aluminum): a*sqrt(L*qa) + b, floor. SI (mm); the US constants (in.) are in units.US.min_t.
MIN_THICKNESS = UN.SI.min_t

# 3-2-3/1.5.2(d) TABLE 3 framing constants C2
C2 = {"floors_or_deep": 1.30, "tee_or_angle": 1.21, "bulb": 1.10, "flat_bar": 1.05}


def k_factor(l_over_s: float) -> float:
    """TABLE 1 aspect-ratio coefficient k."""
    r = max(l_over_s, 1.0)
    if r >= 2.0:
        return 0.500 if r > 2.0 else 0.497
    for (x0, y0), (x1, y1) in zip(_K_TABLE, _K_TABLE[1:]):
        if x0 <= r <= x1:
            return y0 + (y1 - y0) * (r - x0) / (x1 - x0)
    raise AssertionError


def design_stress(mat: AluminumMaterial, case: str, outside_midship_0_4L: bool = False) -> float:
    """sigma_a per TABLE 2. Note 2: bottom slamming may use sigma_y outside midship 0.4L."""
    f = DESIGN_STRESS_FACTOR[case]
    if case == "bottom_slam" and outside_midship_0_4L:
        f = 1.0
    return f * mat.sigma_y_design


def required_thickness_lateral(p: float, s_mm: float, l_mm: float, sigma_a: float, units: str = "SI") -> float:
    """3-2-3/1.3.1: t = s sqrt(p k / (1000 sigma_a)) mm (SI);  t = s sqrt(p k / sigma_a) in. (US, psi)."""
    k = k_factor(l_mm / s_mm)
    return s_mm * math.sqrt(p * k / (UN.get(units).plate_div * sigma_a))


def min_thickness(L: float, mat: AluminumMaterial, location: str) -> float:
    """3-2-3/1.3.3 (reading the root as sqrt(L*qa)), including the stated floor (mm; in. for US)."""
    a, b, floor = mat.U.min_t[location]
    return max(a * math.sqrt(L * mat.q_a) + b, floor)


def buckling_m1(l_over_s: float, framing: str, c2: float = 1.21, sigma_ratio: float = 1.0) -> float:
    """TABLE 3 m1 uniaxial. sigma_ratio = sigma'/sigma between 1/3 and 1.

    transverse m1 = C2 [1+(s/l)^2]^2, read multiplicatively (flagged ambiguity)."""
    t = min(max((1.0 - sigma_ratio) / (2.0 / 3.0), 0.0), 1.0)  # 0 at sigma'=sigma, 1 at sigma/3
    if framing == "longitudinal":
        return 4.0 + (5.8 - 4.0) * t
    if framing == "transverse":
        base = c2 * (1.0 + (1.0 / l_over_s) ** 2) ** 2
        return base * (1.0 + 0.45 * t)
    raise ValueError("framing must be 'longitudinal' or 'transverse'")


def critical_buckling(sigma_E: float, sigma_y: float) -> float:
    """3-2-3/1.5.1(b)."""
    if sigma_E <= 0.5 * sigma_y:
        return sigma_E
    return sigma_y * (1.0 - sigma_y / (4.0 * sigma_E))


def shear_m2(l_over_s: float) -> float:
    """TABLE 3 B: m2 = 5.34 + 4 (s/l)^2."""
    return 5.34 + 4.0 * (1.0 / l_over_s) ** 2


@dataclass
class PlateResult:
    id: str
    kind: str
    clause: str
    required: float
    provided: float
    unit: str = "mm"
    detail: dict = field(default_factory=dict)
    formula: str = ""  # Rule equation as printed
    working: str = ""  # same equation with this item's numbers substituted

    @property
    def utilisation(self) -> float:
        return self.required / self.provided if self.provided else float("inf")

    @property
    def passed(self) -> bool:
        return self.provided + 1e-9 >= self.required


def check_plate(
    pid: str,
    mat: AluminumMaterial,
    L: float,
    s_mm: float,
    l_mm: float,
    t_mm: float,
    location: str,  # key of MIN_THICKNESS
    loads: dict,  # {design_stress_case: pressure kN/m2}
    outside_midship_0_4L: bool = False,
) -> list[PlateResult]:
    """Runs lateral (each load case), secondary-stiffening and minimum thickness checks."""
    U = mat.U
    us = U.name == "US"
    sm, lb, ps, ss = U.small, U.big, U.p, U.sig
    dec = 4 if us else 2  # thickness decimals
    out: list[PlateResult] = []
    for case, p in loads.items():
        sa = design_stress(mat, case, outside_midship_0_4L)
        req = required_thickness_lateral(p, s_mm, l_mm, sa, U.name)
        k = k_factor(l_mm / s_mm)
        div = "1000 sigma_a" if not us else "sigma_a"
        out.append(PlateResult(pid, f"lateral ({case})", "3-2-3/1.3.1", req, t_mm, sm,
                               detail={"p": p, "sigma_a": sa, "k": k, "s": s_mm},
                               formula=f"t = s * sqrt(p k / ({div}))  [{sm}]; k from TABLE 1; sigma_a from TABLE 2",
                               working=f"s = {s_mm:g} {sm}, l/s = {l_mm / s_mm:.2f}, k = {k:.3f}, p = {p:.{3 if us else 2}f} {ps}, "
                                       f"sigma_a = {DESIGN_STRESS_FACTOR[case]:g} x {sa / DESIGN_STRESS_FACTOR[case]:.{0 if us else 1}f}"
                                       f" = {sa:.{0 if us else 1}f} {ss};  t = {req:.{dec}f} {sm}"))
    out.append(PlateResult(pid, "secondary stiffening", "3-2-3/1.3.2", 0.012 * s_mm, t_mm, sm, detail={"s": s_mm},
                           formula=f"t_al = 0.012 s  [{sm}]", working=f"0.012 x {s_mm:g} = {0.012 * s_mm:.{dec}f} {sm}"))
    a, b, fl = U.min_t[location]
    tmin_raw = a * math.sqrt(L * mat.q_a) + b
    qn = U.q5_n
    out.append(PlateResult(pid, "minimum thickness", "3-2-3/1.3.3", min_thickness(L, mat, location), t_mm, sm,
                           detail={"location": location, "qa": mat.q_a},
                           formula=f"t_al = {a:g} sqrt(L qa) + {b:g}, not less than {fl:g} {sm}  ({location})",
                           working=f"L = {L:g} {lb}, qa = {qn:g}/sigma_ya = {mat.q_a:.3f};  {a:g} x sqrt({L:g} x {mat.q_a:.3f}) + {b:g}"
                                   f" = {tmin_raw:.{dec}f} {sm}; floor {fl:g} {sm}"))
    return out


def check_plate_buckling(
    pid: str, mat: AluminumMaterial, s_mm: float, l_mm: float, t_mm: float,
    framing: str, sigma_work: float, c2: float = 1.21, sigma_ratio: float = 1.0,
) -> PlateResult:
    """3-2-3/1.5.1: sigma_c >= sigma_a (working compressive stress supplied by caller).
    Reported as required=sigma_a, provided=sigma_c (N/mm2)."""
    m1 = buckling_m1(l_mm / s_mm, framing, c2, sigma_ratio)
    sE = 0.9 * m1 * mat.E * (t_mm / s_mm) ** 2
    sc = critical_buckling(sE, mat.sigma_y_unwelded)
    return PlateResult(pid, "buckling (uniaxial)", "3-2-3/1.5.1", sigma_work, sc, mat.U.sig,
                       {"m1": m1, "sigma_E": sE, "sigma_c": sc},
                       formula="sigma_E = 0.9 m1 E (t/s)^2; sigma_c = sigma_E (<= 0.5 sigma_y) else sigma_y (1 - sigma_y/(4 sigma_E)); need sigma_c >= sigma_a",
                       working=f"m1 = {m1:.2f}, E = {mat.E:g}, t/s = {t_mm:g}/{s_mm:g}, sigma_E = {sE:.1f}, "
                               f"sigma_y = {mat.sigma_y_unwelded:g};  sigma_c = {sc:.1f} N/mm2 vs sigma_a = {sigma_work:g}")
