/**
 * BeamNG Racing Dashboard – Frontend
 *
 * Data flow:
 *   WebSocket (server push) → frontendState → render loop (rAF, ~60 FPS)
 *
 * The render loop is intentionally decoupled from the WebSocket events so
 * the UI stays smooth even when network jitter delays a packet.
 */

'use strict';

// ── Configuration ─────────────────────────────────────────────────────────────

const WS_RECONNECT_DELAY_MS = 3000;

// ── Frontend state (single source of truth in the browser) ───────────────────

const state = {
  speed: 0,      // km/h
  rpm: 0,        // rev/min
  gear: 1,       // 0=R, 1=N, 2=1st …
  throttle: 0,   // 0–1
  brake: 0,      // 0–1
  fuel: 0,       // 0–1
};

// ── Gauge drawing ─────────────────────────────────────────────────────────────

/**
 * Draw a circular analog gauge onto a canvas.
 *
 * The gauge arc spans 300° – from the 7-o'clock position (lower-left)
 * clockwise to the 5-o'clock position (lower-right).
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} cx          Centre x
 * @param {number} cy          Centre y
 * @param {number} radius      Outer track radius
 * @param {number} value       Current value
 * @param {number} min         Minimum scale value
 * @param {number} max         Maximum scale value
 * @param {number} numTicks    Number of major tick intervals
 * @param {string} arcColor    CSS color for the value arc
 * @param {number|null} redZoneStart  Scale value where the red zone begins
 */
function drawGauge(ctx, cx, cy, radius, value, min, max, numTicks, arcColor, redZoneStart) {
  // Arc geometry: 7 o'clock → 5 o'clock, clockwise, spanning 300° (5π/3 rad)
  const START = (2 / 3) * Math.PI;   // 7 o'clock in canvas coords
  const SPAN  = (5 / 3) * Math.PI;   // 300°
  const END   = START + SPAN;         // 5 o'clock (wraps past 2π, that's fine)

  const clamped    = Math.max(min, Math.min(max, value));
  const normalized = (clamped - min) / (max - min);
  const valueAngle = START + normalized * SPAN;

  const trackWidth = Math.round(radius * 0.13);

  // ── Background track ──────────────────────────────────────────────────────
  ctx.beginPath();
  ctx.arc(cx, cy, radius, START, END, false);
  ctx.strokeStyle = '#222230';
  ctx.lineWidth = trackWidth;
  ctx.lineCap = 'butt';
  ctx.stroke();

  // ── Red zone (optional) ───────────────────────────────────────────────────
  if (redZoneStart !== null && redZoneStart < max) {
    const redNorm  = (redZoneStart - min) / (max - min);
    const redStart = START + redNorm * SPAN;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, redStart, END, false);
    ctx.strokeStyle = '#550000';
    ctx.lineWidth = trackWidth;
    ctx.stroke();
  }

  // ── Value arc ─────────────────────────────────────────────────────────────
  if (normalized > 0) {
    ctx.beginPath();
    ctx.arc(cx, cy, radius, START, valueAngle, false);

    // Switch to red when inside the red zone
    const inRedZone = redZoneStart !== null && value >= redZoneStart;
    ctx.strokeStyle = inRedZone ? '#ff3300' : arcColor;
    ctx.lineWidth = trackWidth - 2;
    ctx.lineCap = 'round';
    ctx.stroke();
  }

  // ── Tick marks & labels ───────────────────────────────────────────────────
  ctx.lineCap = 'butt';
  for (let i = 0; i <= numTicks; i++) {
    const t = i / numTicks;
    const angle = START + t * SPAN;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);

    const isMajor = true; // every tick is a labelled major tick here
    const outerR  = radius + radius * 0.07;
    const innerR  = radius - radius * 0.22;

    ctx.beginPath();
    ctx.moveTo(cx + outerR * cos, cy + outerR * sin);
    ctx.lineTo(cx + innerR * cos, cy + innerR * sin);
    ctx.strokeStyle = '#555';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Half-ticks between majors
    if (i < numTicks) {
      const ht = t + 0.5 / numTicks;
      const ha = START + ht * SPAN;
      const hc = Math.cos(ha);
      const hs = Math.sin(ha);
      const halfInner = radius - radius * 0.12;
      ctx.beginPath();
      ctx.moveTo(cx + outerR * hc, cy + outerR * hs);
      ctx.lineTo(cx + halfInner * hc, cy + halfInner * hs);
      ctx.strokeStyle = '#3a3a4a';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Labels
    const labelR   = radius - radius * 0.38;
    const labelVal = Math.round(min + t * (max - min));
    ctx.fillStyle = '#888';
    ctx.font = `${Math.round(radius * 0.13)}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(labelVal, cx + labelR * cos, cy + labelR * sin);
  }

  // ── Needle ────────────────────────────────────────────────────────────────
  const needleLen  = radius - radius * 0.08;
  const needleBack = radius * 0.18;

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(valueAngle);

  // Glow effect
  ctx.shadowColor = '#ff4444';
  ctx.shadowBlur  = 8;

  ctx.beginPath();
  ctx.moveTo(-needleBack, 0);
  ctx.lineTo(needleLen, 0);
  ctx.strokeStyle = '#ff4444';
  ctx.lineWidth = 2.5;
  ctx.lineCap = 'round';
  ctx.stroke();

  ctx.shadowBlur = 0;
  ctx.restore();

  // ── Centre hub ────────────────────────────────────────────────────────────
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 0.09, 0, Math.PI * 2);
  ctx.fillStyle = '#1a1a2a';
  ctx.fill();
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 0.05, 0, Math.PI * 2);
  ctx.fillStyle = '#ff4444';
  ctx.fill();

  // ── Digital readout ───────────────────────────────────────────────────────
  ctx.fillStyle = '#fff';
  ctx.font = `bold ${Math.round(radius * 0.28)}px 'Segoe UI', sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(Math.round(clamped), cx, cy + radius * 0.58);
}

// ── Canvas setup ──────────────────────────────────────────────────────────────

const speedCanvas = document.getElementById('speedometer');
const rpmCanvas   = document.getElementById('tachometer');
const speedCtx    = speedCanvas.getContext('2d');
const rpmCtx      = rpmCanvas.getContext('2d');

function getGaugeDimensions(canvas) {
  const w  = canvas.width;
  const h  = canvas.height;
  const cx = w / 2;
  const cy = h / 2;
  const r  = Math.min(w, h) * 0.38;
  return { w, h, cx, cy, r };
}

// ── DOM references ────────────────────────────────────────────────────────────

const gearEl       = document.getElementById('gear-display');
const fuelEl       = document.getElementById('fuel-bar');
const throttleEl   = document.getElementById('throttle-bar');
const brakeEl      = document.getElementById('brake-bar');
const statusEl     = document.getElementById('connection-status');

function gearLabel(g) {
  if (g === 0) return 'R';
  if (g === 1) return 'N';
  return String(g - 1);
}

// ── Render loop (~60 FPS, driven by requestAnimationFrame) ───────────────────

function render() {
  // Speedometer
  const sd = getGaugeDimensions(speedCanvas);
  speedCtx.clearRect(0, 0, sd.w, sd.h);
  drawGauge(speedCtx, sd.cx, sd.cy, sd.r, state.speed, 0, 300, 6, '#00aaff', null);

  // Tachometer
  const rd = getGaugeDimensions(rpmCanvas);
  rpmCtx.clearRect(0, 0, rd.w, rd.h);
  drawGauge(rpmCtx, rd.cx, rd.cy, rd.r, state.rpm / 1000, 0, 10, 10, '#00dd88', 7);

  // Gear
  gearEl.textContent = gearLabel(state.gear);

  // Bars (percentage width)
  fuelEl.style.width     = (state.fuel     * 100).toFixed(1) + '%';
  throttleEl.style.width = (state.throttle * 100).toFixed(1) + '%';
  brakeEl.style.width    = (state.brake    * 100).toFixed(1) + '%';

  requestAnimationFrame(render);
}

requestAnimationFrame(render);

// ── WebSocket client ──────────────────────────────────────────────────────────

function connectWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${location.host}/ws`;
  const ws  = new WebSocket(url);

  ws.addEventListener('open', () => {
    statusEl.textContent = '● Live';
    statusEl.className   = 'status-connected';
  });

  ws.addEventListener('message', (evt) => {
    try {
      const data = JSON.parse(evt.data);
      if (typeof data.speed    === 'number') state.speed    = data.speed;
      if (typeof data.rpm      === 'number') state.rpm      = data.rpm;
      if (typeof data.gear     === 'number') state.gear     = data.gear;
      if (typeof data.throttle === 'number') state.throttle = data.throttle;
      if (typeof data.brake    === 'number') state.brake    = data.brake;
      if (typeof data.fuel     === 'number') state.fuel     = data.fuel;
    } catch (_) {
      // Malformed packet – ignore
    }
  });

  ws.addEventListener('close', () => {
    statusEl.textContent = '✕ Disconnected';
    statusEl.className   = 'status-disconnected';
    setTimeout(connectWebSocket, WS_RECONNECT_DELAY_MS);
  });

  ws.addEventListener('error', () => {
    statusEl.textContent = '✕ Error';
    statusEl.className   = 'status-disconnected';
    ws.close();
  });
}

connectWebSocket();
