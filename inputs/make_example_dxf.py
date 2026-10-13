"""Writes the two example section drawings as closed outlines (run from the repository root: python inputs/make_example_dxf.py).

example_section.dxf   half midship section (right side), mm: mitred plating shapes plus a rectangle for every
                      stiffener web and flange, drawn edge to edge. Layer names carry no thickness.
example_crossdeck.dxf cross-deck section through the wet deck, mm.
"""
import math


def dxf(shapes, path, insunits=4):
    out = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", str(insunits), "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    for layer, pts in shapes:
        out += ["0", "LWPOLYLINE", "8", layer, "90", str(len(pts)), "70", "1"]
        for x, y in pts:
            out += ["10", f"{x:.4f}", "20", f"{y:.4f}"]
    out += ["0", "ENDSEC", "0", "EOF"]
    open(path, "w").write("\n".join(out) + "\n")


def _off(p, q, d):
    """Line p->q offset to its left by d: returns (point, direction)."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    l = math.hypot(dx, dy)
    ux, uy = dx / l, dy / l
    return (p[0] - uy * d, p[1] + ux * d), (ux, uy)


def _isect(a, da, b, db):
    det = da[0] * db[1] - da[1] * db[0]
    if abs(det) < 1e-12:
        return a
    t = ((b[0] - a[0]) * db[1] - (b[1] - a[1]) * db[0]) / det
    return (a[0] + t * da[0], a[1] + t * da[1])


def plating(center, thick, ref):
    """Mitred plate shapes along a centre-line polyline (ends cut on the line y = 0)."""
    n = len(center) - 1
    left = [_off(center[i], center[i + 1], 0.0) for i in range(n)]
    # the side of the section interior is the 'in' side
    sides = []
    for i in range(n):
        mid = ((center[i][0] + center[i + 1][0]) / 2, (center[i][1] + center[i + 1][1]) / 2)
        ux, uy = left[i][1]
        nx, ny = -uy, ux
        sides.append(1 if nx * (ref[0] - mid[0]) + ny * (ref[1] - mid[1]) > 0 else -1)  # +1: left normal points inside
    inner, outer, norm = [], [], []
    for i in range(n):
        t = thick[i] / 2
        s = sides[i]
        inner.append(_off(center[i], center[i + 1], s * t))
        outer.append(_off(center[i], center[i + 1], -s * t))
        ux, uy = left[i][1]
        norm.append((-uy * s, ux * s))  # inward unit normal
    def corners(lines, i):  # start and end point of line i, mitred with its neighbours
        a, da = lines[i]
        if i == 0:
            p0 = _isect(a, da, (0.0, 0.0), (0.0, 1.0))  # cut on y = 0
        else:
            p0 = _isect(a, da, *lines[i - 1])
        if i == n - 1:
            p1 = _isect(a, da, (0.0, 0.0), (0.0, 1.0))
        else:
            p1 = _isect(a, da, *lines[i + 1])
        return p0, p1
    shapes = []
    for i in range(n):
        i0, i1 = corners(inner, i)
        o0, o1 = corners(outer, i)
        shapes.append(("PLATING", [o0, o1, i1, i0]))
    return shapes, inner, norm


def rect_on(p, u, nrm, along0, along1, h0, h1):
    """Rectangle in the frame (origin p, unit u along the surface, nrm inwards): along in [a0,a1], height in [h0,h1]."""
    def pt(a, h):
        return (p[0] + u[0] * a + nrm[0] * h, p[1] + u[1] * a + nrm[1] * h)
    return [pt(along0, h0), pt(along1, h0), pt(along1, h1), pt(along0, h1)]


def stiffeners(center, i, inner, nrm, spacing, hw, tw, bf=0.0, tf=0.0):
    p, q = center[i], center[i + 1]
    l = math.hypot(q[0] - p[0], q[1] - p[1])
    u = ((q[0] - p[0]) / l, (q[1] - p[1]) / l)
    panels = max(1, round(l / spacing))
    out = []
    for k in range(1, panels):
        a = k * l / panels
        # inner surface point at this station: project the centre-line point onto the inner offset line
        base = (inner[i][0][0] + u[0] * (a), inner[i][0][1] + u[1] * (a))
        c0 = (p[0] + u[0] * a, p[1] + u[1] * a)
        d = (c0[0] - inner[i][0][0]) * u[0] + (c0[1] - inner[i][0][1]) * u[1]
        base = (inner[i][0][0] + u[0] * d, inner[i][0][1] + u[1] * d)
        out.append(("STIFFENERS", rect_on(base, u, nrm, -tw / 2, tw / 2, 0, hw)))
        if bf:
            out.append(("STIFFENERS", rect_on(base, u, nrm, -bf / 2, bf / 2, hw, hw + tf)))
    return out


# ---- midship half section: centre line (0,0) -> (2800,400) -> (3000,3000) -> (0,3000)
C = [(0.0, 0.0), (2800.0, 400.0), (3000.0, 3000.0), (0.0, 3000.0)]
T = [8.0, 6.0, 6.0]
shapes, inner, norm = plating(C, T, ref=(1200.0, 1500.0))
shapes += stiffeners(C, 0, inner, norm[0], 300, 100, 6, 50, 8)
shapes += stiffeners(C, 1, inner, norm[1], 350, 80, 6)
shapes += stiffeners(C, 2, inner, norm[2], 300, 80, 6)
dxf(shapes, "inputs/example_section.dxf")


# ---- cross-deck section: wet deck 8 mm at z = 0, deck 6 mm at z = 1000, three 6 mm bulkheads (mm)
def R(x0, z0, x1, z1):
    return [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]


cd = [("PLATE", R(0, -4, 8000, 4)), ("PLATE", R(0, 997, 8000, 1003))]
for x in (3, 4000, 7997):
    cd.append(("PLATE", R(x - 3, 4, x + 3, 997)))
dxf(cd, "inputs/example_crossdeck.dxf")
