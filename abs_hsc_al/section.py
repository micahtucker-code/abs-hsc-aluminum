"""Midship section properties (vertical bending) from a thin-walled idealisation.

Geometry is in mm (inches when units = "US") in a section plane: y horizontal (0 = centreline), z vertical (0 = baseline).
Results are in cm2 / cm3 / cm4 (SI) or in2 / in3 / in4 (US); the result keys keep their `_cm2/_cm3/_cm4/_mm` names.
Members:
  plate    a straight line from (y1,z1) to (y2,z2) with thickness t_mm; may carry a regular set of
           stiffeners (flat bar / tee / angle) expanded into web and flange lines
  lump     a stand-alone area (e.g. an extrusion or bulb taken from a catalogue): area_mm2, z_mm, I_mm4
  dxf      segments imported from a CAD drawing, thickness and effectiveness set per layer

Every element may carry an 'effective' factor (0..1) that scales its area and inertia, so non-effective
structure (superstructure, bulwarks) can be left in the drawing at 0.

Not modelled: shear lag, buckling-based effective-width reduction of compressed plating, openings other than
as negative lumps, and more than one alloy in the section.
"""
from __future__ import annotations

import math

from . import units as UN


def _seg(y1, z1, y2, z2, t):
    """Area, centroid z and own inertia about the horizontal centroidal axis of a thin straight member."""
    dy, dz = y2 - y1, z2 - z1
    l = math.hypot(dy, dz)
    if l < 1e-9:
        return 0.0, (z1 + z2) / 2, 0.0
    I = t * l * dz * dz / 12.0 + t ** 3 * l * (dy * dy / (l * l)) / 12.0
    return l * t, (z1 + z2) / 2, I


def _expand_stiffeners(m: dict, ref: tuple[float, float]) -> list[dict]:
    """Web and flange lines for the stiffeners on a plate member."""
    st = m["stiffeners"]
    y1, z1, y2, z2, tp = m["y1"], m["z1"], m["y2"], m["z2"], m["t_mm"]
    dy, dz = y2 - y1, z2 - z1
    l = math.hypot(dy, dz)
    if l < 1e-9:
        return []
    ux, uz = dy / l, dz / l
    nx, nz = -uz, ux  # left normal
    my, mz = (y1 + y2) / 2, (z1 + z2) / 2
    dot = nx * (ref[0] - my) + nz * (ref[1] - mz)
    if dot < -1e-9 or (abs(dot) <= 1e-9 and nz < 0):
        nx, nz = -nx, -nz
    side = st.get("side", "in")
    if side == "out":
        nx, nz = -nx, -nz
    elif side != "in":
        raise ValueError("stiffener side must be 'in' or 'out'")
    if "count" in st:
        n = int(st["count"])
        pos = [(i + 1) * l / (n + 1) for i in range(n)]
    else:
        s = float(st.get("spacing_mm", 0))
        if s <= 0:
            raise ValueError("stiffeners need a positive spacing_mm (or a count)")
        panels = max(1, round(l / s))
        pos = [i * l / panels for i in range(0 if st.get("ends") else 1, panels + (1 if st.get("ends") else 0))]
    hw, tw = float(st["hw_mm"]), float(st["tw_mm"])
    prof = st.get("profile", "flat")
    bf, tf = float(st.get("bf_mm", 0.0)), float(st.get("tf_mm", 0.0))
    out = []
    for p in pos:
        py, pz = y1 + ux * p, z1 + uz * p
        b0 = (py + nx * tp / 2, pz + nz * tp / 2)
        b1 = (py + nx * (tp / 2 + hw), pz + nz * (tp / 2 + hw))
        out.append({"y1": b0[0], "z1": b0[1], "y2": b1[0], "z2": b1[1], "t": tw, "kind": "web"})
        if prof in ("tee", "angle") and bf > 0 and tf > 0:
            fc = (py + nx * (tp / 2 + hw + tf / 2), pz + nz * (tp / 2 + hw + tf / 2))
            a, b = ((-bf / 2, bf / 2) if prof == "tee" else (0.0, bf))
            out.append({"y1": fc[0] + ux * a, "z1": fc[1] + uz * a, "y2": fc[0] + ux * b, "z2": fc[1] + uz * b,
                        "t": tf, "kind": "flange"})
    return out


def compute(sec: dict, units: str = "SI") -> dict:
    """sec: {"mirror": bool, "deck_z_mm": opt, "base_z_mm": opt, "members": [...], "dxf": {...}} -> results."""
    U = UN.get(units)
    members = sec.get("members", [])
    dxf = sec.get("dxf")
    mirror = bool(sec.get("mirror", False))

    # --- gather base lines (for the stiffener reference point) ---
    lines = []  # dicts: group, y1,z1,y2,z2,t,eff,kind
    lumps = []
    for m in members:
        name = m.get("name", "member")
        eff = float(m.get("effective", 1.0))
        typ = m.get("type", "plate")
        if typ == "plate":
            for k in ("y1", "z1", "y2", "z2", "t_mm"):
                if k not in m:
                    raise ValueError(f"section member '{name}' is missing '{k}'")
            lines.append({"group": name, "y1": m["y1"], "z1": m["z1"], "y2": m["y2"], "z2": m["z2"],
                          "t": m["t_mm"], "eff": eff, "kind": "plate", "src": m})
        elif typ == "lump":
            for k in ("area_mm2", "z_mm"):
                if k not in m:
                    raise ValueError(f"section lump '{name}' is missing '{k}'")
            lumps.append({"group": name, "A": m["area_mm2"], "z": m["z_mm"], "I": m.get("I_mm4", 0.0),
                          "y": m.get("y_mm", 0.0), "eff": eff})
        else:
            raise ValueError(f"section member '{name}': type must be 'plate' or 'lump'")
    skipped: dict[str, int] = {}
    if dxf:
        lay = dxf.get("layers", {})
        for s in dxf.get("segments", []):
            L = lay.get(s[0])
            if L and L.get("ignore"):
                continue
            if not L or not L.get("t_mm"):
                skipped[s[0]] = skipped.get(s[0], 0) + 1
                continue
            lines.append({"group": "dxf: " + s[0], "y1": s[1], "z1": s[2], "y2": s[3], "z2": s[4],
                          "t": float(L["t_mm"]), "eff": float(L.get("eff", 1.0)), "kind": "plate", "src": None})
    if not lines and not lumps:
        raise ValueError("section has no members")

    ys = [v for l in lines for v in (l["y1"], l["y2"])]
    zs = [v for l in lines for v in (l["z1"], l["z2"])] + [x["z"] for x in lumps]
    ref = (0.0 if mirror or not ys else (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)

    # --- expand stiffeners ---
    allx = list(lines)
    for l in lines:
        src = l["src"]
        if src and src.get("stiffeners"):
            for e in _expand_stiffeners(src, ref):
                allx.append({"group": l["group"], "y1": e["y1"], "z1": e["z1"], "y2": e["y2"], "z2": e["z2"],
                             "t": e["t"], "eff": l["eff"], "kind": e["kind"], "src": None})

    # --- elements (area, z, own I), mirrored where required ---
    elems = []
    geom = []
    for l in allx:
        A, zc, I = _seg(l["y1"], l["z1"], l["y2"], l["z2"], l["t"])
        on_cl = abs(l["y1"]) < 1e-6 and abs(l["y2"]) < 1e-6
        mf = 2.0 if (mirror and not on_cl) else 1.0
        k = mf * l["eff"]
        elems.append({"group": l["group"], "A": A * k, "z": zc, "I": I * k, "line": l, "k": k, "mf": mf, "on_cl": on_cl})
        geom.append([round(l["y1"], 2), round(l["z1"], 2), round(l["y2"], 2), round(l["z2"], 2),
                     round(l["t"], 3), l["kind"], l["eff"]])
        if mirror and not on_cl:
            geom.append([round(-l["y1"], 2), round(l["z1"], 2), round(-l["y2"], 2), round(l["z2"], 2),
                         round(l["t"], 3), l["kind"], l["eff"]])
    lump_geom = []
    for x in lumps:
        k = (2.0 if (mirror and abs(x["y"]) > 1e-6) else 1.0) * x["eff"]
        elems.append({"group": x["group"], "A": x["A"] * k, "z": x["z"], "I": x["I"] * k})
        lump_geom.append([round(x["y"], 2), round(x["z"], 2), x["A"]])
        if mirror and abs(x["y"]) > 1e-6:
            lump_geom.append([round(-x["y"], 2), round(x["z"], 2), x["A"]])

    A = sum(e["A"] for e in elems)
    if A <= 0:
        raise ValueError("section has no net effective area")
    zna = sum(e["A"] * e["z"] for e in elems) / A
    I = sum(e["I"] + e["A"] * (e["z"] - zna) ** 2 for e in elems)

    zs = zs + [v for l in allx for v in (l["z1"], l["z2"])]
    z_bot = float(sec["base_z_mm"]) if "base_z_mm" in sec else min(zs)
    z_deck = float(sec["deck_z_mm"]) if "deck_z_mm" in sec else max(zs)
    if not (z_bot < zna < z_deck):
        raise ValueError(f"neutral axis ({zna:.1f} {U.small}) lies outside baseline ({z_bot:.1f}) and deck ({z_deck:.1f})")

    groups: dict[str, dict] = {}
    for e in elems:
        g = groups.setdefault(e["group"], {"name": e["group"], "A_mm2": 0.0, "Az": 0.0, "I_own": 0.0})
        g["A_mm2"] += e["A"]
        g["Az"] += e["A"] * e["z"]
        g["I_own"] += e["I"]
    rows = []
    for g in groups.values():
        zc = g["Az"] / g["A_mm2"] if g["A_mm2"] else 0.0
        dist = sum(e["A"] * (e["z"] - zna) ** 2 for e in elems if e["group"] == g["name"])
        rows.append({"name": g["name"], "A_cm2": g["A_mm2"] / U.area_div, "z_mm": zc,
                     "I_own_cm4": g["I_own"] / U.inertia_div, "I_total_cm4": (g["I_own"] + dist) / U.inertia_div})
    z_lev = float(sec["shear_level_z_mm"]) if "shear_level_z_mm" in sec else zna
    shear = _shear_geometry(elems, lumps, mirror, z_lev, zna, U)
    shear["web_area_cm2"] = sum(e["k"] * e["line"]["t"] * abs(e["line"]["z2"] - e["line"]["z1"])
                                for e in elems if "line" in e and e["line"]["kind"] == "plate"
                                and abs(e["line"]["z2"] - e["line"]["z1"]) > abs(e["line"]["y2"] - e["line"]["y1"])) / U.area_div
    return {
        "shear": shear,
        "units": U.name,
        "A_cm2": A / U.area_div, "z_NA_mm": zna, "I_cm4": I / U.inertia_div,
        "z_deck_mm": z_deck, "z_bottom_mm": z_bot,
        "SM_deck_cm3": I / (z_deck - zna) / U.mod_div, "SM_bottom_cm3": I / (zna - z_bot) / U.mod_div,
        "mirror": mirror, "rows": rows, "geometry": geom, "lumps": lump_geom,
        "skipped_layers": skipped, "n_lines": len(allx), "n_stiffener_lines": len(allx) - len(lines),
        "bbox": [min(ys + [-y for y in ys] if mirror else ys), min(zs), max(ys + [-y for y in ys] if mirror else ys), max(zs)] if ys else [0, min(zs), 0, max(zs)],
    }


def _shear_geometry(elems, lumps, mirror, z_lev, zna, U=UN.SI):
    """First moment m (cm3; in3 for US) about the neutral axis of the effective area above the level z_lev, and the shear
    webs (plate members that cross the level): count, total thickness, thinnest, any on the centreline."""
    m = 0.0
    webs_t = 0.0
    n_webs = 0.0
    t_min = None
    on_cl_web = False
    for e in elems:
        l = e.get("line")
        if not l:
            continue
        z1, z2, t, k = l["z1"], l["z2"], l["t"], e["k"]
        lo, hi = min(z1, z2), max(z1, z2)
        if hi <= z_lev:
            continue
        frac = 1.0 if lo >= z_lev else (hi - z_lev) / (hi - lo)
        zc_top = (max(lo, z_lev) + hi) / 2
        length = math.hypot(l["y2"] - l["y1"], z2 - z1)
        m += k * t * length * frac * (zc_top - zna)
        if l["kind"] == "plate" and lo < z_lev < hi:
            webs_t += k * t
            n_webs += e["mf"]
            t_min = t if t_min is None else min(t_min, t)
            on_cl_web = on_cl_web or e["on_cl"]
    for x in lumps:
        if x["z"] > z_lev:
            m += x["A"] * x["eff"] * (2.0 if (mirror and abs(x["y"]) > 1e-6) else 1.0) * (x["z"] - zna)
    return {"z_level_mm": z_lev, "m_cm3": m / U.mod_div, "web_t_sum_mm": webs_t, "n_webs": n_webs,
            "t_min_mm": t_min, "centreline_web": on_cl_web}
