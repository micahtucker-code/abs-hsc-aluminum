"""JSON-string entry points used by the in-browser (Pyodide) version."""
import json

from .report import run, markdown
from .alloys import lookup
from . import dxf as DXF
from . import section as SEC


def run_json(text: str) -> str:
    try:
        rep = run(json.loads(text))
        rep["markdown"] = markdown(rep)
        return json.dumps({"ok": True, "data": rep})
    except Exception as e:
        return json.dumps({"ok": False, "data": {"error": f"{type(e).__name__}: {e}"}})


def alloy_json(alloy: str, t: str) -> str:
    try:
        a, pr = alloy.split("|")
        return json.dumps({"ok": True, "data": lookup(a, pr, float(t))})
    except Exception as e:
        return json.dumps({"ok": False, "data": {"error": str(e)}})


def dxf_json(text: str, plane: str, unit: str, y0: str, z0: str) -> str:
    """Parse a DXF; unit/y0/z0 may be empty strings for 'automatic'."""
    try:
        d = DXF.parse(text, plane or "xy", unit or None, float(y0) if y0 != "" else None, float(z0) if z0 != "" else None)
        return json.dumps({"ok": True, "data": d})
    except Exception as e:
        return json.dumps({"ok": False, "data": {"error": f"{type(e).__name__}: {e}"}})


def section_json(text: str) -> str:
    try:
        return json.dumps({"ok": True, "data": SEC.compute(json.loads(text))})
    except Exception as e:
        return json.dumps({"ok": False, "data": {"error": f"{type(e).__name__}: {e}"}})
