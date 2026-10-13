"""Plane polygon geometry for section outlines: area properties, nesting (holes), clipping, overlap detection, and a
thin-web classifier for the shear checks. Pure Python; polygons are lists of (y, z) vertices (not repeated at the end)."""
from __future__ import annotations

import math


def signed_area(p) -> float:
    return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))


def ccw(p):
    return list(p) if signed_area(p) >= 0 else list(reversed(p))


def props(p) -> dict:
    """Area (>0), centroid (cy, cz), own central second moments Iyy (about the vertical axis), Izz (about the horizontal
    axis = the bending inertia), Iyz, for a simple polygon."""
    p = ccw(p)
    n = len(p)
    a2 = sy = sz = ixx = iyy = ixy = 0.0
    for i in range(n):
        y0, z0 = p[i]
        y1, z1 = p[(i + 1) % n]
        c = y0 * z1 - y1 * z0
        a2 += c
        sy += (y0 + y1) * c
        sz += (z0 + z1) * c
        ixx += (z0 * z0 + z0 * z1 + z1 * z1) * c
        iyy += (y0 * y0 + y0 * y1 + y1 * y1) * c
        ixy += (y0 * z1 + 2 * y0 * z0 + 2 * y1 * z1 + y1 * z0) * c
    A = a2 / 2
    if abs(A) < 1e-12:
        return {"A": 0.0, "cy": 0.0, "cz": 0.0, "Izz": 0.0, "Iyy": 0.0, "Iyz": 0.0}
    cy, cz = sy / (6 * A), sz / (6 * A)
    return {"A": A, "cy": cy, "cz": cz,
            "Izz": ixx / 12 - A * cz * cz,       # about the horizontal centroidal axis (bending)
            "Iyy": iyy / 12 - A * cy * cy,
            "Iyz": ixy / 24 - A * cy * cz}


def perimeter(p) -> float:
    return sum(math.hypot(p[(i + 1) % len(p)][0] - p[i][0], p[(i + 1) % len(p)][1] - p[i][1]) for i in range(len(p)))


def bbox(p):
    ys = [q[0] for q in p]
    zs = [q[1] for q in p]
    return min(ys), min(zs), max(ys), max(zs)


def _on_seg(pt, a, b, tol) -> bool:
    (x, y), (x0, y0), (x1, y1) = pt, a, b
    dx, dy = x1 - x0, y1 - y0
    l2 = dx * dx + dy * dy
    if l2 < 1e-18:
        return math.hypot(x - x0, y - y0) <= tol
    t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / l2))
    return math.hypot(x - (x0 + t * dx), y - (y0 + t * dy)) <= tol


def locate(pt, poly, tol=1e-6) -> int:
    """1 strictly inside, 0 on the boundary, -1 outside (ray casting)."""
    n = len(poly)
    for i in range(n):
        if _on_seg(pt, poly[i], poly[(i + 1) % n], tol):
            return 0
    x, y = pt
    inside = False
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return 1 if inside else -1


def inside_of(a, b, tol=1e-6) -> bool:
    """Polygon a lies inside polygon b (touching allowed, at least one point strictly inside)."""
    pts = list(a) + [((a[i][0] + a[(i + 1) % len(a)][0]) / 2, (a[i][1] + a[(i + 1) % len(a)][1]) / 2) for i in range(len(a))]
    inn = 0
    for q in pts:
        r = locate(q, b, tol)
        if r < 0:
            return False
        inn += r > 0
    return inn > 0


def nest_depths(polys, tol=1e-6) -> list[int]:
    """Number of other polygons that contain each polygon (even = solid material, odd = hole)."""
    n = len(polys)
    bbs = [bbox(p) for p in polys]
    ar = [abs(signed_area(p)) for p in polys]
    depth = [0] * n
    for i in range(n):
        for j in range(n):
            if i == j or ar[j] <= ar[i]:
                continue
            bi, bj = bbs[i], bbs[j]
            if bi[0] < bj[0] - tol or bi[1] < bj[1] - tol or bi[2] > bj[2] + tol or bi[3] > bj[3] + tol:
                continue
            if inside_of(polys[i], polys[j], tol):
                depth[i] += 1
    return depth


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _proper_cross(p1, p2, p3, p4, tol) -> bool:
    """Segments cross at a single interior point: each end of one lies more than `tol` (a length) off the other
    (touching at the ends and collinear overlap do not count)."""
    l12 = math.hypot(p2[0] - p1[0], p2[1] - p1[1]) or 1.0
    l34 = math.hypot(p4[0] - p3[0], p4[1] - p3[1]) or 1.0
    d1, d2 = _cross(p3, p4, p1) / l34, _cross(p3, p4, p2) / l34
    d3, d4 = _cross(p1, p2, p3) / l12, _cross(p1, p2, p4) / l12
    return ((d1 > tol and d2 < -tol) or (d1 < -tol and d2 > tol)) and ((d3 > tol and d4 < -tol) or (d3 < -tol and d4 > tol))


def overlapping_pairs(polys, tol=1e-3) -> list[tuple[int, int]]:
    """Index pairs of polygons whose outlines cross each other by more than `tol` (partial overlap; nesting and shared edges are fine)."""
    out = []
    bbs = [bbox(p) for p in polys]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            a, b = bbs[i], bbs[j]
            if a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]:
                continue
            pi, pj = polys[i], polys[j]
            hit = False
            for k in range(len(pi)):
                p1, p2 = pi[k], pi[(k + 1) % len(pi)]
                for m in range(len(pj)):
                    if _proper_cross(p1, p2, pj[m], pj[(m + 1) % len(pj)], tol):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                out.append((i, j))
    return out


def clip_above(p, z0):
    """Part of polygon p with z >= z0 (Sutherland-Hodgman against one horizontal line); [] if nothing remains."""
    out = []
    n = len(p)
    for i in range(n):
        a, b = p[i], p[(i + 1) % n]
        ain, bin_ = a[1] >= z0, b[1] >= z0
        if ain:
            out.append(a)
        if ain != bin_:
            t = (z0 - a[1]) / (b[1] - a[1])
            out.append((a[0] + t * (b[0] - a[0]), z0))
    return out if len(out) >= 3 else []


def chords_at(p, z0) -> list[tuple[float, float]]:
    """Horizontal intervals (y_left, y_right) of polygon p at height z0 (z0 taken just above any horizontal edge)."""
    zs = [q[1] for q in p]
    z0 = z0 + 1e-9 * (max(zs) - min(zs) + 1.0) if any(abs(z - z0) < 1e-12 for z in zs) else z0
    xs = []
    n = len(p)
    for i in range(n):
        (x0, y0), (x1, y1) = p[i], p[(i + 1) % n]
        if (y0 > z0) != (y1 > z0):
            xs.append(x0 + (z0 - y0) * (x1 - x0) / (y1 - y0))
    xs.sort()
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]


def web_chords(p, z0, min_ratio=2.0) -> list[dict]:
    """Thin steep web pieces of polygon p at height z0: horizontal chords whose two bounding edges are both steeper than
    45 degrees and long compared with the chord (so the end of a flange or a lug is not taken for a web).
    Each: {"y": (left, right), "t": normal thickness = chord x sin(angle of the edges from horizontal)}."""
    zs = [q[1] for q in p]
    if any(abs(z - z0) < 1e-12 for z in zs):
        z0 += 1e-9 * (max(zs) - min(zs) + 1.0)
    xs = []
    n = len(p)
    for i in range(n):
        (x0, y0), (x1, y1) = p[i], p[(i + 1) % n]
        if (y0 > z0) != (y1 > z0):
            ln = math.hypot(x1 - x0, y1 - y0)
            xs.append((x0 + (z0 - y0) * (x1 - x0) / (y1 - y0), abs(y1 - y0) / ln, ln))
    xs.sort()
    out = []
    for i in range(0, len(xs) - 1, 2):
        (a, sa, la), (b, sb, lb) = xs[i], xs[i + 1]
        chord = b - a
        sn = (sa + sb) / 2
        if sa >= math.sqrt(0.5) and sb >= math.sqrt(0.5) and min(la, lb) >= min_ratio * chord * sn and chord > 0:
            out.append({"y": (a, b), "t": chord * sn})
    return out


def web_area(p, n=300) -> float:
    """Area of the steep thin web parts of polygon p: the integral over height of the web thickness."""
    z0, z1 = min(q[1] for q in p), max(q[1] for q in p)
    if z1 - z0 < 1e-12:
        return 0.0
    dz = (z1 - z0) / n
    return sum(c["t"] for k in range(n) for c in web_chords(p, z0 + (k + 0.5) * dz)) * dz
