"""Update-path safety for the served build.

    python build.py && python tests/update.py

1. Mismatched deploy: the new app.js paired with the page deployed before it
   (tests/fixtures/index-v6.html) still boots, counts, and keeps the count
   across a reload.
2. The service worker never writes to its cache after install, so a file
   changed on the server is not picked up piecemeal and every page load is
   built from one version.
3. Bumping CACHE still installs the complete new shell in one step and purges
   the old cache.

Serves temporary copies of docs/ with HTTP caching disabled, so anything the
browser sees change is the worker's doing. Needs playwright. Exits non-zero on
any failure.
"""
import contextlib
import functools
import http.server
import pathlib
import re
import shutil
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OLD_PAGE = ROOT / "tests" / "fixtures" / "index-v6.html"
CACHE = re.search(r"const CACHE = '([^']+)'", (DOCS / "sw.js").read_text(encoding="utf-8")).group(1)
MARK = "\n// changed on the server\n"

# Evaluated in the page. Guarded, so a dead script reports instead of crashing the test.
STATE = """() => { try { return { n: S.ev.length, shown: document.getElementById('occ').textContent }; }
                  catch (e) { return 'threw: ' + e.message; } }"""
# CacheStorage.match with cacheName never creates the cache as a side effect.
CACHED_APP = "async name => { const r = await caches.match('app.js', { cacheName: name }); return r ? r.text() : null; }"

failures = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail != "" else ""))
    if not ok:
        failures.append(name)


class NoStore(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def served_copy(adjust=None):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="hc-update-"))
    shutil.copytree(DOCS, tmp, dirs_exist_ok=True)
    if adjust:
        adjust(tmp)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(NoStore, directory=str(tmp)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield tmp, f"http://127.0.0.1:{httpd.server_address[1]}/"
    finally:
        httpd.shutdown()
        httpd.server_close()
        shutil.rmtree(tmp, ignore_errors=True)


def poll(pg, js, want, tries=60):
    got = None
    for _ in range(tries):
        got = pg.evaluate(js)
        if got == want:
            break
        pg.wait_for_timeout(250)
    return got


with sync_playwright() as pw:
    browser = pw.chromium.launch()

    # 1 -- new script on the previous page -----------------------------------
    with served_copy(lambda tmp: shutil.copy(OLD_PAGE, tmp / "index.html")) as (tmp, url):
        ctx = browser.new_context(service_workers="block")
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url)
        for sel in ("#padIn", "#padIn", "#padIn", "#padOut"):
            pg.click(sel)
        live = pg.evaluate(STATE)
        pg.reload()
        again = pg.evaluate(STATE)
        check("previous page + new script: pads count", live == {"n": 4, "shown": "2"}, live)
        check("previous page + new script: count survives reload and renders",
              again == {"n": 4, "shown": "2"}, again)
        check("previous page + new script: no uncaught errors", not errors, "; ".join(errors)[:160])
        ctx.close()

    # 2 + 3 -- worker cache consistency --------------------------------------
    with served_copy() as (tmp, url):
        ctx = browser.new_context()
        pg = ctx.new_page()
        pg.goto(url)
        pg.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
        original = (tmp / "app.js").read_bytes().decode("utf-8")
        check("installed cache holds the served app.js", pg.evaluate(CACHED_APP, CACHE) == original)

        (tmp / "app.js").write_bytes((original + MARK).encode("utf-8"))
        for _ in range(3):
            pg.reload()
            pg.wait_for_timeout(600)
        check("server change not written into the live cache", pg.evaluate(CACHED_APP, CACHE) == original)
        check("page still loads the installed version",
              pg.evaluate("async () => (await fetch('app.js')).text()") == original)

        sw = (tmp / "sw.js").read_bytes().decode("utf-8")
        (tmp / "sw.js").write_bytes(sw.replace(f"'{CACHE}'", f"'{CACHE}-next'").encode("utf-8"))
        pg.reload()
        keys = poll(pg, "async () => (await caches.keys()).sort()", [f"{CACHE}-next"])
        check("bumped CACHE replaces the old cache entirely", keys == [f"{CACHE}-next"], keys)
        count = pg.evaluate(f"async () => (await (await caches.open('{CACHE}-next')).keys()).length")
        check("new cache holds the complete shell", count == 9, count)
        pg.reload()
        check("next load gets the new version",
              pg.evaluate("async () => (await fetch('app.js')).text()") == original + MARK)
        ctx.close()

    browser.close()

print()
print(f"{'FAILED' if failures else 'ALL PASSED'}  ({len(failures)} failure{'s' if len(failures) != 1 else ''})")
sys.exit(1 if failures else 0)
