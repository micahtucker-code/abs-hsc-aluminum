"""Aluminum alloy property library from the ABS Rules for Materials and Welding (Part 2, July 2022).

Base-metal minimums (unwelded): 2-5-5 TABLE 1B (marine-grade plate), TABLE 2 (6061 plate),
TABLE 3 / TABLE 4 (extrusions).  As-welded minimums: 2-4-5/17 TABLE 2 (butt welds, plate up to
38 mm, filler per 2-4-5 TABLE 4).  Units N/mm2.

Only alloy/temper/product combinations where BOTH an unwelded and an as-welded value are
published are included.  Not included (no welded value published in 2-4-5 TABLE 2, or the
welded yield exceeds the unwelded yield): 5059, 5083-H128, 5086-H321, 6082, 6005A, 6063,
and the non-marine 5083-H111/H112 plate.  For those, enter the values yourself.
"""
from __future__ import annotations

# (alloy_temper, product, t_from_mm, t_to_mm, sy, su, sy_welded, su_welded, source)
_P = "2-5-5 T1B"
_X3, _X4 = "2-5-5 T3", "2-5-5 T4"
_W = "2-4-5/17 T2"
_ROWS = [
    ("5083-H116", "plate", 3.0, 12.5, 215, 305, 165, 276, _P),
    ("5083-H116", "plate", 12.5, 40.0, 215, 305, 165, 276, _P),
    ("5083-H116", "plate", 40.0, 80.0, 200, 285, 165, 276, _P),
    ("5083-H321", "plate", 3.2, 40.0, 215, 305, 165, 276, _P),
    ("5083-H321", "plate", 40.0, 80.0, 200, 285, 165, 276, _P),
    ("5086-H116", "plate", 3.0, 50.0, 195, 275, 131, 241, _P),
    ("5383-H116", "plate", 3.0, 50.0, 230, 330, 165, 290, _P),
    ("5383-H321", "plate", 3.0, 50.0, 230, 330, 165, 290, _P),
    ("5456-H116", "plate", 3.0, 30.0, 230, 315, 179, 290, _P),
    ("5456-H116", "plate", 30.0, 40.0, 215, 305, 179, 290, _P),
    ("5456-H116", "plate", 40.0, 80.0, 200, 285, 179, 290, _P),
    ("5456-H321", "plate", 3.0, 4.0, 235, 330, 179, 290, _P),
    ("5456-H321", "plate", 4.0, 12.5, 230, 315, 179, 290, _P),
    ("5456-H321", "plate", 12.5, 40.0, 215, 305, 179, 290, _P),
    ("5456-H321", "plate", 40.0, 80.0, 200, 285, 179, 290, _P),
    ("6061-T6", "plate", 3.0, 9.5, 240, 290, 138, 165, "2-5-5 T2"),
    ("6061-T6", "plate", 9.5, 80.0, 240, 290, 103, 165, "2-5-5 T2"),
    ("5083-H111", "extrusion", 3.0, 130.0, 165, 275, 145, 269, _X3),
    ("5086-H111", "extrusion", 3.0, 130.0, 145, 250, 124, 241, _X3),
    ("5383-H111", "extrusion", 3.0, 50.0, 145, 290, 145, 290, _X3),
    ("5456-H111", "extrusion", 3.0, 130.0, 180, 290, 165, 283, _X3),
    ("6061-T6", "extrusion", 3.0, 9.5, 240, 260, 138, 165, _X4),
    ("6061-T6", "extrusion", 9.5, 150.0, 240, 260, 103, 165, _X4),
]


def list_alloys() -> list[tuple[str, str]]:
    seen = []
    for r in _ROWS:
        k = (r[0], r[1])
        if k not in seen:
            seen.append(k)
    return seen


# Thickness band edges as the Rule prints them in inches (the mm edge converts to a slightly different inch value).
_EDGE_IN = {3.0: 0.118, 3.2: 0.125, 4.0: 0.1875, 9.5: 0.375, 12.5: 0.500, 30.0: 1.250, 40.0: 1.500, 50.0: 2.0,
            80.0: 3.0, 130.0: 5.0, 150.0: 6.0}


def _edge_in(mm: float) -> float:
    return _EDGE_IN.get(mm, mm / 25.4)


def _psi(n_mm2: float) -> float:
    """The Rule's US value: the N/mm2 figure in psi, rounded to the nearest ksi as printed in 2-4-5/17 and 2-5-5."""
    return round(n_mm2 * 1e6 / 6894.757293168 / 1000.0) * 1000.0


def lookup(alloy: str, product: str, thickness_mm: float, units: str = "SI") -> dict:
    """Return a material dict for `AluminumMaterial.from_dict`.

    Thickness bands are [from, to); the upper bound of the last band is inclusive. With units = "US" the thickness
    argument is in inches and the strengths are returned in psi (the Rule's ksi values, e.g. 5083-H116: 31.0 ksi)."""
    us = (units or "SI").upper() == "US"
    rows = [r for r in _ROWS if r[0] == alloy and r[1] == product]
    if not rows:
        raise ValueError(f"No library entry for {alloy} {product}. Available: "
                         + ", ".join(f"{a} {p}" for a, p in list_alloys()) + ". Or enter values from 2-5-5 / 2-4-5.")
    last = max(r[3] for r in rows)
    for a, p, t0, t1, sy, su, wy, wu, src in rows:
        if us:
            hit = _edge_in(t0) <= thickness_mm < _edge_in(t1) or (thickness_mm == _edge_in(t1) and t1 == last)
        else:
            hit = t0 <= thickness_mm < t1 or (thickness_mm == t1 == last)
        if hit:
            if us:
                return {"name": f"{a} {p}, {_edge_in(t0):g}-{_edge_in(t1):g} in", "sigma_y_unwelded": _psi(sy),
                        "sigma_u_unwelded": _psi(su), "sigma_y_welded": _psi(wy), "sigma_u_welded": _psi(wu),
                        "source": f"unwelded {src}; as-welded {_W} (ABS Materials & Welding Jul 2022, psi column)"}
            return {"name": f"{a} {p}, {t0:g}-{t1:g} mm", "sigma_y_unwelded": sy, "sigma_u_unwelded": su,
                    "sigma_y_welded": wy, "sigma_u_welded": wu,
                    "source": f"unwelded {src}; as-welded {_W} (ABS Materials & Welding Jul 2022)"}
    lo, hi = min(r[2] for r in rows), last
    if us:
        raise ValueError(f"{alloy} {product}: thickness {thickness_mm} in. is outside the tabulated {_edge_in(lo):g}-{_edge_in(hi):g} in. range")
    raise ValueError(f"{alloy} {product}: thickness {thickness_mm} mm is outside the tabulated {lo:g}-{hi:g} mm range")
