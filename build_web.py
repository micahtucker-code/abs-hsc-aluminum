"""Build the static web app into ./web  (python build_web.py [--pyodide DIR]).

Output is plain files: host the `web` folder on any static host. Pyodide (Python in WebAssembly)
is self-hosted from web/pyodide, so the site has no third-party runtime dependencies.
"""
import argparse, datetime, json, os, shutil, zipfile

from abs_hsc_al import __version__
from abs_hsc_al.gui import _meta, HERE

ap = argparse.ArgumentParser()
ap.add_argument("--pyodide", default="pyodide_core", help="folder with the Pyodide core files (see web/README.md)")
ap.add_argument("--out", default="web")
a = ap.parse_args()

out = a.out
os.makedirs(out, exist_ok=True)
# engine as a zip that Pyodide unpacks
with zipfile.ZipFile(os.path.join(out, "engine.zip"), "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(os.listdir(HERE)):
        if f.endswith(".py"):
            z.write(os.path.join(HERE, f), f"abs_hsc_al/{f}")
# pyodide runtime
dst = os.path.join(out, "pyodide")
if os.path.isdir(a.pyodide):
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst)
    for f in ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"):
        shutil.copy(os.path.join(a.pyodide, f), dst)
elif not os.path.isdir(dst):
    raise SystemExit("Pyodide core files not found; see web/README.md")

page = open(os.path.join(HERE, "gui_page.html"), encoding="utf-8").read()
api = """const API=(()=>{let py;
 const ready=(async()=>{const s=document.getElementById("status");
  const pyodide=await loadPyodide({indexURL:"pyodide/"});
  const buf=await (await fetch("engine.zip?v=__VER__")).arrayBuffer();
  pyodide.unpackArchive(buf,"zip");
  py=pyodide.pyimport("abs_hsc_al.webapi");s.textContent="Ready (v__VER__, offline-capable)";return py})();
 const call=async(f,...a)=>{const p=await ready;return JSON.parse(p[f](...a))};
 return {run:d=>call("run_json",JSON.stringify(d)),alloy:(a,t,u)=>call("alloy_json",a,String(t),u||"SI"),
  dxf:(t,pl,u,y0,z0,us)=>call("dxf_json",t,pl,u,String(y0),String(z0),us||"SI"),section:(d,us)=>call("section_json",JSON.stringify(d),us||"SI"),
  convert:(d,to)=>call("convert_json",JSON.stringify(d),to),
  example:async()=>(await fetch("example.json?v=__VER__")).json(),ready}})();
document.addEventListener("DOMContentLoaded",()=>{});""".replace("__VER__", __version__)
footer = (f"Version {__version__} (built {datetime.date.today()}). Runs entirely in your browser; no vessel data is uploaded. "
          "Supports a designer's check; not an ABS approval.")
page = (page.replace("__META__", json.dumps(_meta())).replace("/*__API__*/", api).replace("/*__REPORT__*/", open(os.path.join(HERE, "report_view.js"), encoding="utf-8").read()).replace("__FOOTER__", footer)
        .replace("<header>", '<script src="pyodide/pyodide.js"></script>\n<header>', 1)
        .replace('<button class="p" onclick="runCheck()">Run checks</button></header>',
                 '<span id="status" class="hint" style="margin:0">Loading calculation engine…</span><button class="p" onclick="runCheck()">Run checks</button></header>'))
open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(page)
shutil.copy(os.path.join("inputs", "example_vessel.json"), os.path.join(out, "example.json"))
print("built", out, "version", __version__)
