# Archive

Work that is not being developed. Nothing here is built, tested, shipped, or
referenced by the app. `build.py` copies only its `SHIPPED` allowlist, so none
of it can reach `docs/` or a public URL.

## clicker/ — shelved 2026-10-11
A three-button physical clicker (IN / OUT / UNDO) for counting the door without
looking at a screen, built as **an HID keyboard** sending keys the app already
counted, plus an optional OLED that the phone drew over Bluetooth.

| File | What it is |
|---|---|
| `clicker.ino` | Firmware for ESP32-C3, nRF52840 or wired USB. **Never compiled or run on hardware.** |
| `README-firmware.md` | Build, flash and wiring notes |
| `SPEC.md` | Its behaviour spec, lifted out of `CLAUDE.md` |
| `app-side.patch` | Re-applies the app's half: key tones, the screen wake lock, the Bluetooth display downlink |
| `tests/clicker.py` | The key path, driven as a keyboard |
| `tests/link.py` | The display downlink, against a fake Bluetooth stack |

To bring it back:

```
git apply archive/clicker/app-side.patch
cp archive/clicker/tests/*.py tests/
python build.py
```

Then bump `CACHE` in `sw.js` and fold `SPEC.md` back into `CLAUDE.md`. The patch
was cut against the app on 2026-10-11; if the app has moved on, expect to place
some hunks by hand.

The open question when it was shelved: whether Chrome can reach a custom GATT
service on a device the operating system already holds as a keyboard. The
keyboard half never needed that answer — it works on any host that accepts a
keyboard, iOS included, where Web Bluetooth does not exist at all.
