import json, math, unittest

from abs_hsc_al import hullgirder as HG, pressures as P, shear as SH
from abs_hsc_al.materials import AluminumMaterial
from abs_hsc_al.report import run


def _box():
    """1000 x 600 mm hollow box, t = 10 mm (I = 216017 cm4, m above N.A. = 3900 cm3)."""
    return {"members": [
        {"name": "top", "y1": -500, "z1": 600, "y2": 500, "z2": 600, "t_mm": 10},
        {"name": "bottom", "y1": -500, "z1": 0, "y2": 500, "z2": 0, "t_mm": 10},
        {"name": "side P", "y1": -500, "z1": 0, "y2": -500, "z2": 600, "t_mm": 10},
        {"name": "side S", "y1": 500, "z1": 0, "y2": 500, "z2": 600, "t_mm": 10}]}

M = AluminumMaterial("test", 200, 275, 120, 215)
V = P.Vessel(L=70, Lw=65, B=10, Bw=4, D=5, d=1.5, delta_t=300, V=25, service="coastal", n_hulls=2, B_cl=6.0)


def _example():
    with open("inputs/example_vessel.json", encoding="utf-8") as f:
        return json.load(f)


class HullShear(unittest.TestCase):
    def test_wave_and_slam_forces(self):
        f = SH.shear_forces(V, 0.6, 0.7, 0.5)
        c1 = HG.C1(70)
        self.assertAlmostEqual(f["Fwp"], 30 * 0.7 * c1 * 70 * 10 * 1.3 * 1e-2)
        self.assertAlmostEqual(f["Fwn"], -30 * 0.5 * c1 * 70 * 10 * 1.3 * 1e-2)
        n = 1 + P.ncg(V)
        self.assertAlmostEqual(f["Fslp"], 4.9 * 0.7 * 300 * n)
        self.assertAlmostEqual(f["Fsln"], -4.9 * 0.5 * 300 * n)

    def test_stress_hand_calc(self):
        I, m, t = 216016.6667, 3900.0, 20.0  # box section of tests.test_section
        res, rows = SH.check_hull_shear(V, M, 0.6, I, m, t, [{"name": "S1", "x_over_L": 0.5, "F1": 0.7, "F2": 0.5, "Fsw_kN": 100}])
        f = SH.shear_forces(V, 0.6, 0.7, 0.5)
        want = max(abs(100 + f["Fwp"]), abs(100 + f["Fwn"])) * m / (2.0 * I)
        self.assertAlmostEqual(rows[0]["fs_sw_w"], want, places=9)
        self.assertAlmostEqual(res[0].provided, 11.0 / M.Q)
        self.assertEqual(len(res), 3)  # Fsw+Fw, Fsl, combined (1.9.1)
        self.assertEqual(len(SH.check_hull_shear(V, M, 0.6, I, m, t, [{"x_over_L": 0.5, "F1": 1, "F2": 1}], combined=False)[0]), 2)

    def test_missing_factor_is_an_error(self):
        with self.assertRaises(ValueError):
            SH.check_hull_shear(V, M, 0.6, 1e5, 1e3, 20, [{"name": "x", "x_over_L": 0.5, "F1": 0.7}])


class CrossStructure(unittest.TestCase):
    def test_loads_and_stresses(self):
        res, info = SH.cross_structure_checks(V, M, 500.0, 200.0)
        n1 = max(1 + P.ncg(V), HG.min_1_plus_ncg(300))
        self.assertAlmostEqual(info["Mtb"], 2.5 * 300 * 6 * n1)
        self.assertAlmostEqual(info["sigma_t"], 10 * info["Mtb"] / 500)
        self.assertAlmostEqual(info["tau_t"], 10 * info["Qt"] / 200)
        self.assertAlmostEqual(res[0].provided, 0.66 * M.sigma_ya)
        self.assertAlmostEqual(res[1].provided, 0.38 * M.sigma_ya)

    def test_torsion_equilibrium(self):
        els = [{"name": "A", "x_m": 1.0, "span_m": 2.0, "I_cm4": 5e4, "SM_cm3": 800, "Aw_cm2": 40},
               {"name": "B", "x_m": 3.0, "span_m": 2.0, "I_cm4": 5e4, "SM_cm3": 800, "Aw_cm2": 40}]
        res, t = SH.torsion_elements(1000.0, els, M)
        self.assertAlmostEqual(t["Lc_m"], 2.0)
        self.assertAlmostEqual(t["rows"][0]["P_N"], 500 * 1000 * 1.0)  # 500 Mtt xc
        self.assertAlmostEqual(sum(r["P_N"] * abs(r["xc_m"]) for r in t["rows"]), 1000 * 1000.0)  # sum(P xc) = Mtt (N-m)
        self.assertAlmostEqual(t["rows"][0]["sigma"], t["rows"][0]["BM_Nm"] / 800)
        self.assertAlmostEqual(t["rows"][0]["tau"], t["rows"][0]["P_N"] / (100 * 40))

    def test_stiffer_element_takes_more_load(self):
        els = [{"x_m": 0, "span_m": 2, "I_cm4": 1e5, "SM_cm3": 1, "Aw_cm2": 1}, {"x_m": 4, "span_m": 2, "I_cm4": 3e5, "SM_cm3": 1, "Aw_cm2": 1}]
        _, t = SH.torsion_elements(100.0, els, M)
        self.assertGreater(t["Lc_m"], 2.0)  # centre of rotation moves to the stiffer element
        self.assertAlmostEqual(t["rows"][0]["P_N"], t["rows"][1]["P_N"])  # a pure couple: equal and opposite forces
        self.assertGreater(t["rows"][0]["delta_mm"], t["rows"][1]["delta_mm"])  # the softer element deflects more

    def test_single_position_rejected(self):
        with self.assertRaises(ValueError):
            SH.torsion_elements(1.0, [{"x_m": 1, "span_m": 2, "I_cm4": 1, "SM_cm3": 1, "Aw_cm2": 1}], M)


class EndToEnd(unittest.TestCase):
    def test_shear_from_section(self):
        d = _example()
        d["section"] = _box()
        d.pop("hull_girder", None)
        d["hull_shear"] = {"stations": [{"name": "0.25L", "x_over_L": 0.25, "F1": 0.6, "F2": 0.6, "Fsw_kN": 50}]}
        rep = run(d)
        rows = [r for r in rep["results"] if r["kind"].startswith("shear stress")]
        self.assertEqual(len(rows), 3)
        g = rep["global_loads"]
        self.assertAlmostEqual(g["shear"]["m_cm3"], rep["section"]["shear"]["m_cm3"])
        self.assertTrue(any("61 m" in n for n in g["notes"]))  # 24 m craft: shear not required by the Rule

    def test_shear_without_section_needs_inputs(self):
        d = _example()
        d.pop("section")
        d["hull_shear"] = {"stations": [{"x_over_L": 0.5, "F1": 1, "F2": 1}]}
        with self.assertRaises(ValueError):
            run(d)
        d["hull_shear"].update({"I_cm4": 216000, "m_cm3": 3900, "ts_mm": 10})
        rep = run(d)
        self.assertFalse(rep["global_loads"]["shear"]["from_section"])
        self.assertTrue(any("zero" in n for n in rep["global_loads"]["notes"]))

    def test_cross_structure_from_section_and_elements(self):
        d = _example()
        d["vessel"].update({"n_hulls": 2, "B_cl": 3.0})
        d["cross_structure"] = {"section": _box(), "elements": [
            {"name": "frame 1", "x_m": 5, "span_m": 2.5, "I_cm4": 2e4, "SM_cm3": 500, "Aw_cm2": 30},
            {"name": "frame 2", "x_m": 9, "span_m": 2.5, "I_cm4": 2e4, "SM_cm3": 500, "Aw_cm2": 30}]}
        rep = run(d)
        kinds = {r["kind"] for r in rep["results"] if r["id"] == "cross structure"}
        self.assertIn("transverse bending stress", kinds)
        self.assertTrue(any(k.startswith("torsional") for k in kinds))
        c = rep["global_loads"]["cross"]
        self.assertAlmostEqual(c["SMt"], min(c["section"]["SM_deck_cm3"], c["section"]["SM_bottom_cm3"]) / 100)
        self.assertAlmostEqual(c["At"], 120.0)  # two 600 x 10 mm webs

    def test_cross_structure_needs_multihull(self):
        d = _example()
        d["cross_structure"] = {"SMt_cm2m": 100, "At_cm2": 50}
        with self.assertRaises(ValueError):
            run(d)

    def test_multihull_loads_listed_without_check(self):
        d = _example()
        d["vessel"].update({"n_hulls": 2, "B_cl": 3.0})
        g = run(d)["global_loads"]
        self.assertFalse(g["cross"]["checked"])
        self.assertGreater(g["cross"]["Mtb"], 0)


if __name__ == "__main__":
    unittest.main()
