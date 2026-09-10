# Head Count — spec

Offline counter for people in and out of a venue across one long event
(typically a whole night, phone locked most of it). Plain HTML/CSS/JS, no
dependencies, no network calls, no framework.

## Two builds, one source
- **Served** — `index.html` + `styles.css` + `app.js` + `sw.js` +
  `manifest.webmanifest` + `icons/`. Installs to a home screen.
  Bump `CACHE` in `sw.js` on **any** shell change or clients keep the old app.
- **Single file** — `python build.py` → `dist/head-count.html`. Inlines the CSS,
  JS and favicon; drops the manifest and worker (neither works on `file://`).
  Opened straight from disk, no server. `build.py` refuses to ship if anything
  failed to inline.

`app.js` skips service-worker registration when `location.protocol === 'file:'`,
so the same source runs unmodified in both.

## Model
`Session = { id, label, startedAt, endedAt, ev: [[epochMs, +1|-1], ...] }`

- `startedAt` is set by the first tap, not by page load.
- Occupancy = running sum of deltas. **Negative is allowed** and shown amber:
  people already inside before counting began are entitled to leave.
- Keys: `hc.active.v1` (live session, rewritten on *every* tap),
  `hc.active.bak.v1` (identical copy every 10 taps, **read back to prove the
  write landed**; `loadActive` takes whichever copy parses and holds more taps),
  `hc.arch.v1` (last 30 ended sessions).
- All localStorage access goes through `LS`, which never throws. If storage is
  unavailable or a write fails, a persistent amber banner appears telling the
  user to export the CSV — the app keeps counting in memory rather than dying.
  Re-probed on every return to the foreground, and the banner clears itself.
- State is re-read from storage on load and on every foreground. Nothing
  depends on the page staying alive, a timer surviving, or the screen being on
  — timestamps are absolute epoch ms, never elapsed counters.

## Behaviour
- IN / OUT pads fire on `pointerdown`, not click: the tap counts the instant
  the finger lands. Each tap flashes the pad and vibrates.
- `Undo` removes the last tap only, and forces a backup write so the backup
  cannot outlive the removed tap.
- `End event` → confirmation dialog with a summary → archived, counter reset,
  ended session opened in the data sheet. Not undoable.
- Data sheet: six analysis tiles, a one-paragraph plain-English read of the
  night, occupancy chart, arrivals/exits flow chart, CSV export, last 300 taps
  newest-first, archive list with per-event CSV + delete.

## Analysis (`analyze()` / `narrate()`)
Derived from the tap log alone — it never identifies anyone, only counts and
times. Tiles: **peak inside** (+ when), **duration** (+ start), **peak
arrivals** and **peak exits** (busiest sliding window, normalised to per-hour,
window = `span/6` clamped to 5–60 min), **avg stay** (area under the occupancy
curve ÷ arrivals — Little's law, the only honest dwell time available from
anonymous counts), **half in by** (median arrival). `turnover` = arrivals ÷
peak, reported in the narrative when ≥ 1.35×. Live sessions get a current
fill/empty rate over the tail window; ended ones get anyone left inside.

Deliberately **not** shown: "inside now", "total in", "total out" — the running
count is already the biggest thing on the main screen, and the totals are in
the CSV.

## Charts
- Occupancy: step line (occupancy holds flat between taps), filled, peak
  marked, x axis clock time, y axis nearest-nice steps.
- Flow: arrivals up / exits down per bucket, bucket auto-picked from
  `BUCKETS` so ~48 bars span the event. Axis numbers are colour-coded rather
  than labelled "in"/"out" — words overrun the 28px gutter.
- Both share `frame()` / `xAxis()` and the same time range. Redraw every 2 s
  while the sheet is open and the session is live.

## CSV
`seq, iso_timestamp, local_time, epoch_ms, elapsed_s, elapsed_hms, direction,
delta, occupancy, cumulative_in, cumulative_out`. UTF-8 BOM so Excel opens it
clean. Always the complete log; only the on-screen table is capped at 300.

## Constraints
- Must work with no network for the entire session.
- localStorage is ~5 MB; a tap costs ~18 bytes, so ~250k taps fit.
- Chrome buckets every `file://` URL under one storage origin, so the single
  file survives being moved or renamed. Firefox partitions per file path
  (`browser.storage.file_unique_origin`) — there, don't move the file
  mid-event. iOS has no dependable `file://` story; use the served build.
- Service worker needs https or localhost.

## Run and test
```
python build.py                                   # -> dist/head-count.html
python -m http.server 8123 --directory head-count # served build
python tests/durability.py                        # file:// survival, needs playwright
```
`tests/durability.py` taps, then reloads, closes and reopens the tab, copies
the file elsewhere, and relaunches the browser on the same profile — asserting
the count survives all five.
