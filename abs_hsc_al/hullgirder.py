"""Longitudinal hull girder strength, ABS HSC Rules July 2022, Part 3, Ch.2, Sec.1 (3-2-1).

SI: moments in kN-m, section modulus in cm2-m, inertia in cm2-m2 as printed in the Rule; displacement in tonnes.
US (`units="US"`): Ltf-ft, in2-ft, in2-ft2, displacement in long tons, with the Rule's US constants (units.py).
"""
from __future__ import annotations

import math

from .materials import AluminumMaterial
from .plating import PlateResult
from . import pressures as P
from . import units as UN

C_ALUMINUM = 0.90
FP = 17.5  # kN/cm2, 3-2-1/1.1.2(c),(e); US 11.33 Ltf/in2
K1_W, K2_W = 110.0, 190.0
C3 = 1.25
C4 = 4.9
K_TABLE2_ALUM = (13.33, 11.1)  # (L <= 61 m (200 ft), L > 61 m) - the same numbers in both unit systems


def C1(L: float, units: str = "SI") -> float:
    """3-2-1/1.1.1: 0.044 L + 3.75 (L < 90 m), 10.75 - ((300 - L)/100)^1.5 above;
    US: 0.0134 L + 3.75 (L < 295 ft), 10.75 - ((984 - L)/328)^1.5."""
    U = UN.get(units)
    if L < U.C1_L:
        return U.C1_a * L + 3.75
    return 10.75 - ((U.C1_off - L) / U.C1_div) ** 1.5


def Cb_min(L: float, units: str = "SI") -> float:
    U = UN.get(units)
    if L < U.Cb_L_lo:
        return 0.45
    if L >= U.Cb_L_hi:
        return 0.60
    return 0.45 + 0.15 * (L - U.Cb_L_lo) / (U.Cb_L_hi - U.Cb_L_lo)


def Cb_used(L: float, Cb: float, units: str = "SI") -> float:
    return max(Cb, Cb_min(L, units))


def K3(V: float, L: float, units: str = "SI") -> float:
    """3-2-1/1.1.1: 0.70 + 0.30 V / (2.36 sqrt(L)) (SI/MKS), 0.70 + 0.30 V / (1.30 sqrt(L)) (US); 1.0 to 1.30."""
    return min(max(0.70 + 0.30 * V / (UN.get(units).K3_div * math.sqrt(L)), 1.0), 1.30)


def SM_all_craft(L: float, B: float, Cb: float, V: float, mat: AluminumMaterial) -> float:
    """3-2-1/1.1.1 (cm2-m; in2-ft for US)."""
    u = mat.units
    U = mat.U
    return U.C2 * C1(L, u) * L ** 2 * B * (Cb_used(L, Cb, u) + 0.7) * K3(V, L, u) * C_ALUMINUM * mat.Q


# 3-2-1/1.1.2(d) TABLE 1 minimum (1 + ncg)
def min_1_plus_ncg(delta_t: float, units: str = "SI") -> float:
    pts = [(a, b) for a, b in UN.get(units).ncg_table]  # (180, 3), (400, 2), (1200, 1)  [US: 177, 394, 1181 long tons]
    if delta_t <= pts[0][0]:
        return pts[0][1]
    if delta_t >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= delta_t <= x1:
            return y0 + (y1 - y0) * (delta_t - x0) / (x1 - x0)
    raise AssertionError


def moments_61m_plus(v: P.Vessel, Cb: float) -> dict:
    """3-2-1/1.1.2(b)-(d). Returns kN-m (Ltf-ft) values (signs as magnitudes)."""
    U = v.U
    c1, L, B = C1(v.L, v.units), v.L, v.B
    cb = Cb_used(L, Cb, v.units)
    Mws = U.k1 * c1 * L ** 2 * B * (cb + 0.7) * 1e-3
    Mwh = U.k2 * c1 * L ** 2 * B * cb * 1e-3
    Msws = 0.0
    Mswh = 0.375 * U.fp * c1 * U.C2 * L ** 2 * B * (cb + 0.7)
    n1 = max(1.0 + P.ncg(v), min_1_plus_ncg(v.delta_t, v.units))
    AR = U.AR_hg * v.delta_t / v.d_min
    ls = AR / v.Bw
    Msl = U.C3 * v.delta_t * n1 * (L - ls)
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
    return Mt * C_ALUMINUM * mat.Q / mat.U.fp, m


def I_required(L: float, SM: float, mat: AluminumMaterial, restricted_service: bool = False) -> float:
    """3-2-1/1.5: I = (L / (Q C)) (SM / K), K aluminum 13.33 (L<=61 m / 200 ft) / 11.1 (L>61 m)."""
    K = K_TABLE2_ALUM[1] if L > mat.U.L61 else K_TABLE2_ALUM[0]
    return L / (mat.Q * C_ALUMINUM) * SM / K


def shear_allowable(mat: AluminumMaterial) -> float:
    """3-2-1/1.9.1: 11.0 / Q kN/cm2  (7.122 / Q Ltf/in2)."""
    return mat.U.shear_allow_n / mat.Q


def slam_shear(delta_t: float, n1: float, F: float, units: str = "SI") -> float:
    """3-2-1/1.9.3: Fsl = C4 F Delta (ncg+1) (kN; Ltf for US with C4 = 0.5); F is F1 or F2 from figures."""
    return UN.get(units).C4 * F * delta_t * n1


def wave_shear(L: float, B: float, Cb: float, F: float, positive: bool = True, units: str = "SI") -> float:
    """3-2-1/1.9.2 (kN; Ltf for US with k = 0.2797)."""
    U = UN.get(units)
    f = U.k_wave * F * C1(L, units) * L * B * (Cb_used(L, Cb, units) + 0.7) * 1e-2
    return f if positive else -f


def catamaran_loads(delta_t: float, B_cl: float, L: float, ncg: float, units: str = "SI") -> dict:
    """3-2-1/3.3: Mtb = K1 Delta Bcl (1 + ncg), Mtt = K2 Delta L (1 + ncg), Qt = K1 Delta (1 + ncg).

    SI: K1 = 2.5, K2 = 1.25, Delta in tonnes -> kN-m, kN.  US: K1 = 0.255, K2 = 0.1275, Delta in lb -> ft-lbf, lbf
    (delta_t is entered in long tons and converted to lb here)."""
    U = UN.get(units)
    n1 = max(1.0 + ncg, min_1_plus_ncg(delta_t, units))
    D = delta_t * (U.delta_to_load if U.name == "US" else 1.0)
    return {"Mtb": U.K1_cat * D * B_cl * n1, "Mtt": U.K2_cat * D * L * n1, "Qt": U.K1_cat * D * n1, "n1": n1, "Delta": D}


def catamaran_allowables(mat: AluminumMaterial) -> dict:
    """3-2-1/3.5.3, sigma_y unwelded capped at 0.7 sigma_uw."""
    sy = mat.sigma_ya
    return {"sigma_a": 0.66 * sy, "sigma_ab": 0.75 * sy, "tau_a": 0.38 * sy}


def check_hull_girder(v: P.Vessel, mat: AluminumMaterial, SM_prov_deck: float, SM_prov_bottom: float,
                      I_prov: float, Cb: float | None = None,
                      Mswh: float | None = None, Msws: float | None = None) -> list[PlateResult]:
    """SM_prov_* in cm3 (in3 for US), converted to the Rule's cm2-m (in2-ft); I_prov in cm4 (in4) -> cm2-m2 (in2-ft2)."""
    U = mat.U
    us = U.name == "US"
    SM_prov_deck, SM_prov_bottom, I_prov = (SM_prov_deck * U.sm_hg_per_mod, SM_prov_bottom * U.sm_hg_per_mod,
                                            I_prov * U.i_hg_per_inertia)
    cb = Cb if Cb is not None else (v.Cb if v.Cb is not None else v.Cb_calc)
    SM_req = SM_all_craft(v.L, v.B, cb, v.V, mat)
    res = []
    detail = {"Cb_used": Cb_used(v.L, cb, v.units), "C1": C1(v.L, v.units), "K3": K3(v.V, v.L, v.units), "Q": mat.Q}
    governing = SM_req
    lb, smu, iu = U.big, U.sm_hg, U.i_hg
    mu = U.moment
    if v.L >= U.L61:
        sm2, m = SM_1_1_2e(v, cb, mat, Mswh, Msws)
        detail.update(m)
        res.append(PlateResult("hull girder", "section modulus 0.4L (1.1.2e)", "3-2-1/1.1.2(e)", sm2,
                               min(SM_prov_deck, SM_prov_bottom), smu, m,
                               formula=f"SM = Mt C Q / fp, Mt = greatest of (Mswh + Mwh), (Msws + Mws), Msl;  fp = {U.fp:g} {'Ltf/in2' if us else 'kN/cm2'}",
                               working=f"Mws = {m['Mws']:.0f}, Mwh = {m['Mwh']:.0f}, Mswh = {m['Mswh']:.0f}, Msws = {m['Msws']:.0f}, "
                                       f"Msl = {m['Msl']:.0f} {mu};  Mt = {m['Mt']:.0f};  SM = {sm2:.1f} {smu}"))
        governing = max(SM_req, sm2)
    res.insert(0, PlateResult("hull girder", "section modulus (1.1.1)", "3-2-1/1.1.1", SM_req,
                              min(SM_prov_deck, SM_prov_bottom), smu, detail,
                              formula=f"SM = C1 C2 L^2 B (Cb + 0.7) K3 C Q  [{smu}];  C2 = {U.C2:g}, C = 0.90 (aluminum)",
                              working=f"C1 = {detail['C1']:.3f}, L = {v.L:g}, B = {v.B:g}, Cb = {detail['Cb_used']:.3f}, K3 = {detail['K3']:.3f}, "
                                      f"Q = {mat.Q:.3f};  SM = {SM_req:.1f} {smu}" + ("" if us else f" (= {SM_req * 100:.0f} cm3)")))
    i_req = I_required(v.L, governing, mat)
    res.append(PlateResult("hull girder", "moment of inertia", "3-2-1/1.5",
                           i_req, I_prov, iu, {"SM_governing": governing},
                           formula=f"I = (L / (Q C)) (SM / K)  [{iu}];  K = 13.33 (L <= {U.L61:g} {lb}) / 11.1 (L > {U.L61:g} {lb}), aluminum",
                           working=f"L = {v.L:g}, Q = {mat.Q:.3f}, C = 0.9, SM = {governing:.1f};  I = {i_req:.1f} {iu}"
                                   + ("" if us else f" (= {i_req * 1e4:.3g} cm4)")))
    return res
