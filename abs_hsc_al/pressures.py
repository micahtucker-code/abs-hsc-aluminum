"""Design pressures, ABS HSC Rules July 2022, Part 3, Chapter 2, Section 2 (3-2-2).

SI units (default): m, kN/m2, knots, degrees; displacement is entered in tonnes and converted to kg where the
Rule equations call for kg. US units (Vessel.units = "US"): ft, psi, knots, degrees; displacement is entered in
long tons and converted to lb for the pressure equations. All constants come from `units.py` (the Rule's own SI and
US values). The module-level N1..KN names are the SI values, kept for reference.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import units as UN

N1 = 0.1
N2 = 0.0078
N3 = 9.8
KN = 0.256  # 3-2-2/1.1.1, SI
SERVICE_H13 = UN.SI.h13  # Table 1, m; crewboat = 5-2-3/5 (min. h1/3 3.35 m, V is the speed at that h1/3)


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
    units: str = "SI"  # "SI" (m, tonnes) or "US" (ft, long tons)
    v1_printed_us: bool = False  # US wet deck, L >= 200 ft: use the printed 16.4 instead of the consistent 9.06

    @property
    def U(self) -> UN.UnitSystem:
        return UN.get(self.units)

    @property
    def delta_load(self) -> float:
        """Displacement as the 3-2-2 / 3-2-1/3.3 equations take it: kg (SI) or lb (US)."""
        return self.delta_t * self.U.delta_to_load

    @property
    def delta_kg(self) -> float:
        return self.delta_t * (1000.0 if self.units.upper() == "SI" else 1016.0469088)

    @property
    def h13(self) -> float:
        return self.U.h13[self.service]

    @property
    def H(self) -> float:
        """3-2-2/1.1.3: wave parameter 0.0172 L + 3.653 m (0.0172 L + 11.98 ft)."""
        return self.U.H_a * self.L + self.U.H_b

    @property
    def NhBw(self) -> float:
        return self.n_hulls * self.Bw

    @property
    def d_min(self) -> float:
        return max(self.d, 0.04 * self.L)  # 'generally not less than 0.04 L'

    @property
    def Cb_calc(self) -> float:
        """3-1-1/17.3: Cb = delta / (1.025 L Bwl d) (SI), 35 delta / (L Bwl d) (US, long tons, ft)."""
        return self.U.Cb_calc_c * self.delta_t / (self.Lw * self.Bw * self.d)

    @property
    def AR(self) -> float:
        """3-2-2/1.1.3: AR = 6.95 delta(kg) / d  (cm2);  1.61 delta(lb) / d  (in2)."""
        return self.U.AR_pr * self.delta_load / self.d_min

    @property
    def AR_cm2(self) -> float:  # SI name kept for callers
        return self.AR


def ncg_formula(v: Vessel) -> float:
    """1/100 highest vertical acceleration at LCG, g (3-2-2/1.1.3), with the
    stated upper limit 1.39 + kn V/sqrt(L) (not above 6.0 g; 7.0 g SAR) and
    lower limit 1.0 g for L < 24 m."""
    U = v.U
    nh_bw = v.NhBw
    raw = (
        U.N2
        * (12.0 * v.h13 / nh_bw + 1.0)
        * v.tau
        * (50.0 - v.beta_cg)
        * (v.V ** 2 * nh_bw ** 2 / v.delta_load)
    )
    cap_speed = 1.39 + U.KN * v.V / math.sqrt(v.L)
    cap_abs = 7.0 if v.search_and_rescue else 6.0
    n = min(raw, cap_speed, cap_abs)
    if v.L < U.L24:
        n = max(n, 1.0)
    return n


def ncg(v: Vessel) -> float:
    return v.ncg_override if v.ncg_override is not None else ncg_formula(v)


def _slam_base(v: Vessel) -> float:
    """N1 * delta(kg or lb) / (Lw * NhBw)."""
    return v.U.N1 * v.delta_load / (v.Lw * v.NhBw)


def beta_clamp(beta: float) -> float:
    return min(max(beta, 10.0), 30.0)  # 3-2-2/1.1.3 (bottom)


def bottom_slam_cg(v: Vessel, FD: float) -> float:
    """3-2-2/1.1.1 (and 3.1.1): pbcg."""
    return _slam_base(v) * (1.0 + ncg(v)) * FD


def bottom_slam_xx(v: Vessel, FD: float, Kv: float, beta_bx: float, Fv: float | None = None) -> float:
    """pbxx. For L >= 61 m: 3-2-2/1.1.1 with nxx = ncg*Kv and the deadrise ratio.
    For L < 61 m the Rule allows 3-2-2/1.1.2: (1+ncg) FD Fv (pass Fv)."""
    if v.L < v.U.L61 and Fv is not None:
        return _slam_base(v) * (1.0 + ncg(v)) * FD * Fv
    nxx = ncg(v) * Kv
    bb = beta_clamp(beta_bx)
    bc = beta_clamp(v.beta_cg)
    return _slam_base(v) * (1.0 + nxx) * (70.0 - bb) / (70.0 - bc) * FD


def hydro_bottom(v: Vessel) -> float:
    """3-2-2/1.1.3: pd = N3 (0.64 H + d)."""
    return v.U.N3 * (0.64 * v.H + v.d_min)


def Hs(v: Vessel) -> float:
    """3-2-2/1.3.2 definition of Hs."""
    U = v.U
    if v.L < U.L30_hs:
        return max(U.Hs_a * v.L + v.d, v.D + U.Hs_min_add)
    return 0.64 * v.H + v.d  # "over 30 m (100 ft)"; exactly 30 m is not specified, treated as >30


def side_slam(v: Vessel, FD: float, Kv: float, beta_sx: float) -> float:
    """3-2-2/1.3.1."""
    nxx = ncg(v) * Kv
    bs = min(beta_sx, 55.0)
    bc = beta_clamp(v.beta_cg)
    return _slam_base(v) * (1.0 + nxx) * (70.0 - bs) / (70.0 - bc) * FD


def side_hydro(v: Vessel, y: float, forward_of_0125L: bool = False) -> float:
    """3-2-2/1.3.2 with the stated minimums."""
    N3 = v.U.N3
    p = N3 * (Hs(v) - y)
    if forward_of_0125L or y <= v.L / 15.0:
        floor = 0.05 * N3 * v.L
    else:
        floor = 0.033 * N3 * v.L
    return max(p, floor)


def side_fore_end(v: Vessel, alpha_deg: float, beta_entry_deg: float, plating: bool) -> float:
    """3-2-2/1.3.3: psf (kN/m2 or psi). Fa = 3.25 plating, 1.0 stiffening. L >= 30 m (98 ft).

    SI: 0.28 Fa CF N3 (...)(0.4 V sin b + 0.6 sqrt(L))^2;  US: 0.92 Fa CF N3 (...)(0.4 V sin b + 0.33 sqrt(L))^2."""
    U = v.U
    Fa = 3.25 if plating else 1.0
    L = max(v.L, U.L30_fore)
    CF = U.CF_a * v.L if v.L < U.L80_cf else 1.0
    return (
        U.fore_c
        * Fa
        * CF
        * U.N3
        * (0.22 + 0.15 * math.tan(math.radians(alpha_deg)))
        * (0.4 * v.V * math.sin(math.radians(beta_entry_deg)) + U.fore_L * math.sqrt(L)) ** 2
    )


# --- decks, superstructures, bulkheads ------------------------------------

def deck_pressure(v: Vessel, kind: str, nxx: float = 0.0, W: float = 0.0, rho: float | None = None, h: float = 0.0) -> float:
    """3-2-2/5 Table 3 (kN/m2 or psi).

    kind: 'exposed_forward' (exposed freeboard/superstructure decks fwd of 0.25L),
          'enclosed_or_aft'  (inside enclosed superstructure, exposed aft of 0.25L,
                              internal decks in hull girder bending),
          'accommodation', 'cargo' (W kN/m2 or psi), 'stores' (rho kN/m3 >= 7.04, or lb/ft3 >= 44.8, h m or ft)."""
    U = v.U
    if kind == "exposed_forward":
        return U.deck_fwd[0] * v.L + U.deck_fwd[1]
    if kind == "enclosed_or_aft":
        return U.deck_encl[0] * v.L + U.deck_encl[1]
    if kind == "accommodation":
        return U.deck_accom
    if kind == "cargo":
        return W * (1.0 + 0.5 * nxx)
    if kind == "stores":
        r = U.deck_rho_min if rho is None else rho
        return max(r, U.deck_rho_min) / U.deck_rho_div * h * (1.0 + 0.5 * nxx)
    raise ValueError(f"unknown deck kind {kind}")


_T4 = UN.SI.T4  # (L<=12.2 m, L>30.5 m) kN/m2, 3-2-2/7 Table 4; the US column (psi, 40 ft / 100 ft) is in units.US.T4


def superstructure_pressure(v: Vessel, location: str) -> float:
    U = v.U
    lo, hi = U.T4[location]
    if v.L <= U.T4_L_lo:
        return lo
    if v.L >= U.T4_L_hi:
        return hi
    return lo + (hi - lo) * (v.L - U.T4_L_lo) / (U.T4_L_hi - U.T4_L_lo)


def tank_pressure(h: float, h2: float, nxx: float, rho_g: float | None = None, units: str = "SI") -> float:
    """3-2-2/9.1: greater of N3 h and rho g (1 + 0.5 nxx) h2. rho_g >= 10.05 kN/m3 (0.44 psi/ft)."""
    U = UN.get(units)
    rg = U.tank_rhog_min if rho_g is None else max(rho_g, U.tank_rhog_min)
    return max(U.N3 * h, rg * (1.0 + 0.5 * nxx) * h2)


def watertight_pressure(h: float, units: str = "SI") -> float:
    """3-2-2/9.3."""
    return UN.get(units).N3 * h


# --- multihull wet deck ----------------------------------------------------

def wet_deck_pressure(v: Vessel, FD: float, F1: float, ha: float) -> float:
    """3-2-2/3.5. ha is limited to 1.176 h1/3. V1 uses sqrt(L): the square root is
    implied by the Rule's unit conversions (see RULE_REFERENCE.md). US: N1 = 0.00442, V1 in ft/s."""
    U = v.U
    ha = min(ha, 1.176 * v.h13)
    if v.L < U.L61:
        V1 = U.wd_V1_a_short * v.h13 / math.sqrt(v.L) + U.wd_V1_b_short
        return 30.0 * U.N1_wd * FD * F1 * v.V * V1 * (1.0 - 0.85 * ha / v.h13)
    a = U.wd_V1_a_long_printed if (v.units.upper() == "US" and v.v1_printed_us) else U.wd_V1_a_long
    V1 = a * v.h13 / math.sqrt(v.L) + U.wd_V1_b_long
    V = min(v.V, 20.0)
    return U.wd_55 * FD * F1 * V ** 0.1 * V1 * (1.0 - 0.35 * ha / v.h13)


def design_area_FD_floor(v: Vessel, s_mm: float, FD: float) -> float:
    """FD is generally not less than 0.4; for L <= 24 m (79 ft) the Table 2 minimum
    (by stiffener spacing, mm or in.) applies."""
    floor = 0.4
    if v.L <= v.U.L24:
        pts = list(v.U.FD_table)
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
