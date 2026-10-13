import json, math, unittest

from abs_hsc_al import dxf, section as SC
from abs_hsc_al.report import run


def _box(extra=None):
    """1000 wide x 600 high hollow box, t = 10 mm, centred on y = 0 (full section, no mirror)."""
    m = [{"name": "top", "y1": -500, "z1": 600, "y2": 500, "z2": 600, "t_mm": 10},
         {"name": "bottom", "y1": -500, "z1": 0, "y2": 500, "z2": 0, "t_mm": 10},
         {"name": "side P", "y1": -500, "z1": 0, "y2": -500, "z2": 600, "t_mm": 10},
         {"name": "side S", "y1": 500, "z1": 0, "y2": 500, "z2": 600, "t_mm": 10}]
    return {"members": m + (extra or [])}


def _box_area():
    return (2 * 1000 + 2 * 600) * 10 / 100


class SectionProps(unittest.TestCase):
    def test_hollow_box_matches_hand_calc(self):
        r = SC.compute(_box())
        I = 2 * (1e4 * 300 ** 2 + 1000 * 1e3 / 12) + 2 * (10 * 600 ** 3 / 12)  # mm4
        self.assertAlmostEqual(r["z_NA_mm"], 300.0, places=6)
        self.assertAlmostEqual(r["I_cm4"], I / 1e4, places=3)
        self.assertAlmostEqual(r["SM_deck_cm3"], I / 300 / 1e3, places=3)
        self.assertAlmostEqual(r["SM_bottom_cm3"], r["SM_deck_cm3"], places=6)
        self.assertAlmostEqual(r["A_cm2"], _box_area())

    def test_inclined_member_inertia(self):
        A, zc, I = SC._seg(0, 0, 300, 400, 10)  # 3-4-5 member, l = 500
        self.assertAlmostEqual(I, 10 * 500 ** 3 / 12 * 0.8 ** 2 + 500 * 1000 / 12 * 0.6 ** 2)
        self.assertAlmostEqual(A, 5000)

    def test_mirror_halves_input_and_keeps_centreline_members(self):
        full = SC.compute(_box())
        half = {"mirror": True, "members": [
            {"name": "top", "y1": 0, "z1": 600, "y2": 500, "z2": 600, "t_mm": 10},
            {"name": "bottom", "y1": 0, "z1": 0, "y2": 500, "z2": 0, "t_mm": 10},
            {"name": "side", "y1": 500, "z1": 0, "y2": 500, "z2": 600, "t_mm": 10}]}
        h = SC.compute(half)
        self.assertAlmostEqual(h["I_cm4"], full["I_cm4"], places=4)
        cl = SC.compute({"mirror": True, "members": half["members"] + [
            {"name": "CL girder", "y1": 0, "z1": 0, "y2": 0, "z2": 600, "t_mm": 10}]})
        self.assertAlmostEqual(cl["A_cm2"], full["A_cm2"] + 600 * 10 / 100)  # counted once, not twice

    def test_effective_factor_scales_member(self):
        b = _box()
        b["members"][0]["effective"] = 0.0
        r = SC.compute(b)
        self.assertAlmostEqual(r["A_cm2"], (1000 + 1200) * 10 / 100)
        self.assertLess(r["z_NA_mm"], 300.0)

    def test_stiffeners_expand_inward(self):
        b = _box()
        b["members"][0]["stiffeners"] = {"spacing_mm": 250, "profile": "flat", "hw_mm": 80, "tw_mm": 6}
        r = SC.compute(b)
        self.assertEqual(r["n_stiffener_lines"], 3)  # l = 1000, 4 panels -> 3 interior stiffeners
        self.assertAlmostEqual(r["A_cm2"], _box_area() + 3 * 80 * 6 / 100)
        webs = [g for g in r["geometry"] if g[5] == "web"]
        self.assertTrue(all(g[1] < 600 and g[3] < 600 for g in webs))  # top-plate stiffeners hang below the plate

    def test_tee_flange_centred_angle_flange_one_sided(self):
        for prof, expect in (("tee", (-50, 50)), ("angle", (0, 100))):
            b = {"members": [{"name": "p", "y1": 0, "z1": 0, "y2": 1000, "z2": 0, "t_mm": 8,
                              "stiffeners": {"count": 1, "profile": prof, "hw_mm": 100, "tw_mm": 6, "bf_mm": 100,
                                             "tf_mm": 8, "side": "out"}},
                            {"name": "deck", "y1": 0, "z1": 300, "y2": 1000, "z2": 300, "t_mm": 8}]}
            g = [x for x in SC.compute(b)["geometry"] if x[5] == "flange"][0]
            self.assertAlmostEqual(min(g[0], g[2]) - 500, expect[0], places=3)
            self.assertAlmostEqual(max(g[0], g[2]) - 500, expect[1], places=3)
            self.assertAlmostEqual(g[1], -(4 + 100 + 4), places=3)

    def test_na_outside_section_rejected(self):
        with self.assertRaises(ValueError):
            SC.compute({"members": _box()["members"], "deck_z_mm": 100})

    def test_missing_field_and_empty(self):
        with self.assertRaises(ValueError):
            SC.compute({"members": [{"name": "x", "y1": 0, "z1": 0, "y2": 1, "z2": 1}]})
        with self.assertRaises(ValueError):
            SC.compute({"members": []})

    def test_lump(self):
        r = SC.compute({"members": _box()["members"] + [{"name": "bulb", "type": "lump", "area_mm2": 1000, "z_mm": 300, "I_mm4": 5e5}]})
        self.assertAlmostEqual(r["A_cm2"], _box_area() + 10.0)

    def test_feeds_hull_girder(self):
        d = json.load(open("inputs/example_vessel.json", encoding="utf-8"))
        d["section"] = _box()
        d.pop("hull_girder", None)
        rep = run(d)
        rows = [r for r in rep["results"] if r["id"] == "hull girder"]
        self.assertTrue(rows)
        self.assertAlmostEqual(rows[0]["provided"], rep["section"]["SM_deck_cm3"] / 100.0)
        self.assertTrue(rep["hull_girder_used"]["from_section"])


DXF_BOX = "\n".join(str(x) for x in [
    0, "SECTION", 2, "HEADER", 9, "$INSUNITS", 70, 4, 0, "ENDSEC",
    0, "SECTION", 2, "ENTITIES",
    0, "LINE", 8, "T10", 10, -500, 20, 100, 30, 0, 11, 500, 21, 100, 31, 0,
    0, "LINE", 8, "T10", 10, 500, 20, 100, 11, 500, 21, 700,
    0, "LWPOLYLINE", 8, "PL_8", 90, 2, 70, 0, 10, 500, 20, 700, 10, -500, 20, 700,
    0, "LINE", 8, "T10", 10, -500, 20, 700, 11, -500, 21, 100,
    0, "TEXT", 8, "NOTES", 10, 0, 20, 0,
    0, "INSERT", 8, "NOTES", 2, "BLK",
    0, "ENDSEC", 0, "EOF"]) + "\n"


class Dxf(unittest.TestCase):
    def test_parse_box(self):
        d = dxf.parse(DXF_BOX)
        self.assertEqual(d["unit"], "mm")
        self.assertEqual(d["layers"]["T10"]["n"], 3)
        self.assertEqual(d["layers"]["PL_8"]["n"], 1)
        self.assertEqual(d["layers"]["T10"]["suggested_t_mm"], 10.0)
        self.assertEqual(d["layers"]["PL_8"]["suggested_t_mm"], 8.0)
        self.assertAlmostEqual(d["bbox"][1], 0.0)  # baseline shifted to the lowest point
        self.assertAlmostEqual(d["bbox"][3], 600.0)
        self.assertTrue(any("INSERT" in w for w in d["warnings"]))

    def test_units_and_origin(self):
        d = dxf.parse(DXF_BOX, unit="m", y0=0.0, z0=0.0)
        self.assertAlmostEqual(max(s[4] for s in d["segments"]), 700000.0)

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            dxf.parse("hello\nworld\nfoo")
        with self.assertRaises(ValueError):
            dxf.parse(DXF_BOX, plane="xx")

    def test_arc_and_bulge_length(self):
        txt = "\n".join(str(x) for x in [
            0, "SECTION", 2, "ENTITIES",
            0, "ARC", 8, "A", 10, 0, 20, 0, 40, 1000, 50, 0, 51, 90,
            0, "LWPOLYLINE", 8, "B", 70, 0, 10, 0, 20, 0, 42, 1, 10, 2000, 20, 0,
            0, "ENDSEC"]) + "\n"
        d = dxf.parse(txt, z0=-5000)
        self.assertAlmostEqual(d["layers"]["A"]["length_mm"], math.pi * 1000 / 2, delta=3)
        self.assertAlmostEqual(d["layers"]["B"]["length_mm"], math.pi * 1000, delta=4)

    def test_dxf_into_section(self):
        d = dxf.parse(DXF_BOX)
        lay = {"T10": {"t_mm": 10}, "PL_8": {"t_mm": 10}}
        r = SC.compute({"dxf": {"layers": lay, "segments": d["segments"]}})
        self.assertAlmostEqual(r["A_cm2"], _box_area())
        r2 = SC.compute({"dxf": {"layers": {"T10": {"t_mm": 10}, "PL_8": {"t_mm": 10, "ignore": True}}, "segments": d["segments"]}})
        self.assertAlmostEqual(r2["A_cm2"], 2200 * 10 / 100)


class SampleFiles(unittest.TestCase):
    def test_crossdeck_sample_dxf(self):
        with open("inputs/example_crossdeck.dxf", encoding="utf-8") as f:
            d = dxf.parse(f.read())
        lay = {"T6_DECK": {"t_mm": 6}, "T8_WETDECK": {"t_mm": 8}, "T6_BHD": {"t_mm": 6}}
        r = SC.compute({"dxf": {"layers": lay, "segments": d["segments"]}})
        self.assertAlmostEqual(r["A_cm2"], (8000 * 6 + 8000 * 8 + 3 * 1000 * 6) / 100)
        self.assertAlmostEqual(r["shear"]["web_area_cm2"], 180.0)


if __name__ == "__main__":
    unittest.main()
