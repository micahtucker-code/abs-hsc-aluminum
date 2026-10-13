"""Pressure dispatch, JSON driver and Markdown/JSON report."""
from __future__ import annotations

import json
from dataclasses import asdict

from . import pressures as P
from .figures import Factors
from .materials import AluminumMaterial
from .plating import check_plate, check_plate_buckling, PlateResult
from .stiffeners import Section, effective_plate_width, check_stiffener
from .hullgirder import check_hull_girder


def resolve_pressure(spec, v: P.Vessel, fac: Factors) -> float:
    """spec: number, {"value": p}, or {"calc": name, ...args}. Figure factors may be
    given directly (FD, Kv, Fv, F1) or via curves with x position 'x_over_L'."""
    if isinstance(spec, (int, float)):
        return float(spec)
    if "value" in spec:
        return float(spec["value"])
    c, x = spec["calc"], spec.get("x_over_L")
    FD = lambda: fac.resolve("FD", spec.get("AD_over_AR"), spec.get("FD"))
    Kv = lambda: fac.resolve("Kv", x, spec.get("Kv"))
    if c == "bottom_slam_cg":
        return P.bottom_slam_cg(v, FD())
    if c == "bottom_slam_xx":
        Fv = spec.get("Fv")
        if Fv is None and v.L < 61.0 and "Fv" in fac.curves:
            Fv = fac.resolve("Fv", x, None)
        return P.bottom_slam_xx(v, FD(), Kv() if Fv is None else 1.0, spec.get("beta_bx", v.beta_cg), Fv)
    if c == "hydro_bottom":
        return P.hydro_bottom(v)
    if c == "side_slam":
        return P.side_slam(v, FD(), Kv(), spec["beta_sx"])
    if c == "side_hydro":
        return P.side_hydro(v, spec["y"], spec.get("forward_of_0125L", False))
    if c == "side_fore_end":
        return P.side_fore_end(v, spec["alpha"], spec["beta_entry"], spec.get("plating", True))
    if c == "deck":
        return P.deck_pressure(v, spec["kind"], spec.get("nxx", 0.0), spec.get("W", 0.0),
                               spec.get("rho", 7.04), spec.get("h", 0.0))
    if c == "superstructure":
        return P.superstructure_pressure(v, spec["location"])
    if c == "tank":
        return P.tank_pressure(spec["h"], spec["h2"], spec.get("nxx", 0.0), spec.get("rho_g", 10.05))
    if c == "watertight":
        return P.watertight_pressure(spec["h"])
    if c == "wet_deck":
        return P.wet_deck_pressure(v, FD(), fac.resolve("F1_wetdeck", x, spec.get("F1")), spec["ha"])
    raise ValueError(f"unknown pressure calc '{c}'")


def run(data: dict) -> dict:
    vd = dict(data["vessel"])
    v = P.Vessel(**vd)
    mat = AluminumMaterial.from_dict(data["material"])
    fac = Factors(data.get("curves"))
    results: list[PlateResult] = []
    pressures = {}
    for pl in data.get("plates", []):
        loads = {}
        for case, spec in pl["loads"].items():
            p = resolve_pressure(spec, v, fac)
            loads[case] = p
            pressures[f"{pl['id']}:{case}"] = p
        results += check_plate(pl["id"], mat, v.L, pl["s_mm"], pl["l_mm"], pl["t_mm"], pl["location"],
                               loads, pl.get("outside_midship_0_4L", False))
        if "buckling" in pl:
            b = pl["buckling"]
            results.append(check_plate_buckling(pl["id"], mat, pl["s_mm"], pl["l_mm"], pl["t_mm"],
                                                b["framing"], b["sigma_work"], b.get("c2", 1.21),
                                                b.get("sigma_ratio", 1.0)))
    for st in data.get("stiffeners", []):
        t_pl = st["t_plate_mm"]
        kind = st.get("kind", "secondary")
        beff = effective_plate_width(kind, st["spacing_mm"], t_pl, st["l_m"])
        sec = Section(st["profile"], st["hw_mm"], st["tw_mm"], st.get("bf_mm", 0.0), st.get("tf_mm", 0.0), t_pl, beff)
        p = resolve_pressure(st["load"], v, fac)
        pressures[f"{st['id']}:{st['member_case']}"] = p
        results += check_stiffener(st["id"], mat, st["member_case"], p, st["spacing_mm"] / 1000.0, st["l_m"], sec,
                                   st.get("deck", False), st.get("bottom_primary", False),
                                   st.get("no_end_attach_wt", False), st.get("sigma_compr"))
    if "hull_girder" in data:
        h = data["hull_girder"]
        results += check_hull_girder(v, mat, h["SM_deck_cm3"], h["SM_bottom_cm3"], h["I_cm4"],
                                     h.get("Cb"), h.get("Mswh_kNm"), h.get("Msws_kNm"))
    return {"vessel": vd, "ncg": P.ncg(v), "material": {"name": mat.name, "sigma_y_design": mat.sigma_y_design,
            "Q": mat.Q, "q_a": mat.q_a, "source": mat.source}, "pressures": pressures,
            "results": [dict(asdict(r), utilisation=r.utilisation, passed=r.passed) for r in results]}


def markdown(rep: dict) -> str:
    rows = rep["results"]
    n_fail = sum(not r["passed"] for r in rows)
    out = [f"# Aluminum scantling check - ABS HSC Rules (July 2022)", "",
           f"Material: {rep['material']['name']} (source: {rep['material']['source']}); "
           f"sigma_y design {rep['material']['sigma_y_design']:.1f} N/mm2, Q {rep['material']['Q']:.3f}",
           f"ncg = {rep['ncg']:.2f} g", "",
           f"**{len(rows) - n_fail} of {len(rows)} checks pass; {n_fail} fail.**", "",
           "| Item | Check | Clause | Required | Provided | Util. | Result |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['id']} | {r['kind']} | {r['clause']} | {r['required']:.3g} {r['unit']} | "
                   f"{r['provided']:.3g} | {r['utilisation']:.2f} | {'PASS' if r['passed'] else 'FAIL'} |")
    out += ["", "Buckling/proportion rows: 'Required' is the working or actual value and 'Provided' the limit or capacity.",
            "Not implemented: torsional/flexural buckling (3-2-4/1.5.2), plate shear buckling stress calc, direct analysis. "
            "See RULE_REFERENCE.md."]
    return "\n".join(out)
