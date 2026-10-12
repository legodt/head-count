"""The physical clicker's input path, run against the single-file build.

    python build.py && python tests/clicker.py

The clicker is an HID keyboard sending the arrows app.js already counts, so
everything it does can be tested without it. What matters:

1. A key records exactly what the matching pad records, and Backspace undoes.
2. A held or stuck button records nothing beyond the first press - the one
   failure that would quietly invent hundreds of guests.
3. Arrows never scroll: the default is cancelled, so a press cannot drag the
   data sheet out from under the count.
4. Keys are ignored while the end dialog is open or a text field has focus,
   and Escape still closes sheets.
5. Every clicker key answers with its own tone and no pad tap does - over
   one-way HID that tone is the only proof a press was counted, so an undo with
   nothing to undo must still make a sound. Silence has to mean one thing only:
   not receiving.
6. The screen wake lock is taken while visible, dropped on hide, retaken on
   return. Without it the screen sleeps and presses vanish.

Needs playwright. Exits non-zero on any failure.
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

URL = (pathlib.Path(__file__).resolve().parent.parent / "dist" / "head-count.html").as_uri()

# Installed before app.js. The wake lock and AudioContext are stubbed rather
# than driven for real: headless Chromium has no screen to keep awake and no
# speaker, and what is under test is this app's logic, not the browser's.
SPY = """
window.__wake = [];
Object.defineProperty(navigator, 'wakeLock', {
  configurable: true,
  value: { request: () => { window.__wake.push('request');
    return Promise.resolve({ release() { window.__wake.push('release'); }, addEventListener() {} }); } }
});

let hidden = false;
Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
window.__setHidden = v => { hidden = v; document.dispatchEvent(new Event('visibilitychange')); };

window.__blips = [];
window.AudioContext = function () {
  this.state = 'running';
  this.currentTime = 0;
  this.destination = {};
  this.resume = function () {};
  this.createOscillator = function () {
    const o = { frequency: {}, connect: n => n, stop() {} };
    o.start = () => window.__blips.push(o.frequency.value);
    return o;
  };
  this.createGain = function () {
    return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect: n => n };
  };
};
"""

STATE = "() => ({ n: S.ev.length, occ: fold(S).occ, shown: document.getElementById('occ').textContent })"

failures = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail != "" else ""))
    if not ok:
        failures.append(name)


# The init script re-runs on every reload, so the spies reset themselves - and
# must not be cleared afterwards, or boot's own wake lock request is wiped.
def fresh(pg):
    pg.evaluate("localStorage.clear()")
    pg.reload()


# Dispatches a keydown we control - the only way to present repeat:true, which
# is what a host OS sends for a button held down.
FIRE = """([key, repeat]) => {
  const e = new KeyboardEvent('keydown', { key, repeat, bubbles: true, cancelable: true });
  document.dispatchEvent(e);
  return e.defaultPrevented;
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context()
    ctx.add_init_script(SPY)
    pg = ctx.new_page()
    pg.goto(URL)
    fresh(pg)

    # 1. a key counts exactly like a pad
    pg.keyboard.press("ArrowUp")
    pg.keyboard.press("ArrowUp")
    pg.keyboard.press("ArrowDown")
    by_key = pg.evaluate(STATE)
    fresh(pg)
    pg.click("#padIn"); pg.click("#padIn"); pg.click("#padOut")
    by_pad = pg.evaluate(STATE)
    check("arrow keys record exactly what the pads record", by_key == by_pad == {"n": 3, "occ": 1, "shown": "1"},
          f"key={by_key} pad={by_pad}")

    fresh(pg)
    pg.keyboard.press("i"); pg.keyboard.press("o")
    check("i / o still count, for desktop testing", pg.evaluate(STATE)["n"] == 2)

    # 2. a held button is one guest, not forty
    fresh(pg)
    pg.keyboard.down("ArrowUp")
    for _ in range(40):
        pg.evaluate(FIRE, ["ArrowUp", True])
    pg.keyboard.up("ArrowUp")
    st = pg.evaluate(STATE)
    check("a button held down records exactly one tap", st == {"n": 1, "occ": 1, "shown": "1"}, st)

    # 3. an arrow must never scroll the page out from under the count
    check("arrow keys cancel their default (no scrolling)",
          pg.evaluate(FIRE, ["ArrowUp", False]) and pg.evaluate(FIRE, ["ArrowDown", False]))
    pg.evaluate("document.getElementById('btnData').click()")
    before = pg.evaluate("document.querySelector('#sheet .sheetbody').scrollTop")
    pg.keyboard.press("ArrowDown"); pg.keyboard.press("ArrowDown")
    after = pg.evaluate("document.querySelector('#sheet .sheetbody').scrollTop")
    check("data sheet does not scroll while the clicker counts", before == after, f"{before} -> {after}")

    # 4. ignored where a key means something else
    pg.keyboard.press("Escape")
    check("Escape still closes the data sheet", pg.evaluate("document.getElementById('sheet').hidden"))

    fresh(pg)
    pg.evaluate("record(1)")
    pg.evaluate("document.getElementById('btnEnd').click()")
    n_before = pg.evaluate("S.ev.length")
    pg.keyboard.press("ArrowUp"); pg.keyboard.press("ArrowDown")
    check("keys are ignored while the end dialog is open", pg.evaluate("S.ev.length") == n_before)
    pg.evaluate("document.getElementById('dlgCancel').click()")

    fresh(pg)
    pg.evaluate("const i = document.createElement('input'); i.id = '__t'; document.body.appendChild(i); i.focus();")
    pg.keyboard.press("i"); pg.keyboard.press("ArrowUp")
    check("keys are ignored while a text field has focus", pg.evaluate("S.ev.length") == 0)
    pg.evaluate("document.getElementById('__t').remove()")

    # 4b. undo, the third button
    fresh(pg)
    pg.keyboard.press("ArrowUp"); pg.keyboard.press("ArrowUp"); pg.keyboard.press("ArrowDown")
    pg.keyboard.press("Backspace")
    check("Backspace removes the last tap", pg.evaluate(STATE) == {"n": 2, "occ": 2, "shown": "2"},
          pg.evaluate(STATE))
    pg.keyboard.press("u")
    check("u undoes too, for desktop testing", pg.evaluate("S.ev.length") == 1)

    pg.evaluate("window.__blips = []")
    pg.keyboard.down("Backspace")
    for _ in range(20):
        pg.evaluate(FIRE, ["Backspace", True])
    pg.keyboard.up("Backspace")
    check("a held undo removes exactly one tap", pg.evaluate("S.ev.length") == 0)
    check("a held undo answers exactly once", pg.evaluate("window.__blips") == [740, 370],
          pg.evaluate("window.__blips"))

    check("undo cancels its default - Backspace must not navigate back",
          pg.evaluate(FIRE, ["Backspace", False]))

    # 5. the tones are the only acknowledgement the clicker ever gets
    fresh(pg)
    pg.keyboard.press("ArrowUp"); pg.keyboard.press("ArrowDown"); pg.keyboard.press("ArrowUp")
    blips = pg.evaluate("window.__blips")
    check("every key tap blips, high for in and low for out", blips == [880, 494, 880], blips)

    pg.evaluate("window.__blips = []")
    pg.keyboard.press("Backspace")
    check("undo answers with a falling pair", pg.evaluate("window.__blips") == [740, 370],
          pg.evaluate("window.__blips"))

    # silence must only ever mean "not receiving", so a no-op undo still speaks
    fresh(pg)
    pg.keyboard.press("Backspace")
    check("undo with nothing to undo still makes a sound", pg.evaluate("window.__blips") == [200],
          pg.evaluate("window.__blips"))
    check("undo with nothing to undo changes nothing", pg.evaluate("S.ev.length") == 0)

    fresh(pg)
    pg.click("#padIn"); pg.click("#padOut")
    check("pad taps stay silent - they already flash and vibrate", pg.evaluate("window.__blips") == [])

    pg.click("#btnUndo")
    check("the on-screen Undo button stays silent too", pg.evaluate("window.__blips") == [])
    check("the on-screen Undo button still works", pg.evaluate("S.ev.length") == 1)

    # 6. no wake lock, no clicker: the screen sleeps and presses vanish
    fresh(pg)
    pg.wait_for_function("window.__wake.length > 0")
    check("a wake lock is held while the app is visible", pg.evaluate("window.__wake") == ["request"])

    pg.evaluate("window.__setHidden(true)")
    check("the wake lock is released when the app is hidden", pg.evaluate("window.__wake") == ["request", "release"])

    pg.evaluate("window.__setHidden(false)")
    pg.wait_for_function("window.__wake.length > 2")
    check("the wake lock is retaken on return to the foreground",
          pg.evaluate("window.__wake") == ["request", "release", "request"])

    pg.keyboard.press("ArrowUp")
    check("the clicker still counts after a hide and return", pg.evaluate("S.ev.length") == 1)

    # holdWake() runs on every tap, so it must stay cheap across a whole night
    fresh(pg)
    pg.wait_for_function("window.__wake.length > 0")
    pg.evaluate("for (let i = 0; i < 200; i++) record(1)")
    check("200 taps do not re-request a lock already held", pg.evaluate("window.__wake") == ["request"],
          pg.evaluate("window.__wake.length"))

    ctx.close()

    # a browser that refuses must be asked once per foreground, not once per tap
    ctx = br.new_context()
    ctx.add_init_script(SPY.replace("window.__wake.push('request');",
                                    "window.__wake.push('request'); return Promise.reject(new Error('denied'));"))
    pg = ctx.new_page()
    pg.goto(URL)
    fresh(pg)
    pg.wait_for_function("window.__wake.length > 0")
    pg.evaluate("for (let i = 0; i < 200; i++) record(1)")
    denied = pg.evaluate("window.__wake")
    check("a refused wake lock is not re-requested on every tap", denied == ["request"], len(denied))
    check("counting is completely unaffected by a refused wake lock",
          pg.evaluate(STATE) == {"n": 200, "occ": 200, "shown": "200"})

    pg.evaluate("window.__setHidden(true); window.__setHidden(false);")
    pg.wait_for_function("window.__wake.length > 1")
    check("a refusal is retried once on the next foreground", pg.evaluate("window.__wake") == ["request", "request"])

    ctx.close()
    br.close()

print()
print(f"{'FAILED' if failures else 'ALL PASSED'}  ({len(failures)} failure{'s' if len(failures) != 1 else ''})")
sys.exit(1 if failures else 0)
