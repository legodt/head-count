"""The clicker display downlink, run against the single-file build.

    python build.py && python tests/link.py

The clicker counts nothing. If it has a screen, the host fills it, so what the
packet says is what the door sees. What matters:

1. Web Bluetooth absent (iOS, every Safari) - no button, no calls, nothing
   changed. This is the primary host, so it has to be exactly as before.
2. The packet decodes to the app's own numbers, negative occupancy included.
3. The series is a faithful step resample of occupancy over the whole session,
   in even time columns, ending at the current value.
4. Every tap and undo pushes at once - a door cannot wait a second to see the
   number move.
5. A write that fails drops the link instead of throwing on every later tap.

Needs playwright. Exits non-zero on any failure.
"""
import pathlib
import struct
import sys

from playwright.sync_api import sync_playwright

URL = (pathlib.Path(__file__).resolve().parent.parent / "dist" / "head-count.html").as_uri()

# A fake Web Bluetooth stack that records every packet written.
BT = """
window.__writes = [];
window.__failNext = false;
const chr = {
  writeValueWithoutResponse(buf) {
    if (window.__failNext) { window.__failNext = false; return Promise.reject(new Error('gone')); }
    window.__writes.push(Array.from(new Uint8Array(buf)));
    return Promise.resolve();
  }
};
const dev = {
  addEventListener() {},
  gatt: { connect: () => Promise.resolve({
    getPrimaryService: () => Promise.resolve({ getCharacteristic: () => Promise.resolve(chr) })
  }) }
};
Object.defineProperty(navigator, 'bluetooth', {
  configurable: true,
  value: { requestDevice: () => Promise.resolve(dev) }
});
"""

failures = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail != "" else ""))
    if not ok:
        failures.append(name)


def decode(p):
    ver, flags, occ, peak, lo, hi, n = struct.unpack_from("<BBhhhhB", bytes(p))
    return {"ver": ver, "live": flags & 1, "occ": occ, "peak": peak,
            "lo": lo, "hi": hi, "n": n, "series": list(p[11:11 + n])}


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)

    # 1. no Web Bluetooth: the app must be untouched. Chromium ships the API, so
    # iOS has to be simulated by taking it away.
    ctx = br.new_context()
    ctx.add_init_script("delete Navigator.prototype.bluetooth;"
                        "Object.defineProperty(navigator, 'bluetooth',"
                        " { configurable: true, value: undefined });")
    pg = ctx.new_page()
    pg.goto(URL)
    pg.evaluate("localStorage.clear()"); pg.reload()
    check("without Web Bluetooth the Clicker button stays hidden",
          pg.evaluate("document.getElementById('btnLink').hidden") is True)
    pg.keyboard.press("ArrowUp"); pg.keyboard.press("ArrowUp"); pg.keyboard.press("ArrowDown")
    check("without Web Bluetooth counting is completely unaffected",
          pg.evaluate("S.ev.length") == 3 and pg.evaluate("fold(S).occ") == 1)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.keyboard.press("ArrowUp")
    check("without Web Bluetooth a tap raises no error", errs == [], errs)
    ctx.close()

    # 2-5. with Web Bluetooth
    ctx = br.new_context()
    ctx.add_init_script(BT)
    pg = ctx.new_page()
    pg.goto(URL)
    pg.evaluate("localStorage.clear()"); pg.reload()
    check("with Web Bluetooth the Clicker button appears",
          pg.evaluate("document.getElementById('btnLink').hidden") is False)

    pg.click("#btnLink")
    pg.wait_for_function("window.__writes.length > 0")
    check("connecting marks the button as linked",
          pg.evaluate("document.getElementById('btnLink').textContent").strip().endswith("✓"))

    # a session with a real shape, and a dip below zero
    pg.evaluate("window.__writes = []")
    pg.evaluate("""() => {
      const t0 = Date.now() - 60000;
      S.startedAt = t0;
      S.ev = [];
      for (let i = 0; i < 10; i++) S.ev.push([t0 + i * 2000, 1]);          // climb to 10
      for (let i = 0; i < 13; i++) S.ev.push([t0 + 20000 + i * 2000, -1]); // down to -3
      save();
    }""")
    pg.evaluate("linkPush()")
    pg.wait_for_function("window.__writes.length > 0")
    p = decode(pg.evaluate("window.__writes[0]"))

    check("packet carries version and live flag", p["ver"] == 1 and p["live"] == 1, p["ver"])
    check("packet occupancy matches the app, negative and all", p["occ"] == -3, p["occ"])
    check("packet peak matches the app", p["peak"] == 10, p["peak"])
    check("packet range brackets the session", p["lo"] == -3 and p["hi"] == 10, (p["lo"], p["hi"]))
    check("packet carries a full column of series", p["n"] == 96, p["n"])
    check("packet fits one MTU", len(pg.evaluate("window.__writes[0]")) <= 107,
          len(pg.evaluate("window.__writes[0]")))

    s = p["series"]
    check("series starts near the bottom of the range", s[0] < 80, s[0])
    check("series peaks at full scale", max(s) == 255, max(s))
    check("series ends at the current occupancy, which is the floor", s[-1] == 0, s[-1])
    # slices kept clear of the turn itself: one column there spans the last
    # arrival and the first exit, so it is legitimately neither rising nor falling
    rise, fall = s[:28], s[56:]
    check("series rises over the arrivals", rise == sorted(rise), rise[:6])
    check("series falls and flattens over the exits", fall == sorted(fall, reverse=True), fall[:6])

    # decoding the series back through the stated scale must land on real numbers
    back = [p["lo"] + v * (p["hi"] - p["lo"]) / 255 for v in s]
    check("series decodes back to the true peak", abs(max(back) - 10) < 0.5, round(max(back), 2))
    check("series decodes back to the true final occupancy", abs(back[-1] - -3) < 0.5, round(back[-1], 2))

    # 4. a door cannot wait a second to see the number move
    pg.evaluate("window.__writes = []")
    pg.keyboard.press("ArrowUp")
    pg.wait_for_function("window.__writes.length > 0")
    check("a tap pushes immediately", decode(pg.evaluate("window.__writes[0]"))["occ"] == -2,
          decode(pg.evaluate("window.__writes[0]"))["occ"])

    pg.evaluate("window.__writes = []")
    pg.keyboard.press("Backspace")
    pg.wait_for_function("window.__writes.length > 0")
    check("an undo pushes immediately", decode(pg.evaluate("window.__writes[0]"))["occ"] == -3,
          decode(pg.evaluate("window.__writes[0]"))["occ"])

    # 5. a dead link must not throw on every tap for the rest of the night
    pg.evaluate("window.__failNext = true")
    pg.keyboard.press("ArrowUp")
    pg.wait_for_function("window.__writes.length === 0 || true")
    pg.wait_for_function("() => document.getElementById('btnLink').textContent.indexOf('✓') === -1")
    check("a failed write drops the link and resets the button", pg.evaluate("link") is None)
    pg.evaluate("window.__writes = []")
    pg.keyboard.press("ArrowUp"); pg.keyboard.press("ArrowUp")
    check("counting continues after the link drops", pg.evaluate("S.ev.length") == 26,
          pg.evaluate("S.ev.length"))
    check("nothing is pushed once the link is gone", pg.evaluate("window.__writes") == [])

    ctx.close()
    br.close()

print()
print(f"{'FAILED' if failures else 'ALL PASSED'}  ({len(failures)} failure{'s' if len(failures) != 1 else ''})")
sys.exit(1 if failures else 0)
