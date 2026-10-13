"""Design pressures, ABS HSC Rules July 2022, Part 3, Chapter 2, Section 2 (3-2-2).

SI units: m, kN/m2, knots, degrees. Displacement is entered in tonnes and
converted to kg where the Rule equations call for kg.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

N1 = 0.1
N2 = 0.0078
N3 = 9.8
KN = 0.256  # 3-2-2/1.1.1, SI
SERVICE_H13 = {"high-speed": 4.0, "coastal": 2.5, "riverine": 0.5,
                "crewboat": 3.35}  # Table 1, m; crewboat = 5-2-3/5 (min. h1/3 3.35 m, V is the speed at that h1/3)


@dataclass
class Vessel:
    L: float  # scantling length, 3-1-1/3 (m)
    Lw: float  # waterline length at design displacement (m)
    B: float  # molded breadth (m)
    Bw: float  # max waterline beam, one hull (m)
    D: float  # molded depth (m)
    d: float  # draft (m)
    delta_t: float  # displacement (tonnes)
    V: float  # design speed (knots)
    tau: float = 4.0  # running trim (deg)
    beta_cg: float = 15.0  # deadrise at LCG (deg)
    service: str = "high-speed"
    n_hulls: int = 1
    search_and_rescue: bool = False
    ncg_override: float | None = None  # g, from model test / direct analysis (3-1-3/5)
    Cb: float | None = None
    B_cl: float | None = None  # hull centerline distance, multihull

    @property
    def delta_kg(self) -> float:
        return self.delta_t * 1000.0

    @property
    def h13(self) -> float:
        return SERVICE_H13[self.service]

    @property
    def H(self) -> float:
        """3-2-2/1.1.3: wave parameter 0.0172 L + 3.653 (m)."""
        return 0.0172 * self.L + 3.653

    @property
    def NhBw(self) -> float:
        return self.n_hulls * self.Bw

    @property
    def d_min(self) -> float:
        return max(self.d, 0.04 * self.L)  # 'generally not less than 0.04 L'

    @property
    def Cb_calc(self) -> float:
        """3-1-1/17.3 (SI): Cb = delta / (1.025 L Bwl d)."""
        return self.delta_t / (1.025 * self.Lw * self.Bw * self.d)

    @property
    def AR_cm2(self) -> float:
        """3-2-2/1.1.3: AR = 6.95 delta(kg) / d  (cm2)."""
        return 6.95 * self.delta_kg / self.d_min


def ncg_formula(v: Vessel) -> float:
    """1/100 highest vertical acceleration at LCG, g (3-2-2/1.1.3), with the
    stated upper limit 1.39 + kn V/sqrt(L) (not above 6.0 g; 7.0 g SAR) and
    lower limit 1.0 g for L < 24 m."""
    nh_bw = v.NhBw
    raw = (
        N2
        * (12.0 * v.h13 / nh_bw + 1.0)
        * v.tau
        * (50.0 - v.beta_cg)
        * (v.V ** 2 * nh_bw ** 2 / v.delta_kg)
    )
    cap_speed = 1.39 + KN * v.V / math.sqrt(v.L)
    cap_abs = 7.0 if v.search_and_rescue else 6.0
    n = min(raw, cap_speed, cap_abs)
    if v.L < 24.0:
        n = max(n, 1.0)
    return n


def ncg(v: Vessel) -> float:
    return v.ncg_override if v.ncg_override is not None else ncg_formula(v)


def _slam_base(v: Vessel) -> float:
    """N1 * delta(kg) / (Lw * NhBw)."""
    return N1 * v.delta_kg / (v.Lw * v.NhBw)


def beta_clamp(beta: float) -> float:
    return min(max(beta, 10.0), 30.0)  # 3-2-2/1.1.3 (bottom)


def bottom_slam_cg(v: Vessel, FD: float) -> float:
    """3-2-2/1.1.1 (and 3.1.1): pbcg."""
    return _slam_base(v) * (1.0 + ncg(v)) * FD


def bottom_slam_xx(v: Vessel, FD: float, Kv: float, beta_bx: float, Fv: float | None = None) -> float:
    """pbxx. For L >= 61 m: 3-2-2/1.1.1 with nxx = ncg*Kv and the deadrise ratio.
    For L < 61 m the Rule allows 3-2-2/1.1.2: (1+ncg) FD Fv (pass Fv)."""
    if v.L < 61.0 and Fv is not None:
        return _slam_base(v) * (1.0 + ncg(v)) * FD * Fv
    nxx = ncg(v) * Kv
    bb = beta_clamp(beta_bx)
    bc = beta_clamp(v.beta_cg)
    return _slam_base(v) * (1.0 + nxx) * (70.0 - bb) / (70.0 - bc) * FD


def hydro_bottom(v: Vessel) -> float:
    """3-2-2/1.1.3: pd = N3 (0.64 H + d)."""
    return N3 * (0.64 * v.H + v.d_min)


def Hs(v: Vessel) -> float:
    """3-2-2/1.3.2 definition of Hs."""
    if v.L < 30.0:
        return max(0.083 * v.L + v.d, v.D + 1.22)
    return 0.64 * v.H + v.d  # "over 30 m"; exactly 30 m is not specified, treated as >30


def side_slam(v: Vessel, FD: float, Kv: float, beta_sx: float) -> float:
    """3-2-2/1.3.1."""
    nxx = ncg(v) * Kv
    bs = min(beta_sx, 55.0)
    bc = beta_clamp(v.beta_cg)
    return _slam_base(v) * (1.0 + nxx) * (70.0 - bs) / (70.0 - bc) * FD


def side_hydro(v: Vessel, y: float, forward_of_0125L: bool = False) -> float:
    """3-2-2/1.3.2 with the stated minimums."""
    p = N3 * (Hs(v) - y)
    if forward_of_0125L or y <= v.L / 15.0:
        floor = 0.05 * N3 * v.L
    else:
        floor = 0.033 * N3 * v.L
    return max(p, floor)


def side_fore_end(v: Vessel, alpha_deg: float, beta_entry_deg: float, plating: bool) -> float:
    """3-2-2/1.3.3: psf (kN/m2). Fa = 3.25 plating, 1.0 stiffening. L >= 30 m."""
    Fa = 3.25 if plating else 1.0
    L = max(v.L, 30.0)
    CF = 0.0125 * v.L if v.L < 80.0 else 1.0
    return (
        0.28
        * Fa
        * CF
        * N3
        * (0.22 + 0.15 * math.tan(math.radians(alpha_deg)))
        * (0.4 * v.V * math.sin(math.radians(beta_entry_deg)) + 0.6 * math.sqrt(L)) ** 2
    )


# --- decks, superstructures, bulkheads ------------------------------------

def deck_pressure(v: Vessel, kind: str, nxx: float = 0.0, W: float = 0.0, rho: float = 7.04, h: float = 0.0) -> float:
    """3-2-2/5 Table 3 (kN/m2).

    kind: 'exposed_forward' (exposed freeboard/superstructure decks fwd of 0.25L),
          'enclosed_or_aft'  (inside enclosed superstructure, exposed aft of 0.25L,
                              internal decks in hull girder bending),
          'accommodation', 'cargo' (W kN/m2), 'stores' (rho kN/m3 >= 7.04, h m)."""
    if kind == "exposed_forward":
        return 0.20 * v.L + 7.6
    if kind == "enclosed_or_aft":
        return 0.10 * v.L + 6.1
    if kind == "accommodation":
        return 5.0
    if kind == "cargo":
        return W * (1.0 + 0.5 * nxx)
    if kind == "stores":
        return max(rho, 7.04) * h * (1.0 + 0.5 * nxx)
    raise ValueError(f"unknown deck kind {kind}")


_T4 = {  # (L<=12.2, L>30.5) kN/m2, 3-2-2/7 Table 4
    "front_plating": (24.1, 37.9),
    "front_stiffeners": (24.1, 24.1),
    "side_aft_plating": (10.3, 13.8),
    "side_aft_stiffeners": (10.3, 10.3),
    "top_forward": (6.9, 8.6),
    "top_aft": (3.4, 6.9),
}


def superstructure_pressure(v: Vessel, location: str) -> float:
    lo, hi = _T4[location]
    if v.L <= 12.2:
        return lo
    if v.L >= 30.5:
        return hi
    return lo + (hi - lo) * (v.L - 12.2) / (30.5 - 12.2)


def tank_pressure(h: float, h2: float, nxx: float, rho_g: float = 10.05) -> float:
    """3-2-2/9.1: greater of N3 h and rho g (1 + 0.5 nxx) h2. rho_g >= 10.05 kN/m3."""
    return max(N3 * h, max(rho_g, 10.05) * (1.0 + 0.5 * nxx) * h2)


def watertight_pressure(h: float) -> float:
    """3-2-2/9.3."""
    return N3 * h


# --- multihull wet deck ----------------------------------------------------

def wet_deck_pressure(v: Vessel, FD: float, F1: float, ha: float) -> float:
    """3-2-2/3.5. ha is limited to 1.176 h1/3. V1 uses sqrt(L): the square root is
    implied by the Rule's unit conversions (see RULE_REFERENCE.md)."""
    ha = min(ha, 1.176 * v.h13)
    if v.L < 61.0:
        V1 = 4.0 * v.h13 / math.sqrt(v.L) + 1.0
        return 30.0 * N1 * FD * F1 * v.V * V1 * (1.0 - 0.85 * ha / v.h13)
    V1 = 5.0 * v.h13 / math.sqrt(v.L) + 1.0
    V = min(v.V, 20.0)
    return 55.0 * FD * F1 * V ** 0.1 * V1 * (1.0 - 0.35 * ha / v.h13)


def design_area_FD_floor(v: Vessel, s_mm: float, FD: float) -> float:
    """FD is generally not less than 0.4; for L <= 24 m the Table 2 minimum
    (by stiffener spacing) applies."""
    floor = 0.4
    if v.L <= 24.0:
        pts = [(250, 0.85), (500, 0.75), (750, 0.60), (1000, 0.50), (1250, 0.40)]
        if s_mm <= pts[0][0]:
            floor = pts[0][1]
        elif s_mm >= pts[-1][0]:
            floor = pts[-1][1]
        else:
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                if x0 <= s_mm <= x1:
                    floor = y0 + (y1 - y0) * (s_mm - x0) / (x1 - x0)
                    break
    return max(FD, floor)
