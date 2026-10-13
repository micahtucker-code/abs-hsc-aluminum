"""JSON-string entry points used by the in-browser (Pyodide) version."""
import json

from .report import run, markdown
from .alloys import lookup


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
