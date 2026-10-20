"""Door Read (tools/analyze.html) against a night whose answers are worked out
here rather than read back from the page.

    python tests/analyze.py

Feeds it a Head Count CSV recorded in UTC+10 while the browser sits in Chicago,
so the times on screen prove the door's own zone is used, not the reader's.
Checks the headline figures, that the three charts and the folded tables
render, that hover and the capacity input work, that the page makes no group or
door-pressure claims, and that neither theme nor a 390px phone scrolls
sideways. Needs playwright. Exits non-zero on any failure.
"""
import datetime as dt
import pathlib
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "tools" / "analyze.html").as_uri()
CSV = pathlib.Path(tempfile.gettempdir()) / "hc-known-night.csv"

# ---- a night with answers known here -------------------------------------
TZ = dt.timezone(dt.timedelta(hours=10))                     # fixed offset, no DST
t0 = int(dt.datetime(2026, 9, 12, 21, 0, tzinfo=TZ).timestamp() * 1000)
ev, occ = [], 0
for m in range(360):                                          # 9 PM -> 3 AM
    base = t0 + m * 60000
    if m < 200:                                               # filling
        ev.append([base, 1])
        if m % 3 == 0:
            ev.append([base + 20000, 1])
        if m % 5 == 2 and occ > 0:
            ev.append([base + 40000, -1])
    else:                                                     # emptying
        if m % 2 == 0:
            ev.append([base, -1])
        if m % 7 == 3:
            ev.append([base + 30000, 1])
    occ = sum(d for _, d in ev)
ev.sort()

occ = peak = 0
peak_at = t0
tin = tout = 0
for t, d in ev:
    occ += d
    if d > 0:
        tin += 1
    else:
        tout += 1
    if occ > peak:
        peak, peak_at = occ, t
t1 = ev[-1][0]
span_min = round((t1 - t0) / 60000)
expect = {
    "guests in": f"{tin:,}",
    "peak inside": f"{peak:,}",
    "door open": f"{span_min // 60}h {span_min % 60}m" if span_min % 60 else f"{span_min // 60}h",
    "turnover": f"{tin / peak:.1f}×",
}
peak_hm = dt.datetime.fromtimestamp(peak_at / 1000, TZ)
expect_peak_at = f"at {peak_hm.hour % 12 or 12}:{peak_hm.minute:02d} {'AM' if peak_hm.hour < 12 else 'PM'}"

rows = ["seq,iso_timestamp,local_time,epoch_ms,elapsed_s,elapsed_hms,direction,delta,occupancy,cumulative_in,cumulative_out"]
occ = ci = co = 0
for i, (t, d) in enumerate(ev):
    occ += d
    ci += d > 0
    co += d < 0
    loc = dt.datetime.fromtimestamp(t / 1000, TZ)
    h12 = f"{loc.hour % 12 or 12}:{loc.minute:02d}:{loc.second:02d} {'AM' if loc.hour < 12 else 'PM'}"
    iso = dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{t % 1000:03d}Z"
    rows.append(f"{i+1},{iso},{loc:%Y-%m-%d} {h12},{t},{(t-t0)/1000:.3f},,{'IN' if d > 0 else 'OUT'},{d},{occ},{ci},{co}")
CSV.write_text("﻿" + "\r\n".join(rows) + "\r\n", encoding="utf-8")
print(f"known night: {tin} in, {tout} out, peak {peak} at {expect_peak_at}, span {span_min} min, {len(ev)} taps")

failures = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{str(detail)[:200]}]" if detail != "" else ""))
    if not ok:
        failures.append(name)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    # viewer in a different zone than the door, to prove times are shown as recorded
    ctx = b.new_context(viewport={"width": 1180, "height": 1000}, device_scale_factor=2,
                        timezone_id="America/Chicago", locale="en-US")
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)

    pg.goto(PAGE)
    pg.wait_for_selector("#strip .fig")
    check("opens on a sample night", "Sample night" in pg.inner_text("#source"), pg.inner_text("#source")[:80])

    pg.set_input_files("#file", str(CSV))
    pg.wait_for_function("document.getElementById('source').textContent.includes('known-night')", timeout=5000)
    figs = pg.eval_on_selector_all("#strip .fig", "ns => ns.map(n => [n.querySelector('span').textContent, n.querySelector('b').textContent, n.querySelector('i') ? n.querySelector('i').textContent : ''])")
    got = {label: value for label, value, _ in figs}
    check("five figures, no more", len(figs) == 5, [f[0] for f in figs])
    for k, v in expect.items():
        check(f"figure {k} = {v}", got.get(k) == v, got.get(k))
    peak_note = next(n for l, v, n in figs if l == "peak inside")
    check(f"peak time shown as recorded at the door ({expect_peak_at})", peak_note == expect_peak_at, peak_note)

    layout = pg.evaluate("""() => ({
      sections: [...document.querySelectorAll('main section')].map(s => s.id),
      plots: [...document.querySelectorAll('.plot')].map(p => p.id),
      svgs: document.querySelectorAll('.plot svg').length,
      hours: document.querySelectorAll('#hours tbody tr').length,
      chips: document.querySelectorAll('.chip').length,
      log: document.querySelectorAll('#log tbody tr').length,
      folded: [...document.querySelectorAll('details')].every(d => !d.open),
    })""")
    check("three sections: summary, charts, trust",
          layout["sections"] == ["summary", "charts", "trust"], layout["sections"])
    check("three charts, in order: how full, the door, how long",
          layout["plots"] == ["plotOcc", "plotFlow", "plotDwell"] and layout["svgs"] == 3, layout["plots"])
    check("hour rows and the tap log are present but folded away",
          layout["hours"] >= 6 and layout["log"] > 100 and layout["folded"], layout)
    check("four check chips", layout["chips"] == 4, layout["chips"])

    read = pg.inner_text("#narrative")
    check("the read is three sentences at most", read.count(".") <= 3, read)
    check("no group or door-pressure claims", "group" not in pg.inner_text("main").lower(),
          "bunching is set by trains and queue clearance, not by who came together")

    pg.hover("#plotOcc")
    pg.mouse.move(600, pg.evaluate("document.getElementById('plotOcc').getBoundingClientRect().top + 110"))
    tip = pg.evaluate("""() => { const t = document.querySelector('#plotOcc .tip');
                                 return t && !t.hidden ? t.textContent : null; }""")
    check("occupancy chart has a working hover readout", bool(tip), tip)

    pg.fill("#capacity", "250")
    pg.wait_for_timeout(250)
    hint = pg.inner_text("#caphint")
    check("capacity feeds the headroom hint", "spare" in hint or "over" in hint, hint)

    check("no horizontal scroll at 1180px", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))

    pg.emulate_media(color_scheme="dark")
    pg.set_viewport_size({"width": 390, "height": 900})
    pg.wait_for_timeout(400)
    pg.evaluate("render()")
    check("no horizontal scroll at 390px",
          pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),
          pg.evaluate("document.documentElement.scrollWidth"))

    check("no page errors", not errs, errs[:3])
    ctx.close()
    b.close()

print()
print(f"{'FAILED' if failures else 'ALL PASSED'}  ({len(failures)} failure{'s' if len(failures) != 1 else ''})")
sys.exit(1 if failures else 0)
