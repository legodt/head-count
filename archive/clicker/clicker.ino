/* Head Count clicker - IN, OUT and UNDO, so the door is counted without ever
   looking at a screen.

   The device is simply a keyboard. Head Count counts Up arrow, Down arrow and
   Backspace (see the keydown handler in app.js), so there is no protocol, no
   pairing app, no driver and no companion service: every OS that accepts a
   keyboard accepts this, iOS included. That is also the only option on iOS,
   which has neither Web Bluetooth nor Web Serial.

   One sketch, three boards. Only the transport block differs; set TRANSPORT.
     TRANSPORT_ESP32 - ESP32-C3 SuperMini. Wireless, and the cheapest that works.
     TRANSPORT_NRF52 - Seeed XIAO nRF52840. Wireless, far better on battery.
     TRANSPORT_USB   - Arduino Pro Micro. Wired, no battery, nothing to pair.

   The clicks are one-way: a press cannot be acknowledged, so the app holds a
   screen wake lock and answers every key with a distinct tone. That tone is the proof a
   press was counted - the motor in your hand only proves the button moved. The
   one thing this firmware can tell you by itself is that the radio is *not*
   linked, and it says so with a long buzz instead of a short one.

   OPTIONAL DISPLAY. The clicker counts nothing and knows nothing - the host
   owns every number. If a screen is fitted, the app pushes a ready-made packet
   over a custom GATT characteristic (see linkPacket() in app.js) and this draws
   it verbatim: no local tally to drift, so what is on the door is what is in
   the app. Needs Web Bluetooth, so it is fed by Chrome on desktop and Android
   and never by iOS - where the display simply says so and the clicking carries
   on exactly as before. Set DISPLAY to 0 to build without it. */

#define TRANSPORT_ESP32 1
#define TRANSPORT_NRF52 2
#define TRANSPORT_USB   3

#define TRANSPORT TRANSPORT_ESP32
#define DISPLAY   1                    // 0 builds the clicker with no screen at all

/* ---------------- boards ----------------
   Buttons go straight to ground on INPUT_PULLUP. The motor is driven through a
   transistor, never off a pin. ESP32-C3 strapping pins (0, 2, 8, 9) are left
   alone - a button held across a reset on one of those stops the board booting. */

#if TRANSPORT == TRANSPORT_ESP32
  #include <BleKeyboard.h>
  const uint8_t PIN_IN = 3, PIN_OUT = 4, PIN_UNDO = 5, PIN_MOTOR = 6;
  const uint8_t PIN_SDA = 7, PIN_SCL = 10;      // off the strapping pins (0, 2, 8, 9)
  BleKeyboard ble("Head Count Clicker", "Head Count", 100);

#elif TRANSPORT == TRANSPORT_NRF52
  #include <bluefruit.h>
  const uint8_t PIN_IN = D0, PIN_OUT = D1, PIN_UNDO = D2, PIN_MOTOR = D3;   // I2C on D4/D5
  BLEDis bledis;
  BLEHidAdafruit blehid;
  #define KEY_UP_ARROW   HID_KEY_ARROW_UP        // HID usage ids, not ASCII
  #define KEY_DOWN_ARROW HID_KEY_ARROW_DOWN
  #define KEY_BACKSPACE  HID_KEY_BACKSPACE
  void wakeISR() {}                              // exists only to end waitForEvent()

#else
  #include <Keyboard.h>
  const uint8_t PIN_IN = 5, PIN_OUT = 6, PIN_UNDO = 7, PIN_MOTOR = 9;   // 2 and 3 are this board's I2C
#endif

/* ---------------- display ----------------
   A 128x64 SSD1306 on I2C, about $2. It holds no state of its own: everything
   drawn here arrived in the last packet from the host. Redraws are coalesced
   and never sit in front of a keystroke - the key goes out first, always. */

#if DISPLAY
  #include <U8g2lib.h>
  #include <Wire.h>
  U8G2_SSD1306_128X64_NONAME_F_HW_I2C oled(U8G2_R0, U8G2_PIN_NONE);

  const uint8_t COLS = 96;             // must match LINK_COLS in app.js
  const uint16_t DRAW_MS = 120;        // ~8fps is plenty, and leaves the bus alone
  const uint32_t STALE_MS = 5000;      // no packet for this long and we say so
  const uint32_t DIM_MS = 30000;       // blank the panel when nothing is happening

  struct Host {                        // the last thing the app told us, verbatim
    int16_t occ, peak, lo, hi;
    uint8_t n, series[COLS];
    bool live, seen;
    uint32_t at;
  } host = { 0, 0, 0, 0, 0, {0}, false, false, 0 };

  bool dirty = true;
  uint32_t drawnAt = 0, touchedAt = 0;
  bool panelOn = true;

  int16_t le16(const uint8_t* p) { return (int16_t)(p[0] | (p[1] << 8)); }

  // Packet layout is documented in app.js. Anything malformed is dropped whole:
  // a half-applied packet would draw a graph that never existed.
  void onPacket(const uint8_t* d, size_t len) {
    if (len < 11 || d[0] != 1) return;
    uint8_t n = d[10];
    if (n > COLS || len < (size_t)11 + n) return;
    host.live = d[1] & 1;
    host.occ  = le16(d + 2);
    host.peak = le16(d + 4);
    host.lo   = le16(d + 6);
    host.hi   = le16(d + 8);
    host.n    = n;
    memcpy(host.series, d + 11, n);
    host.seen = true;
    host.at = millis();
    dirty = true;
  }

  void drawGraph(uint8_t x0, uint8_t y0, uint8_t w, uint8_t h) {
    if (!host.n) return;
    uint8_t prev = 0;
    for (uint8_t c = 0; c < host.n; c++) {
      uint8_t x = x0 + (uint16_t)c * w / host.n;
      uint8_t y = y0 + h - 1 - ((uint16_t)host.series[c] * (h - 1) / 255);
      if (c) oled.drawVLine(x, min(prev, y), abs((int)prev - (int)y) + 1);  // step, not slope
      else oled.drawPixel(x, y);
      uint8_t xn = x0 + (uint16_t)(c + 1) * w / host.n;
      if (xn > x) oled.drawHLine(x, y, xn - x);
      prev = y;
    }
    if (host.lo < 0) {                 // the zero line matters when it is not the floor
      uint8_t zy = y0 + h - 1 - ((uint16_t)(0 - host.lo) * (h - 1) / (host.hi - host.lo ? host.hi - host.lo : 1));
      for (uint8_t x = x0; x < x0 + w; x += 4) oled.drawPixel(x, zy);
    }
  }

  void redraw() {
    oled.clearBuffer();
    if (!host.seen || millis() - host.at > STALE_MS) {
      oled.setFont(u8g2_font_6x12_tf);
      oled.drawStr(0, 12, host.seen ? "app not sending" : "waiting for app");
      oled.drawStr(0, 26, "clicks still work");
    } else {
      char buf[16];
      oled.setFont(u8g2_font_logisoso24_tn);          // digits only, so print the sign apart
      snprintf(buf, sizeof buf, "%d", host.occ < 0 ? -host.occ : host.occ);
      uint8_t w = oled.getStrWidth(buf), x = 2;
      if (host.occ < 0) { oled.setFont(u8g2_font_6x12_tf); oled.drawStr(0, 22, "-"); x = 8; }
      oled.setFont(u8g2_font_logisoso24_tn);
      oled.drawStr(x, 25, buf);
      oled.setFont(u8g2_font_5x7_tf);
      oled.drawStr(x + w + 4, 25, "inside");
      snprintf(buf, sizeof buf, "peak %d", host.peak);
      oled.drawStr(x + w + 4, 14, buf);
      if (!host.live) oled.drawStr(104, 7, "end");
      drawGraph(0, 30, 128, 34);
    }
    oled.sendBuffer();
    drawnAt = millis();
    dirty = false;
  }

  // Blanking the panel is safe where sleeping the radio is not: it lights again
  // in microseconds and no press is lost waiting for it.
  void displayTick() {
    bool want = millis() - touchedAt < DIM_MS;
    if (want != panelOn) { panelOn = want; oled.setPowerSave(!want); dirty = true; }
    if (!panelOn) return;
    if (!dirty && millis() - drawnAt < STALE_MS) return;
    if (millis() - drawnAt < DRAW_MS) return;
    redraw();
  }
#endif

const uint16_t DEBOUNCE = 20;        // arcade microswitches settle well inside this

/* ---------------- transport ---------------- */

bool linked() {
#if TRANSPORT == TRANSPORT_ESP32
  return ble.isConnected();
#elif TRANSPORT == TRANSPORT_NRF52
  return Bluefruit.connected();
#else
  return true;                                   // a cable is either in or it is not
#endif
}

void sendKey(uint8_t key) {
#if TRANSPORT == TRANSPORT_ESP32
  ble.write(key);                                // write() presses and releases
#elif TRANSPORT == TRANSPORT_NRF52
  uint8_t keys[6] = { key, 0, 0, 0, 0, 0 };
  blehid.keyboardReport(0, keys);
  delay(6);
  blehid.keyRelease();
#else
  Keyboard.press(key);
  delay(6);
  Keyboard.release(key);
#endif
}

/* ---------------- downlink ----------------
   A custom GATT service carrying the host's packet. It sits beside the HID
   service, so the app writes here while the OS still sees a plain keyboard.
   UUIDs must match LINK_SVC / LINK_CHR in app.js.

   Bluefruit adds a service alongside BLEHidAdafruit as a matter of course. The
   ESP32 path is left out on purpose: BleKeyboard owns its BLE server and does
   not hand it over, so a second service there means forking the library.
   Build DISPLAY on the nRF52; a C3 can drive the panel only once that is
   sorted. This is the part to prove on hardware before buying three of them. */

#if DISPLAY && TRANSPORT == TRANSPORT_NRF52
  const uint8_t LINK_SVC_UUID[16] = {   // 48ea0001-6b75-4b1b-9c3b-1a2c4d5e6f70, LE
    0x70,0x6f,0x5e,0x4d,0x2c,0x1a,0x3b,0x9c,0x1b,0x4b,0x75,0x6b,0x01,0x00,0xea,0x48 };
  const uint8_t LINK_CHR_UUID[16] = {   // ...0002...
    0x70,0x6f,0x5e,0x4d,0x2c,0x1a,0x3b,0x9c,0x1b,0x4b,0x75,0x6b,0x02,0x00,0xea,0x48 };

  BLEService linkSvc(LINK_SVC_UUID);
  BLECharacteristic linkChr(LINK_CHR_UUID);

  void onLinkWrite(uint16_t, BLECharacteristic*, uint8_t* data, uint16_t len) {
    onPacket(data, len);
  }

  void linkBegin() {
    linkSvc.begin();
    linkChr.setProperties(CHR_PROPS_WRITE | CHR_PROPS_WRITE_WO_RESP);
    linkChr.setPermission(SECMODE_OPEN, SECMODE_OPEN);
    linkChr.setMaxLen(180);
    linkChr.setWriteCallback(onLinkWrite);
    linkChr.begin();
  }
#else
  void linkBegin() {}
#endif

/* ---------------- feedback ----------------
   A piezo is inaudible at a door at 1am and an LED means looking, so the local
   feedback is a coin vibration motor. Four shapes, tellable apart through a
   pocket: IN one pulse, OUT two, UNDO three, and one long buzz for "the radio
   is not linked, that press went nowhere". Non-blocking, because a run of fast
   taps must never be slowed by its own feedback. */

const uint16_t PAT_IN[]    = { 25, 0 };              // alternating on/off ms, 0 ends it
const uint16_t PAT_OUT[]   = { 12, 40, 12, 0 };
const uint16_t PAT_UNDO[]  = { 10, 35, 10, 35, 10, 0 };
const uint16_t PAT_LOST[]  = { 400, 0 };
const uint16_t PAT_READY[] = { 40, 90, 40, 0 };

const uint16_t* pat = NULL;
uint8_t patStep = 0;
uint32_t patAt = 0;

void buzz(const uint16_t* p) {
  pat = p; patStep = 0; patAt = millis();
  digitalWrite(PIN_MOTOR, HIGH);
}

void buzzTick() {
  if (!pat) return;
  if (millis() - patAt < pat[patStep]) return;
  patAt += pat[patStep];
  if (pat[++patStep] == 0) { pat = NULL; digitalWrite(PIN_MOTOR, LOW); return; }
  digitalWrite(PIN_MOTOR, (patStep % 2) ? LOW : HIGH);
}

/* ---------------- buttons ----------------
   Edge triggered, pressed and released in one go. Nothing repeats while a
   button is held: a key left down would let the host's own auto-repeat turn one
   stuck button into hundreds of phantom guests. The app drops repeats too, but
   the fix belongs here, at the source. */

struct Button {
  uint8_t pin, key;
  const uint16_t* pattern;
  bool stable, raw;                  // INPUT_PULLUP: HIGH released, LOW pressed
  uint32_t changed;
};

Button buttons[] = {
  { PIN_IN,   KEY_UP_ARROW,   PAT_IN,   true, true, 0 },
  { PIN_OUT,  KEY_DOWN_ARROW, PAT_OUT,  true, true, 0 },
  { PIN_UNDO, KEY_BACKSPACE,  PAT_UNDO, true, true, 0 },
};
const uint8_t N = sizeof(buttons) / sizeof(buttons[0]);

void pollButton(Button& b) {
  bool now = digitalRead(b.pin);
  if (now != b.raw) { b.raw = now; b.changed = millis(); return; }
  if (now == b.stable || millis() - b.changed < DEBOUNCE) return;
  b.stable = now;
  if (now) return;                                 // rising edge = released
#if DISPLAY
  touchedAt = millis();                            // any press wakes the panel
#endif
  if (!linked()) { buzz(PAT_LOST); return; }       // say so rather than drop it silently
  sendKey(b.key);                                  // the key goes first, always
  buzz(b.pattern);
}

#if DISPLAY
  bool dirtyOrLit() { return dirty || panelOn; }
#else
  bool dirtyOrLit() { return false; }
#endif

bool idle() {
  if (pat) return false;
  for (uint8_t i = 0; i < N; i++) if (!buttons[i].stable) return false;
  return true;
}

/* ---------------- run ---------------- */

void setup() {
  pinMode(PIN_MOTOR, OUTPUT);
  digitalWrite(PIN_MOTOR, LOW);
  for (uint8_t i = 0; i < N; i++) pinMode(buttons[i].pin, INPUT_PULLUP);

#if TRANSPORT == TRANSPORT_ESP32
  ble.begin();

#elif TRANSPORT == TRANSPORT_NRF52
  Bluefruit.begin();
  Bluefruit.setTxPower(4);
  Bluefruit.setName("Head Count Clicker");         // what you look for when pairing
  bledis.setManufacturer("Head Count");
  bledis.setModel("Clicker");
  bledis.begin();
  blehid.begin();
  Bluefruit.Periph.setConnInterval(9, 16);         // 11-20ms, so a press feels instant

  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  Bluefruit.Advertising.addAppearance(BLE_APPEARANCE_HID_KEYBOARD);
  Bluefruit.Advertising.addService(blehid);
  Bluefruit.Advertising.addName();
  Bluefruit.Advertising.restartOnDisconnect(true); // walk out of range, walk back, keep counting
  Bluefruit.Advertising.setInterval(32, 244);
  Bluefruit.Advertising.setFastTimeout(30);
  linkBegin();
#if DISPLAY
  Bluefruit.Advertising.addService(linkSvc);        // so the app's filter can find us
#endif
  Bluefruit.Advertising.start(0);                  // advertise forever

  for (uint8_t i = 0; i < N; i++)
    attachInterrupt(digitalPinToInterrupt(buttons[i].pin), wakeISR, CHANGE);

#else
  Keyboard.begin();
#endif

#if DISPLAY
  #if TRANSPORT == TRANSPORT_ESP32
    Wire.begin(PIN_SDA, PIN_SCL);
  #else
    Wire.begin();
  #endif
  oled.begin();
  oled.setBusClock(400000);
  touchedAt = millis();
#endif

  buzz(PAT_READY);                                 // alive, without looking
}

/* No idle timeout and no deep sleep on purpose. Waking the radio and
   re-establishing a BLE link takes a second or more, and the press that woke it
   would be the one that is lost - after exactly the quiet spell a door has all
   the time. The slide switch is the power saving. */
void loop() {
  for (uint8_t i = 0; i < N; i++) pollButton(buttons[i]);
  buzzTick();
#if DISPLAY
  displayTick();                                   // after the buttons, never before
#endif
#if TRANSPORT == TRANSPORT_NRF52
  if (idle() && !dirtyOrLit()) waitForEvent();     // sleep until a button or the radio
#endif
}
