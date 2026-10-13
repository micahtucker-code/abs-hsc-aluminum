"""Pressure dispatch, JSON driver and Markdown/JSON report."""
from __future__ import annotations

import json
from dataclasses import asdict

from . import __version__
from . import pressures as P
from .figures import Factors
from . import stations as ST
from .materials import AluminumMaterial
from .plating import check_plate, check_plate_buckling, PlateResult
from .stiffeners import Section, effective_plate_width, check_stiffener
from .hullgirder import check_hull_girder
from . import section as SEC


def resolve_pressure_detail(spec, v: P.Vessel, fac: Factors, stations=None):
    """Returns (p kN/m2, used-factors dict, Rule equation text, clause). spec: number, {"value": p},
    or {"calc": name, ...}. Figure factors may be given directly or via curves ('x_over_L', 'AD_over_AR')."""
    if isinstance(spec, (int, float)):
        return float(spec), {}, "p entered directly", "-"
    if "value" in spec:
        return float(spec["value"]), {}, "p entered directly", "-"
    c, x = spec["calc"], spec.get("x_over_L")
    used = {}
    if spec.get("station"):  # panel is tied to a named station: take its position, deadrise and figure factors
        st = ST.find(stations or [], spec["station"])
        spec = dict(spec)
        x = spec.setdefault("x_over_L", st.x_over_L)
        for k_spec, v_st in (("beta_bx", st.beta_bx), ("beta_sx", st.beta_sx), ("Kv", st.Kv), ("Fv", st.Fv),
                             ("alpha", st.alpha), ("beta_entry", st.beta_entry)):
            if v_st is not None:
                spec.setdefault(k_spec, v_st)
        used["station"] = st.name

    def F(name, xx, key=None):
        val = fac.resolve(name, xx, spec.get(key or name))
        used[name] = val
        return val
    FD = lambda: F("FD", spec.get("AD_over_AR"))
    Kv = lambda: F("Kv", x)
    base = f"N1 = 0.1, Delta = {v.delta_kg:.0f} kg, Lw = {v.Lw:g} m, Nh*Bw = {v.NhBw:g} m, ncg = {P.ncg(v):.2f} g"
    if c == "bottom_slam_cg":
        p = P.bottom_slam_cg(v, FD())
        return p, used, "pbcg = N1 (Delta / (Lw Nh Bw)) (1 + ncg) FD  [" + base + "]", "3-2-2/1.1.1"
    if c == "bottom_slam_xx":
        Fv = spec.get("Fv")
        if Fv is None and v.L < 61.0 and "Fv" in fac.curves:
            Fv = fac.resolve("Fv", x, None)
        if Fv is not None:
            used["Fv"] = Fv
        fd = FD()
        kv = Kv() if Fv is None else 1.0
        p = P.bottom_slam_xx(v, fd, kv, spec.get("beta_bx", v.beta_cg), Fv)
        return p, used, ("pbxx = N1 (Delta/(Lw Nh Bw)) (1 + ncg) FD Fv  (L < 61 m)" if Fv is not None else
                         "pbxx = N1 (Delta/(Lw Nh Bw)) (1 + nxx) ((70 - beta_bx)/(70 - beta_cg)) FD, nxx = ncg Kv") + f"  [{base}]", "3-2-2/1.1.1-1.1.2"
    if c == "hydro_bottom":
        return P.hydro_bottom(v), used, f"pd = N3 (0.64 H + d), N3 = 9.8, H = 0.0172 L + 3.653 = {v.H:.3f} m, d = {v.d_min:g} m", "3-2-2/1.1.3"
    if c == "side_slam":
        p = P.side_slam(v, FD(), Kv(), spec["beta_sx"])
        return p, used, f"pss = N1 (Delta/(Lw Nh Bw)) (1 + nxx) ((70 - beta_sx)/(70 - beta_cg)) FD  [{base}, beta_sx = {spec['beta_sx']:g}]", "3-2-2/1.3.1"
    if c == "side_hydro":
        return P.side_hydro(v, spec["y"], spec.get("forward_of_0125L", False)), used, f"ps = N3 (Hs - y), Hs = {P.Hs(v):.3f} m, y = {spec['y']:g} m, with stated minimum", "3-2-2/1.3.2"
    if c == "side_fore_end":
        return (P.side_fore_end(v, spec["alpha"], spec["beta_entry"], spec.get("plating", True)), used,
                f"psf = 0.28 Fa CF N3 (0.22 + 0.15 tan alpha)(0.4 V sin beta + 0.6 sqrt(L))^2, alpha = {spec['alpha']:g}, beta = {spec['beta_entry']:g}", "3-2-2/1.3.3")
    if c == "deck":
        return (P.deck_pressure(v, spec["kind"], spec.get("nxx", 0.0), spec.get("W", 0.0), spec.get("rho", 7.04), spec.get("h", 0.0)),
                used, f"Table 3, deck kind '{spec['kind']}'", "3-2-2/5")
    if c == "superstructure":
        return P.superstructure_pressure(v, spec["location"]), used, f"Table 4, '{spec['location']}', interpolated on L", "3-2-2/7"
    if c == "tank":
        return (P.tank_pressure(spec["h"], spec["h2"], spec.get("nxx", 0.0), spec.get("rho_g", 10.05)), used,
                "p = greater of N3 h and rho g (1 + 0.5 nxx) h2", "3-2-2/9.1")
    if c == "watertight":
        return P.watertight_pressure(spec["h"]), used, f"p = N3 h, h = {spec['h']:g} m", "3-2-2/9.3"
    if c == "wet_deck":
        f1 = F("F1_wetdeck", x, "F1")
        return P.wet_deck_pressure(v, FD(), f1, spec["ha"]), used, f"wet deck equation, ha = {spec['ha']:g} m, h1/3 = {v.h13:g} m", "3-2-2/3.5"
    raise ValueError(f"unknown pressure calc '{c}'")


def resolve_pressure(spec, v: P.Vessel, fac: Factors, stations=None) -> float:
    return resolve_pressure_detail(spec, v, fac, stations)[0]


def station_table(data, v, stns, fac):
    blk = data.get("stations") or {}
    if not stns:
        return {"rows": [], "FD": None}
    FD = fac.resolve("FD", blk.get("AD_over_AR"), blk.get("FD"))
    return {"FD": FD, "rows": ST.table(stns, v, FD)}


def operating_limits(v: P.Vessel):
    """Maximum speed for each h1/3 holding the 3-2-2/1.1.3 acceleration at its design-point value
    (n_cg ~ (12 h/NhBw + 1) V^2); speed never exceeds the design speed. Empty if ncg was overridden."""
    if v.ncg_override is not None:
        return []
    k0 = 12.0 * v.h13 / v.NhBw + 1.0
    out = []
    for h in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.35, 3.5, 4.0, 4.5, 5.0):
        vm = min(v.V, v.V * (k0 / (12.0 * h / v.NhBw + 1.0)) ** 0.5)
        out.append({"h13": h, "V": vm})
    return out


def run(data: dict) -> dict:
    vd = dict(data["vessel"])
    v = P.Vessel(**vd)
    mat = AluminumMaterial.from_dict(data["material"])
    fac = Factors(data.get("curves"))
    stns = ST.parse(data.get("stations"), v)
    ids = [x["id"] for x in data.get("plates", [])] + [x["id"] for x in data.get("stiffeners", [])]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup or "hull girder" in ids:
        raise ValueError(f"Item names must be unique (and not 'hull girder'); duplicated: {dup or ['hull girder']}")
    results: list[PlateResult] = []
    pressures = {}
    plog = []
    for pl in data.get("plates", []):
        loads = {}
        for case, spec in pl["loads"].items():
            p, used, eq, cl = resolve_pressure_detail(spec, v, fac, stns)
            loads[case] = p
            pressures[f"{pl['id']}:{case}"] = p
            plog.append({"item": pl["id"], "case": case, "p": p, "factors": used, "equation": eq, "clause": cl})
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
        p, used, eq, cl = resolve_pressure_detail(st["load"], v, fac, stns)
        pressures[f"{st['id']}:{st['member_case']}"] = p
        plog.append({"item": st["id"], "case": st["member_case"], "p": p, "factors": used, "equation": eq, "clause": cl})
        results += check_stiffener(st["id"], mat, st["member_case"], p, st["spacing_mm"] / 1000.0, st["l_m"], sec,
                                   st.get("deck", False), st.get("bottom_primary", False),
                                   st.get("no_end_attach_wt", False), st.get("sigma_compr"))
    section = None
    hull_used = None
    if data.get("section"):
        section = SEC.compute(data["section"])
    if "hull_girder" in data or section:
        h = dict(data.get("hull_girder", {}))
        if section and not all(k in h for k in ("SM_deck_cm3", "SM_bottom_cm3", "I_cm4")):
            h.setdefault("SM_deck_cm3", section["SM_deck_cm3"])
            h.setdefault("SM_bottom_cm3", section["SM_bottom_cm3"])
            h.setdefault("I_cm4", section["I_cm4"])
            h["from_section"] = True
        results += check_hull_girder(v, mat, h["SM_deck_cm3"], h["SM_bottom_cm3"], h["I_cm4"],
                                     h.get("Cb"), h.get("Mswh_kNm"), h.get("Msws_kNm"))
        hull_used = h
    return {"vessel": vd, "ncg": P.ncg(v), "material": {"name": mat.name, "sigma_y_design": mat.sigma_y_design,
            "Q": mat.Q, "q_a": mat.q_a, "source": mat.source,
            "sigma_y_unwelded": mat.sigma_y_unwelded, "sigma_u_unwelded": mat.sigma_u_unwelded,
            "sigma_y_welded": mat.sigma_y_welded, "sigma_u_welded": mat.sigma_u_welded, "sigma_ya": mat.sigma_ya, "tau_yw": mat.tau_yw},
            "pressures": pressures, "pressure_log": plog, "inputs": data, "project": data.get("project", {}),
            "derived": {"delta_kg": v.delta_kg, "h13": v.h13, "H": v.H, "NhBw": v.NhBw, "d_min": v.d_min, "Cb_calc": v.Cb_calc,
                        "ncg_formula": P.ncg_formula(v), "ncg_used": P.ncg(v), "ncg_override": v.ncg_override},
            "version": __version__,
            "station_table": station_table(data, v, stns, fac),
            "section": section, "hull_girder_used": hull_used,
            "operating_limits": operating_limits(v),
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
