"""file:// durability for the single-file build, in a persistent Chromium profile.

Simulates the real overnight failure modes: tab reload, tab closed and
reopened, the whole browser killed and relaunched, and the file being moved.
"""
from playwright.sync_api import sync_playwright
import pathlib, shutil, tempfile

SRC = pathlib.Path(r"D:\OneDrive\Work\Claude\head-count\dist\head-count.html")
PROFILE = pathlib.Path(tempfile.gettempdir()) / "hc-profile"
shutil.rmtree(PROFILE, ignore_errors=True)

MOVED_DIR = pathlib.Path(tempfile.gettempdir()) / "hc-moved"
MOVED_DIR.mkdir(exist_ok=True)
MOVED = MOVED_DIR / "head-count.html"
shutil.copy(SRC, MOVED)

state = "({occ: fold(S).occ, n: S.ev.length, shown: document.getElementById('occ').textContent})"

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(str(PROFILE), headless=True)
    pg = ctx.new_page()
    pg.goto(SRC.as_uri())
    pg.evaluate("for(let i=0;i<40;i++) record(1); for(let i=0;i<15;i++) record(-1);")
    print("1 after tapping        :", pg.evaluate(state))

    pg.reload()
    print("2 after reload         :", pg.evaluate(state))

    pg.close()
    pg = ctx.new_page(); pg.goto(SRC.as_uri())
    print("3 tab closed + reopened:", pg.evaluate(state))

    pg2 = ctx.new_page(); pg2.goto(MOVED.as_uri())
    print("4 file copied elsewhere:", pg2.evaluate(state))
    ctx.close()

    # the browser itself is killed and relaunched on the same profile
    ctx = pw.chromium.launch_persistent_context(str(PROFILE), headless=True)
    pg = ctx.new_page(); pg.goto(SRC.as_uri())
    final = pg.evaluate(state)
    print("5 browser relaunched   :", final)

    pg.evaluate("document.getElementById('btnData').click()")
    print("   insight:", pg.evaluate("document.getElementById('insight').textContent"))
    print("   csv rows:", pg.evaluate("csvOf(S).trim().split(String.fromCharCode(13,10)).length"))
    ctx.close()

print("RESULT:", "PASS" if final["n"] == 55 and final["occ"] == 25 else "FAIL")
