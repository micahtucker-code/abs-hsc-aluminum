"""Project files: a design history of input snapshots (revisions) with the check results at each one.

A project file is JSON:  {format, version, name, created, modified, assets, revisions: [revision, ...]}
A revision is an immutable snapshot:  {id, label, note, date, engine, inputs, summary}
`inputs` is exactly the input document that `report.run` takes (so any revision can be re-run or opened in the GUI);
`summary` is the compact result list taken at the time it was saved, so the history can be compared without re-running.
"""
from __future__ import annotations

import copy
import datetime as _dt
import json

from . import __version__
from .report import run

FORMAT = "abs-hsc-aluminum-project"
VERSION = 1


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _key(r: dict) -> str:
    return f'{r["id"]} | {r["kind"]} | {r["clause"]}'


def summarise(rep: dict) -> dict:
    """Compact, comparable record of a `run()` result."""
    res = [{"key": _key(r), "id": r["id"], "kind": r["kind"], "clause": r["clause"], "unit": r.get("unit", ""),
            "required": r["required"], "provided": r["provided"], "utilisation": r["utilisation"],
            "passed": bool(r["passed"])} for r in rep["results"]]
    keys = [r["key"] for r in res]
    dup = {k for k in keys if keys.count(k) > 1}  # two loads on one panel share id/kind/clause: number them
    seen: dict[str, int] = {}
    for r in res:
        if r["key"] in dup:
            seen[r["key"]] = seen.get(r["key"], 0) + 1
            r["key"] += f' #{seen[r["key"]]}'
    return {"units": rep.get("units", "SI"), "ncg": rep.get("ncg"), "n": len(res),
            "n_fail": sum(1 for r in res if not r["passed"]),
            "max_util": max((r["utilisation"] for r in res), default=0.0), "results": res}


def new_project(name: str = "Untitled project") -> dict:
    t = _now()
    return {"format": FORMAT, "version": VERSION, "name": name, "created": t, "modified": t, "assets": {}, "revisions": []}


def is_project(doc) -> bool:
    return isinstance(doc, dict) and doc.get("format") == FORMAT


def next_id(proj: dict) -> str:
    used = {r["id"] for r in proj["revisions"]}
    n = len(used) + 1
    while f"R{n}" in used:
        n += 1
    return f"R{n}"


def add_revision(proj: dict, inputs: dict, label: str = "", note: str = "", report: dict | None = None) -> dict:
    """Run the checks on `inputs` and append the snapshot. Raises whatever `run` raises for unusable inputs."""
    rep = report if report is not None else run(copy.deepcopy(inputs))
    rid = next_id(proj)
    rev = {"id": rid, "label": label.strip() or rid, "note": note.strip(), "date": _now(), "engine": __version__,
           "inputs": copy.deepcopy(inputs), "summary": summarise(rep)}
    proj["revisions"].append(rev)
    proj["modified"] = rev["date"]
    return rev


def delete_revision(proj: dict, rid: str) -> None:
    n = len(proj["revisions"])
    proj["revisions"] = [r for r in proj["revisions"] if r["id"] != rid]
    if len(proj["revisions"]) == n:
        raise KeyError(f"no revision {rid}")
    proj["modified"] = _now()


def get_revision(proj: dict, rid: str) -> dict:
    for r in proj["revisions"]:
        if r["id"] == rid:
            return r
    raise KeyError(f"no revision {rid}")


def recheck(proj: dict) -> list[str]:
    """Re-run every revision with the current engine and replace its summary. Returns ids whose pass/fail pattern changed."""
    changed = []
    for r in proj["revisions"]:
        old = {x["key"]: x["passed"] for x in r["summary"]["results"]}
        r["summary"] = summarise(run(copy.deepcopy(r["inputs"])))
        r["engine"] = __version__
        if old != {x["key"]: x["passed"] for x in r["summary"]["results"]}:
            changed.append(r["id"])
    proj["modified"] = _now()
    return changed


def load(text_or_doc) -> dict:
    """Read a project file; a bare input document is wrapped as a one-revision project (and checked)."""
    doc = json.loads(text_or_doc) if isinstance(text_or_doc, (str, bytes)) else text_or_doc
    if is_project(doc):
        if doc.get("version", 0) > VERSION:
            raise ValueError(f"project file version {doc['version']} is newer than this program understands ({VERSION})")
        doc.setdefault("assets", {})
        ids = [r.get("id") for r in doc.get("revisions", [])]
        if len(ids) != len(set(ids)):
            raise ValueError("project file has duplicate revision ids")
        for r in doc.get("revisions", []):
            for k in ("id", "inputs", "summary"):
                if k not in r:
                    raise ValueError(f"revision {r.get('id', '?')} is missing '{k}'")
        return doc
    if isinstance(doc, dict) and ("vessel" in doc or "plates" in doc):
        p = new_project((doc.get("project") or {}).get("project") or "Imported project")
        add_revision(p, doc, "Imported")
        return p
    raise ValueError("not a project file or an input file")


def compare(proj: dict, ids: list[str] | None = None) -> dict:
    """Side-by-side history. Returns {revisions: [...], rows: [...], changes: [...]}.

    rows: one per check item (union over the revisions, first-seen order) with a cell per revision
    ({utilisation, passed} or None when the item is absent). changes: between each pair of consecutive revisions,
    the items that went pass->fail (regressions), fail->pass (fixed), appeared, disappeared, and the largest
    utilisation moves.
    """
    revs = [r for r in proj["revisions"] if ids is None or r["id"] in ids]
    heads = [{"id": r["id"], "label": r["label"], "date": r["date"], "note": r["note"], "engine": r.get("engine", ""),
              "units": r["summary"]["units"], "n": r["summary"]["n"], "n_fail": r["summary"]["n_fail"],
              "max_util": r["summary"]["max_util"]} for r in revs]
    order: list[str] = []
    cells: list[dict] = []
    for r in revs:
        m = {x["key"]: x for x in r["summary"]["results"]}
        cells.append(m)
        order += [k for k in m if k not in order]
    rows = []
    for k in order:
        first = next(m[k] for m in cells if k in m)
        rows.append({"key": k, "id": first["id"], "kind": first["kind"], "clause": first["clause"],
                     "cells": [({"utilisation": m[k]["utilisation"], "passed": m[k]["passed"]} if k in m else None) for m in cells]})
    changes = []
    for i in range(1, len(revs)):
        a, b = cells[i - 1], cells[i]
        ch = {"from": revs[i - 1]["id"], "to": revs[i]["id"], "regressions": [], "fixed": [], "added": [], "removed": [],
              "moves": []}
        for k in order:
            if k in a and k in b:
                if a[k]["passed"] and not b[k]["passed"]:
                    ch["regressions"].append(k)
                elif not a[k]["passed"] and b[k]["passed"]:
                    ch["fixed"].append(k)
                ch["moves"].append((k, b[k]["utilisation"] - a[k]["utilisation"]))
            elif k in b:
                ch["added"].append(k)
            elif k in a:
                ch["removed"].append(k)
        ch["moves"] = [{"key": k, "delta": d} for k, d in sorted(ch["moves"], key=lambda x: -abs(x[1]))[:5] if abs(d) >= 0.005]
        changes.append(ch)
    warn = []
    if len({h["engine"] for h in heads}) > 1:
        warn.append("Revisions were checked with different program versions (" + ", ".join(sorted({h["engine"] for h in heads})) +
                    "); use 'Recheck all' to bring them to the current version before relying on differences.")
    return {"revisions": heads, "rows": rows, "changes": changes, "warnings": warn}


def to_csv(cmp: dict) -> str:
    import csv, io
    s = io.StringIO()
    w = csv.writer(s)
    w.writerow(["Item", "Check", "Clause"] + [f'{h["id"]} {h["label"]}' for h in cmp["revisions"]])
    for r in cmp["rows"]:
        w.writerow([r["id"], r["kind"], r["clause"]] + [("" if c is None else f'{c["utilisation"]:.3f}{"" if c["passed"] else " FAIL"}') for c in r["cells"]])
    w.writerow(["", "Checks failing", ""] + [h["n_fail"] for h in cmp["revisions"]])
    return s.getvalue()


def dumps(proj: dict) -> str:
    return json.dumps(proj, indent=1, ensure_ascii=False)
