'use strict';
/* Head Count - offline door counter. All state lives in localStorage and is
   written on every tap, so a locked phone, a killed tab or a reboot mid-event
   loses nothing. Timestamps are absolute epoch ms; nothing depends on the page
   staying awake or on a timer surviving the night. */

const K_ACTIVE = 'hc.active.v1', K_BAK = 'hc.active.bak.v1', K_ARCH = 'hc.arch.v1';
const $ = id => document.getElementById(id);

/* ---------------- storage ----------------
   Wrapped because localStorage is not guaranteed: opened from file:// some
   browsers throw on access, and any browser can throw on quota. The app must
   keep counting either way, loudly. */

const LS = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); return true; } catch { return false; } },
  del(k) { try { localStorage.removeItem(k); } catch {} },
  probe() {
    try {
      localStorage.setItem('hc.probe', 'x');
      const ok = localStorage.getItem('hc.probe') === 'x';
      localStorage.removeItem('hc.probe');
      return ok;
    } catch { return false; }
  }
};

let storageOk = true;
function warnBanner(msg) { const el = $('warn'); el.textContent = msg; el.hidden = false; storageOk = false; }
function clearBanner() { $('warn').hidden = true; storageOk = true; }

/* ---------------- state ---------------- */

// The random suffix matters: ids reconcile an interrupted End event, so two
// sessions created in the same millisecond must never share one.
const blank = () => ({
  id: 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
  label: '', startedAt: null, endedAt: null, ev: [],
});

function readKey(k) {
  try { const o = JSON.parse(LS.get(k) || 'null'); return o && Array.isArray(o.ev) ? o : null; }
  catch { return null; }
}
function loadActive() {
  const a = readKey(K_ACTIVE), b = readKey(K_BAK);
  if (a && b) return b.ev.length > a.ev.length ? b : a;   // main write torn? take the fuller copy
  return a || b || blank();
}
function loadArch() {
  try { const a = JSON.parse(LS.get(K_ARCH) || '[]'); return Array.isArray(a) ? a : []; }
  catch { return []; }
}

let S, ARCH;
let viewing = null;          // session shown in the data sheet (null = the live one)
let tick = null, chartTick = null;

// Every tap writes the whole session. A second copy lands every 10 taps and is
// read back to prove the write landed, so a write torn by the OS killing the
// tab costs at most a handful of taps.
function save(forceBackup) {
  const json = JSON.stringify(S);
  if (!LS.set(K_ACTIVE, json)) {
    warnBanner('Could not save the last tap - storage is full or blocked. Export the CSV now.');
    return;
  }
  if (forceBackup || S.ev.length % 10 === 0) {
    if (!LS.set(K_BAK, json) || LS.get(K_BAK) !== json) {
      warnBanner('Backup copy is not saving. Export the CSV now.');
      return;
    }
  }
  if (!storageOk) clearBanner();
}
// Writes a candidate archive and reads it back. Callers adopt the new list only
// on success. The archive is never trimmed to make room: deleting an event is
// the user's decision, made on the Events screen.
function saveArch(list) {
  const json = JSON.stringify(list);
  return LS.set(K_ARCH, json) && LS.get(K_ARCH) === json;
}

// An End event interrupted between the archive write and the reset leaves the
// same session in both places. The archive copy is the finished one, so the
// live slot starts fresh instead of the event being counted twice.
function reload() {
  S = loadActive(); ARCH = loadArch();
  if (ARCH.some(a => a.id === S.id)) { S = blank(); save(true); }
}
reload();   // now, before any wiring: nothing below may leave the pads without state

/* ---------------- derived ---------------- */

function fold(s) {
  let occ = 0, tin = 0, tout = 0, peak = 0, low = 0, peakAt = s.startedAt;
  for (const [t, d] of s.ev) {
    occ += d; d > 0 ? tin++ : tout++;
    if (occ > peak) { peak = occ; peakAt = t; }
    if (occ < low) low = occ;
  }
  return { occ, tin, tout, peak, low, peakAt, n: s.ev.length };
}
const endOf = s => s.endedAt || Date.now();
const durOf = s => s.startedAt ? endOf(s) - s.startedAt : 0;

/* ---------------- analysis ----------------
   Everything here is derived from the tap log alone - no assumptions about
   who anyone is, only how many and when. */

// Most events inside any window of `win` ms, found by sliding the window
// along the event times.
function busiest(ts, win) {
  if (!ts.length) return null;
  let best = 0, at = ts[0], j = 0;
  for (let i = 0; i < ts.length; i++) {
    while (ts[i] - ts[j] > win) j++;
    if (i - j + 1 > best) { best = i - j + 1; at = ts[j]; }
  }
  return { n: best, from: at, to: at + win, rate: best / (win / 3600000) };
}

function analyze(s) {
  const f = fold(s);
  const t0 = s.startedAt, t1 = endOf(s), span = Math.max(1, t1 - t0);
  const ins = [], outs = [];
  for (const [t, d] of s.ev) (d > 0 ? ins : outs).push(t);

  // Area under the occupancy curve. Divided by arrivals it gives the average
  // time a guest spent inside (Little's law) - the tap log never identifies
  // anyone, so this is the only honest way to get a dwell time out of it.
  let area = 0, occ = 0, prev = t0;
  for (const [t, d] of s.ev) { area += occ * (t - prev); prev = t; occ += d; }
  area += occ * (t1 - prev);

  // Surge window scales with the event: a 20-minute session should not be
  // measured against an hour-long window.
  const win = Math.min(3600000, Math.max(300000, Math.round(span / 6)));
  const tailWin = Math.min(1800000, Math.max(600000, Math.round(span / 8)));
  let net = 0;
  for (const [t, d] of s.ev) if (t >= t1 - tailWin) net += d;

  return Object.assign(f, {
    span, area,
    avgStay: f.tin ? area / f.tin : 0,
    surgeIn: busiest(ins, win),
    surgeOut: busiest(outs, win),
    medianIn: f.tin ? ins[Math.ceil(f.tin / 2) - 1] : null,
    trend: net / (tailWin / 3600000),
    turnover: f.peak ? f.tin / f.peak : 0,
  });
}

function narrate(s, a) {
  if (!a.n) return '';
  const b = [];
  if (a.surgeIn) b.push(`Arrivals ran hardest ${spanOf(a.surgeIn.from, a.surgeIn.to)}, about ${Math.round(a.surgeIn.rate)} an hour.`);
  if (a.peak) b.push(`Fullest at ${hm(a.peakAt)} with ${a.peak} inside.`);
  if (a.surgeOut && a.tout > 2) b.push(`Heaviest exits ${spanOf(a.surgeOut.from, a.surgeOut.to)}.`);
  if (a.tin && a.turnover >= 1.35) b.push(`${a.tin} guests passed through a room that held at most ${a.peak}, so the crowd turned over about ${a.turnover.toFixed(1)}×.`);
  if (!s.endedAt) {
    b.push(Math.abs(a.trend) < 2 ? 'Right now it is holding steady.'
      : `Right now it is ${a.trend > 0 ? 'filling' : 'emptying'} at about ${Math.abs(Math.round(a.trend))} an hour.`);
  } else if (a.occ > 0) {
    b.push(`${a.occ} ${a.occ === 1 ? 'person was' : 'people were'} still counted inside at the end.`);
  }
  return b.join(' ');
}

/* ---------------- formatting ----------------
   Every clock time comes from local Date getters, so the phone's own clock and
   time zone decide what is shown - never UTC, never a fixed zone. People read
   12-hour times with AM/PM; durations stay H:MM:SS. */

const p2 = n => String(n).padStart(2, '0');
function hms(ms) {
  const t = Math.max(0, Math.floor(ms / 1000));
  return p2(Math.floor(t / 3600)) + ':' + p2(Math.floor(t / 60) % 60) + ':' + p2(t % 60);
}
function durShort(ms) {
  const m = Math.round(ms / 60000);
  if (m < 60) return m + 'm';
  const h = Math.floor(m / 60), r = m % 60;
  return r ? h + 'h ' + r + 'm' : h + 'h';
}
function clock12(t, secs) {
  const d = new Date(t), h = d.getHours();
  return (h % 12 || 12) + ':' + p2(d.getMinutes()) + (secs ? ':' + p2(d.getSeconds()) : '') + (h < 12 ? ' AM' : ' PM');
}
const hm = t => clock12(t, false);        // 9:05 PM
const clockOf = t => clock12(t, true);    // 9:05:12 PM
// "9:40–10:40 PM", or "11:30 PM–12:30 AM" when the range crosses noon or midnight.
function spanOf(a, b) {
  const x = hm(a), y = hm(b);
  return x.slice(-2) === y.slice(-2) ? x.slice(0, -3) + '–' + y : x + '–' + y;
}
const dateOf = t => { const d = new Date(t); return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate()); };
const stampOf = t => { const d = new Date(t); return '' + d.getFullYear() + p2(d.getMonth() + 1) + p2(d.getDate()) + '-' + p2(d.getHours()) + p2(d.getMinutes()); };
const localOf = t => dateOf(t) + ' ' + clockOf(t);
const titleOf = s => s.label || (s.startedAt ? 'Event ' + dateOf(s.startedAt) : 'New event');

/* ---------------- counting ---------------- */

function record(d, pad) {
  const t = Date.now();
  if (!S.startedAt) S.startedAt = t;
  S.ev.push([t, d]);
  save(); render(); refreshSheet(false);
  if (pad) { pad.classList.add('hit'); setTimeout(() => pad.classList.remove('hit'), 90); }
  if (navigator.vibrate) navigator.vibrate(d > 0 ? 14 : [10, 30, 10]);
  startTick();
}

function undo() {
  if (!S.ev.length) return;
  const last = S.ev.pop();
  if (!S.ev.length) S.startedAt = null;
  save(true);                       // the backup must not outlive the removed tap
  render(); refreshSheet(true);
  toast('Removed last ' + (last[1] > 0 ? 'IN' : 'OUT'));
}

// Order is the whole point. The event is written into the archive and verified
// before the live session is reset, so it never exists only in memory. If the
// archive cannot take it, the event simply stays live.
function endEvent() {
  const done = Object.assign({}, S, { endedAt: Date.now() });
  const next = [done].concat(ARCH);
  if (!saveArch(next)) {
    warnBanner('Storage is full - this event was NOT ended and is still counting. Export its CSV, then delete old events in Events.');
    return;
  }
  ARCH = next;
  S = blank();
  LS.del(K_BAK);
  save(); render();
  viewing = done; openSheet();
  toast('Event ended - saved to Events');
}

/* ---------------- render ---------------- */

function render() {
  const f = fold(S);
  const occEl = $('occ');
  occEl.textContent = f.occ;
  occEl.classList.toggle('neg', f.occ < 0);
  $('tin').textContent = f.tin;
  $('tout').textContent = f.tout;
  $('peak').textContent = f.peak;
  $('label').textContent = S.label || 'Tap to name event';
  $('label').classList.toggle('unnamed', !S.label);
  $('btnUndo').disabled = !f.n;
  $('btnEnd').disabled = !f.n;
  paintClock();
}
// The clock is the device's own time; the session's running length sits beside it.
function paintClock() {
  $('clock').textContent = hm(Date.now());
  const el = $('elapsed');
  if (el) { el.hidden = !S.startedAt; el.textContent = hms(durOf(S)) + ' elapsed'; }
}

function startTick() {
  if (tick || document.hidden) return;
  tick = setInterval(paintClock, 1000);
}
function stopTick() { clearInterval(tick); tick = null; }

/* ---------------- data sheet ---------------- */

const cur = () => viewing || S;

function openSheet() {
  $('sheet').hidden = false;
  $('sheet').querySelector('.sheetbody').scrollTop = 0;
  refreshSheet(true);
  clearInterval(chartTick);
  chartTick = setInterval(() => { if (!document.hidden && !cur().endedAt) refreshSheet(false); }, 2000);
}
function closeSheet() {
  $('sheet').hidden = true; viewing = null;
  clearInterval(chartTick); chartTick = null;
  renderEvents();                   // Events may be underneath
}

function refreshSheet(full) {
  if ($('sheet').hidden) return;
  const s = cur(), a = analyze(s);
  $('sheetTitle').textContent = titleOf(s) + (s.endedAt ? ' (ended)' : ' (live)');

  const rate = r => (r > 0 && r < 1 ? r.toFixed(1) : Math.round(r));
  $('stats').innerHTML = [
    [a.peak, 'peak inside', a.peak ? 'at ' + hm(a.peakAt) : ''],
    [hms(a.span), 'duration', s.startedAt ? 'from ' + hm(s.startedAt) : ''],
    [a.surgeIn ? '+' + rate(a.surgeIn.rate) + '/hr' : '—', 'peak arrivals',
      a.surgeIn ? spanOf(a.surgeIn.from, a.surgeIn.to) : ''],
    [a.surgeOut ? '−' + rate(a.surgeOut.rate) + '/hr' : '—', 'peak exits',
      a.surgeOut ? spanOf(a.surgeOut.from, a.surgeOut.to) : ''],
    [a.tin ? durShort(a.avgStay) : '—', 'avg stay', 'estimated'],
    [a.medianIn ? hm(a.medianIn) : '—', 'half in by',
      a.tin ? Math.ceil(a.tin / 2) + ' of ' + a.tin + ' arrivals' : ''],
  ].map(r => '<div class="stat"><b>' + r[0] + '</b><span>' + r[1] + '</span><i>' + r[2] + '</i></div>').join('');

  $('insight').textContent = narrate(s, a);
  drawChart(s, a);
  drawFlow(s);
  if (full) renderTable(s);
}

function renderTable(s) {
  const CAP = 300, rows = [];
  let occ = 0; const occs = s.ev.map(e => (occ += e[1]));
  const from = Math.max(0, s.ev.length - CAP);
  for (let i = s.ev.length - 1; i >= from; i--) {
    const t = s.ev[i][0], d = s.ev[i][1];
    rows.push('<tr><td>' + (i + 1) + '</td><td>' + clockOf(t) + '</td><td>' + hms(t - s.startedAt) +
      '</td><td class="' + (d > 0 ? 'din' : 'dout') + '">' + (d > 0 ? 'IN' : 'OUT') +
      '</td><td>' + occs[i] + '</td></tr>');
  }
  $('tbody').innerHTML = rows.join('') || '<tr><td colspan="5">No taps yet.</td></tr>';
  $('tcap').textContent = s.ev.length > CAP
    ? 'Newest first - showing last ' + CAP + ' of ' + s.ev.length + ' taps. Full log is in the CSV.'
    : 'Newest first - ' + s.ev.length + ' tap' + (s.ev.length === 1 ? '' : 's') + '. Full log is in the CSV.';
}

const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ---------------- events archive ----------------
   Every ended event stays on the device until the user deletes it. Storage is
   the only limit, and the screen shows how close to it the device is. */

const QUOTA = 5 * 1024 * 1024;   // Safari's localStorage quota - the tightest mainstream one
const kb = n => n < 1048576 ? Math.max(1, Math.round(n / 1024)) + ' KB' : (n / 1048576).toFixed(1) + ' MB';
const storedBytes = () => [K_ACTIVE, K_BAK, K_ARCH].reduce((n, k) => n + (LS.get(k) || '').length, 0);

function openEvents() {
  $('events').hidden = false;
  $('events').querySelector('.sheetbody').scrollTop = 0;
  renderEvents();
}
function closeEvents() { $('events').hidden = true; }

function renderEvents() {
  if (!$('events') || $('events').hidden) return;
  const used = storedBytes(), tight = used / QUOTA > 0.8;
  const guests = ARCH.reduce((n, s) => n + fold(s).tin, 0);
  const sum = $('evsum');
  sum.classList.toggle('full', tight);
  sum.textContent = !ARCH.length ? '' :
    `${ARCH.length} ended event${ARCH.length === 1 ? '' : 's'} · ${guests} guests counted · ~${kb(used)} of ~5 MB used on this device` +
    (tight ? '. Nearly full - export and delete old events.' : '');

  $('evlist').innerHTML = !ARCH.length
    ? '<p class="evempty">No ended events yet.<br>An event lands here when you tap <b>End event</b>.</p>'
    : ARCH.map((s, i) => {
      const a = analyze(s), t0 = s.startedAt || s.endedAt;
      const day = new Date(t0).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
      return '<article class="evcard">' +
        '<button class="evopen" data-view="' + i + '"><b>' + esc(titleOf(s)) + '</b>' +
        '<span>' + day + ' · ' + spanOf(t0, s.endedAt) + ' · ' + durShort(a.span) + '</span>' +
        '<span class="evnums"><em>' + a.tin + '</em> guests · <em>' + a.peak + '</em> peak · <em>' +
        (a.tin ? durShort(a.avgStay) : '—') + '</em> avg stay</span></button>' +
        '<div class="evacts"><button class="mini" data-csv="' + i + '">' + (canShareFiles ? 'Share CSV' : 'Download CSV') + '</button>' +
        '<button class="mini danger" data-del="' + i + '">Delete</button></div></article>';
    }).join('');
}

// Names the live session or, from the data sheet, any ended one. An ended
// event is renamed by writing the whole archive, read back and adopted only on
// success - the same as End and Delete. Matched by id, because a foreground
// reload swaps ARCH for fresh objects the sheet may not be holding.
function renameEvent(s) {
  const v = prompt(s.label ? 'Rename this event' : 'Name this event', s.label || '');
  if (v === null) return;
  const label = v.trim().slice(0, 60);
  if (label === s.label) return;
  if (!s.endedAt) {
    S.label = label; save(true);
  } else {
    const i = ARCH.findIndex(a => a.id === s.id);
    if (i < 0) return toast('That event is no longer on this device');
    const next = ARCH.slice();
    next[i] = Object.assign({}, ARCH[i], { label });
    if (!saveArch(next)) return warnBanner('Could not rename that event - storage is full or blocked.');
    ARCH = next;
    if (viewing) viewing = next[i];
  }
  render(); refreshSheet(true); renderEvents();
}

function deleteEvent(i) {
  const s = ARCH[i];
  if (!confirm('Delete "' + titleOf(s) + '" permanently? Export its CSV first if you need it.')) return;
  const next = ARCH.slice(0, i).concat(ARCH.slice(i + 1));
  if (!saveArch(next)) return warnBanner('Could not delete that event - storage is blocked.');
  ARCH = next;
  renderEvents();
  toast('Event deleted');
}

/* ---------------- charts ---------------- */

// Shared frame setup: sizes the backing store for the display density and
// returns the plot rectangle plus the session's time range.
function frame(id, s) {
  const c = $(id), ctx = c.getContext('2d');
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const W = c.clientWidth, H = c.clientHeight;
  if (!W || !H) return null;
  c.width = Math.round(W * dpr); c.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  ctx.font = '11px system-ui, sans-serif';
  if (!s.startedAt) {
    ctx.fillStyle = '#8ba0b4'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('Tap IN to start the session', W / 2, H / 2);
    return null;
  }
  const L = 34, R = 10, T = 12, B = 22;
  const t0 = s.startedAt, t1 = Math.max(endOf(s), t0 + 60000);
  return { ctx, W, H, L, T, pw: W - L - R, ph: H - T - B, t0, t1, X: t => L + (t - t0) / (t1 - t0) * (W - L - R) };
}

// The most evenly spaced times, 2 to 5, that neither touch nor repeat (a short
// session would otherwise read 11:58, 11:58, 11:59). Widths are measured:
// "12:45 AM" is far wider than "00:45" was. The end labels align inward so
// neither clips. Time runs on epoch ms, so midnight is just a point on a line.
function xAxis(g) {
  const { ctx, T, ph, t0, t1, X } = g;
  let marks;
  for (let n = 5; n >= 2; n--) {
    marks = [];
    for (let i = 0; i < n; i++) {
      const t = t0 + (t1 - t0) * i / (n - 1), text = hm(t), w = ctx.measureText(text).width, x = X(t);
      const left = i === 0 ? x : i === n - 1 ? x - w : x - w / 2;
      marks.push({ text, left, right: left + w });
    }
    if (marks.every((m, i) => !i || (m.left - marks[i - 1].right >= 12 && m.text !== marks[i - 1].text))) break;
  }
  ctx.fillStyle = '#8ba0b4'; ctx.textBaseline = 'top'; ctx.textAlign = 'left';
  for (const m of marks) ctx.fillText(m.text, m.left, T + ph + 6);
}

function drawChart(s, a) {
  const g = frame('chart', s); if (!g) return;
  const { ctx, L, T, pw, ph, t0, t1, X } = g;

  const top = Math.max(1, a.peak) * 1.08, bot = Math.min(0, a.low) * 1.08;
  const step = niceStep((top - bot) / 4);
  const yMax = Math.max(step, Math.ceil(top / step) * step);
  const yMin = Math.min(0, Math.floor(bot / step) * step);
  const Y = v => T + ph - (v - yMin) / (yMax - yMin) * ph;

  ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.lineWidth = 1;
  for (let v = yMin; v <= yMax + 1e-9; v += step) {
    const y = Math.round(Y(v)) + 0.5;
    ctx.strokeStyle = v === 0 ? '#3a4b5c' : '#1e2a36';
    ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + pw, y); ctx.stroke();
    ctx.fillStyle = '#8ba0b4'; ctx.fillText(String(v), L - 6, Y(v));
  }

  // step line: occupancy holds flat between taps
  const pts = [[t0, 0]]; let occ = 0;
  for (const e of s.ev) { pts.push([e[0], occ]); occ += e[1]; pts.push([e[0], occ]); }
  pts.push([t1, occ]);

  ctx.beginPath(); ctx.moveTo(X(t0), Y(0));
  for (const p of pts) ctx.lineTo(X(p[0]), Y(p[1]));
  ctx.lineTo(X(t1), Y(0)); ctx.closePath();
  ctx.fillStyle = 'rgba(63,209,139,.16)'; ctx.fill();

  ctx.beginPath();
  pts.forEach((p, i) => i ? ctx.lineTo(X(p[0]), Y(p[1])) : ctx.moveTo(X(p[0]), Y(p[1])));
  ctx.strokeStyle = '#3fd18b'; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.stroke();

  if (a.peak > 0) {
    const px = X(a.peakAt), py = Y(a.peak), flip = px > L + pw - 46;
    ctx.fillStyle = '#e8eef5';
    ctx.beginPath(); ctx.arc(px, py, 3, 0, Math.PI * 2); ctx.fill();
    ctx.textBaseline = 'bottom'; ctx.textAlign = flip ? 'right' : 'left';
    ctx.fillText('peak ' + a.peak, px + (flip ? -6 : 6), py - 4);
  }
  xAxis(g);
}

const BUCKETS = [60e3, 120e3, 300e3, 600e3, 900e3, 1800e3, 3600e3, 7200e3];

// Arrivals above the line, exits below: the shape of the flow itself, which
// the occupancy curve only shows as a slope.
function drawFlow(s) {
  const g = frame('flow', s); if (!g) return;
  const { ctx, L, T, pw, ph, t0, t1, X } = g;

  const unit = BUCKETS.find(u => (t1 - t0) / u <= 48) || BUCKETS[BUCKETS.length - 1];
  const nb = Math.max(1, Math.ceil((t1 - t0) / unit));
  const ins = new Array(nb).fill(0), outs = new Array(nb).fill(0);
  for (const [t, d] of s.ev) {
    const i = Math.min(nb - 1, Math.floor((t - t0) / unit));
    if (d > 0) ins[i]++; else outs[i]++;
  }
  const max = Math.max(1, ...ins, ...outs);
  const mid = T + ph / 2, half = ph / 2 - 2;
  const bw = Math.max(1, pw / nb - 1);

  ctx.strokeStyle = '#3a4b5c'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(L, Math.round(mid) + 0.5); ctx.lineTo(L + pw, Math.round(mid) + 0.5); ctx.stroke();

  for (let i = 0; i < nb; i++) {
    const x = X(t0 + i * unit);
    if (ins[i]) { ctx.fillStyle = '#3fd18b'; ctx.fillRect(x, mid - ins[i] / max * half, bw, ins[i] / max * half); }
    if (outs[i]) { ctx.fillStyle = '#ff8b83'; ctx.fillRect(x, mid + 1, bw, outs[i] / max * half); }
  }

  // Colour says which direction; the caption spells it out. Words here would
  // overrun the narrow gutter.
  ctx.textAlign = 'right';
  ctx.fillStyle = '#3fd18b'; ctx.textBaseline = 'top'; ctx.fillText(String(max), L - 6, T);
  ctx.fillStyle = '#ff8b83'; ctx.textBaseline = 'bottom'; ctx.fillText(String(max), L - 6, T + ph);
  xAxis(g);

  $('flowcap').textContent = 'Arrivals (up) and exits (down) per ' +
    (unit >= 3600e3 ? unit / 3600e3 + ' hr' : unit / 60e3 + ' min');
}

// Nearest nice number, not the next one up: rounding 2.6 up to 5 leaves the
// chart mostly empty space.
function niceStep(x) {
  const p = Math.pow(10, Math.floor(Math.log10(Math.max(x, 1e-9)))), f = x / p;
  let best = 1;
  for (const c of [1, 2, 2.5, 5, 10]) if (Math.abs(Math.log(f / c)) < Math.abs(Math.log(f / best))) best = c;
  return Math.max(1, Math.round(best * p) || 1);
}

/* ---------------- CSV ---------------- */

function csvOf(s) {
  const q = v => { v = String(v); return /[",\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  const out = [['seq', 'iso_timestamp', 'local_time', 'epoch_ms', 'elapsed_s', 'elapsed_hms',
    'direction', 'delta', 'occupancy', 'cumulative_in', 'cumulative_out']];
  let occ = 0, ci = 0, co = 0;
  s.ev.forEach((e, i) => {
    const t = e[0], d = e[1];
    occ += d; d > 0 ? ci++ : co++;
    out.push([i + 1, new Date(t).toISOString(), localOf(t), t, ((t - s.startedAt) / 1000).toFixed(3),
      hms(t - s.startedAt), d > 0 ? 'IN' : 'OUT', d, occ, ci, co]);
  });
  return out.map(r => r.map(q).join(',')).join('\r\n') + '\r\n';
}
function csvName(s) {
  const slug = titleOf(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'event';
  return 'headcount_' + slug + '_' + stampOf(s.startedAt || Date.now()) + '.csv';
}
const csvBlob = s => new Blob(['﻿' + csvOf(s)], { type: 'text/csv;charset=utf-8' });

function downloadCsv(s) {
  if (!s.ev.length) return toast('Nothing to export yet');
  const url = URL.createObjectURL(csvBlob(s));
  const a = document.createElement('a');
  a.href = url; a.download = csvName(s);
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
// iOS hands a shared file to AirDrop / Mail / Files; downloads from a
// home-screen web app are clumsy there, so sharing wins wherever it exists.
const canShareFiles = (() => {
  try { return !!(navigator.canShare && navigator.canShare({ files: [new File([''], 'a.csv', { type: 'text/csv' })] })); }
  catch { return false; }
})();

async function shareCsv(s) {
  if (!s.ev.length) return toast('Nothing to export yet');
  try { await navigator.share({ files: [new File([csvBlob(s)], csvName(s), { type: 'text/csv' })], title: titleOf(s) }); }
  catch {}
}
async function copyCsv(s) {
  if (!s.ev.length) return toast('Nothing to export yet');
  try { await navigator.clipboard.writeText(csvOf(s)); toast('CSV copied to clipboard'); }
  catch { toast('Copy blocked - use Download instead'); }
}

/* ---------------- toast ---------------- */

let toastT;
function toast(msg) {
  const el = $('toast'); el.textContent = msg; el.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => { el.hidden = true; }, 2200);
}

/* ---------------- wiring ---------------- */

// Wire by id, skipping anything absent. A deploy can briefly pair this script
// with an older page; the pads must keep counting rather than the script dying
// at the first button it cannot find.
const on = (id, type, fn) => { const el = $(id); if (el) el.addEventListener(type, fn); };

// pointerdown, not click: the tap must count the instant the finger lands.
const padHandler = delta => e => {
  if (e.pointerType === 'mouse' && e.button !== 0) return;
  record(delta, e.currentTarget);
};
on('padIn', 'pointerdown', padHandler(1));
on('padOut', 'pointerdown', padHandler(-1));

on('btnUndo', 'click', undo);
on('btnData', 'click', () => { viewing = null; openSheet(); });
on('sheetClose', 'click', closeSheet);

on('label', 'click', () => renameEvent(S));
on('sheetRename', 'click', () => renameEvent(cur()));

on('btnEnd', 'click', () => {
  const f = fold(S);
  $('dlgSummary').textContent = titleOf(S) + ' - ' + hms(durOf(S)) + ', ' + f.tin + ' in, ' +
    f.tout + ' out, ' + f.occ + ' still inside.';
  $('dlgEnd').showModal();
});
on('dlgCancel', 'click', () => $('dlgEnd').close());
on('dlgConfirm', 'click', () => { $('dlgEnd').close(); endEvent(); });

on('btnCsv', 'click', () => downloadCsv(cur()));
on('btnCopy', 'click', () => copyCsv(cur()));
on('btnShare', 'click', () => shareCsv(cur()));
if ($('btnShare')) $('btnShare').hidden = !canShareFiles;

on('btnEvents', 'click', openEvents);
on('eventsClose', 'click', closeEvents);
on('evlist', 'click', e => {
  const b = e.target.closest('button'); if (!b) return;
  const d = b.dataset;
  if (d.view != null) { viewing = ARCH[+d.view]; openSheet(); }
  else if (d.csv != null) { const s = ARCH[+d.csv]; canShareFiles ? shareCsv(s) : downloadCsv(s); }
  else if (d.del != null) deleteEvent(+d.del);
});

document.addEventListener('keydown', e => {           // desktop testing
  if ($('dlgEnd').open) return;
  if (e.key === 'ArrowUp' || e.key === 'i') record(1, $('padIn'));
  else if (e.key === 'ArrowDown' || e.key === 'o') record(-1, $('padOut'));
  else if (e.key === 'Escape') {
    if (!$('sheet').hidden) closeSheet();
    else if ($('events') && !$('events').hidden) closeEvents();
  }
});

// Re-read storage on every return to the foreground: the tab may have been
// evicted and rebuilt, or a second tab may have moved the count on.
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { stopTick(); return; }
  if (!LS.probe()) warnBanner('This browser is not saving your count. Export the CSV before closing this tab.');
  else {
    if (!storageOk) clearBanner();
    reload();
  }
  render(); startTick(); refreshSheet(true); renderEvents();
});
window.addEventListener('pageshow', () => { reload(); render(); startTick(); });
window.addEventListener('storage', e => {
  if (e.key === K_ACTIVE || e.key === K_ARCH) { reload(); render(); refreshSheet(true); renderEvents(); }
});
window.addEventListener('resize', () => refreshSheet(false));

/* ---------------- boot ---------------- */

render(); startTick();
if (!LS.probe())
  warnBanner('This browser is not saving your count. Keep this tab open and export the CSV before closing it.');
if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
if ('serviceWorker' in navigator && location.protocol !== 'file:')
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
