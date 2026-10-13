"""JSON-string entry points used by the in-browser (Pyodide) version."""
import json

from .report import run, markdown
from .alloys import lookup
from . import dxf as DXF
from . import section as SEC
from . import units as UN
from . import project as PR


def run_json(text: str) -> str:
    try:
        rep = run(json.loads(text))
        rep["markdown"] = markdown(rep)
        return json.dumps({"ok": True, "data": rep})
    except Exception as e:
        return json.dumps({"ok": False, "data": {"error": f"{type(e).__name__}: {e}"}})


def alloy_json(alloy: str, t: str, units: str = "SI") -> str:
    try:
        a, pr = alloy.split("|")
        return json.dumps({"ok": True, "data": lookup(a, pr, float(t), units)})
    except Exception as e:
        return json.dumps({"ok": False, "data": {"error": str(e)}})


def dxf_json(text: str, plane: str, unit: str, y0: str, z0: str, units: str = "SI") -> str:
    """Parse a DXF; unit/y0/z0 may be empty strings for 'automatic'. units: 'SI' (mm output) or 'US' (inches)."""
    try:
        d = DXF.parse(text, plane or "xy", unit or None, float(y0) if y0 != "" else None, float(z0) if z0 != "" else None,
                      units or "SI")
        return json.dumps({"ok": True, "data": d})
    except Exception as e:
        return json.dumps({"ok": False, "data": {"error": f"{type(e).__name__}: {e}"}})


def section_json(text: str, units: str = "SI") -> str:
    try:
        return json.dumps({"ok": True, "data": SEC.compute(json.loads(text), units or "SI")})
    except Exception as e:
        return json.dumps({"ok": False, "data": {"error": f"{type(e).__name__}: {e}"}})


def convert_json(text: str, to: str) -> str:
    """Convert an input document between SI and US units (the GUI unit selector)."""
    try:
        return json.dumps({"ok": True, "data": UN.convert_inputs(json.loads(text), to)})
    except Exception as e:
        return json.dumps({"ok": False, "data": {"error": f"{type(e).__name__}: {e}"}})


def _wrap(fn):
    try:
        return json.dumps({"ok": True, "data": fn()})
    except Exception as e:
        return json.dumps({"ok": False, "data": {"error": f"{type(e).__name__}: {e}"}})


def project_load_json(text: str) -> str:
    return _wrap(lambda: PR.load(text))


def project_add_json(proj_text: str, inputs_text: str, label: str = "", note: str = "") -> str:
    """Append a checked revision; returns the updated project and the new revision id."""
    def f():
        p = PR.load(proj_text) if proj_text else PR.new_project()
        rev = PR.add_revision(p, json.loads(inputs_text), label, note)
        return {"project": p, "id": rev["id"], "summary": rev["summary"]}
    return _wrap(f)


def project_compare_json(proj_text: str) -> str:
    def f():
        p = PR.load(proj_text)
        c = PR.compare(p)
        c["csv"] = PR.to_csv(c)
        return c
    return _wrap(f)


def project_recheck_json(proj_text: str) -> str:
    def f():
        p = PR.load(proj_text)
        return {"project": p, "changed": PR.recheck(p)}
    return _wrap(f)


def project_json(op: str, text: str) -> str:
    """One entry point for the GUIs. op: load | add | compare | recheck.  text: JSON {project?, inputs?, label?, note?}
    (for 'load' the text is the file contents itself)."""
    if op == "load":
        return project_load_json(text)
    o = json.loads(text) if text else {}
    ptxt = json.dumps(o["project"]) if o.get("project") else ""
    if op == "add":
        return project_add_json(ptxt, json.dumps(o["inputs"]), o.get("label", ""), o.get("note", ""))
    if op == "compare":
        return project_compare_json(ptxt)
    if op == "recheck":
        return project_recheck_json(ptxt)
    return json.dumps({"ok": False, "data": {"error": f"unknown project operation {op}"}})
