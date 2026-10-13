"""Minimal ASCII DXF reader for section drawings (no third-party packages).

The drawing shows every structural shape as a closed outline (a rectangle for a plate, the profile outline for a
stiffener or extrusion). The section properties are computed from the enclosed areas, so no thickness is read from
layer names. Reads LINE, LWPOLYLINE (with bulges), POLYLINE/VERTEX, ARC and CIRCLE from the ENTITIES section.
Closed polylines and circles are shapes as drawn; loose lines, arcs and open polylines are joined end to end
(within a small tolerance) wherever exactly two ends meet, and chains that close become shapes. A shape drawn inside
another is a hole. Anything that cannot be closed, and every other entity type (SPLINE, ELLIPSE, INSERT blocks, HATCH,
TEXT, DIMENSION), is reported so nothing is silently dropped. Export an ASCII DXF with blocks exploded.
"""
from __future__ import annotations

import math

from . import shapes as SH

UNIT_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
INSUNITS = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}
AXES = {"x": 0, "y": 1, "z": 2}
IGNORED = {"TEXT", "MTEXT", "DIMENSION", "HATCH", "POINT", "LEADER", "MLEADER", "ATTDEF", "ATTRIB", "VIEWPORT", "IMAGE"}
UNSUPPORTED = {"SPLINE", "ELLIPSE", "INSERT", "3DFACE", "SOLID", "TRACE", "MLINE", "RAY", "XLINE", "REGION", "BODY", "3DSOLID", "SURFACE"}


def _pairs(text: str):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i in range(0, len(lines) - 1, 2):
        try:
            yield int(lines[i].strip()), lines[i + 1].strip()
        except ValueError:
            raise ValueError(f"not an ASCII DXF (bad group code near line {i + 1})")


def _arc_points(cx, cy, r, a0, a1, step_mm=0.05):
    """Points along an arc from angle a0 to a1 (radians, counter-clockwise), sagitta <= step_mm."""
    sweep = (a1 - a0) % (2 * math.pi)
    if sweep == 0:
        sweep = 2 * math.pi
    d = max(2 * math.acos(max(0.0, 1 - step_mm / r)), 0.02) if r > step_mm else math.pi / 2
    n = max(1, min(400, math.ceil(sweep / d)))
    return [(cx + r * math.cos(a0 + sweep * i / n), cy + r * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]


def _bulge_points(p0, p1, bulge, step=0.05):
    """Points along a polyline arc segment defined by a bulge (tan of a quarter of the included angle)."""
    if abs(bulge) < 1e-12:
        return [p0, p1]
    (x0, y0), (x1, y1) = p0, p1
    c = math.hypot(x1 - x0, y1 - y0)
    if c < 1e-12:
        return [p0, p1]
    theta = 4 * math.atan(bulge)  # signed included angle (CCW positive)
    r = c / (2 * math.sin(abs(theta) / 2))
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    ux, uy = (x1 - x0) / c, (y1 - y0) / c
    d = (1.0 if bulge > 0 else -1.0) * r * math.cos(abs(theta) / 2)
    cx, cy = mx - uy * d, my + ux * d  # centre on the left of the chord for CCW arcs, right for CW
    a0 = math.atan2(y0 - cy, x0 - cx)
    n = max(1, min(400, math.ceil(abs(theta) / max(2 * math.acos(max(0.0, 1 - step / r)), 0.02)))) if r > step else 8
    return [(cx + r * math.cos(a0 + theta * i / n), cy + r * math.sin(a0 + theta * i / n)) for i in range(n + 1)]


def parse(text: str, plane: str = "xy", unit: str | None = None, y0: float | None = None, z0: float | None = None,
          units: str = "SI", tol: float | None = None) -> dict:
    """Return {layers, loops, open_segments, bbox, warnings, insunits, unit}. loops are [layer, [[y, z], ...]] closed
    shapes in mm (inches when units = "US"; the default drawing unit is then 'in'); open_segments are
    [layer, y1, z1, y2, z2] pieces that could not be closed. tol: gap tolerance when joining loose lines
    (default 0.5 mm, 0.02 in).

    plane: two letters, horizontal then vertical drawing axis ('xy', 'xz', 'yz', 'yx', ...). unit: 'mm', 'cm', 'm',
    'in', 'ft' (default: the file's $INSUNITS, else mm). y0 / z0: drawing coordinates (in drawing units) of the
    centreline and the baseline; default 0 and the lowest point of the drawing."""
    if len(plane) != 2 or plane[0] not in AXES or plane[1] not in AXES or plane[0] == plane[1]:
        raise ValueError("plane must be two different axes, e.g. 'xy' or 'yz'")
    ih, iv = AXES[plane[0]], AXES[plane[1]]
    pairs = list(_pairs(text))
    insunits = None
    for i, (c, v) in enumerate(pairs):
        if c == 9 and v == "$INSUNITS" and i + 1 < len(pairs):
            try:
                insunits = INSUNITS.get(int(pairs[i + 1][1]))
            except ValueError:
                pass
            break
    us = (units or "SI").upper() == "US"
    u = unit or insunits or ("in" if us else "mm")
    if u not in UNIT_MM:
        raise ValueError(f"unit must be one of {sorted(UNIT_MM)}")
    scale = UNIT_MM[u]  # drawing unit -> mm
    out_div = 25.4 if us else 1.0  # mm -> output unit

    # --- entity records between ENTITIES and its ENDSEC ---
    ents, cur, inside = [], None, False
    i = 0
    while i < len(pairs):
        c, v = pairs[i]
        if c == 0 and v == "SECTION":
            inside = i + 1 < len(pairs) and pairs[i + 1] == (2, "ENTITIES")
        elif c == 0 and v == "ENDSEC":
            inside = False
        elif inside and c == 0:
            cur = {"type": v, "g": []}
            ents.append(cur)
        elif inside and cur is not None:
            cur["g"].append((c, v))
        i += 1

    paths: list[tuple[str, list, bool]] = []  # (layer, [(h, v), ...], closed) in drawing units
    warn_types: dict[str, int] = {}

    def pt(g):
        """3D point from a flat list of (code, value) for codes 10/20/30 (first occurrence)."""
        d = {}
        for c, v in g:
            if c in (10, 20, 30) and c not in d:
                d[c] = float(v)
        return (d.get(10, 0.0), d.get(20, 0.0), d.get(30, 0.0))

    def hv(p):
        return (p[ih], p[iv])

    def add(layer, pts, closed=False):
        clean = [pts[0]] if pts else []
        for q in pts[1:]:
            if math.hypot(q[0] - clean[-1][0], q[1] - clean[-1][1]) > 1e-9:
                clean.append(q)
        if len(clean) > 2 and math.hypot(clean[0][0] - clean[-1][0], clean[0][1] - clean[-1][1]) <= 1e-9:
            clean.pop()
            closed = True
        if len(clean) >= 2:
            paths.append((layer, clean, closed and len(clean) >= 3))

    k = 0
    while k < len(ents):
        e = ents[k]
        t, g = e["type"], e["g"]
        layer = next((v for c, v in g if c == 8), "0")
        try:
            if t == "LINE":
                d = {}
                for c, v in g:
                    d[c] = float(v) if c in (10, 20, 30, 11, 21, 31) else v
                p0 = (d.get(10, 0.0), d.get(20, 0.0), d.get(30, 0.0))
                p1 = (d.get(11, 0.0), d.get(21, 0.0), d.get(31, 0.0))
                add(layer, [hv(p0), hv(p1)])
            elif t == "LWPOLYLINE":
                if plane != "xy":
                    warn_types["LWPOLYLINE (only usable in plane 'xy')"] = warn_types.get("LWPOLYLINE (only usable in plane 'xy')", 0) + 1
                    k += 1
                    continue
                flags = int(next((v for c, v in g if c == 70), "0"))
                vs, cx, cb = [], None, 0.0
                for c, v in g:
                    if c == 10:
                        if cx is not None:
                            vs.append((cx, cy, cb))
                        cx, cy, cb = float(v), 0.0, 0.0
                    elif c == 20 and cx is not None:
                        cy = float(v)
                    elif c == 42 and cx is not None:
                        cb = float(v)
                if cx is not None:
                    vs.append((cx, cy, cb))
                closed = bool(flags & 1)
                n = len(vs)
                pts = []
                for j in range(n if closed else n - 1):
                    a, b = vs[j], vs[(j + 1) % n]
                    seg = _bulge_points((a[0], a[1]), (b[0], b[1]), a[2], 0.05 / scale)
                    pts.extend(seg if not pts else seg[1:])
                add(layer, pts, closed)
            elif t == "POLYLINE":
                flags = int(next((v for c, v in g if c == 70), "0"))
                if flags & 16 or flags & 64:
                    warn_types["POLYLINE mesh"] = warn_types.get("POLYLINE mesh", 0) + 1
                verts = []
                k += 1
                while k < len(ents) and ents[k]["type"] == "VERTEX":
                    vg = ents[k]["g"]
                    p = pt(vg)
                    bl = next((float(v) for c, v in vg if c == 42), 0.0)
                    verts.append((p, bl))
                    k += 1
                closed = bool(flags & 1)
                n = len(verts)
                pts = []
                for j in range(n if closed else n - 1):
                    a, b = verts[j], verts[(j + 1) % n]
                    seg = _bulge_points(hv(a[0]), hv(b[0]), a[1], 0.05 / scale)
                    pts.extend(seg if not pts else seg[1:])
                add(layer, pts, closed)
                continue  # k already points at SEQEND/next
            elif t in ("ARC", "CIRCLE"):
                p = pt(g)
                r = float(next(v for c, v in g if c == 40))
                if plane != "xy":
                    warn_types[f"{t} (only usable in plane 'xy')"] = warn_types.get(f"{t} (only usable in plane 'xy')", 0) + 1
                else:
                    if t == "ARC":
                        a0 = math.radians(float(next(v for c, v in g if c == 50)))
                        a1 = math.radians(float(next(v for c, v in g if c == 51)))
                    else:
                        a0, a1 = 0.0, 2 * math.pi
                    stp = 0.05 / scale
                    add(layer, _arc_points(p[0], p[1], r, a0, a1, stp), closed=(t == "CIRCLE"))
            elif t in ("SEQEND", "VERTEX") or t in IGNORED:
                pass
            elif t in UNSUPPORTED:
                warn_types[t] = warn_types.get(t, 0) + 1
            else:
                warn_types[t] = warn_types.get(t, 0) + 1
        except StopIteration:
            warn_types[f"{t} (incomplete)"] = warn_types.get(f"{t} (incomplete)", 0) + 1
        k += 1

    if not paths:
        raise ValueError("no usable LINE / POLYLINE / ARC / CIRCLE geometry found in the DXF"
                         + (f" (skipped: {warn_types})" if warn_types else ""))
    allv = [q[1] for _, pts, _ in paths for q in pts]
    yo = 0.0 if y0 is None else y0
    zo = min(allv) if z0 is None else z0
    f = scale / out_div
    tol_out = tol if tol is not None else (0.02 if us else 0.5)
    outp = [(lay, [((h - yo) * f, (v - zo) * f) for h, v in pts], cl) for lay, pts, cl in paths]
    loops, opens = _resolve(outp, tol_out)

    notes = []
    # duplicate outlines (the same shape drawn twice) would be counted twice
    seen, uniq = [], []
    for lay, pts in loops:
        pr = SH.props(pts)
        key = (pr["A"], pr["cy"], pr["cz"])
        if any(abs(key[0] - k[0]) <= 1e-6 * max(key[0], 1) + 1e-9 and abs(key[1] - k[1]) <= tol_out and abs(key[2] - k[2]) <= tol_out for k in seen):
            continue
        seen.append(key)
        uniq.append([lay, pts])
    if len(uniq) < len(loops):
        notes.append(f"{len(loops) - len(uniq)} duplicate outline(s) drawn on top of another were ignored")
    loops = uniq
    if loops:
        ov = SH.overlapping_pairs([pts for _, pts in loops], tol_out * 0.01)
        if ov:
            names = ", ".join(sorted({f"{loops[i][0]}/{loops[j][0]}" for i, j in ov}))
            notes.append(f"{len(ov)} pair(s) of shapes cross each other's outlines ({names}); the overlapping area is counted twice. "
                         "Draw touching shapes edge to edge, or one inside another for a hole.")
    if not loops:
        raise ValueError("the drawing has no closed outlines. Draw each plate, stiffener or extrusion as a closed polyline "
                         "(or lines that meet end to end); the enclosed area is what is calculated"
                         + (f". {len(opens)} open line piece(s) were found" if opens else ""))
    layers: dict[str, dict] = {}
    for lay, pts in loops:
        L = layers.setdefault(lay, {"n": 0, "n_open": 0, "area_mm2": 0.0})
        L["n"] += 1
        L["area_mm2"] += abs(SH.signed_area(pts))
    for o in opens:
        L = layers.setdefault(o[0], {"n": 0, "n_open": 0, "area_mm2": 0.0})
        L["n_open"] += 1
    for L in layers.values():
        L["area_mm2"] = round(L["area_mm2"], 2)
    if opens:
        by = {}
        for o in opens:
            by[o[0]] = by.get(o[0], 0) + 1
        notes.append(f"{len(opens)} line piece(s) do not form a closed outline and are not part of the section (" +
                     ", ".join(f"{k}: {v}" for k, v in by.items()) + "). Check for gaps larger than the tolerance "
                     f"({tol_out:g} {'in' if us else 'mm'}), or lines meeting at a junction; closed polylines avoid both.")
    hs = [q[0] for _, pts in loops for q in pts] + [o[1] for o in opens] + [o[3] for o in opens]
    vs_ = [q[1] for _, pts in loops for q in pts] + [o[2] for o in opens] + [o[4] for o in opens]
    warnings = [f"{n} x {t} skipped (not supported: explode blocks / convert curves to arcs, lines or polylines)"
                if t.split(" ")[0] in UNSUPPORTED or "only usable" in t or "incomplete" in t or t == "POLYLINE mesh"
                else f"{n} x {t} skipped" for t, n in warn_types.items()] + notes
    r = 4 if us else 3
    return {"layers": layers, "loops": [[lay, [[round(a, r), round(b, r)] for a, b in pts]] for lay, pts in loops],
            "open_segments": [[o[0]] + [round(x, r) for x in o[1:]] for o in opens],
            "bbox": [min(hs), min(vs_), max(hs), max(vs_)], "warnings": warnings,
            "insunits": insunits, "unit": u, "y0_used": yo, "z0_used": zo, "tol": tol_out}


def _resolve(paths, tol):
    """Closed paths are loops; open paths are chained end to end where exactly two ends meet. Returns (loops, opens):
    loops = [(layer, pts)], opens = [[layer, y1, z1, y2, z2], ...] for everything that did not close."""
    loops, opens = [], []
    by_layer: dict[str, list] = {}
    for lay, pts, closed in paths:
        if closed:
            loops.append((lay, pts))
        else:
            by_layer.setdefault(lay, []).append(pts)
    for lay, plist in by_layer.items():
        cell = max(tol, 1e-9)
        grid: dict[tuple[int, int], list[int]] = {}
        clusters: list[list[tuple[int, int]]] = []  # per cluster: the (path, end) pairs that meet there
        cpos: list[tuple[float, float]] = []

        def find(pt):
            cx, cy = int(math.floor(pt[0] / cell)), int(math.floor(pt[1] / cell))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for ci in grid.get((cx + dx, cy + dy), ()):
                        if math.hypot(cpos[ci][0] - pt[0], cpos[ci][1] - pt[1]) <= tol:
                            return ci
            clusters.append([])
            cpos.append(pt)
            grid.setdefault((cx, cy), []).append(len(clusters) - 1)
            return len(clusters) - 1

        ends = []
        for i, pts in enumerate(plist):
            a, b = find(pts[0]), find(pts[-1])
            ends.append((a, b))
            clusters[a].append((i, 0))
            clusters[b].append((i, 1))
        used = [False] * len(plist)

        def oriented(j, f):  # path j read starting from its end f
            return list(plist[j]) if f == 0 else list(reversed(plist[j]))

        def walk(i, e):
            """Follow the chain that starts at end e of path i. Returns (points, closed)."""
            used[i] = True
            pts = oriented(i, e)
            ci, ce = i, 1 - e
            while True:
                c = ends[ci][ce]
                if len(clusters[c]) != 2:
                    return pts, False
                j, f = next(x for x in clusters[c] if x != (ci, ce))
                if j == i and f == e:
                    return pts, True
                if used[j]:
                    return pts, False
                used[j] = True
                pts.extend(oriented(j, f)[1:])
                ci, ce = j, 1 - f

        for i in range(len(plist)):          # chains that start at a free end or a junction: never closed
            for e in (0, 1):
                if not used[i] and len(clusters[ends[i][e]]) != 2:
                    pts, _ = walk(i, e)
                    opens.extend([lay, a[0], a[1], b[0], b[1]] for a, b in zip(pts, pts[1:]))
        for i in range(len(plist)):          # what is left is made of cycles
            if used[i]:
                continue
            pts, closed = walk(i, 0)
            if closed and len(pts) >= 4:
                if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= tol:
                    pts = pts[:-1]
                if len(pts) >= 3 and abs(SH.signed_area(pts)) > 1e-9:
                    loops.append((lay, pts))
                    continue
            opens.extend([lay, a[0], a[1], b[0], b[1]] for a, b in zip(pts, pts[1:]))
    return loops, opens
