# Head Count — spec

Offline counter for people in and out of a venue across one long event
(typically a whole night, phone locked most of it). Plain HTML/CSS/JS, no
dependencies, no network calls, no framework.

## Two builds, one source
Source of truth is the repo root: `index.html`, `styles.css`, `app.js`,
`sw.js`, `manifest.webmanifest`, `icons/`. `python build.py` emits both
shippable forms and nothing is edited inside them.

- **`docs/`** — the deployable site. Installs to a home screen. Named `docs`
  because a GitHub Pages branch deploy serves only the repo root or `/docs`,
  and the root would expose `build.py` and this spec. Rebuilt from scratch each
  run: stale files are pruned so a renamed source cannot reappear on a public
  URL, and the build **refuses to ship** if `sw.js` names a file that is not
  there. Carries `.nojekyll`.
- **`dist/head-count.html`** — one self-contained file opened straight from
  disk. Inlines the CSS, JS and favicon; drops the manifest and worker (neither
  works on `file://`). `build.py` refuses to ship if anything failed to inline.

Bump `CACHE` in `sw.js` on **any** shell change — it is the only way a change
reaches installed clients.

**Update safety.** A deploy must never hand a phone a page built from two
versions.
- `sw.js` is strictly cache-first and never writes to its cache after install.
  Install fetches the whole shell with `cache: 'reload'`, past the HTTP cache —
  GitHub Pages sends `max-age=600`, which would otherwise let a stale `app.js`
  be baked in beside a new `index.html`. A new `CACHE` installs complete or not
  at all, and `activate` purges the old one.
- Clients switch on a later launch, usually the second: the launch that finds
  the new worker finishes on the old version. The 10-minute max-age on `sw.js`
  can push the switch one launch further.
- `app.js` loads state before any wiring and wires every element through
  `on()`, which skips absent ids, so the pads keep counting even if the script
  meets an older page. **Never wire with `$(id).addEventListener` directly.**
  `tests/update.py` proves it against every page deployed before
  (`tests/fixtures/index-v*.html`). **Before changing `index.html`, save the
  live one there as the next fixture.**

Manifest `start_url` and `scope` are relative (`./`), so a subpath deploy such
as `user.github.io/head-count/` works — verified, not assumed.

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
  `hc.arch.v1` (every ended event, newest first — **never trimmed**; storage
  is the only limit).
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
- HUD: count; in / out / peak; the **device's current time** and, once the
  first tap starts the session, its elapsed length.
- **Velocity** is on screen the whole time an event is running, under the
  count: `▲ 24/hr filling`, `▼ 18/hr emptying`, or holding steady inside
  ±2/hr. `velocity()` is the one definition, shared with the narrative so the
  two can never disagree: net flow over the tail window (`span/8`, clamped
  10–30 min) divided by the time actually elapsed, **floored at 5 minutes** —
  without that floor a flurry in the first seconds reads as 200,000 an hour.
  It scans back from the last tap, so it costs the taps in the window, not the
  night.
- **Naming.** Until named, the title at the top is a dashed pill with a pencil
  — a call to action; once named, plain text with a faint pencil. Tap to name.
  The data sheet head has **Rename** for whichever event it shows, live or
  ended. An ended event is renamed by writing the whole archive, read back and
  adopted only on success, matched by `id` — a foreground `reload()` swaps
  `ARCH` for fresh objects. Storage full → name unchanged, banner.
- `Undo` removes the last tap only, and forces a backup write so the backup
  cannot outlive the removed tap.
- `End event` → confirmation dialog with a summary → the event is written to
  the archive **and read back**, and only then is the live count reset; the
  ended event opens in the data sheet. Not undoable. If the archive write
  fails (storage full) the event is **not** ended — it stays live, still
  counting, and a banner says why.
- An end interrupted between those two writes leaves one session in both
  slots. `reload()` matches on `id`, keeps the archive copy and resets the
  live slot — never a duplicate. Ids carry a random suffix so two sessions
  created in the same millisecond cannot collide.
- **Events** (main bar) lists every ended event, newest first: name, date,
  clock span, duration, guests, peak, avg stay. Tapping a card opens its full
  data sheet, which stacks on top, so Close returns to Events. Per event:
  Share CSV (Download where file sharing is unavailable) and Delete, behind a
  confirm. The header shows event count, total guests, and approximate storage
  used against Safari's 5 MB, turning amber past 80%.
- Data sheet: six analysis tiles, a one-paragraph plain-English read of the
  night, occupancy chart, arrivals/exits flow chart, CSV export, last 300 taps
  newest-first.

## Time
Every clock time comes from local `Date` getters on epoch ms, so the device's
own clock and zone decide it — never UTC, never a fixed zone. People read
12-hour with AM/PM: `hm` → `9:05 PM`, `clockOf` → `9:05:12 PM` (tap table).
`spanOf` collapses a shared meridiem: `9:40–10:40 PM`, but `11:30 PM–12:30 AM`.
Durations stay `HH:MM:SS` or `2h 18m`. CSV filenames keep a 24-hour
`YYYYMMDD-HHMM` stamp so they sort.

Midnight is nothing special: every position is linear in epoch ms. A
daylight-saving night plots and measures real elapsed time; only its labels
jump, so a fall-back hour can read `1:30–1:30 AM`.

## Analysis (`analyze()` / `narrate()`)
Derived from the tap log alone — it never identifies anyone, only counts and
times. Tiles: **peak inside** (+ when), **duration** (+ start), **peak
arrivals** and **peak exits** (busiest sliding window, normalised to per-hour,
window = `span/6` clamped to 5–60 min), **avg stay** (area under the occupancy
curve ÷ arrivals — Little's law, the only honest dwell time available from
anonymous counts), **half in by** (median arrival). `turnover` = arrivals ÷
peak, reported in the narrative when ≥ 1.35×. Live sessions get the same
`velocity()` the HUD shows; ended ones get anyone left inside.

Deliberately **not** shown: "inside now", "total in", "total out" — the running
count is already the biggest thing on the main screen, and the totals are in
the CSV.

## Charts
- Occupancy: step line (occupancy holds flat between taps), filled, peak
  marked, y axis nearest-nice steps.
- Flow: arrivals up / exits down per bucket, bucket auto-picked from
  `BUCKETS` so ~48 bars span the event. Axis numbers are colour-coded rather
  than labelled "in"/"out" — words overrun the 28px gutter.
- Both share `frame()` / `xAxis()` and the same time range. The x axis shows
  2–5 evenly spaced clock times — the most that neither touch nor repeat,
  measured, since `12:45 AM` is wide — end labels aligned inward. Redraw every
  2 s while the sheet is open and the session is live.

## CSV
`seq, iso_timestamp, local_time, epoch_ms, elapsed_s, elapsed_hms, direction,
delta, occupancy, cumulative_in, cumulative_out`. UTF-8 BOM so Excel opens it
clean. `local_time` is device time, `2026-09-12 9:05:03 PM`; `iso_timestamp` is
UTC. Always the complete log; only the on-screen table is capped at 300.

## Door Read (`tools/analyze.html`)
A separate single-file page for reading an exported CSV after the night, in one
screen: four figures, a read of three sentences at most with every figure in it
bolded for skimming, then two charts — **how full** (occupancy, the night's
phases as shaded bands, capacity as a dashed line) and **the door that filled
it** (arrivals up, exits down, net line), sharing one time axis so they read as
a single picture. Integrity flags are one row of chips; hour rows and the tap
log fold away. No dependencies but a web font; the file is parsed in
the page and never uploaded.

**Redundancy is the thing to resist.** A cumulative in/out chart only redraws
the gap under the occupancy curve, a velocity chart only redraws the flow bars
with one subtraction done, and a phases panel only restates the shape the
occupancy curve already has. All three were cut. The dwell histogram went too:
its median and p90 are a clause in the read, which is all the shape anyone
needed. The page went from roughly 4,300px of scroll to around 1,000.

- Times are shown **as they were at the door**: `local_time` minus `epoch_ms`
  recovers the event's UTC offset per row, so a reader in another zone — or a
  clock change mid-event — still sees the door's own clock.
- Reads this app's columns by name, and other files by sniffing a timestamp
  column and an IN/OUT or ±1 column.
- Dwell pairs each exit with the earliest guest still inside: right on average,
  wrong for any individual, and labelled as such on the page.
- The CSV carries no end time, so the night ends at the last tap.
- **No group or door-pressure claims.** How tightly taps bunch is set by train
  arrivals and how fast the queue is cleared, not by who came with whom, so
  group size, average group and busiest-minute were cut rather than left to be
  read as facts about guests.
- Not in `build.py`'s `SHIPPED`, so it cannot reach `docs/`. Published as an
  artifact (same file, document wrapper stripped): <https://claude.ai/artifact/6JfXd6T6oty1apb4NQoXps>.

## Shelved
`archive/clicker/` holds the hardware clicker, shelved 2026-10-11: firmware,
its spec, its two test suites, and `app-side.patch`, which re-applies the app's
half of it (keys answering with tones, a screen wake lock, and the Bluetooth
display downlink). Nothing under `archive/` is built, tested or shipped, and
nothing in the app refers to it. Active work is this app and
`tools/analyze.html`.

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
python build.py                              # -> docs/ and dist/head-count.html
python -m http.server 8123 --directory docs  # the deployable build
python tests/durability.py                   # file:// survival, needs playwright
python tests/archive.py                      # events archive integrity, needs playwright
python tests/update.py                       # deploy/update safety, needs playwright
python tests/overnight.py                    # time zones, midnight, DST, needs playwright
python tests/analyze.py                      # Door Read CSV analyser, needs playwright
```
`durability.py`, `archive.py` and `overnight.py` drive `dist/head-count.html`;
`analyze.py` drives `tools/analyze.html`; `update.py` serves temporary copies
of `docs/`. Run `python build.py` first.
`tests/durability.py` taps, then reloads, closes and reopens the tab, copies
the file elsewhere, and relaunches the browser on the same profile — asserting
the count survives all five.

`tests/archive.py` exercises the archive against a **really filled** quota, not
a mock: 35 events survive with no cap and unique ids, End refuses when storage
is full and leaves the event live, an interrupted end resolves without
duplicating, deletes persist across a reload, and renames — live or ended,
after a foreground reload, cancelled, or with storage full — land on the right
event or change nothing.

`tests/update.py` serves copies of `docs/` with HTTP caching off, so anything
that changes is the worker's doing. It pairs the new script with each previous
page and checks the pads still count and persist; checks a file changed on the
server never leaks into the live cache; and checks a `CACHE` bump still
installs the complete new shell and purges the old.

`tests/overnight.py` works every expected time out in Python from the zone
database and reads the charts through a canvas spy: the HUD clock in four
zones; a 9 PM–3 AM event and both daylight-saving directions (axis, line, peak
marker and flow buckets across midnight; tiles, narrative, card, table, CSV);
and a live session with the device clock run through 12:00 AM.

`tests/analyze.py` builds a night in Python, exports it as a Head Count CSV and
opens Door Read on it from a browser in another time zone: the five figures must
match the Python, the peak must read in the door's clock and not the reader's,
there must be exactly two charts in order and three sections, hour rows and the
tap log must be present but folded, the read must stay within three sentences
and bold its figures, hover and capacity must work, the page may make no group claim, and
neither theme nor a 390px phone may scroll sideways.
