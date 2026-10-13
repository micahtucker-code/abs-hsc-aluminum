import argparse, json, sys
from .report import run, markdown
from . import project as PR

ap = argparse.ArgumentParser(prog="abs_hsc_al", description="ABS HSC aluminum scantling checker")
ap.add_argument("input", help="input JSON, or a project file (.json with revisions)")
ap.add_argument("--json", help="write JSON report here"); ap.add_argument("--md", help="write Markdown here")
ap.add_argument("--rev", help="project file: revision id to check (default: the latest)")
ap.add_argument("--compare", action="store_true", help="project file: print the revision comparison (utilisation per item) and exit")
ap.add_argument("--csv", help="project file: write the comparison as CSV here")
a = ap.parse_args()
doc = json.load(open(a.input, encoding="utf-8"))
if PR.is_project(doc):
    proj = PR.load(doc)
    if a.compare or a.csv:
        c = PR.compare(proj)
        if a.csv: open(a.csv, "w", encoding="utf-8").write(PR.to_csv(c))
        print(PR.to_csv(c)); [print("note:", w) for w in c["warnings"]]
        last = c["revisions"][-1] if c["revisions"] else None
        sys.exit(0 if last and last["n_fail"] == 0 else 1)
    if not proj["revisions"]:
        sys.exit("project has no revisions")
    doc = (PR.get_revision(proj, a.rev) if a.rev else proj["revisions"][-1])["inputs"]
rep = run(doc)
md = markdown(rep)
if a.json: json.dump(rep, open(a.json, "w"), indent=2)
if a.md: open(a.md, "w").write(md)
print(md)
sys.exit(0 if all(r["passed"] for r in rep["results"]) else 1)
