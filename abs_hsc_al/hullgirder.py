"""Longitudinal hull girder strength, ABS HSC Rules July 2022, Part 3, Ch.2, Sec.1 (3-2-1).

Moments in kN-m, section modulus in cm2-m, inertia in cm2-m2 as printed in the Rule.
Displacement in tonnes.
"""
from __future__ import annotations

import math

from .materials import AluminumMaterial
from .plating import PlateResult
from . import pressures as P

C_ALUMINUM = 0.90
FP = 17.5  # kN/cm2, 3-2-1/1.1.2(c),(e)
K1_W, K2_W = 110.0, 190.0
C3 = 1.25
C4 = 4.9
K_TABLE2_ALUM = (13.33, 11.1)  # (L <= 61 m, L > 61 m)


def C1(L: float) -> float:
    """3-2-1/1.1.1."""
    if L < 90.0:
        return 0.044 * L + 3.75
    return 10.75 - ((300.0 - L) / 100.0) ** 1.5


def Cb_min(L: float) -> float:
    if L < 35.0:
        return 0.45
    if L >= 61.0:
        return 0.60
    return 0.45 + 0.15 * (L - 35.0) / (61.0 - 35.0)


def Cb_used(L: float, Cb: float) -> float:
    return max(Cb, Cb_min(L))


def K3(V: float, L: float) -> float:
    return min(max(0.70 + 0.30 * V / (2.36 * math.sqrt(L)), 1.0), 1.30)


def SM_all_craft(L: float, B: float, Cb: float, V: float, mat: AluminumMaterial) -> float:
    """3-2-1/1.1.1 (cm2-m)."""
    return 0.01 * C1(L) * L ** 2 * B * (Cb_used(L, Cb) + 0.7) * K3(V, L) * C_ALUMINUM * mat.Q


# 3-2-1/1.1.2(d) TABLE 1 minimum (1 + ncg)
def min_1_plus_ncg(delta_t: float) -> float:
    if delta_t <= 180.0:
        return 3.0
    if delta_t >= 1200.0:
        return 1.0
    pts = [(180.0, 3.0), (400.0, 2.0), (1200.0, 1.0)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= delta_t <= x1:
            return y0 + (y1 - y0) * (delta_t - x0) / (x1 - x0)
    raise AssertionError


def moments_61m_plus(v: P.Vessel, Cb: float) -> dict:
    """3-2-1/1.1.2(b)-(d). Returns kN-m values (signs as magnitudes)."""
    c1, L, B = C1(v.L), v.L, v.B
    cb = Cb_used(L, Cb)
    Mws = K1_W * c1 * L ** 2 * B * (cb + 0.7) * 1e-3
    Mwh = K2_W * c1 * L ** 2 * B * cb * 1e-3
    Msws = 0.0
    Mswh = 0.375 * FP * c1 * 0.01 * L ** 2 * B * (cb + 0.7)
    n1 = max(1.0 + P.ncg(v), min_1_plus_ncg(v.delta_t))
    AR = 0.697 * v.delta_t / v.d_min
    ls = AR / v.Bw
    Msl = C3 * v.delta_t * n1 * (L - ls)
    return {"Mws": Mws, "Mwh": Mwh, "Msws": Msws, "Mswh": Mswh, "Msl": Msl, "1+ncg": n1, "ls": ls}


def SM_1_1_2e(v: P.Vessel, Cb: float, mat: AluminumMaterial,
              Mswh: float | None = None, Msws: float | None = None) -> tuple[float, dict]:
    """3-2-1/1.1.2(e): SM = Mt C Q / fp, Mt greatest of Mswh+Mwh, -Msws-Mws (magnitudes), Msl."""
    m = moments_61m_plus(v, Cb)
    if Mswh is not None:
        m["Mswh"] = Mswh
    if Msws is not None:
        m["Msws"] = Msws
    Mt = max(m["Mswh"] + m["Mwh"], abs(m["Msws"]) + m["Mws"], m["Msl"])
    m["Mt"] = Mt
    return Mt * C_ALUMINUM * mat.Q / FP, m


def I_required(L: float, SM: float, mat: AluminumMaterial, restricted_service: bool = False) -> float:
    """3-2-1/1.5: I = (L / (Q C)) (SM / K), K aluminum 13.33 (L<=61 m) / 11.1 (L>61 m)."""
    K = K_TABLE2_ALUM[1] if L > 61.0 else K_TABLE2_ALUM[0]
    return L / (mat.Q * C_ALUMINUM) * SM / K


def shear_allowable(mat: AluminumMaterial) -> float:
    """3-2-1/1.9.1: 11.0 / Q kN/cm2."""
    return 11.0 / mat.Q


def slam_shear(delta_t: float, n1: float, F: float) -> float:
    """3-2-1/1.9.3: Fsl = C4 F Delta (ncg+1) (kN); F is F1 or F2 from figures."""
    return C4 * F * delta_t * n1


def wave_shear(L: float, B: float, Cb: float, F: float, positive: bool = True) -> float:
    """3-2-1/1.9.2 (kN)."""
    f = 30.0 * F * C1(L) * L * B * (Cb_used(L, Cb) + 0.7) * 1e-2
    return f if positive else -f


def catamaran_loads(delta_t: float, B_cl: float, L: float, ncg: float) -> dict:
    """3-2-1/3.3."""
    n1 = max(1.0 + ncg, min_1_plus_ncg(delta_t))
    return {"Mtb": 2.5 * delta_t * B_cl * n1, "Mtt": 1.25 * delta_t * L * n1, "Qt": 2.5 * delta_t * n1, "n1": n1}


def catamaran_allowables(mat: AluminumMaterial) -> dict:
    """3-2-1/3.5.3, sigma_y unwelded capped at 0.7 sigma_uw."""
    sy = mat.sigma_ya
    return {"sigma_a": 0.66 * sy, "sigma_ab": 0.75 * sy, "tau_a": 0.38 * sy}


def check_hull_girder(v: P.Vessel, mat: AluminumMaterial, SM_prov_deck: float, SM_prov_bottom: float,
                      I_prov: float, Cb: float | None = None,
                      Mswh: float | None = None, Msws: float | None = None) -> list[PlateResult]:
    """SM_prov_* in cm3 (converted x1/100 to the Rule's cm2-m); I_prov in cm4 (x1/1e4 to cm2-m2)."""
    SM_prov_deck, SM_prov_bottom, I_prov = SM_prov_deck / 100.0, SM_prov_bottom / 100.0, I_prov / 1e4
    cb = Cb if Cb is not None else (v.Cb if v.Cb is not None else v.Cb_calc)
    SM_req = SM_all_craft(v.L, v.B, cb, v.V, mat)
    res = []
    detail = {"Cb_used": Cb_used(v.L, cb), "C1": C1(v.L), "K3": K3(v.V, v.L), "Q": mat.Q}
    governing = SM_req
    if v.L >= 61.0:
        sm2, m = SM_1_1_2e(v, cb, mat, Mswh, Msws)
        detail.update(m)
        res.append(PlateResult("hull girder", "section modulus 0.4L (1.1.2e)", "3-2-1/1.1.2(e)", sm2,
                               min(SM_prov_deck, SM_prov_bottom), "cm2-m", m,
                               formula="SM = Mt C Q / fp, Mt = greatest of (Mswh + Mwh), (Msws + Mws), Msl;  fp = 17.5 kN/cm2",
                               working=f"Mws = {m['Mws']:.0f}, Mwh = {m['Mwh']:.0f}, Mswh = {m['Mswh']:.0f}, Msws = {m['Msws']:.0f}, "
                                       f"Msl = {m['Msl']:.0f} kN-m;  Mt = {m['Mt']:.0f};  SM = {sm2:.1f} cm2-m"))
        governing = max(SM_req, sm2)
    res.insert(0, PlateResult("hull girder", "section modulus (1.1.1)", "3-2-1/1.1.1", SM_req,
                              min(SM_prov_deck, SM_prov_bottom), "cm2-m", detail,
                              formula="SM = C1 C2 L^2 B (Cb + 0.7) K3 C Q  [cm2-m];  C2 = 0.01, C = 0.90 (aluminum)",
                              working=f"C1 = {detail['C1']:.3f}, L = {v.L:g}, B = {v.B:g}, Cb = {detail['Cb_used']:.3f}, K3 = {detail['K3']:.3f}, "
                                      f"Q = {mat.Q:.3f};  SM = {SM_req:.1f} cm2-m (= {SM_req * 100:.0f} cm3)"))
    res.append(PlateResult("hull girder", "moment of inertia", "3-2-1/1.5",
                           I_required(v.L, governing, mat), I_prov, "cm2-m2", {"SM_governing": governing},
                           formula="I = (L / (Q C)) (SM / K)  [cm2-m2];  K = 13.33 (L <= 61 m) / 11.1 (L > 61 m), aluminum",
                           working=f"L = {v.L:g}, Q = {mat.Q:.3f}, C = 0.9, SM = {governing:.1f};  I = {I_required(v.L, governing, mat):.1f} cm2-m2 "
                                   f"(= {I_required(v.L, governing, mat) * 1e4:.3g} cm4)"))
    return res
