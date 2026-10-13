import math, unittest, json
from abs_hsc_al import plating as PL, stiffeners as ST, hullgirder as HG, pressures as P
from abs_hsc_al.materials import AluminumMaterial
from abs_hsc_al.figures import Factors, Curve
from abs_hsc_al.report import run

M = AluminumMaterial("test", 200, 275, 120, 215)  # hand-checkable, not an ABS alloy
V = P.Vessel(L=24, Lw=22.5, B=6, Bw=5.2, D=3, d=1.1, delta_t=60, V=30, service="coastal")


class Material(unittest.TestCase):
    def test_factors(self):
        self.assertAlmostEqual(M.sigma_y_design, 120.0)            # min(120, 0.7*215=150.5)
        self.assertAlmostEqual(M.sigma_ya, 150.5)                  # min(200,150.5)
        self.assertAlmostEqual(M.q_a, 115 / 150.5)
        self.assertAlmostEqual(M.Q, max(0.9 + 115 / 150.5, 635 / (150.5 + 215)))
        self.assertAlmostEqual(M.tau_yw, 120 / math.sqrt(3))

    def test_welded_over_unwelded_rejected(self):
        with self.assertRaises(ValueError):
            AluminumMaterial("x", 100, 200, 150, 200)


class Plating(unittest.TestCase):
    def test_k_table(self):
        self.assertAlmostEqual(PL.k_factor(1.0), 0.308)
        self.assertAlmostEqual(PL.k_factor(1.25), (0.383 + 0.412) / 2)
        self.assertAlmostEqual(PL.k_factor(2.0), 0.497)
        self.assertAlmostEqual(PL.k_factor(3.0), 0.500)

    def test_thickness(self):
        # s=400, l=1200 (ratio 3 -> k=0.5), p=50, sa=0.9*120=108
        t = PL.required_thickness_lateral(50, 400, 1200, 108)
        self.assertAlmostEqual(t, 400 * math.sqrt(50 * 0.5 / (1000 * 108)))

    def test_min_thickness_and_floor(self):
        self.assertAlmostEqual(PL.min_thickness(24, M, "bottom"), max(0.7 * math.sqrt(24 * M.q_a) + 1, 4.0))
        self.assertGreaterEqual(PL.min_thickness(1, M, "side"), 3.5)

    def test_slam_stress_outside_midship(self):
        self.assertAlmostEqual(PL.design_stress(M, "bottom_slam", True), 120.0)
        self.assertAlmostEqual(PL.design_stress(M, "bottom_slam"), 108.0)

    def test_buckling(self):
        self.assertAlmostEqual(PL.critical_buckling(40, 100), 40)
        self.assertAlmostEqual(PL.critical_buckling(100, 100), 100 * (1 - 100 / 400))
        self.assertAlmostEqual(PL.shear_m2(1.0), 9.34)
        self.assertAlmostEqual(PL.buckling_m1(2, "longitudinal", sigma_ratio=1 / 3), 5.8)


class Stiffeners(unittest.TestCase):
    def test_sm_and_i(self):
        self.assertAlmostEqual(ST.required_SM(50, 0.4, 1.2, 78), 83.3 * 50 * 0.4 * 1.44 / 78)
        self.assertAlmostEqual(ST.required_I(50, 0.4, 1.2), 260 * 50 * 0.4 * 1.728 / (0.0021 * 69000))
        self.assertAlmostEqual(ST.required_I(50, 0.4, 1.2, deck=True), 260 * 50 * 0.4 * 1.728 / (0.0018 * 69000))

    def test_section_flat_bar_plus_plate(self):
        s = ST.Section("flat", hw=100, tw=10, t_plate=10, b_eff=100)
        pr = s.properties()
        # two 100x10 rectangles stacked: A=2000 mm2, yb=10 mm, I = 2*(100*1000/12 ... ) by hand:
        I = 100 * 10 ** 3 / 12 + 1000 * 5 ** 0 * 0 + (10 * 100 ** 3 / 12) + 1000 * (60 - 35) ** 2 + 1000 * (35 - 5) ** 2 - 0
        yb = (1000 * 5 + 1000 * 60) / 2000
        I = 100 * 10 ** 3 / 12 + 1000 * (yb - 5) ** 2 + 10 * 100 ** 3 / 12 + 1000 * (60 - yb) ** 2
        self.assertAlmostEqual(pr["A_cm2"], 20.0)
        self.assertAlmostEqual(pr["I_cm4"], I / 1e4)
        self.assertAlmostEqual(pr["SM_cm3"], I / max(yb, 110 - yb) / 1e3)

    def test_effective_width(self):
        self.assertEqual(ST.effective_plate_width("secondary", 400, 5), 300)
        self.assertEqual(ST.effective_plate_width("primary", 2000, 5, 1.0), 330)
        self.assertEqual(ST.effective_plate_width("primary", 2000, 5, 4.0), 750)

    def test_web_thickness(self):
        t, t1, t2 = ST.required_web_thickness(100, 50, 0.4, 1.2, M)
        self.assertAlmostEqual(t1, 2 * math.sqrt(200 / 127.6))
        self.assertAlmostEqual(t2, 1000 * 50 * 0.4 * 1.2 / (2 * 100 * 0.5 * 120 / math.sqrt(3)))

    def test_column(self):
        sE = 69000 * 100 / (1000 * 10 * 1.0)  # 690 > 0.5*200, so Johnson-type reduction applies
        self.assertAlmostEqual(ST.column_buckling(M, 100, 10, 1.0), 200 * (1 - 200 / (4 * sE)))


class HullGirder(unittest.TestCase):
    def test_c1(self):
        self.assertAlmostEqual(HG.C1(24), 0.044 * 24 + 3.75)
        self.assertAlmostEqual(HG.C1(100), 10.75 - (200 / 100) ** 1.5)

    def test_cb_floor(self):
        self.assertEqual(HG.Cb_min(30), 0.45); self.assertEqual(HG.Cb_min(70), 0.60)
        self.assertAlmostEqual(HG.Cb_min(48), 0.525)

    def test_sm(self):
        k3 = min(0.7 + 0.3 * 30 / (2.36 * math.sqrt(24)), 1.3)  # uncapped 1.478 -> capped
        exp = 0.01 * HG.C1(24) * 576 * 6 * (0.45 + 0.7) * k3 * 0.9 * M.Q
        self.assertAlmostEqual(HG.SM_all_craft(24, 6, 0.3, 30, M), exp)

    def test_table1(self):
        self.assertEqual(HG.min_1_plus_ncg(100), 3); self.assertEqual(HG.min_1_plus_ncg(2000), 1)
        self.assertAlmostEqual(HG.min_1_plus_ncg(800), 1.5)

    def test_cat(self):
        c = HG.catamaran_loads(100, 8, 30, 2.0)
        self.assertAlmostEqual(c["Mtb"], 2.5 * 100 * 8 * 3.0)
        self.assertAlmostEqual(c["Qt"], 2.5 * 100 * 3.0)

    def test_61m_moments(self):
        v = P.Vessel(L=70, Lw=65, B=12, Bw=11, D=6, d=2.5, delta_t=1500, V=35, ncg_override=1.0)
        m = HG.moments_61m_plus(v, 0.65)
        c1 = HG.C1(70)
        self.assertAlmostEqual(m["Mws"], 110 * c1 * 4900 * 12 * 1.35 * 1e-3)
        self.assertAlmostEqual(m["Mwh"], 190 * c1 * 4900 * 12 * 0.65 * 1e-3)
        self.assertAlmostEqual(m["1+ncg"], 2.0)


class Pressures(unittest.TestCase):
    def test_ncg_caps(self):
        v = P.Vessel(L=24, Lw=22.5, B=6, Bw=5.2, D=3, d=1.1, delta_t=60, V=60, service="high-speed")
        self.assertLessEqual(P.ncg_formula(v), 6.0)

    def test_hydro(self):
        self.assertAlmostEqual(P.hydro_bottom(V), 9.8 * (0.64 * (0.0172 * 24 + 3.653) + 1.1))

    def test_slam_cg(self):
        exp = 0.1 * 60000 / (22.5 * 5.2) * (1 + P.ncg(V)) * 0.5
        self.assertAlmostEqual(P.bottom_slam_cg(V, 0.5), exp)

    def test_crewboat_h13(self):
        v = P.Vessel(L=24, Lw=22.5, B=6, Bw=5.2, D=3, d=1.1, delta_t=60, V=25, service="crewboat")
        self.assertEqual(v.h13, 3.35)

    def test_Hs(self):
        self.assertAlmostEqual(P.Hs(V), max(0.083 * 24 + 1.1, 3 + 1.22))
        v2 = P.Vessel(L=40, Lw=37, B=8, Bw=7, D=4, d=1.5, delta_t=200, V=30)
        self.assertAlmostEqual(P.Hs(v2), 0.64 * (0.0172 * 40 + 3.653) + 1.5)

    def test_figure_error_is_clear(self):
        with self.assertRaises(ValueError) as c:
            Factors().resolve("FD", 0.1, None)
        self.assertIn("FD", str(c.exception))

    def test_curve(self):
        c = Curve([0, 1], [0, 10]); self.assertEqual(c(0.5), 5); self.assertEqual(c(2), 10)


class Stations(unittest.TestCase):
    V24 = P.Vessel(L=24, Lw=22.5, B=6, Bw=5.2, D=3, d=1.1, delta_t=60, V=30, service="coastal")

    def rows(self):
        return {"rows": [
            {"name": "AP", "x_over_L": 0.0, "beta_bx": 20, "Fv": 0.5},
            {"name": "MID", "x_over_L": 0.5, "beta_bx": 15, "Fv": 0.8},
            {"name": "FWD", "x_over_L": 0.9, "beta_bx": 10, "beta_sx": 40, "Kv": 1.4, "Fv": 1.0}]}

    def test_table_values(self):
        from abs_hsc_al import stations as ST
        st = ST.parse(self.rows(), self.V24)
        tb = ST.table(st, self.V24, FD=0.6)
        base = 0.1 * 60000 / (22.5 * 5.2)
        n = P.ncg(self.V24)
        self.assertAlmostEqual(tb[1]["x_m"], 12.0)
        self.assertAlmostEqual(tb[1]["pbxx"], base * (1 + n) * 0.6 * 0.8)        # L < 61 m: (1+ncg) FD Fv
        self.assertAlmostEqual(tb[2]["pss"], base * (1 + n * 1.4) * (70 - 40) / (70 - 15) * 0.6)
        self.assertIsNone(tb[0]["pss"])                                           # no side deadrise given

    def test_missing_factor_is_reported_not_guessed(self):
        from abs_hsc_al import stations as ST
        st = ST.parse({"rows": [{"name": "A", "x_over_L": 0.2}]}, self.V24)
        r = ST.table(st, self.V24, 0.5)[0]
        self.assertIsNone(r["pbxx"]); self.assertTrue(r["notes"])

    def test_bad_inputs(self):
        from abs_hsc_al import stations as ST
        with self.assertRaises(ValueError):
            ST.parse({"rows": [{"name": "A", "x_over_L": 1.5}]}, self.V24)
        with self.assertRaises(ValueError):
            ST.parse({"rows": [{"name": "A", "x_over_L": .1}, {"name": "A", "x_over_L": .2}]}, self.V24)

    def test_panel_uses_station(self):
        d = {"vessel": {"L": 24, "Lw": 22.5, "B": 6, "Bw": 5.2, "D": 3, "d": 1.1, "delta_t": 60, "V": 30, "service": "coastal"},
             "material": {"alloy": "5083-H116", "product": "plate", "thickness_mm": 8},
             "stations": dict(self.rows(), FD=0.6),
             "plates": [{"id": "bottom MID", "location": "bottom", "s_mm": 400, "l_mm": 1200, "t_mm": 8,
                         "loads": {"bottom_slam": {"calc": "bottom_slam_xx", "station": "MID", "FD": 0.6}}}]}
        rep = run(d)
        base = 0.1 * 60000 / (22.5 * 5.2)
        self.assertAlmostEqual(rep["pressures"]["bottom MID:bottom_slam"], base * (1 + P.ncg(self.V24)) * 0.6 * 0.8)
        self.assertEqual(rep["pressure_log"][0]["factors"]["station"], "MID")
        self.assertEqual(len(rep["station_table"]["rows"]), 3)
        d["plates"][0]["loads"]["bottom_slam"]["station"] = "NOPE"
        with self.assertRaises(ValueError):
            run(d)


class OperatingLimits(unittest.TestCase):
    def test_speed_reduces_with_wave_height_at_constant_ncg(self):
        from abs_hsc_al.report import operating_limits
        v = P.Vessel(L=24, Lw=22.5, B=6, Bw=5.2, D=3, d=1.1, delta_t=60, V=30, service="coastal")
        ol = {o["h13"]: o["V"] for o in operating_limits(v)}
        self.assertEqual(ol[1.0], 30)                       # below design h1/3: capped at design speed
        self.assertAlmostEqual(ol[2.5], 30)                 # at design h1/3
        k0, k4 = 12 * 2.5 / 5.2 + 1, 12 * 4.0 / 5.2 + 1
        self.assertAlmostEqual(ol[4.0], 30 * math.sqrt(k0 / k4))
        # acceleration at (h=4, V=ol) equals design acceleration
        v2 = P.Vessel(L=24, Lw=22.5, B=6, Bw=5.2, D=3, d=1.1, delta_t=60, V=ol[4.0], service="high-speed")
        raw = lambda x: P.N2 * (12 * x.h13 / x.NhBw + 1) * x.tau * (50 - x.beta_cg) * x.V ** 2 * x.NhBw ** 2 / x.delta_kg
        self.assertAlmostEqual(raw(v2), raw(v), places=6)            # uncapped acceleration held constant
        self.assertLessEqual(P.ncg_formula(v2), P.ncg_formula(v) + 1e-9)  # and the speed-based cap only falls with V

    def test_override_gives_no_table(self):
        from abs_hsc_al.report import operating_limits
        v = P.Vessel(L=24, Lw=22.5, B=6, Bw=5.2, D=3, d=1.1, delta_t=60, V=30, ncg_override=2.0)
        self.assertEqual(operating_limits(v), [])


class Alloys(unittest.TestCase):
    def test_lookup_5083_h116(self):
        from abs_hsc_al.alloys import lookup
        m = AluminumMaterial.from_dict(lookup("5083-H116", "plate", 8))
        self.assertEqual((m.sigma_y_unwelded, m.sigma_u_unwelded, m.sigma_y_welded, m.sigma_u_welded), (215, 305, 165, 276))
        self.assertAlmostEqual(m.sigma_y_design, 165)            # min(165, 0.7*276=193.2)
        self.assertAlmostEqual(m.sigma_ya, 193.2)                # min(215, 193.2)
        self.assertAlmostEqual(m.Q, max(0.9 + 115 / 193.2, 635 / (193.2 + 276)))

    def test_thickness_bands(self):
        from abs_hsc_al.alloys import lookup
        self.assertEqual(lookup("5083-H116", "plate", 50)["sigma_y_unwelded"], 200)
        self.assertEqual(lookup("6061-T6", "plate", 12)["sigma_y_welded"], 103)
        self.assertEqual(lookup("6061-T6", "plate", 8)["sigma_y_welded"], 138)
        with self.assertRaises(ValueError):
            lookup("5083-H116", "plate", 1.0)
        with self.assertRaises(ValueError):
            lookup("6082-T6", "extrusion", 8)

    def test_all_rows_valid(self):
        from abs_hsc_al import alloys
        for a, p in alloys.list_alloys():
            for t in (3.5, 10, 45):
                try:
                    AluminumMaterial.from_dict(alloys.lookup(a, p, t))
                except ValueError as e:
                    self.assertIn("outside", str(e))

    def test_from_dict_alloy_key(self):
        m = AluminumMaterial.from_dict({"alloy": "5086-H116", "product": "plate", "thickness_mm": 6})
        self.assertEqual(m.sigma_y_welded, 131)


class EndToEnd(unittest.TestCase):
    def test_example(self):
        with open("inputs/example_vessel.json") as f:
            rep = run(json.load(f))
        self.assertTrue(len(rep["results"]) >= 10)
        by = {(r["id"], r["kind"]): r for r in rep["results"]}
        p = rep["pressures"]["bottom plate:bottom_slam"]
        self.assertAlmostEqual(by[("bottom plate", "lateral (bottom_slam)")]["required"],
                               400 * math.sqrt(p * PL.k_factor(3) / (1000 * 0.9 * 165)))


if __name__ == "__main__":
    unittest.main()
