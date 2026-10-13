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
from . import shear as SH
from . import hullgirder as HGM
from . import units as UN


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
    U = v.U
    lb, pu = U.big, U.p
    base = f"N1 = {U.N1:g}, Delta = {v.delta_load:.0f} {U.disp_p}, Lw = {v.Lw:g} {lb}, Nh*Bw = {v.NhBw:g} {lb}, ncg = {P.ncg(v):.2f} g"
    if c == "bottom_slam_cg":
        p = P.bottom_slam_cg(v, FD())
        return p, used, "pbcg = N1 (Delta / (Lw Nh Bw)) (1 + ncg) FD  [" + base + "]", "3-2-2/1.1.1"
    if c == "bottom_slam_xx":
        Fv = spec.get("Fv")
        if Fv is None and v.L < v.U.L61 and "Fv" in fac.curves:
            Fv = fac.resolve("Fv", x, None)
        if Fv is not None:
            used["Fv"] = Fv
        fd = FD()
        kv = Kv() if Fv is None else 1.0
        p = P.bottom_slam_xx(v, fd, kv, spec.get("beta_bx", v.beta_cg), Fv)
        return p, used, ("pbxx = N1 (Delta/(Lw Nh Bw)) (1 + ncg) FD Fv  (L < " + f"{U.L61:g} {lb})" if Fv is not None else
                         "pbxx = N1 (Delta/(Lw Nh Bw)) (1 + nxx) ((70 - beta_bx)/(70 - beta_cg)) FD, nxx = ncg Kv") + f"  [{base}]", "3-2-2/1.1.1-1.1.2"
    if c == "hydro_bottom":
        return P.hydro_bottom(v), used, f"pd = N3 (0.64 H + d), N3 = {U.N3:g}, H = {U.H_a:g} L + {U.H_b:g} = {v.H:.3f} {lb}, d = {v.d_min:g} {lb}", "3-2-2/1.1.3"
    if c == "side_slam":
        p = P.side_slam(v, FD(), Kv(), spec["beta_sx"])
        return p, used, f"pss = N1 (Delta/(Lw Nh Bw)) (1 + nxx) ((70 - beta_sx)/(70 - beta_cg)) FD  [{base}, beta_sx = {spec['beta_sx']:g}]", "3-2-2/1.3.1"
    if c == "side_hydro":
        return P.side_hydro(v, spec["y"], spec.get("forward_of_0125L", False)), used, f"ps = N3 (Hs - y), N3 = {U.N3:g}, Hs = {P.Hs(v):.3f} {lb}, y = {spec['y']:g} {lb}, with stated minimum", "3-2-2/1.3.2"
    if c == "side_fore_end":
        return (P.side_fore_end(v, spec["alpha"], spec["beta_entry"], spec.get("plating", True)), used,
                f"psf = {U.fore_c:g} Fa CF N3 (0.22 + 0.15 tan alpha)(0.4 V sin beta + {U.fore_L:g} sqrt(L))^2, N3 = {U.N3:g}, alpha = {spec['alpha']:g}, beta = {spec['beta_entry']:g}", "3-2-2/1.3.3")
    if c == "deck":
        return (P.deck_pressure(v, spec["kind"], spec.get("nxx", 0.0), spec.get("W", 0.0), spec.get("rho"), spec.get("h", 0.0)),
                used, f"Table 3, deck kind '{spec['kind']}'", "3-2-2/5")
    if c == "superstructure":
        return P.superstructure_pressure(v, spec["location"]), used, f"Table 4, '{spec['location']}', interpolated on L", "3-2-2/7"
    if c == "tank":
        return (P.tank_pressure(spec["h"], spec["h2"], spec.get("nxx", 0.0), spec.get("rho_g"), v.units), used,
                "p = greater of N3 h and rho g (1 + 0.5 nxx) h2", "3-2-2/9.1")
    if c == "watertight":
        return P.watertight_pressure(spec["h"], v.units), used, f"p = N3 h, N3 = {U.N3:g}, h = {spec['h']:g} {lb}", "3-2-2/9.3"
    if c == "wet_deck":
        f1 = F("F1_wetdeck", x, "F1")
        return P.wet_deck_pressure(v, FD(), f1, spec["ha"]), used, f"wet deck equation, ha = {spec['ha']:g} {lb}, h1/3 = {v.h13:g} {lb}", "3-2-2/3.5"
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
    hs = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.35, 3.5, 4.0, 4.5, 5.0) if v.units.upper() == "SI" else \
         (1.5, 3.0, 5.0, 6.5, 8.0, 10.0, 11.0, 12.0, 13.0, 15.0, 16.5)
    for h in hs:
        vm = min(v.V, v.V * (k0 / (12.0 * h / v.NhBw + 1.0)) ** 0.5)
        out.append({"h13": h, "V": vm})
    return out


def run(data: dict) -> dict:
    units = UN.get(data.get("units")).name
    U = UN.get(units)
    vd = dict(data["vessel"])
    vd["units"] = units
    v = P.Vessel(**vd)
    mat = AluminumMaterial.from_dict(data["material"], units)
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
        beff = effective_plate_width(kind, st["spacing_mm"], t_pl, st["l_m"], units)
        sec = Section(st["profile"], st["hw_mm"], st["tw_mm"], st.get("bf_mm", 0.0), st.get("tf_mm", 0.0), t_pl, beff, units)
        p, used, eq, cl = resolve_pressure_detail(st["load"], v, fac, stns)
        pressures[f"{st['id']}:{st['member_case']}"] = p
        plog.append({"item": st["id"], "case": st["member_case"], "p": p, "factors": used, "equation": eq, "clause": cl})
        results += check_stiffener(st["id"], mat, st["member_case"], p, st["spacing_mm"] / U.small_per_big, st["l_m"], sec,
                                   st.get("deck", False), st.get("bottom_primary", False),
                                   st.get("no_end_attach_wt", False), st.get("sigma_compr"))
    section = None
    hull_used = None
    if data.get("section"):
        section = SEC.compute(data["section"], units)
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
    global_loads = _global_loads(data, v, mat, section, hull_used, results)
    return {"vessel": vd, "ncg": P.ncg(v), "material": {"name": mat.name, "sigma_y_design": mat.sigma_y_design,
            "Q": mat.Q, "q_a": mat.q_a, "source": mat.source,
            "sigma_y_unwelded": mat.sigma_y_unwelded, "sigma_u_unwelded": mat.sigma_u_unwelded,
            "sigma_y_welded": mat.sigma_y_welded, "sigma_u_welded": mat.sigma_u_welded, "sigma_ya": mat.sigma_ya, "tau_yw": mat.tau_yw},
            "pressures": pressures, "pressure_log": plog, "inputs": data, "project": data.get("project", {}),
            "derived": {"delta_kg": v.delta_kg, "delta_load": v.delta_load, "AR": v.AR, "h13": v.h13, "H": v.H, "NhBw": v.NhBw, "d_min": v.d_min, "Cb_calc": v.Cb_calc,
                        "ncg_formula": P.ncg_formula(v), "ncg_used": P.ncg(v), "ncg_override": v.ncg_override},
            "version": __version__,
            "station_table": station_table(data, v, stns, fac),
            "section": section, "hull_girder_used": hull_used, "global_loads": global_loads,
            "operating_limits": operating_limits(v),
            "units": units, "unit_labels": unit_labels(U), "unit_notes": UN.NOTES if units == "US" else [],
            "results": [dict(asdict(r), utilisation=r.utilisation, passed=r.passed) for r in results]}


def unit_labels(U: UN.UnitSystem) -> dict:
    """Labels and constants the report page needs for the selected unit system."""
    return {"name": U.name, "big": U.big, "small": U.small, "p": U.p, "sig": U.sig, "area": U.area, "mod": U.mod,
            "inertia": U.inertia, "sm_hg": U.sm_hg, "i_hg": U.i_hg, "moment": U.moment, "force": U.force,
            "shear_hg": U.shear_hg, "disp": U.disp, "disp_p": U.disp_p, "rho": U.rho, "N3": U.N3, "N1": U.N1,
            "H_a": U.H_a, "H_b": U.H_b, "L61": U.L61, "N2": U.N2, "KN": U.KN, "Q0_n": U.Q0_n, "sm_div": round(1.0 / U.sm_hg_per_mod), "k_wave": U.k_wave, "C4": U.C4, "K1_cat": U.K1_cat,
            "K2_cat": U.K2_cat, "shear_allow_n": U.shear_allow_n, "q5_n": U.q5_n, "fp": U.fp, "E": U.E,
            "cross_force": "lbf" if U.name == "US" else "kN", "cross_moment": "ft-lbf" if U.name == "US" else "kN-m",
            "cross_disp": "lb" if U.name == "US" else "t", "small_per_big": U.small_per_big}


def _global_loads(data, v, mat, section, hull_used, results) -> dict:
    """Global load summary plus the shear (3-2-1/1.9) and multi-hull cross-structure (3-2-1/3, 3-2-A2) checks.
    Appends check rows to `results` and returns the data for the report sheets."""
    out = {"ncg": P.ncg(v), "n1": max(1.0 + P.ncg(v), HGM.min_1_plus_ncg(v.delta_t, v.units)), "moments": None, "shear": None,
           "cross": None, "notes": []}
    h = hull_used or {}
    cb = h.get("Cb") if h.get("Cb") is not None else (v.Cb if v.Cb is not None else v.Cb_calc)
    if v.L >= v.U.L61:
        m = HGM.moments_61m_plus(v, cb)
        if h.get("Mswh_kNm") is not None:
            m["Mswh"] = h["Mswh_kNm"]
        if h.get("Msws_kNm") is not None:
            m["Msws"] = h["Msws_kNm"]
        m["Mt"] = max(m["Mswh"] + m["Mwh"], abs(m["Msws"]) + m["Mws"], m["Msl"])
        out["moments"] = m
    hs = data.get("hull_shear")
    if hs:
        I = hs.get("I_cm4", h.get("I_cm4"))
        if I is None:
            raise ValueError("hull_shear needs the hull girder moment of inertia: give a midship section, hull girder I_cm4, or hull_shear.I_cm4")
        geom = (section or {}).get("shear")
        m_cm3 = hs.get("m_cm3", geom["m_cm3"] if geom else None)
        if "ts_mm" in hs:
            web_t = hs["ts_mm"] * hs.get("n_webs", 2)
        elif geom and geom["web_t_sum_mm"] > 0:
            web_t = geom["web_t_sum_mm"]
        else:
            web_t = None
        if m_cm3 is None or web_t is None:
            raise ValueError("hull_shear needs the first moment m and the side-shell thickness: give a midship section or hull_shear.m_cm3 and ts_mm")
        rows_res, rows = SH.check_hull_shear(v, mat, cb, I, m_cm3, web_t, hs.get("stations", []), hs.get("combined_sum", True))
        results += rows_res
        out["shear"] = {"rows": rows, "I_cm4": I, "m_cm3": m_cm3, "web_t_mm": web_t, "allow": HGM.shear_allowable(mat),
                        "geometry": geom, "from_section": "m_cm3" not in hs and bool(geom),
                        "required_by_rule": v.L >= v.U.L61 and v.n_hulls < 2}
        if not any(r["Fsw_given"] for r in rows):
            out["notes"].append("Still-water shear force Fsw was not entered and is taken as zero in the shear checks.")
        if geom and geom.get("centreline_web"):
            out["notes"].append("The section has a continuous longitudinal web on the centreline: 3-2-1/1.9.5 applies and shear flow must be determined by an acceptable method; the single-cell formula used here does not apply.")
        if v.L < v.U.L61:
            out["notes"].append(f"Hull girder shear is required only for craft of {v.U.L61:g} {v.U.big} (61 m / 200 ft) and over (3-2-1/1.9); evaluated here at the designer's request.")
    cs = data.get("cross_structure")
    if cs:
        if v.n_hulls < 2 or not v.B_cl:
            raise ValueError("cross_structure needs a multi-hull vessel (n_hulls >= 2) with the hull centreline spacing B_cl")
        cross = {}
        csec = None
        if cs.get("section"):
            csec = SEC.compute(cs["section"], v.units)
            cross["section"] = csec
        SMt = cs.get("SMt_cm2m", min(csec["SM_deck_cm3"], csec["SM_bottom_cm3"]) * v.U.sm_hg_per_mod if csec else None)
        At = cs.get("At_cm2", csec["shear"]["web_area_cm2"] if csec else None)
        if SMt is None or At is None:
            raise ValueError("cross_structure needs SMt_cm2m and At_cm2, or a cross-structure section")
        rr, info = SH.cross_structure_checks(v, mat, SMt, At)
        results += rr
        cross.update(info)
        cross["from_section"] = csec is not None and "SMt_cm2m" not in cs
        if cs.get("elements"):
            rr, tors = SH.torsion_elements(info["Mtt"], cs["elements"], mat)
            results += rr
            cross["torsion"] = tors
        out["cross"] = cross
    elif v.n_hulls >= 2 and v.B_cl:
        out["cross"] = {**HGM.catamaran_loads(v.delta_t, v.B_cl, v.L, P.ncg(v), v.units), "allow": HGM.catamaran_allowables(mat), "checked": False}
    return out


def markdown(rep: dict) -> str:
    rows = rep["results"]
    n_fail = sum(not r["passed"] for r in rows)
    out = [f"# Aluminum scantling check - ABS HSC Rules (July 2022)", "",
           f"Material: {rep['material']['name']} (source: {rep['material']['source']}); "
           f"sigma_y design {rep['material']['sigma_y_design']:.1f} {rep['unit_labels']['sig']}, Q {rep['material']['Q']:.3f}"
           f"  [{rep['unit_labels']['name']} units]",
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
