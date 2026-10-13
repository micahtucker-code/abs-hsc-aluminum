"""Hull girder shear (3-2-1/1.9) and multi-hull cross-structure global loads (3-2-1/3.3, 3-2-1/3.5, 3-2-A2).

Units follow the Rule text: forces kN, moments kN-m, section data cm / cm2 / cm3 / cm4, stresses kN/cm2 for the
longitudinal shear check and N/mm2 for the cross-structure checks.
"""
from __future__ import annotations

import math

from .materials import AluminumMaterial, E_ALUMINUM
from .plating import PlateResult
from . import hullgirder as HG
from . import pressures as P


def shear_forces(v: P.Vessel, Cb: float, F1: float, F2: float) -> dict:
    """Wave (1.9.2) and slam (1.9.3) shear forces at a station for the distribution factors F1, F2 (kN)."""
    n = 1.0 + P.ncg(v)
    return {"Fwp": HG.wave_shear(v.L, v.B, Cb, F1, True), "Fwn": HG.wave_shear(v.L, v.B, Cb, F2, False),
            "Fslp": HG.slam_shear(v.delta_t, n, F1), "Fsln": -HG.slam_shear(v.delta_t, n, F2), "1+ncg": n}


def check_hull_shear(v: P.Vessel, mat: AluminumMaterial, Cb: float, I_cm4: float, m_cm3: float,
                     web_t_mm: float, stations: list[dict], combined: bool = True,
                     geometry_note: str = "") -> tuple[list[PlateResult], list[dict]]:
    """3-2-1/1.9.4. fs = F m / (Sum(t) I), with Sum(t) = 2 ts for the usual two side shells, against 11.0/Q kN/cm2.

    stations: [{name, x_over_L, F1, F2, Fsw_kN (optional)}]. Returns (results, per-station detail rows)."""
    allow = HG.shear_allowable(mat)
    tcm = web_t_mm / 10.0
    res: list[PlateResult] = []
    rows: list[dict] = []
    cb = HG.Cb_used(v.L, Cb)
    for st in stations:
        name = st.get("name") or f"x/L {st['x_over_L']:g}"
        for k in ("F1", "F2"):
            if k not in st:
                raise ValueError(f"hull shear station '{name}': {k} (distribution factor from the Rule figure) is required")
        fsw = float(st.get("Fsw_kN", 0.0))
        f = shear_forces(v, cb, st["F1"], st["F2"])
        k_fs = m_cm3 / (tcm * I_cm4)  # kN/cm2 per kN
        c1 = max(abs(fsw + f["Fwp"]), abs(fsw + f["Fwn"]))
        c2 = max(abs(f["Fslp"]), abs(f["Fsln"]))
        c3 = max(abs(fsw + f["Fwp"] + f["Fslp"]), abs(fsw + f["Fwn"] + f["Fsln"]))
        row = {"name": name, "x_over_L": st.get("x_over_L"), "F1": st["F1"], "F2": st["F2"], "Fsw": fsw, **f,
               "F_sw_w": c1, "F_sl": c2, "F_sum": c3, "fs_sw_w": c1 * k_fs, "fs_sl": c2 * k_fs, "fs_sum": c3 * k_fs,
               "allow": allow, "Fsw_given": "Fsw_kN" in st}
        rows.append(row)
        common = (f"F1 = {st['F1']:g}, F2 = {st['F2']:g}; m = {m_cm3:.0f} cm3, I = {I_cm4:.4g} cm4, "
                  f"2ts = {web_t_mm:.1f} mm; allowable 11.0/Q = {allow:.2f} kN/cm2")
        res.append(PlateResult("hull girder", f"shear stress Fsw+Fw ({name})", "3-2-1/1.9.4", row["fs_sw_w"], allow, "kN/cm2",
                               {"F": c1}, formula="fs = (Fsw + Fw) m / (2 ts I)  [kN/cm2]; Fw = Fwp = +30 F1 C1 L B (Cb + 0.7) 1e-2 or Fwn = -30 F2 C1 L B (Cb + 0.7) 1e-2. 'Required' = working stress, 'Provided' = allowable 11.0/Q",
                               working=f"Fsw = {fsw:.0f}, Fwp = {f['Fwp']:.0f}, Fwn = {f['Fwn']:.0f} kN; governing |Fsw + Fw| = {c1:.0f} kN; {common};  fs = {row['fs_sw_w']:.3f} kN/cm2"))
        res.append(PlateResult("hull girder", f"shear stress Fsl ({name})", "3-2-1/1.9.4", row["fs_sl"], allow, "kN/cm2",
                               {"F": c2}, formula="fs = Fsl m / (2 ts I)  [kN/cm2]; Fsl = C4 F Delta (ncg + 1), C4 = 4.9, F = F1 (positive) or F2 (negative). 'Required' = working stress, 'Provided' = allowable 11.0/Q",
                               working=f"Delta = {v.delta_t:g} t, (1 + ncg) = {f['1+ncg']:.3f}; Fsl+ = {f['Fslp']:.0f}, Fsl- = {f['Fsln']:.0f} kN; {common};  fs = {row['fs_sl']:.3f} kN/cm2"))
        if combined:
            res.append(PlateResult("hull girder", f"shear stress Fsw+Fw+Fsl ({name})", "3-2-1/1.9.1", row["fs_sum"], allow, "kN/cm2",
                                   {"F": c3}, formula="fs = |Fsw + Fw + Fsl| m / (2 ts I)  (maximum algebraic sum, 1.9.1 reading). 'Required' = working stress, 'Provided' = allowable 11.0/Q",
                                   working=f"|Fsw + Fw + Fsl| = {c3:.0f} kN; {common};  fs = {row['fs_sum']:.3f} kN/cm2"))
    return res, rows


def cross_structure_checks(v: P.Vessel, mat: AluminumMaterial, SMt_cm2m: float, At_cm2: float) -> tuple[list[PlateResult], dict]:
    """3-2-1/3.3 loads with the 3-2-1/3.5.3 allowables; 3-2-A2/1 transverse bending and shear stress."""
    loads = HG.catamaran_loads(v.delta_t, v.B_cl, v.L, P.ncg(v))
    allow = HG.catamaran_allowables(mat)
    st = 10.0 * loads["Mtb"] / SMt_cm2m
    tq = 10.0 * loads["Qt"] / At_cm2
    res = [
        PlateResult("cross structure", "transverse bending stress", "3-2-1/3.5.3, 3-2-A2/1", st, allow["sigma_a"], "N/mm2",
                    {"Mtb": loads["Mtb"], "SMt": SMt_cm2m},
                    formula="sigma_t = 10 Mtb / SMt  [N/mm2]; Mtb = K1 Delta Bcl (1 + ncg), K1 = 2.5; allowable sigma_a = 0.66 sigma_y. 'Required' = working stress, 'Provided' = allowable",
                    working=f"Delta = {v.delta_t:g} t, Bcl = {v.B_cl:g} m, 1 + ncg = {loads['n1']:.3f}; Mtb = {loads['Mtb']:.0f} kN-m; SMt = {SMt_cm2m:.1f} cm2-m;  "
                            f"sigma_t = {st:.1f} N/mm2; sigma_a = 0.66 x {mat.sigma_ya:.1f} = {allow['sigma_a']:.1f}"),
        PlateResult("cross structure", "transverse shear stress", "3-2-1/3.5.3, 3-2-A2/1", tq, allow["tau_a"], "N/mm2",
                    {"Qt": loads["Qt"], "At": At_cm2},
                    formula="tau = 10 Qt / At  [N/mm2]; Qt = K1 Delta (1 + ncg), K1 = 2.5; allowable tau_a = 0.38 sigma_y. 'Required' = working stress, 'Provided' = allowable",
                    working=f"Qt = {loads['Qt']:.0f} kN; At = {At_cm2:.1f} cm2;  tau = {tq:.1f} N/mm2; tau_a = 0.38 x {mat.sigma_ya:.1f} = {allow['tau_a']:.1f}"),
    ]
    return res, {**loads, **{"sigma_t": st, "tau_t": tq, "SMt": SMt_cm2m, "At": At_cm2, "allow": allow}}


def torsion_elements(Mtt_kNm: float, elems: list[dict], mat: AluminumMaterial) -> tuple[list[PlateResult], dict]:
    """3-2-A2/1 to 5.7: distribution of the pitch connecting moment Mtt over the cross-structure elements.

    elems: [{name, x_m (from the FP), span_m, I_cm4, SM_cm3, Aw_cm2, E_Nmm2 (optional)}]. Stresses in N/mm2."""
    if not elems:
        raise ValueError("no cross-structure elements given")
    ks, xs = [], []
    for e in elems:
        for k in ("x_m", "span_m", "I_cm4", "SM_cm3", "Aw_cm2"):
            if k not in e:
                raise ValueError(f"cross-structure element '{e.get('name', '?')}': '{k}' is required")
        E_kNm2 = float(e.get("E_Nmm2", E_ALUMINUM)) * 1000.0  # N/mm2 -> kN/m2
        I_m4 = e["I_cm4"] * 1e-8
        ks.append(12000.0 * E_kNm2 * I_m4 / e["span_m"] ** 3)  # N/m
        xs.append(e["x_m"])
    Lc = sum(k * x for k, x in zip(ks, xs)) / sum(ks)
    denom = sum(k * (x - Lc) ** 2 for k, x in zip(ks, xs))
    if denom <= 0:
        raise ValueError("torsion distribution is undefined: all elements lie at the centre of rotation (give at least two distinct x positions)")
    allow = HG.catamaran_allowables(mat)
    res, rows = [], []
    for e, k, x in zip(elems, ks, xs):
        xc = x - Lc
        delta = 1000.0 * Mtt_kNm * xc / denom  # m
        Pn = abs(delta) * k  # N
        BM = Pn * e["span_m"] / 2.0  # N-m
        sig = BM / e["SM_cm3"]  # N/mm2
        tau = Pn / (100.0 * e["Aw_cm2"])  # N/mm2
        name = e.get("name", f"element at x = {x:g} m")
        rows.append({"name": name, "x_m": x, "xc_m": xc, "span_m": e["span_m"], "k_Nm": k, "delta_mm": abs(delta) * 1000.0,
                     "P_N": Pn, "BM_Nm": BM, "sigma": sig, "tau": tau, "SM_cm3": e["SM_cm3"], "Aw_cm2": e["Aw_cm2"]})
        res.append(PlateResult("cross structure", f"torsional bending stress ({name})", "3-2-A2/5.5", sig, allow["sigma_ab"], "N/mm2",
                               {"P": Pn, "BM": BM},
                               formula="ki = 12000 Ei Ii / Li^3; Lc = Sum(ki xi)/Sum(ki); delta_i = 1000 Mtt xci / Sum(ki xci^2) [m]; Pi = delta_i ki; BMi = Pi Li / 2; sigma_i = BMi / SMi [N/mm2]; allowable sigma_ab = 0.75 sigma_y",
                               working=f"x = {x:g} m, Lc = {Lc:.3f} m, xc = {xc:.3f} m; ki = {k:.4g} N/m; delta = {abs(delta) * 1000:.2f} mm; P = {Pn:.0f} N; "
                                       f"BM = {BM:.0f} N-m; SM = {e['SM_cm3']:g} cm3;  sigma = {sig:.1f} N/mm2 vs {allow['sigma_ab']:.1f}"))
        res.append(PlateResult("cross structure", f"torsional shear stress ({name})", "3-2-A2/5.7", tau, allow["tau_a"], "N/mm2",
                               {"P": Pn},
                               formula="tau_i = Pi / (100 Awi)  [N/mm2], Awi in cm2; allowable tau_a = 0.38 sigma_y",
                               working=f"P = {Pn:.0f} N, Aw = {e['Aw_cm2']:g} cm2;  tau = {tau:.1f} N/mm2 vs {allow['tau_a']:.1f}"))
    return res, {"Lc_m": Lc, "Mtt": Mtt_kNm, "rows": rows, "allow": allow, "sum_k_xc2": denom}
