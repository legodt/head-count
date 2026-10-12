# Head Count clicker

Three buttons — **IN**, **OUT**, **UNDO** — sending counts wirelessly to the
phone or laptop running Head Count. The screen is needed only to name the event
and to end it.

**The whole trick:** the clicker is a keyboard. Head Count counts Up arrow, Down
arrow and Backspace, so there is no app to install, no driver, no pairing
service and no protocol to maintain — every OS that accepts a keyboard accepts
this. On iOS it is also the only option: no Web Bluetooth, no Web Serial.

## The cheap build — ESP32-C3 SuperMini, ~$7

The C3 SuperMini is the cheapest board that does BLE HID and programs over
USB-C. Nothing capable is meaningfully cheaper.

Two columns because they are genuinely different purchases: the left is a
three-week wait and the right is on your doorstep in two days. Prices are
approximate as of September 2026 — check before you order.

| Part | Qty | Cheap | US retail |
|---|---|---|---|
| ESP32-C3 SuperMini | 1 | [~$2, AliExpress](https://www.aliexpress.com/w/wholesale-ESP32-C3-Super-Mini.html) | [$12.99 / 3-pack, Amazon](https://www.amazon.com/ESP32-C3-Development-Supermini-Bluetooth-Pre-Soldered/dp/B0F12JS872) |
| 30 mm arcade button — **IN** | 1 | [~$1, AliExpress](https://www.aliexpress.com/w/wholesale-30mm-arcade-button.html) | [$5.95, Adafruit 471](https://www.adafruit.com/product/471) |
| 30 mm arcade button — **OUT** | 1 | [~$1, AliExpress](https://www.aliexpress.com/w/wholesale-30mm-arcade-button.html) | [$5.95, Adafruit 473](https://www.adafruit.com/product/473) |
| 12 mm tactile button + cap — **UNDO** | 1 | [~$0.20, AliExpress](https://www.aliexpress.com/w/wholesale-12mm-tactile-switch-cap.html) | [~$7 / assortment, Amazon](https://www.amazon.com/s?k=12mm+tactile+push+button+switch+with+cap) |
| 2×AAA holder with switch | 1 | [~$0.80, AliExpress](https://www.aliexpress.com/w/wholesale-2-AAA-battery-holder-switch.html) | [$1.95, Adafruit 4191](https://www.adafruit.com/product/4191) · [Amazon](https://www.amazon.com/Adafruit-Battery-Holder-Switch-Connector/dp/B07S8QVWZ8) |
| Coin vibration motor (3 V ERM) | 1 | [~$0.80, AliExpress](https://www.aliexpress.com/w/wholesale-coin-vibration-motor-3v.html) | [$1.95, Adafruit 1201](https://www.adafruit.com/product/1201) · [Amazon](https://www.amazon.com/Adafruit-Vibrating-Mini-Motor-ADA1201/dp/B00OKCPXOC) |
| 2N3904 + 1 kΩ + 1N4148 | 1 | [~$0.15, AliExpress](https://www.aliexpress.com/w/wholesale-2N3904-transistor.html) | [~$12 / kit, Amazon](https://www.amazon.com/s?k=transistor+resistor+diode+assortment+kit) |
| 0.96" SSD1306 OLED, I²C *(optional)* | 1 | [~$2, AliExpress](https://www.aliexpress.com/w/wholesale-0.96-inch-oled-ssd1306-i2c.html) | [~$8 / 2-pack, Amazon](https://www.amazon.com/HiLetgo-Adafruit-Beaglebones-Raspberry-Optional/dp/B076DYCWC8) · [$17.50, Adafruit 326](https://www.adafruit.com/product/326) |
| Project box | 1 | [~$1.20, AliExpress](https://www.aliexpress.com/w/wholesale-abs-project-box-enclosure.html) | [~$10 / pack, Amazon](https://www.amazon.com/s?k=abs+project+box+enclosure+small) |
| | | **~$7** | **~$49** |

Most of that right-hand column is the assortment kit and the box multipack,
which leave you spares for several more builds. The parts that are actually
consumed by one clicker come to about $22 at US retail.

**Absolute floor, ~$4:** the board, three bare tactile switches and a battery
holder, in whatever box you have. You lose the motor, which costs you the
in-hand confirmation — the app's tone still tells you every press landed, so
this is a real option if the host is somewhere you can hear it.

## Worth paying more for

**Seeed XIAO nRF52840, $9.90** —
[Seeed](https://www.seeedstudio.com/Seeed-Studio-XIAO-nRF52840-Pre-Soldered-p-6332.html)
· [3-pack](https://www.seeedstudio.com/Seeed-Studio-XIAO-nRF52840-3PCS-p-5921.html).
Same sketch, one `#define`. You get vastly better battery life, a LiPo charger
on board, and BLE that behaves on iOS without library roulette. If this gets
used every weekend, buy this instead of the C3. Pair it with a
[LiPo cell](https://www.adafruit.com/product/3898) rather than AAAs.

**Wired build, if the host will sit on a desk** — an ATmega32U4 board is the
most reliable thing here: no pairing, no battery, no dropouts.
[SparkFun Pro Micro](https://www.sparkfun.com/pro-micro-5v-16mhz.html) is the
genuine article; [clones](https://www.amazon.com/s?k=pro+micro+atmega32u4) run
~$5 each and work fine for this.

## Cheaper than building anything

A Bluetooth page-turner or camera shutter *already is* a BLE HID keyboard, for
$10–15 with no soldering:

- [Bluetooth Kindle page turner remote](https://www.amazon.com/Bluetooth-Kindle-Page-Turner-Remote/dp/B0BKL3R5RW)
- [Page turner with RF + Bluetooth](https://www.amazon.com/Control-Bluetooth-Clicker-Paperwhite-Colorsoft/dp/B0DJQG9FGM)
- [Scrolling ring](https://www.amazon.com/Control-Bluetooth-Wireless-Recording-Scrolling/dp/B0DHV6R2WN)

The catch: you get whatever keys the maker chose — usually Up/Down arrow or
Volume ±, rarely documented, and not changeable. Pair one to a laptop and press
its buttons in a text editor to find out what it sends; if it sends the arrows,
it drives Head Count today with no changes at all, and it is the fastest way to
try the whole idea before buying parts. What you do not get is three big buttons
you can tell apart by feel in the dark, which is the entire point of the build
above.

## The display (optional)

A 128×64 SSD1306 on I²C, about $2, showing live occupancy and the capacity
graph on the clicker itself. A [1.3" SH1106](https://www.adafruit.com/product/938)
is the same wiring and easier to read across a doorway.

**The clicker still counts nothing.** It has no tally of its own and derives
nothing — the app pushes a finished packet (occupancy, peak, range, and 96
graph columns) over a custom GATT characteristic and the device draws it
verbatim. So the number on the door and the number in the app cannot disagree:
there is only one of them.

That means the display needs a **downlink**, and the downlink needs Web
Bluetooth — Chrome on desktop and Android. **iOS has no Web Bluetooth, so on an
iPhone the panel reads `waiting for app` and the clicking works exactly as it
always did.** The screen is the optional layer; the keys never depend on it.

| | Panel | Clicking |
|---|---|---|
| Chrome desktop / Android | live | works |
| iOS PWA | `waiting for app` | works |
| Clicker out of range | `app not sending` | long buzz, nothing sent |

In the app, a **Clicker** button appears in the bottom bar wherever Web
Bluetooth exists (and nowhere else). Tap it, pick *Head Count Clicker*, and it
turns green. It pushes on every tap and once a second besides.

**Blanking the panel after 30 s idle is safe** — unlike sleeping the radio, it
relights in microseconds, so no press is ever lost to it. That is why the
display sleeps and the radio does not.

### Build it on the nRF52

The downlink is implemented for `TRANSPORT_NRF52` only. Bluefruit adds a custom
service alongside the HID service as a matter of course; `BleKeyboard` on the
ESP32 owns its BLE server and will not share it, so a second service there means
forking the library. Build `DISPLAY 1` on a XIAO nRF52840. On a C3 the panel
will light and say `waiting for app` forever.

**This is the part to prove on hardware first.** Whether Chrome can reach a
custom GATT service on a device the OS already holds as a keyboard is
platform-dependent, and I have not been able to test it. If it proves awkward,
the fallback is USB Web Serial, which is bulletproof but tethers the clicker.

Set `DISPLAY 0` to build the clicker with no screen at all — everything else is
unchanged.

## Wiring

Buttons go straight to ground — the pins are `INPUT_PULLUP`, so no resistors.

| | ESP32-C3 SuperMini | XIAO nRF52840 | Pro Micro (wired) |
|---|---|---|---|
| IN | GPIO3 ↔ GND | D0 ↔ GND | D5 ↔ GND |
| OUT | GPIO4 ↔ GND | D1 ↔ GND | D6 ↔ GND |
| UNDO | GPIO5 ↔ GND | D2 ↔ GND | D7 ↔ GND |
| Motor drive | GPIO6 | D3 | D9 |
| OLED SDA | GPIO7 | D4 | D2 |
| OLED SCL | GPIO10 | D5 | D3 |
| Power | 2×AAA → **3V3** and GND | LiPo → JST | USB |

**Do not move the buttons to GPIO 0, 2, 8 or 9 on the C3.** Those are strapping
pins; a button held down across a reset stops the board booting, which is a
miserable fault to diagnose at a door.

The motor does **not** hang off a GPIO pin — it stalls at more current than a
pin can give and its collapsing field will eventually kill the board:

```
  drive pin ──[1k]── base (2N3904)
                     collector ── motor ── 3V3
                     emitter   ── GND
  1N4148 across the motor, stripe to 3V3        (flyback)
```

## Two cheap-build details that matter

**Feed 3V3, not 5V.** Two AAAs give 3.0–3.2 V straight into the `3V3` pin,
bypassing the regulator and everything on the 5 V rail. Do not also plug in USB
while a battery is connected.

**Scrape off the red power LED.** On the C3 SuperMini it is about 90% of the
board's idle draw — roughly 600 µA down to 100 µA with it gone, and a milliamp
or two saved while running. On two AAAs that is the difference between one night
and several. A fingernail-and-craft-knife job, no desoldering needed.

**Battery life, honestly:** the sketch deliberately does no power management, so
a connected C3 pulls tens of milliamps and a set of AAAs lasts a long night or
two. That is a chosen trade — see the note at the bottom of `loop()`. If you
want more, enable light sleep via `esp_pm_configure()`, and re-test that no
press is ever dropped before you trust it.

## Flash it

1. Arduino IDE → Boards Manager.
   - **ESP32:** add `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
     under Additional Board Manager URLs, install *esp32*, select
     *ESP32C3 Dev Module*, and enable **USB CDC On Boot**.
   - **nRF52:** add `https://www.adafruit.com/package_adafruit_index.json`,
     install *Adafruit nRF52*, select *Seeed XIAO nRF52840*.
   - **Wired:** *Arduino AVR Boards*, select *Arduino Leonardo*.
2. **Display only — install [U8g2](https://github.com/olikraus/u8g2)** from the
   Library Manager.
3. **ESP32 only — install a BLE keyboard library.** The sketch uses the common
   `BleKeyboard` API, which several libraries share. The original
   [T-vK/ESP32-BLE-Keyboard](https://github.com/T-vK/ESP32-BLE-Keyboard) does
   not target the C3; use a NimBLE fork that keeps the same API:
   [pr4u4t/ESP32C3-BLE-Keyboard](https://github.com/pr4u4t/ESP32C3-BLE-Keyboard)
   or [wakwak-koba/ESP32-NimBLE-Keyboard](https://github.com/wakwak-koba/ESP32-NimBLE-Keyboard).
   [HijelHub/HijelHID_BLEKeyboard](https://github.com/HijelHub/HijelHID_BLEKeyboard)
   is a newer NimBLE library explicitly tested against iOS and iPadOS — worth
   reaching for first if pairing gives you trouble.
4. Open `clicker.ino`, set the transport near the top:
   ```c
   #define TRANSPORT TRANSPORT_ESP32   // or TRANSPORT_NRF52, or TRANSPORT_USB
   ```
5. Upload. The motor gives two pulses at boot — that is "alive", and it is the
   only status signal, on purpose.

## Connect it

Bluetooth settings → pair **Head Count Clicker**. Once, in daylight, before the
event. It re-advertises on disconnect, so walking out of range and back
reconnects on its own.

## Use it

Open Head Count, name the event, put the phone down, and count. It holds the
screen awake by itself.

**Learn the four sounds.** Every press the app receives answers with a distinct
tone, and that tone — not the motor — is the proof a press was *counted*:

| | Sound from the app | Buzz in your hand |
|---|---|---|
| IN | one high note | one pulse |
| OUT | one low note | two pulses |
| UNDO | two notes, falling | three pulses |
| Nothing left to undo | one very low note | three pulses |
| **Radio not linked** | *silence* | **one long buzz** |

Silence from the app with a normal buzz means the press went into the void:
bring Head Count back to the front and check the count. A long buzz means the
clicker itself never got through, so the count is untouched.

## Gotchas

- **ESP32 classic Bluetooth HID does not work with iOS.** Only BLE HID does.
  The C3 and S3 are BLE-only, so they are fine; an older ESP32 is not.
- A press that arrives while the app is backgrounded or the phone is locked is
  **lost, silently**. There is no back-channel over HID to notice. Keep Head
  Count in front; that is what the wake lock and the tones are for.
- **Put UNDO where you cannot hit it by accident** — recessed, smaller, on the
  end or on the side, and unmistakable by feel. It is the one button that
  destroys data rather than recording it. Its falling two-note answer is there
  so that if you *do* catch it by mistake, you hear it happen.
- Make IN and OUT tell themselves apart by feel too: different sizes, convex
  against concave, a ridge between them. This gets used with cold hands in the
  dark, and the shape of the thing matters as much as the code.

## Files

- `clicker.ino` — the whole firmware, all three transports.
- Spec for the app side: `../CLAUDE.md`, section **Clicker**.
