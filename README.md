# Head Count

Offline counter for people in and out of a venue across one long event — a
whole night, phone locked most of it. Plain HTML/CSS/JS, no dependencies, no
network calls. Two large tap pads, a running occupancy count, a timestamped
log, flow analytics, a CSV export, and an archive of every ended event.

`CLAUDE.md` is the behaviour spec. Read it before changing anything.

## Build

```
python build.py
```

| Output | What it's for |
|---|---|
| `docs/` | the deployable site — this is what GitHub Pages serves |
| `dist/head-count.html` | one self-contained file, opened straight from disk |

Everything else stays local. `build.py` prunes stale files from `docs/` and
refuses to ship if `sw.js` promises to cache a file that isn't there.

## Deploy to GitHub Pages

1. Create an empty repo on GitHub (no README, no .gitignore).
2. ```
   git remote add origin https://github.com/<you>/head-count.git
   git push -u origin main
   ```
3. Repo → **Settings → Pages** → Source: **Deploy from a branch** →
   Branch: `main`, Folder: **`/docs`** → Save.
4. Wait ~1 minute for `https://<you>.github.io/head-count/`.

The manifest uses relative scope, so the subpath is fine.

Any drag-and-drop host (Netlify Drop, Cloudflare Pages) takes the same `docs/`
folder instead.

## Run it on iOS

1. Open the URL **in Safari**.
2. Share → **Add to Home Screen**.
3. Launch from the **home-screen icon**, not the Safari tab — only the
   installed instance runs standalone and keeps storage beyond Safari's 7-day
   eviction cap.

Then test it: tap a few in, force-quit from the app switcher, reopen. The
count must still be there. Airplane mode is fine from that point on.

iOS notes: no haptics (Safari has no Vibration API), use **Share CSV** rather
than Download, and turn on Guided Access (Settings → Accessibility) to lock
the phone to the app for the night.

## After changing the app

Bump `CACHE` in `sw.js`, rerun `python build.py`, commit and push. `CACHE` is
the only way a change reaches installed phones: the worker serves strictly from
the cache it installed, so a flaky venue network can never block a tap and a
page is never assembled from two versions.

Phones switch on a later launch, usually the second — open the app once with a
connection, close it, open it again. GitHub Pages caches `sw.js` for ten
minutes, which can push the switch one launch further.

## Test

```
python build.py
python tests/durability.py
python tests/archive.py
python tests/update.py
python tests/overnight.py
```

`durability.py` taps, then reloads, closes and reopens the tab, copies the file
elsewhere, and relaunches the browser on the same profile — asserting the count
survives all five.

`archive.py` checks the Events archive against a really filled storage quota:
no cap on stored events, End refuses rather than losing data when storage is
full, an interrupted end never duplicates, deletes persist, and renames land
on the right event or change nothing.

`update.py` pairs the new script with each page deployed before it and checks
the pads still count, then proves the service worker never mixes versions in
its cache and that a `CACHE` bump still installs the whole new shell.

`overnight.py` checks times against the zone database: the clock follows the
device's zone, and an event across midnight or a daylight-saving change charts,
summarises and exports correctly.

`durability.py`, `archive.py` and `overnight.py` drive `dist/head-count.html`;
`update.py` serves copies of `docs/`. All four need `playwright`.
