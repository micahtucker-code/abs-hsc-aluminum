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


def _dxf(*ents):
    return "\n".join(str(x) for x in [0, "SECTION", 2, "ENTITIES", *ents, 0, "ENDSEC", 0, "EOF"]) + "\n"


def _rect(layer, x0, y0, x1, y1):
    return [0, "LWPOLYLINE", 8, layer, 90, 4, 70, 1, 10, x0, 20, y0, 10, x1, 20, y0, 10, x1, 20, y1, 10, x0, 20, y1]


def _line(layer, a, b, c, d):
    return [0, "LINE", 8, layer, 10, a, 20, b, 11, c, 21, d]


def _loops(d, **layer_opts):
    lay = {k: dict(layer_opts) for k in d["layers"]}
    return {"dxf": {"layers": lay, "loops": d["loops"]}}


# a hollow box 1010 x 610 mm outside, 10 mm walls, as four touching plates
BOX_PLATES = [_rect("A", -505, -5, 505, 5), _rect("B", -505, 595, 505, 605), _rect("C", -505, 5, -495, 595), _rect("D", 495, 5, 505, 595)]
BOX_A = (1010 * 610 - 990 * 590) / 100
BOX_I = (1010 * 610 ** 3 - 990 * 590 ** 3) / 12 / 1e4


class Dxf(unittest.TestCase):
    def test_closed_polylines_are_shapes(self):
        d = dxf.parse(_dxf(*_rect("PL", 0, 100, 1000, 110), *_rect("WEB", 0, 110, 10, 700)))
        self.assertEqual(d["unit"], "mm")
        self.assertEqual((d["layers"]["PL"]["n"], d["layers"]["WEB"]["n"]), (1, 1))
        self.assertAlmostEqual(d["layers"]["PL"]["area_mm2"], 10000.0)
        self.assertAlmostEqual(d["bbox"][1], 0.0)  # baseline shifted to the lowest point
        self.assertAlmostEqual(d["bbox"][3], 600.0)
        self.assertEqual(d["open_segments"], [])

    def test_layer_names_and_thickness_are_irrelevant(self):
        a = dxf.parse(_dxf(*_rect("T8", 0, 0, 100, 8)))
        b = dxf.parse(_dxf(*_rect("whatever", 0, 0, 100, 8)))
        self.assertEqual(a["loops"][0][1], b["loops"][0][1])
        r = SC.compute({"dxf": {"layers": {"T999": {}}, "loops": [["T999", a["loops"][0][1]]]}})
        self.assertAlmostEqual(r["A_cm2"], 800 / 100)

    def test_loose_lines_join_into_a_shape_within_tolerance(self):
        d = dxf.parse(_dxf(*_line("L", 0, 0, 100, 0), *_line("L", 100, 0, 100, 10), *_line("L", 100, 10.2, 0, 10), *_line("L", 0, 10, 0, 0)))
        self.assertEqual(len(d["loops"]), 1)
        self.assertAlmostEqual(d["layers"]["L"]["area_mm2"], 1000.0, delta=15)
        self.assertEqual(d["open_segments"], [])

    def test_gap_and_stray_lines_are_reported_not_used(self):
        d = dxf.parse(_dxf(*_rect("R", 0, 0, 100, 10), *_line("S", 0, 50, 100, 50)))
        self.assertEqual(len(d["loops"]), 1)
        self.assertEqual(len(d["open_segments"]), 1)
        self.assertTrue(any("do not form a closed outline" in w for w in d["warnings"]))
        with self.assertRaises(ValueError):  # a U of lines with a 5 mm gap closes nothing
            dxf.parse(_dxf(*_line("L", 0, 0, 100, 0), *_line("L", 100, 0, 100, 10), *_line("L", 100, 10, 0, 10), *_line("L", 0, 15, 0, 0)))

    def test_nested_shape_is_a_hole(self):
        d = dxf.parse(_dxf(*_rect("OUT", -505, -5, 505, 605), *_rect("IN", -495, 5, 495, 595)))
        r = SC.compute(_loops(d))
        self.assertAlmostEqual(r["A_cm2"], BOX_A)
        self.assertAlmostEqual(r["I_cm4"], BOX_I, places=2)
        self.assertEqual((r["n_shapes"], r["n_holes"]), (1, 1))

    def test_circle_and_bulged_polyline_areas(self):
        d = dxf.parse(_dxf(0, "CIRCLE", 8, "C", 10, 0, 20, 0, 40, 100,
                           0, "LWPOLYLINE", 8, "S", 90, 4, 70, 1, 10, 500, 20, 0, 42, -1, 10, 500, 20, 100, 10, 700, 20, 100, 42, -1, 10, 700, 20, 0))
        self.assertAlmostEqual(d["layers"]["C"]["area_mm2"], math.pi * 100 ** 2, delta=math.pi * 100 ** 2 * 0.003)
        self.assertAlmostEqual(d["layers"]["S"]["area_mm2"], 100 * 200 + math.pi * 50 ** 2, delta=60)  # slot: two half discs

    def test_duplicate_outline_counted_once_and_overlap_warned(self):
        d = dxf.parse(_dxf(*_rect("A", 0, 0, 100, 10), *_rect("B", 0, 0, 100, 10)))
        self.assertEqual(len(d["loops"]), 1)
        self.assertTrue(any("duplicate" in w for w in d["warnings"]))
        d = dxf.parse(_dxf(*_rect("A", 0, 0, 100, 10), *_rect("B", 50, 5, 150, 15)))
        self.assertTrue(any("cross each other" in w for w in d["warnings"]))
        d = dxf.parse(_dxf(*_rect("A", 0, 0, 100, 10), *_rect("B", 0, 10, 10, 100)))  # edge to edge is fine
        self.assertEqual(d["warnings"], [])

    def test_units_and_origin(self):
        d = dxf.parse(_dxf(*_rect("A", 0, 0, 1, 0.01)), unit="m", y0=0.0, z0=0.0)
        self.assertAlmostEqual(max(q[0] for q in d["loops"][0][1]), 1000.0)
        d = dxf.parse(_dxf(*_rect("A", 10, 0, 11, 0.01)), unit="m", y0=10.5, z0=0.0)
        self.assertAlmostEqual(min(q[0] for q in d["loops"][0][1]), -500.0)

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            dxf.parse("hello\nworld\nfoo")
        with self.assertRaises(ValueError):
            dxf.parse(_dxf(*_rect("A", 0, 0, 1, 1)), plane="xx")
        with self.assertRaises(ValueError):
            dxf.parse(_dxf(0, "TEXT", 8, "N", 10, 0, 20, 0))

    def test_unsupported_entities_reported(self):
        d = dxf.parse(_dxf(*_rect("A", 0, 0, 100, 10), 0, "SPLINE", 8, "S", 0, "INSERT", 8, "N", 2, "BLK"))
        self.assertTrue(any("SPLINE" in w for w in d["warnings"]) and any("INSERT" in w for w in d["warnings"]))


class OutlineSection(unittest.TestCase):
    def test_four_touching_plates_match_closed_form(self):
        r = SC.compute(_loops(dxf.parse(_dxf(*[x for e in BOX_PLATES for x in e]))))
        self.assertAlmostEqual(r["A_cm2"], BOX_A)
        self.assertAlmostEqual(r["I_cm4"], BOX_I, places=2)
        self.assertAlmostEqual(r["z_NA_mm"], 305.0, places=6)  # baseline = the lowest point of the drawing
        self.assertAlmostEqual(r["SM_deck_cm3"], BOX_I * 1e4 / 305 / 1e3, places=2)
        self.assertAlmostEqual(r["SM_bottom_cm3"], BOX_I * 1e4 / 305 / 1e3, places=2)

    def test_shear_geometry_from_outlines(self):
        r = SC.compute(_loops(dxf.parse(_dxf(*[x for e in BOX_PLATES for x in e]))))
        sh = r["shear"]
        self.assertAlmostEqual(sh["m_cm3"], 3900.25, places=2)  # first moment above the neutral axis
        self.assertEqual(sh["n_webs"], 2)
        self.assertAlmostEqual(sh["web_t_sum_mm"], 20.0, places=3)
        self.assertAlmostEqual(sh["t_min_mm"], 10.0, places=3)
        self.assertFalse(sh["centreline_web"])
        self.assertAlmostEqual(sh["web_area_cm2"], 2 * 10 * 590 / 100, delta=0.5)

    def test_one_polygon_for_the_whole_plating_works_too(self):
        u = [(0, -5), (505, -5), (505, 605), (0, 605), (0, 595), (495, 595), (495, 5), (0, 5)]  # right half of the box as one shape
        r = SC.compute({"mirror": True, "dxf": {"layers": {"x": {}}, "loops": [["x", u]]}})
        self.assertAlmostEqual(r["A_cm2"], BOX_A)
        self.assertAlmostEqual(r["I_cm4"], BOX_I, places=2)
        self.assertEqual(r["shear"]["n_webs"], 2)
        self.assertFalse(r["shear"]["centreline_web"])

    def test_mirror_halves_and_centreline_shape_counted_once(self):
        half = [["x", [(0, -5), (505, -5), (505, 5), (0, 5)]], ["x", [(0, 595), (505, 595), (505, 605), (0, 605)]], ["x", [(495, 5), (505, 5), (505, 595), (495, 595)]]]
        full = SC.compute({"mirror": True, "dxf": {"layers": {"x": {}}, "loops": half}})
        self.assertAlmostEqual(full["A_cm2"], BOX_A)
        cl = SC.compute({"mirror": True, "dxf": {"layers": {"x": {}}, "loops": half + [["x", [(-5, 5), (5, 5), (5, 595), (-5, 595)]]]}})
        self.assertAlmostEqual(cl["A_cm2"], BOX_A + 10 * 590 / 100)  # a shape straddling the centreline is not doubled
        self.assertTrue(cl["shear"]["centreline_web"])

    def test_layer_effectiveness_and_ignore(self):
        d = dxf.parse(_dxf(*_rect("PLATE", 0, 0, 1000, 10), *_rect("DIM", 0, 20, 1000, 30)))
        both = SC.compute({"dxf": {"layers": {"PLATE": {}, "DIM": {}}, "loops": d["loops"]}})
        half = SC.compute({"dxf": {"layers": {"PLATE": {}, "DIM": {"eff": 0.0}}, "loops": d["loops"]}})
        ign = SC.compute({"dxf": {"layers": {"PLATE": {}, "DIM": {"ignore": True}}, "loops": d["loops"]}})
        self.assertAlmostEqual(both["A_cm2"], 200.0)
        self.assertAlmostEqual(half["A_cm2"], 100.0)
        self.assertAlmostEqual(ign["A_cm2"], 100.0)
        self.assertEqual(ign["n_shapes"], 1)

    def test_outlines_combine_with_members(self):
        r = SC.compute({"members": [{"name": "top", "y1": -500, "z1": 600, "y2": 500, "z2": 600, "t_mm": 10}],
                        "dxf": {"layers": {"x": {}}, "loops": [["x", [(-500, 0), (500, 0), (500, 10), (-500, 10)]]]}})
        self.assertAlmostEqual(r["A_cm2"], 2 * 1000 * 10 / 100)

    def test_legacy_line_and_thickness_documents_still_calculate(self):
        segs = [["T10", -500, 100, 500, 100], ["T10", 500, 100, 500, 700], ["PL_8", 500, 700, -500, 700], ["T10", -500, 700, -500, 100]]
        r = SC.compute({"dxf": {"layers": {"T10": {"t_mm": 10}, "PL_8": {"t_mm": 10}}, "segments": segs}})
        self.assertAlmostEqual(r["A_cm2"], _box_area())
        r2 = SC.compute({"dxf": {"layers": {"T10": {"t_mm": 10}, "PL_8": {"t_mm": 10, "ignore": True}}, "segments": segs}})
        self.assertAlmostEqual(r2["A_cm2"], 2200 * 10 / 100)

    def test_us_units(self):
        d = dxf.parse(_dxf(*_rect("A", -20, 0, 20, 0.25), *_rect("B", -20, 23.75, 20, 24)), units="US")
        self.assertEqual(d["unit"], "in")
        r = SC.compute(_loops(d), "US")
        self.assertAlmostEqual(r["A_in2" if "A_in2" in r else "A_cm2"], 2 * 40 * 0.25)
        self.assertEqual(r["units"], "US")


class SampleFiles(unittest.TestCase):
    def test_midship_sample_matches_the_line_model(self):
        with open("inputs/example_section.dxf", encoding="utf-8") as f:
            d = dxf.parse(f.read())
        self.assertEqual(d["warnings"], [])
        self.assertEqual(d["open_segments"], [])
        r = SC.compute({"mirror": True, **_loops(d)})
        with open("inputs/example_vessel.json", encoding="utf-8") as f:
            ref = SC.compute(json.load(f)["section"])
        self.assertAlmostEqual(r["A_cm2"], ref["A_cm2"], delta=ref["A_cm2"] * 0.002)
        self.assertAlmostEqual(r["I_cm4"], ref["I_cm4"], delta=ref["I_cm4"] * 0.002)

    def test_crossdeck_sample_dxf(self):
        with open("inputs/example_crossdeck.dxf", encoding="utf-8") as f:
            d = dxf.parse(f.read())
        r = SC.compute(_loops(d))
        self.assertAlmostEqual(r["A_cm2"], 129874.0 / 100)
        self.assertAlmostEqual(r["shear"]["web_area_cm2"], 3 * 6 * 993 / 100, delta=0.5)


if __name__ == "__main__":
    unittest.main()
