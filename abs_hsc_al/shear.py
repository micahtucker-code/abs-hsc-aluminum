"""Hull girder shear (3-2-1/1.9) and multi-hull cross-structure global loads (3-2-1/3.3, 3-2-1/3.5, 3-2-A2).

Units follow the Rule text. SI: forces kN, moments kN-m, section data cm / cm2 / cm3 / cm4, stresses kN/cm2 for
the longitudinal shear check and N/mm2 for the cross-structure checks. US: Ltf, Ltf-ft, in / in2 / in3 / in4,
Ltf/in2 for the longitudinal shear check; ft-lbf, lbf, and psi for the cross structure (3-2-A2 US equations).
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
    u = v.units
    return {"Fwp": HG.wave_shear(v.L, v.B, Cb, F1, True, u), "Fwn": HG.wave_shear(v.L, v.B, Cb, F2, False, u),
            "Fslp": HG.slam_shear(v.delta_t, n, F1, u), "Fsln": -HG.slam_shear(v.delta_t, n, F2, u), "1+ncg": n}


def check_hull_shear(v: P.Vessel, mat: AluminumMaterial, Cb: float, I_cm4: float, m_cm3: float,
                     web_t_mm: float, stations: list[dict], combined: bool = True,
                     geometry_note: str = "") -> tuple[list[PlateResult], list[dict]]:
    """3-2-1/1.9.4. fs = F m / (Sum(t) I), with Sum(t) = 2 ts for the usual two side shells, against 11.0/Q kN/cm2.

    stations: [{name, x_over_L, F1, F2, Fsw_kN (optional)}]. Returns (results, per-station detail rows)."""
    U = mat.U
    us = U.name == "US"
    allow = HG.shear_allowable(mat)
    tcm = web_t_mm if us else web_t_mm / 10.0  # ts in cm (SI) or in. (US)
    fu, su, mu, d3, d4 = U.force, U.shear_hg, U.moment, U.mod, U.inertia
    dp = 4 if us else 3
    res: list[PlateResult] = []
    rows: list[dict] = []
    cb = HG.Cb_used(v.L, Cb, v.units)
    for st in stations:
        name = st.get("name") or f"x/L {st['x_over_L']:g}"
        for k in ("F1", "F2"):
            if k not in st:
                raise ValueError(f"hull shear station '{name}': {k} (distribution factor from the Rule figure) is required")
        fsw = float(st.get("Fsw_kN", 0.0))
        f = shear_forces(v, cb, st["F1"], st["F2"])
        k_fs = m_cm3 / (tcm * I_cm4)  # kN/cm2 per kN  (Ltf/in2 per Ltf for US)
        c1 = max(abs(fsw + f["Fwp"]), abs(fsw + f["Fwn"]))
        c2 = max(abs(f["Fslp"]), abs(f["Fsln"]))
        c3 = max(abs(fsw + f["Fwp"] + f["Fslp"]), abs(fsw + f["Fwn"] + f["Fsln"]))
        row = {"name": name, "x_over_L": st.get("x_over_L"), "F1": st["F1"], "F2": st["F2"], "Fsw": fsw, **f,
               "F_sw_w": c1, "F_sl": c2, "F_sum": c3, "fs_sw_w": c1 * k_fs, "fs_sl": c2 * k_fs, "fs_sum": c3 * k_fs,
               "allow": allow, "Fsw_given": "Fsw_kN" in st}
        rows.append(row)
        common = (f"F1 = {st['F1']:g}, F2 = {st['F2']:g}; m = {m_cm3:.0f} {d3}, I = {I_cm4:.4g} {d4}, "
                  f"2ts = {web_t_mm:.{3 if us else 1}f} {U.small}; allowable {U.shear_allow_n:g}/Q = {allow:.{4 if us else 2}f} {su}")
        res.append(PlateResult("hull girder", f"shear stress Fsw+Fw ({name})", "3-2-1/1.9.4", row["fs_sw_w"], allow, su,
                               {"F": c1}, formula=f"fs = (Fsw + Fw) m / (2 ts I)  [{su}]; Fw = Fwp = +{U.k_wave:g} F1 C1 L B (Cb + 0.7) 1e-2 or Fwn = -{U.k_wave:g} F2 C1 L B (Cb + 0.7) 1e-2. 'Required' = working stress, 'Provided' = allowable {U.shear_allow_n:g}/Q",
                               working=f"Fsw = {fsw:.0f}, Fwp = {f['Fwp']:.0f}, Fwn = {f['Fwn']:.0f} {fu}; governing |Fsw + Fw| = {c1:.0f} {fu}; {common};  fs = {row['fs_sw_w']:.{dp}f} {su}"))
        res.append(PlateResult("hull girder", f"shear stress Fsl ({name})", "3-2-1/1.9.4", row["fs_sl"], allow, su,
                               {"F": c2}, formula=f"fs = Fsl m / (2 ts I)  [{su}]; Fsl = C4 F Delta (ncg + 1), C4 = {U.C4:g}, F = F1 (positive) or F2 (negative). 'Required' = working stress, 'Provided' = allowable {U.shear_allow_n:g}/Q",
                               working=f"Delta = {v.delta_t:g} {'LT' if us else 't'}, (1 + ncg) = {f['1+ncg']:.3f}; Fsl+ = {f['Fslp']:.0f}, Fsl- = {f['Fsln']:.0f} {fu}; {common};  fs = {row['fs_sl']:.{dp}f} {su}"))
        if combined:
            res.append(PlateResult("hull girder", f"shear stress Fsw+Fw+Fsl ({name})", "3-2-1/1.9.1", row["fs_sum"], allow, su,
                                   {"F": c3}, formula=f"fs = |Fsw + Fw + Fsl| m / (2 ts I)  (maximum algebraic sum, 1.9.1 reading). 'Required' = working stress, 'Provided' = allowable {U.shear_allow_n:g}/Q",
                                   working=f"|Fsw + Fw + Fsl| = {c3:.0f} {fu}; {common};  fs = {row['fs_sum']:.{dp}f} {su}"))
    return res, rows


def cross_structure_checks(v: P.Vessel, mat: AluminumMaterial, SMt_cm2m: float, At_cm2: float) -> tuple[list[PlateResult], dict]:
    """3-2-1/3.3 loads with the 3-2-1/3.5.3 allowables; 3-2-A2/1 transverse bending and shear stress.

    SI: sigma_t = 10 Mtb / SMt, tau = 10 Qt / At (N/mm2). US: sigma_t = Mtb / SMt, tau = Qt / At (psi), SMt in in2-ft."""
    U = mat.U
    us = U.name == "US"
    loads = HG.catamaran_loads(v.delta_t, v.B_cl, v.L, P.ncg(v), v.units)
    allow = HG.catamaran_allowables(mat)
    c = 1.0 if us else 10.0
    st = c * loads["Mtb"] / SMt_cm2m
    tq = c * loads["Qt"] / At_cm2
    ss, mu, fu = U.sig, ("ft-lbf" if us else "kN-m"), ("lbf" if us else "kN")
    dd = 0 if us else 1
    cpre = "" if us else "10 "
    res = [
        PlateResult("cross structure", "transverse bending stress", "3-2-1/3.5.3, 3-2-A2/1", st, allow["sigma_a"], ss,
                    {"Mtb": loads["Mtb"], "SMt": SMt_cm2m},
                    formula=f"sigma_t = {cpre}Mtb / SMt  [{ss}]; Mtb = K1 Delta Bcl (1 + ncg), K1 = {U.K1_cat:g}; allowable sigma_a = 0.66 sigma_y. 'Required' = working stress, 'Provided' = allowable",
                    working=f"Delta = {loads['Delta'] if us else v.delta_t:g} {'lb' if us else 't'}, Bcl = {v.B_cl:g} {U.big}, 1 + ncg = {loads['n1']:.3f}; Mtb = {loads['Mtb']:.0f} {mu}; SMt = {SMt_cm2m:.1f} {U.sm_hg};  "
                            f"sigma_t = {st:.{dd}f} {ss}; sigma_a = 0.66 x {mat.sigma_ya:.{dd}f} = {allow['sigma_a']:.{dd}f}"),
        PlateResult("cross structure", "transverse shear stress", "3-2-1/3.5.3, 3-2-A2/1", tq, allow["tau_a"], ss,
                    {"Qt": loads["Qt"], "At": At_cm2},
                    formula=f"tau = {cpre}Qt / At  [{ss}]; Qt = K1 Delta (1 + ncg), K1 = {U.K1_cat:g}; allowable tau_a = 0.38 sigma_y. 'Required' = working stress, 'Provided' = allowable",
                    working=f"Qt = {loads['Qt']:.0f} {fu}; At = {At_cm2:.1f} {U.area};  tau = {tq:.{dd}f} {ss}; tau_a = 0.38 x {mat.sigma_ya:.{dd}f} = {allow['tau_a']:.{dd}f}"),
    ]
    return res, {**loads, **{"sigma_t": st, "tau_t": tq, "SMt": SMt_cm2m, "At": At_cm2, "allow": allow}}


def torsion_elements(Mtt_kNm: float, elems: list[dict], mat: AluminumMaterial) -> tuple[list[PlateResult], dict]:
    """3-2-A2/1 to 5.7: distribution of the pitch connecting moment Mtt over the cross-structure elements.

    elems: [{name, x_m (from the FP), span_m, I_cm4, SM_cm3, Aw_cm2, E_Nmm2 (optional)}].
    SI: m, cm4, cm3, cm2, N/mm2 -> stresses in N/mm2, Mtt in kN-m.
    US: ft, in4, in3, in2, psi -> stresses in psi, Mtt in ft-lbf; the Rule's US equations work in inches and lbf:
    ki = 12 Ei Ii / Li^3 (lbf/in), delta = 12 Mtt xc / Sum(ki xc^2) (in), P = delta k, BM = P L / 2, sigma = BM / SM,
    tau = P / Aw (the result keys k_Nm, delta_mm, P_N, BM_Nm then hold lbf/in, in, lbf, in-lbf)."""
    if not elems:
        raise ValueError("no cross-structure elements given")
    U = mat.U
    us = U.name == "US"
    ks, xs, ls = [], [], []
    for e in elems:
        for k in ("x_m", "span_m", "I_cm4", "SM_cm3", "Aw_cm2"):
            if k not in e:
                raise ValueError(f"cross-structure element '{e.get('name', '?')}': '{k}' is required")
        E = float(e.get("E_Nmm2", e.get("E", U.E if us else E_ALUMINUM)))
        if us:
            L_in = e["span_m"] * 12.0
            ks.append(12.0 * E * e["I_cm4"] / L_in ** 3)  # lbf/in
            xs.append(e["x_m"] * 12.0)  # in
            ls.append(L_in)
        else:
            E_kNm2 = E * 1000.0  # N/mm2 -> kN/m2
            I_m4 = e["I_cm4"] * 1e-8
            ks.append(12000.0 * E_kNm2 * I_m4 / e["span_m"] ** 3)  # N/m
            xs.append(e["x_m"])
            ls.append(e["span_m"])
    Lc = sum(k * x for k, x in zip(ks, xs)) / sum(ks)
    denom = sum(k * (x - Lc) ** 2 for k, x in zip(ks, xs))
    if denom <= 0:
        raise ValueError("torsion distribution is undefined: all elements lie at the centre of rotation (give at least two distinct x positions)")
    allow = HG.catamaran_allowables(mat)
    res, rows = [], []
    ss = U.sig
    dd = 0 if us else 1
    big = U.big
    for e, k, x, Ls in zip(elems, ks, xs, ls):
        xc = x - Lc
        if us:
            delta = 12.0 * Mtt_kNm * xc / denom  # in (Mtt in ft-lbf)
            Pn = abs(delta) * k  # lbf
            BM = Pn * Ls / 2.0  # in-lbf
            sig = BM / e["SM_cm3"]  # psi
            tau = Pn / e["Aw_cm2"]  # psi
            dmm = abs(delta)
        else:
            delta = 1000.0 * Mtt_kNm * xc / denom  # m
            Pn = abs(delta) * k  # N
            BM = Pn * Ls / 2.0  # N-m
            sig = BM / e["SM_cm3"]  # N/mm2
            tau = Pn / (100.0 * e["Aw_cm2"])  # N/mm2
            dmm = abs(delta) * 1000.0
        name = e.get("name", f"element at x = {e['x_m']:g} {big}")
        kscale = 1.0 / 12.0 if us else 1.0  # report x, xc in ft for US
        rows.append({"name": name, "x_m": e["x_m"], "xc_m": xc * kscale, "span_m": e["span_m"], "k_Nm": k, "delta_mm": dmm,
                     "P_N": Pn, "BM_Nm": BM, "sigma": sig, "tau": tau, "SM_cm3": e["SM_cm3"], "Aw_cm2": e["Aw_cm2"]})
        if us:
            f1 = ("ki = 12 Ei Ii / Li^3 [lbf/in, Li in in.]; Lc = Sum(ki xi)/Sum(ki); delta_i = 12 Mtt xci / Sum(ki xci^2) [in.]; "
                  f"Pi = delta_i ki; BMi = Pi Li / 2; sigma_i = BMi / SMi [psi]; allowable sigma_ab = 0.75 sigma_y")
            w1 = (f"x = {e['x_m']:g} ft, Lc = {Lc / 12:.3f} ft, xc = {xc / 12:.3f} ft; ki = {k:.4g} lbf/in; delta = {dmm:.4f} in; P = {Pn:.0f} lbf; "
                  f"BM = {BM:.0f} in-lbf; SM = {e['SM_cm3']:g} in3;  sigma = {sig:.0f} psi vs {allow['sigma_ab']:.0f}")
            f2 = "tau_i = Pi / Awi  [psi], Awi in in2; allowable tau_a = 0.38 sigma_y"
            w2 = f"P = {Pn:.0f} lbf, Aw = {e['Aw_cm2']:g} in2;  tau = {tau:.0f} psi vs {allow['tau_a']:.0f}"
        else:
            f1 = ("ki = 12000 Ei Ii / Li^3; Lc = Sum(ki xi)/Sum(ki); delta_i = 1000 Mtt xci / Sum(ki xci^2) [m]; Pi = delta_i ki; "
                  "BMi = Pi Li / 2; sigma_i = BMi / SMi [N/mm2]; allowable sigma_ab = 0.75 sigma_y")
            w1 = (f"x = {x:g} m, Lc = {Lc:.3f} m, xc = {xc:.3f} m; ki = {k:.4g} N/m; delta = {dmm:.2f} mm; P = {Pn:.0f} N; "
                  f"BM = {BM:.0f} N-m; SM = {e['SM_cm3']:g} cm3;  sigma = {sig:.1f} N/mm2 vs {allow['sigma_ab']:.1f}")
            f2 = "tau_i = Pi / (100 Awi)  [N/mm2], Awi in cm2; allowable tau_a = 0.38 sigma_y"
            w2 = f"P = {Pn:.0f} N, Aw = {e['Aw_cm2']:g} cm2;  tau = {tau:.1f} N/mm2 vs {allow['tau_a']:.1f}"
        res.append(PlateResult("cross structure", f"torsional bending stress ({name})", "3-2-A2/5.5", sig, allow["sigma_ab"], ss,
                               {"P": Pn, "BM": BM}, formula=f1, working=w1))
        res.append(PlateResult("cross structure", f"torsional shear stress ({name})", "3-2-A2/5.7", tau, allow["tau_a"], ss,
                               {"P": Pn}, formula=f2, working=w2))
    return res, {"Lc_m": Lc / 12.0 if us else Lc, "Mtt": Mtt_kNm, "rows": rows, "allow": allow, "sum_k_xc2": denom}
