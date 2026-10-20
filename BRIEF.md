# Head Count — project brief

Hand this to a new session ("read head-count/BRIEF.md") for the whole picture in
one file. `CLAUDE.md` is the full behaviour spec; read it before changing
behaviour, not for orientation.

## Goal
Count people in and out at a door across one long event — typically a whole
night, on a phone that stays locked in a pocket most of it. Never lose a tap,
never need a network, never need an account. One person, one thumb, in the dark.

## Two pieces
The counter (this repo's app, on a phone at the door) and **Door Read**
(`tools/analyze.html`), a separate page you drop an exported CSV into after the
night: three figures, a short read with its numbers bolded, and two charts —
how full, and the door that filled it — with hour rows and the tap log folded
away. Capacity defaults to 115, buckets to 30 minutes, and it opens on a real
night (Last Saturday Dance, 26 Sep 2026) embedded as deltas. Published at
https://claude.ai/artifact/6JfXd6T6oty1apb4NQoXps and parses the file in the browser.

## Where it lives
- Live app: https://legodt.github.io/head-count/ (GitHub Pages, repo
  `legodt/head-count`, branch `main`, served from `/docs`)
- Also ships as one offline file: `dist/head-count.html`, opened from disk
- Installs to an iOS home screen as a PWA — that is the intended way to run it

## What it does
- Two big pads, IN and OUT, firing on `pointerdown` so the tap counts the
  instant the finger lands. Running occupancy is the biggest thing on screen;
  negative is allowed (people already inside may leave) and shown amber.
- HUD: in / out / peak, the device's current time, elapsed session length, and
  **velocity** — how fast the room is filling or emptying right now, on screen
  for the whole event.
- Undo removes the last tap only.
- Name the event by tapping the title — a dashed pill with a pencil until it
  has a name. Rename any event, live or ended, from the data sheet.
- End event, behind a confirmation, archives the event and resets the counter.
- Events: every ended event, newest first, never trimmed. Open one for its full
  data, share/download its CSV, or delete it. Header shows storage used.
- Data sheet: six analysis tiles (peak inside, duration, peak arrivals, peak
  exits, average stay, half-in-by), a plain-English read of the night, an
  occupancy step chart, an arrivals/exits flow chart, CSV export, and the last
  300 taps newest-first.
- Analysis uses only counts and times — it never identifies anyone. Average
  stay is area under the occupancy curve ÷ arrivals (Little's law).
- All clock times are 12-hour AM/PM from the device's own clock and zone.
  Midnight and daylight-saving changes are handled and tested.
- A physical three-button clicker (`clicker/`) - IN, OUT and UNDO - counts the
  door without looking at the screen at all, except to name the event and end
  it. It is just an HID keyboard, so it needs no app, driver or pairing service
  and works on iOS, Android and desktop alike. Cheapest build is an ESP32-C3
  SuperMini at about $7. The app holds a screen wake lock and answers every key
  with its own tone, which over a one-way link is the only proof a press was
  counted - so silence means "not receiving" and nothing else.
- The clicker can carry a $2 OLED showing live occupancy and the capacity
  graph. It still counts nothing: the app pushes a finished packet over a
  custom GATT characteristic and the device draws it, so the door and the app
  cannot disagree. Needs Web Bluetooth, so Chrome desktop and Android but not
  iOS, where the panel says so and the clicking is unaffected.

## How it works
- Plain HTML/CSS/JS. No framework, no dependencies, no network calls.
- `Session = { id, label, startedAt, endedAt, ev: [[epochMs, +1|-1], ...] }`.
  Keys: `hc.active.v1` (rewritten every tap), `hc.active.bak.v1` (every 10th
  tap, read back to prove the write landed), `hc.arch.v1` (all ended events).
- Timestamps are absolute epoch ms. Nothing depends on the page staying alive,
  a timer surviving, or the screen being on. State is re-read on every
  foreground.
- All storage goes through `LS`, which never throws; a failed write raises a
  persistent amber banner and the app keeps counting in memory.
- Destructive steps write and read back first: End, Delete and Rename only
  commit once the archive is proven saved. Storage full means the event stays
  live, not lost.
- `sw.js` is strictly cache-first and never writes after install, so a page is
  never assembled from two versions. `app.js` loads state before any wiring.

## Layout
Source at the repo root (`index.html`, `styles.css`, `app.js`, `sw.js`,
`manifest.webmanifest`, `icons/`) → `python build.py` → `docs/` (deployed) and
`dist/head-count.html` (single file). Nothing is edited inside either output.
`CLAUDE.md` is the spec, `tests/` holds six Playwright suites. `clicker/` holds
the clicker firmware and its build notes; it is outside `build.py`'s allowlist,
so nothing in it can reach a public URL.

## Commands
```
python build.py                              # -> docs/ and dist/head-count.html
python -m http.server 8123 --directory docs
python tests/durability.py                   # survives reload, reopen, relaunch
python tests/archive.py                      # archive + rename, real full quota
python tests/update.py                       # deploys never mix versions
python tests/overnight.py                    # time zones, midnight, DST
python tests/clicker.py                      # clicker key path, wake lock, blip
python tests/link.py                         # clicker display downlink
```

## Rules for changing it
- Update `CLAUDE.md` with every behaviour change — it is the spec, not a readme.
- Bump `CACHE` in `sw.js` for any shell change; it is the only way an update
  reaches an installed phone. Phones switch on a later launch, usually the 2nd.
- Before editing `index.html`, copy the live one to `tests/fixtures/index-vN.html`.
- Wire listeners through `on()`, never `$(id).addEventListener`.
- Never trim the archive; never reset live state before a verified write.
- Keep it terse: compress comments, delete dead code.
- The clicker's key bindings are a contract: changing them means reflashing
  hardware.

## Constraints and gotchas
- localStorage is ~5 MB; a tap costs ~18 bytes (~250k taps).
- iOS: no vibration; export via Share, not download; home-screen apps are
  exempt from Safari's 7-day eviction.
- Firefox partitions `file://` storage per path (don't move the single file
  mid-event); Chrome does not. Service workers need https or localhost.
- On the night clocks go back, a range inside the repeated hour can read
  "1:30–1:30 AM". Real times, unavoidable, once a year.

## Status — 2026-10-11
Active work is the app and Door Read. `main` is still at `ee881cb` on GitHub
(live worker `headcount-v8`); the working tree adds the HUD velocity readout,
Door Read, and the shelving of the clicker. `sw.js` is at `headcount-v12`.
Five suites pass: durability, archive, update, overnight, analyze.

The hardware clicker is **shelved** in `archive/clicker/` — firmware, spec,
tests, and a patch that puts its app-side support back. It was never verified
on hardware, and nothing in the app refers to it now.

