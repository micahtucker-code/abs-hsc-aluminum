"""Local browser GUI: python -m abs_hsc_al.gui  (stdlib only, serves on 127.0.0.1)."""
from __future__ import annotations

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from urllib.parse import urlparse, parse_qs
from .report import run, markdown
from .alloys import list_alloys, lookup
from .plating import DESIGN_STRESS_FACTOR, MIN_THICKNESS
from .stiffeners import SIGMA_A_FACTOR

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(HERE, "..", "inputs", "example_vessel.json")

_SERVER_API = """const API={
 async run(d){const r=await fetch("/run",{method:"POST",body:JSON.stringify(d)});return {ok:r.ok,data:await r.json()}},
 async alloy(a,t){const r=await fetch("/alloy?alloy="+encodeURIComponent(a)+"&t="+t);return {ok:r.ok,data:await r.json()}},
 async example(){return (await fetch("/example")).json()}};"""
PAGE = (open(os.path.join(HERE, "gui_page.html"), encoding="utf-8").read()
        .replace("/*__API__*/", _SERVER_API).replace("__FOOTER__", "Local version. Supports a designer's check; not an ABS approval."))


def _meta() -> dict:
    return {"plate_cases": list(DESIGN_STRESS_FACTOR), "plate_locations": list(MIN_THICKNESS),
            "member_cases": list(SIGMA_A_FACTOR),
            "alloys": [f"{a}|{p}" for a, p in list_alloys()]}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE.replace("__META__", json.dumps(_meta())).encode(), "text/html; charset=utf-8")
        elif self.path.startswith("/alloy"):
            q = parse_qs(urlparse(self.path).query)
            try:
                a, pr = q["alloy"][0].split("|")
                self._send(200, json.dumps(lookup(a, pr, float(q["t"][0]))).encode())
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}).encode())
        elif self.path == "/example":
            with open(EXAMPLE, encoding="utf-8") as f:
                self._send(200, f.read().encode())
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path != "/run":
            return self._send(404, b'{"error":"not found"}')
        try:
            n = int(self.headers.get("Content-Length", 0))
            rep = run(json.loads(self.rfile.read(n)))
            rep["markdown"] = markdown(rep)
            self._send(200, json.dumps(rep).encode())
        except Exception as e:  # surface rule/input errors to the user
            self._send(400, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode())

    def log_message(self, *a):
        pass


def main(port: int = 8765, open_browser: bool = True):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"ABS HSC aluminum checker GUI at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    main(a.port, not a.no_browser)
