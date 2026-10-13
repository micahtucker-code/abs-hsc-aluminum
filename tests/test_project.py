import copy, json, unittest

from abs_hsc_al import project as PR, webapi


def _ex():
    with open("inputs/example_vessel.json", encoding="utf-8") as f:
        return json.load(f)


def _thin(d, factor):
    d = copy.deepcopy(d)
    for p in d["plates"]:
        p["t_mm"] = round(p["t_mm"] * factor, 2)
    return d


class History(unittest.TestCase):
    def setUp(self):
        self.p = PR.new_project("Test")
        self.ex = _ex()

    def test_add_and_ids(self):
        r1 = PR.add_revision(self.p, self.ex, "Concept", "first pass")
        r2 = PR.add_revision(self.p, _thin(self.ex, 0.6), "Lightweight")
        self.assertEqual((r1["id"], r2["id"]), ("R1", "R2"))
        self.assertEqual(r1["summary"]["n"], len(r1["summary"]["results"]))
        PR.delete_revision(self.p, "R1")
        self.assertEqual(PR.add_revision(self.p, self.ex)["id"], "R3")  # ids are never reused while others exist
        self.assertEqual(r2["inputs"]["plates"][0]["t_mm"], _thin(self.ex, 0.6)["plates"][0]["t_mm"])

    def test_snapshot_is_independent_of_later_edits(self):
        r = PR.add_revision(self.p, self.ex)
        self.ex["plates"][0]["t_mm"] = 99
        self.assertNotEqual(r["inputs"]["plates"][0]["t_mm"], 99)

    def test_round_trip_file(self):
        PR.add_revision(self.p, self.ex, "A")
        q = PR.load(PR.dumps(self.p))
        self.assertEqual(q["revisions"][0]["inputs"], self.p["revisions"][0]["inputs"])

    def test_compare_flags_regression_and_fix(self):
        PR.add_revision(self.p, self.ex, "ok")
        PR.add_revision(self.p, _thin(self.ex, 0.5), "too thin")
        PR.add_revision(self.p, self.ex, "restored")
        c = PR.compare(self.p)
        self.assertEqual([h["id"] for h in c["revisions"]], ["R1", "R2", "R3"])
        self.assertGreater(c["revisions"][1]["n_fail"], c["revisions"][0]["n_fail"])
        self.assertTrue(c["changes"][0]["regressions"])
        self.assertEqual(sorted(c["changes"][1]["fixed"]), sorted(c["changes"][0]["regressions"]))
        self.assertIn("R2", PR.to_csv(c))
        self.assertEqual(c["warnings"], [])

    def test_added_and_removed_items(self):
        PR.add_revision(self.p, self.ex)
        e2 = copy.deepcopy(self.ex)
        e2["plates"].append(copy.deepcopy(e2["plates"][0]))
        e2["plates"][-1]["id"] = "Extra panel"
        e2["plates"].pop(0)
        PR.add_revision(self.p, e2)
        ch = PR.compare(self.p)["changes"][0]
        self.assertTrue(ch["added"])
        self.assertTrue(ch["removed"])

    def test_engine_version_warning_and_recheck(self):
        PR.add_revision(self.p, self.ex)
        PR.add_revision(self.p, self.ex)
        self.p["revisions"][0]["engine"] = "0.0.1"
        self.assertTrue(PR.compare(self.p)["warnings"])
        PR.recheck(self.p)
        self.assertEqual(PR.compare(self.p)["warnings"], [])

    def test_us_and_si_revisions_compare_by_utilisation(self):
        from abs_hsc_al import units as UN
        PR.add_revision(self.p, self.ex, "SI")
        PR.add_revision(self.p, UN.convert_inputs(self.ex, "US"), "US")
        c = PR.compare(self.p)
        self.assertEqual([h["units"] for h in c["revisions"]], ["SI", "US"])
        both = [r for r in c["rows"] if all(x for x in r["cells"])]
        self.assertGreater(len(both), 5)

    def test_load_bare_inputs_and_rejects_junk(self):
        p = PR.load(json.dumps(self.ex))
        self.assertEqual(len(p["revisions"]), 1)
        with self.assertRaises(ValueError):
            PR.load('{"hello": 1}')
        bad = PR.new_project(); bad["version"] = 99
        with self.assertRaises(ValueError):
            PR.load(bad)
        with self.assertRaises(KeyError):
            PR.delete_revision(self.p, "R9")

    def test_unusable_inputs_raise_and_leave_project_unchanged(self):
        with self.assertRaises(Exception):
            PR.add_revision(self.p, {"vessel": {}})
        self.assertEqual(self.p["revisions"], [])


class WebApi(unittest.TestCase):
    def test_api_flow(self):
        ex = _ex()
        r = json.loads(webapi.project_json("add", json.dumps({"inputs": ex, "label": "A"})))
        self.assertTrue(r["ok"])
        proj = r["data"]["project"]
        r = json.loads(webapi.project_json("add", json.dumps({"project": proj, "inputs": _thin(ex, .5), "label": "B"})))
        proj = r["data"]["project"]
        self.assertEqual(len(proj["revisions"]), 2)
        c = json.loads(webapi.project_json("compare", json.dumps({"project": proj})))
        self.assertTrue(c["ok"] and c["data"]["csv"])
        self.assertTrue(json.loads(webapi.project_json("load", json.dumps(proj)))["ok"])
        self.assertFalse(json.loads(webapi.project_json("add", json.dumps({"inputs": {"vessel": {}}})))["ok"])


if __name__ == "__main__":
    unittest.main()
