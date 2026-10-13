"""Minimal ASCII DXF reader for section drawings (no third-party packages).

Reads LINE, LWPOLYLINE (with bulges), POLYLINE/VERTEX, ARC and CIRCLE from the ENTITIES section and turns
them into straight segments. Everything else (SPLINE, ELLIPSE, INSERT blocks, TEXT, DIMENSION, HATCH) is
counted and reported as a warning so nothing is silently dropped. Export an ASCII DXF with blocks exploded
and curves as lines/arcs/polylines.
"""
from __future__ import annotations

import math
import re

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


def _arc_points(cx, cy, r, a0, a1, step_mm=1.0):
    """Points along an arc from angle a0 to a1 (radians, counter-clockwise), sagitta <= step_mm."""
    sweep = (a1 - a0) % (2 * math.pi)
    if sweep == 0:
        sweep = 2 * math.pi
    d = max(2 * math.acos(max(0.0, 1 - step_mm / r)), 0.02) if r > step_mm else math.pi / 2
    n = max(1, min(400, math.ceil(sweep / d)))
    return [(cx + r * math.cos(a0 + sweep * i / n), cy + r * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]


def _bulge_points(p0, p1, bulge):
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
    n = max(1, min(400, math.ceil(abs(theta) / max(2 * math.acos(max(0.0, 1 - 1.0 / r)), 0.02)))) if r > 1.0 else 8
    return [(cx + r * math.cos(a0 + theta * i / n), cy + r * math.sin(a0 + theta * i / n)) for i in range(n + 1)]


def guess_thickness(layer: str):
    """Suggest a plate thickness (mm) from a layer name such as 'T8', 'PL_6.5', 'bottom-10mm'."""
    m = re.findall(r"(\d+(?:[.,]\d+)?)", layer)
    if not m:
        return None
    v = float(m[-1].replace(",", "."))
    return v if 1.0 <= v <= 60.0 else None


def parse(text: str, plane: str = "xy", unit: str | None = None, y0: float | None = None, z0: float | None = None) -> dict:
    """Return {layers, segments, bbox, warnings, insunits, unit}. Segments are [layer, y1, z1, y2, z2] in mm.

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
    u = unit or insunits or "mm"
    if u not in UNIT_MM:
        raise ValueError(f"unit must be one of {sorted(UNIT_MM)}")
    scale = UNIT_MM[u]

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

    segs: list[list] = []  # [layer, h1, v1, h2, v2] in drawing units
    counts: dict[str, int] = {}
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
        if closed and len(pts) > 2:
            pts = pts + [pts[0]]
        for a, b in zip(pts, pts[1:]):
            if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-9:
                segs.append([layer, a[0], a[1], b[0], b[1]])
                counts[layer] = counts.get(layer, 0) + 1

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
                    seg = _bulge_points((a[0], a[1]), (b[0], b[1]), a[2])
                    pts.extend(seg if not pts else seg[1:])
                add(layer, pts)
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
                    seg = _bulge_points(hv(a[0]), hv(b[0]), a[1])
                    pts.extend(seg if not pts else seg[1:])
                add(layer, pts)
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
                    stp = 1.0 / scale
                    add(layer, _arc_points(p[0], p[1], r, a0, a1, stp))
            elif t in ("SEQEND", "VERTEX") or t in IGNORED:
                pass
            elif t in UNSUPPORTED:
                warn_types[t] = warn_types.get(t, 0) + 1
            else:
                warn_types[t] = warn_types.get(t, 0) + 1
        except StopIteration:
            warn_types[f"{t} (incomplete)"] = warn_types.get(f"{t} (incomplete)", 0) + 1
        k += 1

    if not segs:
        raise ValueError("no usable LINE / POLYLINE / ARC geometry found in the DXF"
                         + (f" (skipped: {warn_types})" if warn_types else ""))
    vmin = min(min(s[2], s[4]) for s in segs)
    yo = 0.0 if y0 is None else y0
    zo = vmin if z0 is None else z0
    out = [[s[0], (s[1] - yo) * scale, (s[2] - zo) * scale, (s[3] - yo) * scale, (s[4] - zo) * scale] for s in segs]
    layers: dict[str, dict] = {}
    for s in out:
        L = layers.setdefault(s[0], {"n": 0, "length_mm": 0.0})
        L["n"] += 1
        L["length_mm"] += math.hypot(s[3] - s[1], s[4] - s[2])
    for name, L in layers.items():
        L["suggested_t_mm"] = guess_thickness(name)
        L["length_mm"] = round(L["length_mm"], 1)
    hs = [v for s in out for v in (s[1], s[3])]
    vs_ = [v for s in out for v in (s[2], s[4])]
    warnings = [f"{n} x {t} skipped (not supported: explode blocks / convert curves to arcs, lines or polylines)"
                if t.split(" ")[0] in UNSUPPORTED or "only usable" in t or "incomplete" in t or t == "POLYLINE mesh"
                else f"{n} x {t} skipped" for t, n in warn_types.items()]
    return {"layers": layers, "segments": [[s[0]] + [round(x, 3) for x in s[1:]] for s in out],
            "bbox": [min(hs), min(vs_), max(hs), max(vs_)], "warnings": warnings,
            "insunits": insunits, "unit": u, "y0_used": yo, "z0_used": zo}
