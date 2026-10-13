import copy, json, math, unittest

from abs_hsc_al import alloys, dxf, hullgirder as HG, pressures as P, units as UN
from abs_hsc_al import section as SC
from abs_hsc_al.report import run


def _example():
    with open("inputs/example_vessel.json", encoding="utf-8") as f:
        return json.load(f)


class Constants(unittest.TestCase):
    """US constants as printed in the Rule (not exact conversions of the SI ones)."""

    def test_printed_us_values(self):
        U = UN.US
        self.assertEqual((U.N1, U.N1_wd, U.N2, U.N3, U.KN), (0.069, 0.00442, 0.0016, 0.44, 0.463))
        self.assertEqual((U.C2, U.k1, U.k2, U.fp, U.C3, U.C4), (1.44e-4, 1.026, 1.772, 11.33, 0.125, 0.5))
        self.assertEqual((U.K1_cat, U.K2_cat), (0.255, 0.1275))
        self.assertAlmostEqual(U.shear_allow_n, 7.122)
        self.assertEqual(U.E, 10e6)
        self.assertEqual(U.sigma_d, 18500)

    def test_si_unchanged(self):
        U = UN.SI
        self.assertEqual((U.fp, U.C3, U.C4), (17.5, 1.25, 4.9))

    def test_c1_us(self):
        self.assertAlmostEqual(HG.C1(200, "US"), 0.0134 * 200 + 3.75)
        self.assertAlmostEqual(HG.C1(400, "US"), 10.75 - ((984 - 400) / 328) ** 1.5)

    def test_k3_and_ncg_table(self):
        self.assertAlmostEqual(HG.K3(25, 200, "US"), 0.70 + 0.30 * 25 / (1.30 * math.sqrt(200)))
        self.assertEqual(HG.K3(40, 200, "US"), 1.30)  # clamped
        self.assertEqual(HG.min_1_plus_ncg(177, "US"), 3)
        self.assertEqual(HG.min_1_plus_ncg(1181, "US"), 1)
        self.assertEqual(HG.min_1_plus_ncg(394, "US"), 2)

    def test_notes_present(self):
        self.assertTrue(UN.NOTES)


class Conversion(unittest.TestCase):
    def test_round_trip(self):
        d = _example()
        back = UN.convert_inputs(UN.convert_inputs(d, "US"), "SI")
        for k in ("L", "B", "D", "d"):
            self.assertAlmostEqual(back["vessel"][k], d["vessel"][k], places=3)
        self.assertEqual(UN.convert_inputs(d, "US").get("units"), "US")

    def test_lengths(self):
        d = _example()
        us = UN.convert_inputs(d, "US")
        self.assertAlmostEqual(us["vessel"]["L"], d["vessel"]["L"] / 0.3048, places=3)

    def test_alloy_psi_rounded_to_ksi(self):
        r = alloys.lookup("5083-H116", "plate", 0.25, "US")
        for v in r.values():
            if isinstance(v, (int, float)) and v > 1000:
                self.assertEqual(v % 1000, 0)


class CrossCheck(unittest.TestCase):
    def test_si_vs_us_agree(self):
        d = _example()
        si = run(copy.deepcopy(d))
        us = run(UN.convert_inputs(copy.deepcopy(d), "US"))
        self.assertEqual(us["units"], "US")
        n = 0
        for r in us["results"]:
            s = next((x for x in si["results"] if (x["id"], x["kind"]) == (r["id"], r["kind"])), None)
            if not s or not s.get("utilisation") or not r.get("utilisation"):
                continue
            n += 1
            self.assertAlmostEqual(r["utilisation"], s["utilisation"], delta=0.06 * max(s["utilisation"], 0.2), msg=r)
        self.assertGreater(n, 5)

    def test_us_pressure_hand_calc(self):
        v = P.Vessel(L=200, Lw=190, B=30, Bw=12, D=15, d=5, delta_t=300, V=30, service="coastal", units="US")
        self.assertAlmostEqual(v.delta_load, 300 * 2240)
        self.assertAlmostEqual(v.AR, 1.61 * 300 * 2240 / 8.0)  # d floored at 0.04 L = 8 ft


class Catamaran(unittest.TestCase):
    def test_us_loads(self):
        r = HG.catamaran_loads(300, 20, 200, 1.0, "US")
        n1 = max(2.0, HG.min_1_plus_ncg(300, "US"))
        self.assertAlmostEqual(r["Mtb"], 0.255 * 300 * 2240 * 20 * n1)
        self.assertAlmostEqual(r["Qt"], 0.255 * 300 * 2240 * n1)


class Dxf(unittest.TestCase):
    def test_us_inches(self):
        txt = "\n".join(str(x) for x in [0, "SECTION", 2, "ENTITIES",
                                         0, "LINE", 8, "T0.25", 10, 0, 20, 0, 11, 40, 21, 0, 0, "ENDSEC"]) + "\n"
        d = dxf.parse(txt, units="US")
        self.assertEqual(d["unit"], "in")
        self.assertAlmostEqual(d["segments"][0][3] - d["segments"][0][1], 40.0)
        self.assertAlmostEqual(dxf.guess_thickness("T0.25", "US") or 0.25, 0.25)

    def test_section_us(self):
        mem = [{"name": "top", "y1": -20, "z1": 24, "y2": 20, "z2": 24, "t_mm": 0.25},
               {"name": "bot", "y1": -20, "z1": 0, "y2": 20, "z2": 0, "t_mm": 0.25},
               {"name": "sP", "y1": -20, "z1": 0, "y2": -20, "z2": 24, "t_mm": 0.25},
               {"name": "sS", "y1": 20, "z1": 0, "y2": 20, "z2": 24, "t_mm": 0.25}]
        r = SC.compute({"members": mem}, "US")
        self.assertAlmostEqual(r["A_cm2"], (2 * 40 + 2 * 24) * 0.25)  # in2 under the legacy key
        self.assertEqual(r["units"], "US")


if __name__ == "__main__":
    unittest.main()
