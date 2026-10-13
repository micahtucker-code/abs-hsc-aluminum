import argparse, json, sys
from .report import run, markdown

ap = argparse.ArgumentParser(prog="abs_hsc_al", description="ABS HSC aluminum scantling checker")
ap.add_argument("input"); ap.add_argument("--json", help="write JSON report here"); ap.add_argument("--md", help="write Markdown here")
a = ap.parse_args()
rep = run(json.load(open(a.input)))
md = markdown(rep)
if a.json: json.dump(rep, open(a.json, "w"), indent=2)
if a.md: open(a.md, "w").write(md)
print(md)
sys.exit(0 if all(r["passed"] for r in rep["results"]) else 1)
