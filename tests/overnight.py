"""Clock times, time zones and events that run past midnight, against the
single-file build over file://.

    python build.py && python tests/overnight.py

1. Device time: the HUD clock reads the device's own wall-clock time, 12-hour
   with AM/PM, in whatever zone the device is set to.
2. Overnight event, 9 PM to 3 AM: the chart axis, line, peak marker and flow
   bars run continuously across midnight; tiles, narrative, Events card, tap
   table and CSV all read in local 12-hour time.
3. Daylight saving: events across a clock change, either direction, keep their
   true duration and plot on real elapsed time.
4. Live across midnight: with the device clock running through 12:00 AM, the
   HUD clock and elapsed time tick over by themselves, taps are stamped either
   side, and the event ends and files cleanly.

Every expected value is worked out here from the IANA zone database, never
read back from the app. The charts are checked as data: a spy records what
they draw. Needs playwright. Exits non-zero on any failure.
"""
import datetime as dt
import math
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

URL = (pathlib.Path(__file__).resolve().parent.parent / "dist" / "head-count.html").as_uri()
L, R = 34, 10                                   # frame() gutters
BUCKETS = [60e3, 120e3, 300e3, 600e3, 900e3, 1800e3, 3600e3, 7200e3]
TIME = re.compile(r"^\d{1,2}:\d{2} [AP]M$")
RANGE = re.compile(r"^\d{1,2}:\d{2}( [AP]M)?–\d{1,2}:\d{2} [AP]M$")
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MO = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Records what the charts draw, so the canvas can be checked as data.
SPY = """(() => {
  window.__draw = [];
  const P = CanvasRenderingContext2D.prototype;
  const wrap = (name, rec) => { const f = P[name]; P[name] = function (...a) {
    window.__draw.push(Object.assign({ op: name, id: this.canvas.id }, rec.call(this, ...a)));
    return f.apply(this, a); }; };
  wrap('fillText', function (text, x) { return { text: String(text), x, w: this.measureText(String(text)).width, align: this.textAlign }; });
  wrap('fillRect', function (x, y, w) { return { x, w, color: this.fillStyle }; });
  wrap('moveTo', x => ({ x }));
  wrap('lineTo', x => ({ x }));
  wrap('beginPath', () => ({}));
})();"""

SEED = """s => { localStorage.clear(); localStorage.setItem('hc.arch.v1', JSON.stringify([s]));
                reload(); render(); return ARCH.length; }"""

SHEET = """() => {
  window.__draw = []; refreshSheet(true);
  const all = sel => [...document.querySelectorAll(sel)];
  return {
    draw: window.__draw,
    W: document.getElementById('chart').clientWidth,
    FW: document.getElementById('flow').clientWidth,
    title: document.getElementById('sheetTitle').textContent,
    stats: all('#stats .stat').map(e => [...e.children].map(c => c.textContent)),
    insight: document.getElementById('insight').textContent,
    rows: all('#tbody tr').map(r => [...r.cells].map(c => c.textContent)),
    csv: csvOf(cur()),
  };
}"""

HUD = """() => { const e = document.getElementById('elapsed');
  return { clock: document.getElementById('clock').textContent, elapsed: e.hidden ? null : e.textContent }; }"""

failures, errors = [], []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{str(detail)[:240]}]" if detail != "" else ""))
    if not ok:
        failures.append(name)


# ---------------------------------------------------------------- oracle
def ms(d):
    return round(d.timestamp() * 1000)


def local(t, tz):
    return dt.datetime.fromtimestamp(t / 1000, tz)


def hm(t, tz, secs=False):
    d = local(math.floor(t), tz)
    s = f"{d.hour % 12 or 12}:{d.minute:02d}" + (f":{d.second:02d}" if secs else "")
    return s + (" AM" if d.hour < 12 else " PM")


def span_of(a, b, tz):
    x, y = hm(a, tz), hm(b, tz)
    return f"{x[:-3]}–{y}" if x[-2:] == y[-2:] else f"{x}–{y}"


def hms(n):
    s = max(0, n // 1000)
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}"


def dur_short(n):
    m = math.floor(n / 60000 + 0.5)
    if m < 60:
        return f"{m}m"
    h, r = divmod(m, 60)
    return f"{h}h {r}m" if r else f"{h}h"


def card_day(t, tz):
    d = local(t, tz)
    return f"{WD[d.weekday()]}, {MO[d.month - 1]} {d.day}, {d.year}"


def taps(t0, t1):
    """Filling for the first 3.5 hours, emptying after, so the peak lands after
    midnight. Under 300 taps, so the on-screen table holds all of them."""
    ev, occ = [], 0
    for m in range((t1 - t0) // 60000):
        base = t0 + m * 60000
        if m < 210:
            if m % 2 == 0:
                ev.append([base, 1]); occ += 1
            if m % 6 == 3:
                ev.append([base + 30000, -1]); occ -= 1
        else:
            if m % 2 == 0 and occ > 0:
                ev.append([base, -1]); occ -= 1
            if m % 10 == 5:
                ev.append([base + 30000, 1]); occ += 1
    return ev


# ---------------------------------------------------------------- sheet checks
def inspect(tag, got, tz, t0, t1, ev, midnight):
    span, W, FW, draw = t1 - t0, got["W"], got["FW"], got["draw"]

    def X(t, w=W):
        return L + (t - t0) / span * (w - L - R)

    # axes: evenly spaced local times, first and last exact, never touching
    for cid, width in (("chart", W), ("flow", FW)):
        labels = [d for d in draw if d["op"] == "fillText" and d["id"] == cid and TIME.match(d["text"])]
        texts, n = [d["text"] for d in labels], len(labels)
        want = [hm(t0 + span * i / (n - 1), tz) for i in range(n)] if n >= 2 else None
        check(f"{tag}: {cid} axis runs {' / '.join(texts)}",
              2 <= n <= 5 and texts == want and len(set(texts)) == n
              and texts[0] == hm(t0, tz) and texts[-1] == hm(t1, tz), want)
        gaps = [b["x"] - (a["x"] + a["w"]) for a, b in zip(labels, labels[1:])]
        fits = all(d["align"] == "left" and d["x"] >= 0 and d["x"] + d["w"] <= width + 0.5 for d in labels)
        check(f"{tag}: {cid} axis labels fit the canvas and never touch",
              fits and all(g >= 12 for g in gaps), [round(g) for g in gaps])

    # occupancy line: every tap at its own time, left to right, through midnight
    paths, cur = [], None
    for d in draw:
        if d["id"] != "chart":
            continue
        if d["op"] == "beginPath":
            cur = []; paths.append(cur)
        elif d["op"] in ("moveTo", "lineTo") and cur is not None:
            cur.append(d["x"])
    stroke = next((p for p in paths if len(p) == 2 * len(ev) + 2), None)
    fill = next((p for p in paths if len(p) == 2 * len(ev) + 4), None)
    want = [X(t0)] + [X(t) for t, _ in ev for _ in (0, 1)] + [X(t1)]
    check(f"{tag}: occupancy line plots all {len(ev)} taps at their true times",
          stroke is not None and max(abs(a - b) for a, b in zip(stroke, want)) < 0.01)
    check(f"{tag}: line and fill only ever move forward in time",
          stroke is not None and fill is not None
          and all(b >= a - 1e-9 for p in (stroke, fill) for a, b in zip(p, p[1:])))
    xm = X(midnight)
    check(f"{tag}: line continues either side of midnight",
          stroke is not None and sum(x < xm for x in stroke) > 2 and sum(x > xm for x in stroke) > 2)

    occ = peak = 0
    peak_at, ins = t0, []
    for t, d in ev:
        occ += d
        if d > 0:
            ins.append(t)
        if occ > peak:
            peak, peak_at = occ, t
    mark = [d for d in draw if d["id"] == "chart" and d["op"] == "fillText" and d["text"].startswith("peak ")]
    px = X(peak_at)
    check(f"{tag}: peak marker says {peak} at the peak's time",
          len(mark) == 1 and mark[0]["text"] == f"peak {peak}"
          and abs(mark[0]["x"] - (px + 6 if mark[0]["align"] == "left" else px - 6)) < 0.01, mark)

    # flow bars: each bucket at its own offset from the start
    unit = next((u for u in BUCKETS if span / u <= 48), BUCKETS[-1])
    nb = max(1, math.ceil(span / unit))
    cin, cout = [0] * nb, [0] * nb
    for t, d in ev:
        (cin if d > 0 else cout)[min(nb - 1, math.floor((t - t0) / unit))] += 1
    for color, counts, name in (("#3fd18b", cin, "arrival"), ("#ff8b83", cout, "exit")):
        xs = sorted(d["x"] for d in draw if d["op"] == "fillRect" and d["id"] == "flow" and d["color"] == color)
        want = [X(t0 + i * unit, FW) for i in range(nb) if counts[i]]
        check(f"{tag}: {len(want)} {name} bars sit in their time buckets",
              len(xs) == len(want) and all(abs(a - b) < 0.01 for a, b in zip(xs, want)), (len(xs), len(want)))
    before = sum(1 for i in range(nb) if (cin[i] or cout[i]) and t0 + i * unit < midnight)
    after = sum(1 for i in range(nb) if (cin[i] or cout[i]) and t0 + i * unit >= midnight)
    check(f"{tag}: flow bars both before and after midnight", before and after, (before, after))

    # tiles, narrative
    st = got["stats"]
    check(f"{tag}: peak tile", st[0] == [str(peak), "peak inside", "at " + hm(peak_at, tz)], st[0])
    check(f"{tag}: duration tile is true elapsed time",
          st[1] == [hms(span), "duration", "from " + hm(t0, tz)], st[1])
    check(f"{tag}: surge tiles show 12-hour ranges",
          bool(RANGE.match(st[2][2]) and RANGE.match(st[3][2])), [st[2][2], st[3][2]])
    median = ins[math.ceil(len(ins) / 2) - 1]
    check(f"{tag}: half-in-by tile", st[5][0] == hm(median, tz), st[5])
    check(f"{tag}: narrative names the peak in local time",
          f"Fullest at {hm(peak_at, tz)} with {peak} inside." in got["insight"], got["insight"])
    hours = [int(h) for h in re.findall(r"(\d{1,2}):\d{2}", got["insight"] + " ".join(s[2] for s in st) + st[5][0])]
    check(f"{tag}: no 24-hour times in tiles or narrative", hours and all(1 <= h <= 12 for h in hours), hours)

    # tap table, CSV
    occ, rows = 0, []
    for k, (t, d) in enumerate(ev):
        occ += d
        rows.append([str(k + 1), hm(t, tz, True), hms(t - t0), "IN" if d > 0 else "OUT", str(occ)])
    rows.reverse()
    bad = next(((g, w) for g, w in zip(got["rows"], rows) if g != w), None)
    check(f"{tag}: tap table, all {len(ev)} rows in local 12-hour time",
          len(got["rows"]) == len(rows) and bad is None, bad or len(got["rows"]))

    lines = got["csv"].rstrip("\r\n").split("\r\n")[1:]
    bad = []
    for line, (t, d) in zip(lines, ev):
        c = line.split(",")
        iso = dt.datetime.fromtimestamp(t // 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{t % 1000:03d}Z"
        loc = f"{local(t, tz):%Y-%m-%d} {hm(t, tz, True)}"
        if c[1] != iso or c[2] != loc or c[3] != str(t):
            bad.append(c[:4])
    check(f"{tag}: CSV local_time in 12-hour device time, iso_timestamp in UTC",
          len(lines) == len(ev) and not bad, bad[:2])


# ---------------------------------------------------------------- run
with sync_playwright() as pw:
    browser = pw.chromium.launch()

    def page(tz_name):
        ctx = browser.new_context(timezone_id=tz_name, locale="en-US", viewport={"width": 375, "height": 812})
        ctx.add_init_script(SPY)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"{tz_name}: {e}"))
        return ctx, pg

    # 1 -- device time ------------------------------------------------------
    instant = dt.datetime(2026, 9, 12, 9, 30, 15, tzinfo=dt.timezone.utc)
    for tz_name, want in (("Pacific/Auckland", "9:30 PM"), ("Asia/Kolkata", "3:00 PM"),
                          ("America/Los_Angeles", "2:30 AM"), ("UTC", "9:30 AM")):
        ctx, pg = page(tz_name)
        pg.clock.install(time=instant)
        pg.goto(URL)
        got = pg.evaluate(HUD)
        check(f"device time, {tz_name}: HUD clock reads {want}, no elapsed before the first tap",
              want == hm(ms(instant), ZoneInfo(tz_name)) and got == {"clock": want, "elapsed": None}, got)
        ctx.close()

    # 2 + 3 -- ended events across midnight and clock changes --------------
    cases = [
        ("overnight", "Australia/Sydney", (2026, 9, 12, 21), (2026, 9, 13, 3), 6),
        ("clocks go back", "America/New_York", (2026, 10, 31, 22), (2026, 11, 1, 4), 7),
        ("clocks go forward", "Australia/Sydney", (2026, 10, 3, 22), (2026, 10, 4, 4), 5),
    ]
    for tag, tz_name, a, b, hours in cases:
        tz = ZoneInfo(tz_name)
        t0, t1 = ms(dt.datetime(*a, tzinfo=tz)), ms(dt.datetime(*b, tzinfo=tz))
        midnight = ms(dt.datetime(*b[:3], tzinfo=tz))
        if t1 - t0 != hours * 3600000:
            sys.exit(f"oracle: {tag} should span {hours}h of real time")
        ev = taps(t0, t1)
        label = tag.title()
        ctx, pg = page(tz_name)
        pg.goto(URL)
        pg.evaluate(SEED, {"id": "s-" + tag.replace(" ", "-"), "label": label,
                           "startedAt": t0, "endedAt": t1, "ev": ev})
        pg.click("#btnEvents")
        card = pg.locator(".evopen").first.inner_text()
        want = f"{card_day(t0, tz)} · {span_of(t0, t1, tz)} · {dur_short(t1 - t0)}"
        check(f"{tag}: Events card reads {want}", want in card, card.replace("\n", " | "))
        pg.locator(".evopen").first.click()
        got = pg.evaluate(SHEET)
        check(f"{tag}: sheet title", got["title"] == label + " (ended)", got["title"])
        inspect(tag, got, tz, t0, t1, ev, midnight)
        ctx.close()

    # 4 -- live, with the device clock running through midnight ------------
    tz_name, tz = "Europe/London", ZoneInfo("Europe/London")
    start = dt.datetime(2026, 9, 12, 23, 58, tzinfo=tz)
    t0, midnight = ms(start), ms(dt.datetime(2026, 9, 13, tzinfo=tz))
    ctx, pg = page(tz_name)
    pg.clock.install(time=start - dt.timedelta(minutes=1))
    pg.goto(URL)
    pg.clock.pause_at(start)
    check("live: before the first tap, device time only", pg.evaluate(HUD) == {"clock": "11:58 PM", "elapsed": None},
          pg.evaluate(HUD))
    for _ in range(4):
        pg.click("#padIn")
        pg.clock.run_for(20000)
    pg.clock.run_for(45000)                          # 12:00:05 AM, no tap: the clock must tick over by itself
    got = pg.evaluate(HUD)
    check("live: HUD clock and elapsed tick past midnight on their own",
          got == {"clock": "12:00 AM", "elapsed": "00:02:05 elapsed"}, got)
    pg.click("#padOut")
    pg.clock.run_for(30000)
    pg.click("#padIn")
    now = t0 + 155000
    ev = [[t0, 1], [t0 + 20000, 1], [t0 + 40000, 1], [t0 + 60000, 1], [t0 + 125000, -1], [now, 1]]
    got = pg.evaluate("S.ev")
    check("live: taps stamped with device time either side of midnight", got == ev, got)

    pg.click("#btnData")
    got = pg.evaluate(SHEET)
    check("live: sheet title", got["title"] == "Event 2026-09-12 (live)", got["title"])
    inspect("live", got, tz, t0, now, ev, midnight)
    pg.clock.run_for(4500)                           # the sheet's 2 s redraw, twice
    pg.click("#sheetClose")

    pg.click("#btnEnd")
    pg.click("#dlgConfirm")
    pg.click("#sheetClose")
    pg.click("#btnEvents")
    card = pg.locator(".evopen").first.inner_text()
    want = f"{card_day(t0, tz)} · 11:58 PM–12:00 AM · 3m"
    check(f"live: ended event files as {want}", want in card, card.replace("\n", " | "))
    pg.click("#eventsClose")
    pg.clock.run_for(60000)
    check("live: after End the HUD keeps device time and drops elapsed",
          pg.evaluate(HUD) == {"clock": "12:01 AM", "elapsed": None}, pg.evaluate(HUD))
    ctx.close()

    browser.close()

check("no uncaught page errors", not errors, errors[:3])
print()
print(f"{'FAILED' if failures else 'ALL PASSED'}  ({len(failures)} failure{'s' if len(failures) != 1 else ''})")
sys.exit(1 if failures else 0)
