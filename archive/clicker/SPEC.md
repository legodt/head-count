# Clicker — shelved spec

Lifted out of `CLAUDE.md` when the hardware was shelved on 2026-10-11.
It describes the app side as it was, which `app-side.patch` restores.

## Clicker
A physical three-button clicker (`clicker/`) counts the door without looking at
a screen. It is **an HID keyboard** - BLE or USB - sending keys this app already
counts, so there is no protocol, no pairing app, no driver and no companion
service, and it works on every host that accepts a keyboard. On iOS that is the
only option available: no Web Bluetooth, no Web Serial.

**The key bindings are a contract the firmware depends on.** `ArrowUp`/`i`
records IN, `ArrowDown`/`o` records OUT, `Backspace`/`u` undoes the last tap -
through the same `record()` and `undo()` the on-screen controls use. Changing
them means reflashing hardware.

- One physical press is one tap. `repeat` keydowns are dropped, so a held or
  stuck button cannot invent hundreds of guests; the firmware releases each key
  immediately for the same reason. Belt and braces, because the count is the
  product.
- The counting keys `preventDefault()`, or an arrow scrolls the data sheet out
  from under the user mid-count.
- Keys are ignored while the end dialog is open and while a text field or
  `contenteditable` has focus. Rename uses `prompt()`, which blocks JS outright.
- **Every clicker key answers with its own tone** - high for IN, low for OUT, a
  falling pair for undo, and a floor tone for an undo with nothing to undo. The
  link is one-way, so the tone is the *only* proof a press was counted; the
  motor in the user's hand only proves the button moved. It follows that a key
  must **never** be silent, including when it changes nothing: silence is
  reserved to mean "not receiving" and nothing else. On-screen controls stay
  silent - they already flash, vibrate and toast - so `undo()` and `record()`
  take a flag rather than reading the event, and `btnUndo` is wired through a
  wrapper because a raw listener would hand `undo()` a truthy event.
  `AudioContext` is opened on the first pad tap or key press, since iOS keeps
  audio silent until a real gesture.
- **A screen wake lock is held whenever the app is visible**, released on hide
  and retaken on return, riding on `startTick`/`stopTick` which already track
  exactly that. Best-effort and wrapped: absent on iOS < 16.4 and on some
  `file://` browsers, where the app must behave precisely as it did before.
  Because it is reached from every tap it stays cheap - one request in flight
  at a time, and a refusal is remembered until the next foreground rather than
  re-asked on all 250,000 taps of a night.

**The cost of a one-way link:** a press arriving while the app is backgrounded,
or after the screen has slept, is lost and nothing notices. The wake lock and
the blip are the whole mitigation. The clicker deliberately keeps no log of its
own - a second source of truth to reconcile against the archive would be a
bigger risk than the one it removes.

Undo *is* on the clicker, and it is the one button that destroys data rather
than recording it. The mitigation is physical - recessed, smaller, set apart, so
it cannot be caught by accident - plus its own unmistakable two-note answer, so
that a mistake is heard the moment it happens.

**Display downlink.** The clicker may carry a 128x64 OLED. It counts nothing
and derives nothing: `linkPush()` writes a finished packet - occupancy, peak,
range and 96 graph columns, resampled by `linkSeries()` onto even time columns
with the chart's own step semantics - to a custom GATT characteristic, and the
device draws it verbatim. One number exists, so the door and the app cannot
disagree.

- Uplink stays HID and is untouched. **The keys must never depend on the
  downlink working**, and no failure here may reach the counting path: a failed
  write calls `linkDrop()` rather than throwing on every tap for the rest of the
  night.
- Web Bluetooth only, so Chrome on desktop and Android and **never iOS**, the
  primary host. Where `navigator.bluetooth` is absent the `btnLink` button stays
  hidden and nothing else changes at all - that is the case to keep working.
- Pushed on every tap and undo, not only on the 1 s timer: a door cannot wait a
  second to watch the number move.
- Packet layout is documented above `linkSeries()` and duplicated in the
  firmware. `LINK_COLS` and the firmware's `COLS` must match. Bump the version
  byte if the layout ever changes.

`clicker/` is not in `build.py`'s `SHIPPED` allowlist, so none of it can reach
`docs/` or a public URL.
