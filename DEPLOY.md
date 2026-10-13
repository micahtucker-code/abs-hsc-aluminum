# Publishing the web version

The `web/` folder is the whole site: plain files, no server code. Everything (including the Python
runtime, Pyodide 0.27.7) is served from your own domain, so there are no third-party dependencies and
vessel data never leaves the user's browser.

Suggested address: **checker.tucker-marine.com** (a subdomain leaves your main site alone).

## Option A - fastest: Netlify (or Cloudflare Pages), drag and drop
1. Create a free Netlify account, choose *Add new site > Deploy manually*, drop the `web` folder in.
2. In *Domain management* add `checker.tucker-marine.com` and follow the DNS instruction it shows
   (normally one CNAME record at your domain registrar). HTTPS is automatic.
3. To update: drop the new `web` folder again.

## Option B - best for continued development: GitHub Pages with automatic publishing
1. Put this project in a GitHub repository (private is fine on a paid plan; Pages on free plans needs a public repo).
2. Repo *Settings > Pages > Source: GitHub Actions*. The workflow in `.github/workflows/pages.yml` then runs the
   tests, builds the site and publishes it on every push to `main`. A failing test blocks the publish.
3. DNS: add a CNAME record `checker` -> `<your-github-username>.github.io`, then set the custom domain in *Settings > Pages*.
   (The workflow already writes the CNAME file for `checker.tucker-marine.com`; edit it if you pick another name.)

## Option C - your existing web host
Upload the contents of `web/` by FTP/cPanel into a folder or subdomain. The host must serve `.wasm` files with
type `application/wasm` (almost all do).

## Rebuilding locally
    # one-time: get the Pyodide core files into ./pyodide_core
    curl -L -o core.tar.bz2 https://github.com/pyodide/pyodide/releases/download/0.27.7/pyodide-core-0.27.7.tar.bz2
    tar xjf core.tar.bz2 && mv pyodide pyodide_core
    python build_web.py            # writes ./web
    python -m http.server -d web 8000   # test at http://localhost:8000

Bump `__version__` in `abs_hsc_al/__init__.py` for each release; it is shown in the page footer and used to
bust browser caches.

## Notes
- First visit downloads about 14 MB (6 MB compressed); later visits come from the browser cache.
- The page must be opened over http(s), not by double-clicking `index.html` (browsers block WebAssembly from file://).
- Add a simple "accepts no responsibility / not an ABS approval" line to your site terms if clients will use it.
