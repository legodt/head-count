"""Events archive integrity, run against the single-file build over file://.

    python build.py && python tests/archive.py

1. No cap: 35 ended events all survive a reload, with unique ids.
2. Storage full: End event refuses, leaving the live session untouched and
   still counting, then succeeds once space is freed.
3. Interrupted end: a session left in both the live slot and the archive
   resolves to the archive copy with the counter reset, never duplicated.
4. Delete persists across a reload.
5. Rename: the live event from the main screen, and an ended one from its data
   sheet - persisted, other events untouched, still right after a foreground
   reload, a no-op when cancelled, and refused cleanly when storage is full.

Needs playwright. Exits non-zero on any failure.
"""
import pathlib
import shutil
import sys
import tempfile

from playwright.sync_api import sync_playwright

URL = (pathlib.Path(__file__).resolve().parent.parent / "dist" / "head-count.html").as_uri()
PROFILE = pathlib.Path(tempfile.gettempdir()) / "hc-archive-profile"

TAP = "n => { for (let i = 0; i < n; i++) record(i % 3 ? 1 : -1); }"
STORED = """() => ({
  live: JSON.parse(localStorage.getItem('hc.active.v1')),
  arch: JSON.parse(localStorage.getItem('hc.arch.v1') || '[]'),
})"""
# Fill every remaining byte of the origin's quota with one filler key.
FILL = """() => {
  let lo = 0, hi = 1 << 25;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    try { localStorage.setItem('filler', 'x'.repeat(mid)); lo = mid; }
    catch { hi = mid - 1; }
  }
  localStorage.setItem('filler', 'x'.repeat(lo));
  return lo;
}"""

failures = []
# Prompt answers: None dismisses. The prompt's pre-filled value is recorded.
ANSWER = {"text": None, "seen": None}


def on_dialog(d):
    if d.type != "prompt":
        return d.accept()                          # confirm() on delete
    ANSWER["seen"] = d.default_value
    return d.dismiss() if ANSWER["text"] is None else d.accept(ANSWER["text"])


def labels(pg):
    return pg.evaluate("JSON.parse(localStorage.getItem('hc.arch.v1')).map(a => [a.label, a.ev.length])")


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail != "" else ""))
    if not ok:
        failures.append(name)


def fresh(pg):
    pg.evaluate("localStorage.clear()")
    pg.reload()


shutil.rmtree(PROFILE, ignore_errors=True)
with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(str(PROFILE), headless=True)
    pg = ctx.new_page()
    pg.on("dialog", on_dialog)
    pg.goto(URL)

    # 1 -- no cap ---------------------------------------------------------
    fresh(pg)
    for _ in range(35):
        pg.evaluate(TAP, 12)
        pg.evaluate("endEvent()")
    pg.reload()
    st = pg.evaluate("""() => { openEvents(); return {
      n: ARCH.length, ids: new Set(ARCH.map(a => a.id)).size,
      cards: document.querySelectorAll('.evcard').length } }""")
    check("35 ended events all kept after reload", st["n"] == 35, st["n"])
    check("every event id unique", st["ids"] == 35, st["ids"])
    check("Events screen lists all 35", st["cards"] == 35, st["cards"])

    # 2 -- storage full ---------------------------------------------------
    fresh(pg)
    pg.evaluate(TAP, 500)
    before = pg.evaluate(STORED)
    filled = pg.evaluate(FILL)
    pg.evaluate("endEvent()")
    after = pg.evaluate(STORED)
    check("full: stored live session untouched",
          after["live"]["ev"] == before["live"]["ev"] and not after["live"]["endedAt"],
          f"filler {filled / 1e6:.1f}M chars")
    check("full: stored archive unchanged", after["arch"] == [], len(after["arch"]))
    check("full: in-memory session still live",
          pg.evaluate("S.ev.length === 500 && !S.endedAt && ARCH.length === 0"))
    check("full: warning banner shown", pg.evaluate("!document.getElementById('warn').hidden"))

    pg.evaluate("localStorage.removeItem('filler')")
    pg.evaluate("endEvent()")
    after = pg.evaluate(STORED)
    check("space freed: end succeeds with all 500 taps",
          len(after["arch"]) == 1 and len(after["arch"][0]["ev"]) == 500 and after["live"]["ev"] == [])

    # 3 -- interrupted end ------------------------------------------------
    fresh(pg)
    pg.evaluate(TAP, 40)
    # The crash window: archive written, live slot not yet reset.
    pg.evaluate("localStorage.setItem('hc.arch.v1', JSON.stringify([Object.assign({}, S, { endedAt: Date.now() })]))")
    pg.reload()
    st = pg.evaluate("({ live: S.ev.length, arch: ARCH.length, archTaps: ARCH[0].ev.length })")
    stored = pg.evaluate(STORED)
    check("interrupted end: archive copy kept, not duplicated",
          st == {"live": 0, "arch": 1, "archTaps": 40}, st)
    check("interrupted end: live slot reset in storage too", stored["live"]["ev"] == [])

    # 4 -- delete persists ------------------------------------------------
    pg.evaluate(TAP, 10)
    pg.evaluate("endEvent()")
    pg.evaluate("openEvents(); deleteEvent(0)")
    pg.reload()
    st = pg.evaluate("({ n: ARCH.length, taps: ARCH[0].ev.length })")
    check("delete persists across reload", st == {"n": 1, "taps": 40}, st)

    # 5 -- rename ---------------------------------------------------------
    fresh(pg)
    pg.evaluate(TAP, 30); pg.evaluate("S.label = 'Friday'; save(true); endEvent()")
    pg.evaluate(TAP, 20); pg.evaluate("S.label = 'Saturday'; save(true); endEvent(); closeSheet()")
    pg.evaluate(TAP, 5)
    unnamed = "document.getElementById('label').classList.contains('unnamed')"
    check("unnamed live event: name button styled as a call to action", pg.evaluate(unnamed))

    ANSWER["text"] = "  Sunday Session  "
    pg.click("#label")
    pg.reload()
    st = pg.evaluate("({ label: S.label, shown: document.getElementById('label').textContent,"
                     " unnamed: " + unnamed + " })")
    check("live rename from main screen: trimmed, persisted, call to action gone",
          st == {"label": "Sunday Session", "shown": "Sunday Session", "unnamed": False}, st)

    pg.click("#btnEvents")
    pg.locator(".evopen").nth(1).click()                     # Friday, the older one
    ANSWER["text"] = "Friday Late"
    pg.click("#sheetRename")
    check("rename prompt starts from the current name", ANSWER["seen"] == "Friday", ANSWER["seen"])
    title = pg.evaluate("document.getElementById('sheetTitle').textContent")
    check("ended event renamed from data sheet: title updates", title == "Friday Late (ended)", title)
    st = labels(pg)
    check("ended event renamed: stored, taps and other events untouched",
          st == [["Saturday", 20], ["Friday Late", 30]]
          and pg.evaluate("JSON.parse(localStorage.getItem('hc.active.v1')).label") == "Sunday Session", st)
    pg.click("#sheetClose")
    cards = pg.evaluate("[...document.querySelectorAll('.evopen b')].map(b => b.textContent)")
    check("ended event renamed: Events list shows the new name", cards == ["Saturday", "Friday Late"], cards)

    pg.locator(".evopen").first.click()                      # Saturday
    pg.evaluate("reload()")                                  # foreground re-read: ARCH is now fresh objects
    ANSWER["text"] = "Saturday Warehouse"
    pg.click("#sheetRename")
    pg.reload()
    check("rename after a foreground reload lands on the right event, survives reload",
          labels(pg) == [["Saturday Warehouse", 20], ["Friday Late", 30]], labels(pg))

    pg.click("#btnEvents")
    pg.locator(".evopen").first.click()
    ANSWER["text"] = None
    pg.click("#sheetRename")
    check("cancelled rename changes nothing", labels(pg) == [["Saturday Warehouse", 20], ["Friday Late", 30]])

    pg.evaluate(FILL)
    ANSWER["text"] = "A much longer name that cannot fit in a full store"
    pg.click("#sheetRename")
    st = pg.evaluate("() => ({ mem: ARCH[0].label, title: document.getElementById('sheetTitle').textContent,"
                     " banner: !document.getElementById('warn').hidden })")
    check("storage full: rename refused - stored, in memory and on screen unchanged, banner shown",
          labels(pg) == [["Saturday Warehouse", 20], ["Friday Late", 30]]
          and st == {"mem": "Saturday Warehouse", "title": "Saturday Warehouse (ended)", "banner": True}, st)
    pg.evaluate("localStorage.removeItem('filler')")

    ctx.close()

print()
print(f"{'FAILED' if failures else 'ALL PASSED'}  ({len(failures)} failure{'s' if len(failures) != 1 else ''})")
sys.exit(1 if failures else 0)
