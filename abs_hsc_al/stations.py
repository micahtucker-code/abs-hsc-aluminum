"""Station-by-station design pressures (3-2-2/1.1 bottom slamming, 1.3 side slamming and fore end).

Stations run from the aft perpendicular (x/L = 0) to the forward perpendicular (x/L = 1).
Figure-based factors (Kv, Fv) are entered per station from the Rule figures; nothing is assumed.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import pressures as P


@dataclass
class Station:
    name: str
    x_over_L: float
    beta_bx: float | None = None   # bottom deadrise at the section (deg)
    beta_sx: float | None = None   # side deadrise / flare at the section (deg)
    Kv: float | None = None        # 3-2-2/1.1.3 FIGURE 4 (vertical acceleration distribution)
    Fv: float | None = None        # 3-2-2/1.1.3 FIGURE 5 (craft under 61 m)
    alpha: float | None = None     # flare angle, fore-end pressure (deg)
    beta_entry: float | None = None  # entry angle, fore-end pressure (deg)


def parse(block: dict | None, v: P.Vessel) -> list[Station]:
    """block: {"rows": [ {name, x_over_L, beta_bx, beta_sx, Kv, Fv, alpha, beta_entry}, ... ]}"""
    if not block:
        return []
    out = []
    for i, r in enumerate(block.get("rows", [])):
        if r.get("x_over_L") in (None, ""):
            raise ValueError(f"Station row {i + 1}: x_over_L is required")
        x = float(r["x_over_L"])
        if not 0.0 <= x <= 1.0:
            raise ValueError(f"Station '{r.get('name', i + 1)}': x_over_L must be between 0 (AP) and 1 (FP)")
        f = lambda k: (None if r.get(k) in (None, "") else float(r[k]))
        out.append(Station(str(r.get("name") or f"Sta {i}"), x, f("beta_bx"), f("beta_sx"), f("Kv"), f("Fv"), f("alpha"), f("beta_entry")))
    names = [s.name for s in out]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ValueError(f"Station names must be unique; duplicated: {dup}")
    return out


def find(stations: list[Station], name: str) -> Station:
    for s in stations:
        if s.name == name:
            return s
    raise ValueError(f"Station '{name}' is not in the station table. Available: {[s.name for s in stations]}")


def table(stations: list[Station], v: P.Vessel, FD: float) -> list[dict]:
    """One row per station. FD is the design-area factor for the representative panel (3-2-2/1.1.3 FIGURE 3)."""
    rows = []
    ncg = P.ncg(v)
    short = v.L < v.U.L61
    for s in stations:
        r = {"name": s.name, "x_over_L": s.x_over_L, "x_m": s.x_over_L * v.L,  # m (ft for US)
              "Kv": s.Kv, "Fv": s.Fv,
             "beta_bx": s.beta_bx if s.beta_bx is not None else v.beta_cg,
             "beta_sx": s.beta_sx, "nxx": None, "pbxx": None, "pss": None, "psf": None, "notes": []}
        if s.Kv is not None:
            r["nxx"] = ncg * s.Kv
        # bottom slamming
        if short and s.Fv is not None:
            r["pbxx"] = P.bottom_slam_xx(v, FD, 1.0, r["beta_bx"], s.Fv)
        elif s.Kv is not None:
            r["pbxx"] = P.bottom_slam_xx(v, FD, s.Kv, r["beta_bx"], None)
        else:
            r["notes"].append("bottom slamming: enter " + ("Fv" if short else "Kv") + " for this station")
        # side slamming
        if s.Kv is not None and s.beta_sx is not None:
            r["pss"] = P.side_slam(v, FD, s.Kv, s.beta_sx)
        elif s.beta_sx is not None:
            r["notes"].append("side slamming: enter Kv")
        # fore end (L >= 30 m, forward of 0.125 L from the stem)
        if s.alpha is not None and s.beta_entry is not None and v.L >= v.U.L30_fore and s.x_over_L >= 0.875:
            r["psf"] = P.side_fore_end(v, s.alpha, s.beta_entry, plating=True)
        rows.append(r)
    return rows
