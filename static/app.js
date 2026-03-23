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
  speed: 0,         // km/h
  rpm: 0,           // rev/min
  gear: 1,          // 0=R, 1=N, 2=1st …
  throttle: 0,      // 0–1
  brake: 0,         // 0–1
  fuel: 0,          // 0–1
  maxRpm: 8000,     // dynamic vehicle-specific rev limit
  airSpeed: 0,      // airspeed in km/h
  clutch: 0,        // 0–1
  turbo: 0,         // bar
  engTemp: 0,       // °C
  wheelPower: 0,    // 0–1
  handbrake: false, // parking brake engaged
  abs: false,       // ABS active
  tc: false,        // traction control active
  signalLeft: false, // left turn signal
  signalRight: false, // right turn signal
};

// ── Gauge drawing ─────────────────────────────────────────────────────────────

/**
 * Draw a realistic circular analog gauge onto a canvas.
 *
 * The gauge arc spans 300° – from the 7-o'clock position (lower-left)
 * clockwise to the 5-o'clock position (lower-right).
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} cx            Centre x
 * @param {number} cy            Centre y
 * @param {number} radius        Outer track radius
 * @param {number} value         Current value
 * @param {number} min           Minimum scale value
 * @param {number} max           Maximum scale value
 * @param {number} numTicks      Number of major tick intervals
 * @param {string} arcColor      CSS color for the value arc
 * @param {number|null} yellowZoneStart  Scale value where yellow zone begins
 * @param {number|null} redZoneStart     Scale value where red zone begins
 * @param {function|null} labelFn  Optional transform for tick labels (e.g. v => v/1000)
 */
function drawGauge(ctx, cx, cy, radius, value, min, max, numTicks,
                   arcColor, yellowZoneStart, redZoneStart, labelFn) {
  // Arc geometry: 7 o'clock → 5 o'clock, clockwise, spanning 300° (5π/3 rad)
  const START = (2 / 3) * Math.PI;   // 7 o'clock in canvas coords
  const SPAN  = (5 / 3) * Math.PI;   // 300°
  const END   = START + SPAN;         // 5 o'clock

  const clamped    = Math.max(min, Math.min(max, value));
  const normalized = (clamped - min) / (max - min);
  const valueAngle = START + normalized * SPAN;

  const trackW = Math.round(radius * 0.13);

  // ── Dial face – radial gradient for depth ─────────────────────────────────
  const face = ctx.createRadialGradient(cx, cy - radius * 0.1, radius * 0.05,
                                        cx, cy, radius * 1.1);
  face.addColorStop(0, '#1e1e2e');
  face.addColorStop(1, '#0d0d18');
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 1.18, 0, Math.PI * 2);
  ctx.fillStyle = face;
  ctx.fill();

  // ── Outer bezel ring ──────────────────────────────────────────────────────
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 1.18, 0, Math.PI * 2);
  ctx.strokeStyle = '#2a2a3a';
  ctx.lineWidth = radius * 0.08;
  ctx.stroke();

  // ── Background track (inactive arc) ───────────────────────────────────────
  ctx.beginPath();
  ctx.arc(cx, cy, radius, START, END, false);
  ctx.strokeStyle = '#1c1c2c';
  ctx.lineWidth = trackW;
  ctx.lineCap = 'butt';
  ctx.stroke();

  // ── Yellow zone (caution) ─────────────────────────────────────────────────
  if (yellowZoneStart !== null && yellowZoneStart < max) {
    const yNorm  = (yellowZoneStart - min) / (max - min);
    const yStart = START + yNorm * SPAN;
    const yEnd   = redZoneStart !== null
      ? START + ((redZoneStart - min) / (max - min)) * SPAN
      : END;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, yStart, yEnd, false);
    ctx.strokeStyle = '#443300';
    ctx.lineWidth = trackW;
    ctx.stroke();
  }

  // ── Red zone (danger) ─────────────────────────────────────────────────────
  if (redZoneStart !== null && redZoneStart < max) {
    const redNorm  = (redZoneStart - min) / (max - min);
    const redStart = START + redNorm * SPAN;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, redStart, END, false);
    ctx.strokeStyle = '#440000';
    ctx.lineWidth = trackW;
    ctx.stroke();
  }

  // ── Value arc ─────────────────────────────────────────────────────────────
  if (normalized > 0) {
    ctx.beginPath();
    ctx.arc(cx, cy, radius, START, valueAngle, false);

    const inRed    = redZoneStart !== null && value >= redZoneStart;
    const inYellow = !inRed && yellowZoneStart !== null && value >= yellowZoneStart;
    ctx.strokeStyle = inRed ? '#ff3300' : (inYellow ? '#ffaa00' : arcColor);
    ctx.lineWidth = trackW - 2;
    ctx.lineCap = 'round';
    ctx.stroke();
  }

  // ── Tick marks & labels ───────────────────────────────────────────────────
  ctx.lineCap = 'butt';
  const minorTicksPerMajor = 4;
  for (let i = 0; i <= numTicks; i++) {
    const t     = i / numTicks;
    const angle = START + t * SPAN;
    const cos   = Math.cos(angle);
    const sin   = Math.sin(angle);

    const outerR = radius + radius * 0.06;
    const innerR = radius - radius * 0.20;

    // Major tick
    ctx.beginPath();
    ctx.moveTo(cx + outerR * cos, cy + outerR * sin);
    ctx.lineTo(cx + innerR * cos, cy + innerR * sin);
    ctx.strokeStyle = '#777';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Minor ticks between major ticks
    if (i < numTicks) {
      for (let m = 1; m < minorTicksPerMajor; m++) {
        const mt  = t + (m / minorTicksPerMajor) / numTicks;
        const ma  = START + mt * SPAN;
        const mc   = Math.cos(ma);
        const msin = Math.sin(ma);
        const isMid = m === minorTicksPerMajor / 2;
        const minorInner = radius - radius * (isMid ? 0.13 : 0.08);
        ctx.beginPath();
        ctx.moveTo(cx + outerR * mc, cy + outerR * msin);
        ctx.lineTo(cx + minorInner * mc, cy + minorInner * msin);
        ctx.strokeStyle = isMid ? '#4a4a5a' : '#333344';
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }

    // Label
    const labelR   = radius - radius * 0.35;
    const rawVal   = min + t * (max - min);
    const labelVal = labelFn ? labelFn(rawVal) : Math.round(rawVal);
    ctx.fillStyle = '#888';
    ctx.font = `${Math.round(radius * 0.12)}px 'Segoe UI', sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(labelVal, cx + labelR * cos, cy + labelR * sin);
  }

  // ── Needle ────────────────────────────────────────────────────────────────
  const needleLen  = radius - radius * 0.06;
  const needleBack = radius * 0.20;
  const needleTip  = radius * 0.04;  // width at tip

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(valueAngle);

  // Glow
  ctx.shadowColor = '#ff5533';
  ctx.shadowBlur  = 10;

  // Tapered needle shape
  ctx.beginPath();
  ctx.moveTo(-needleBack, 0);
  ctx.lineTo(0, -needleTip);
  ctx.lineTo(needleLen, 0);
  ctx.lineTo(0, needleTip);
  ctx.closePath();
  ctx.fillStyle = '#ff4422';
  ctx.fill();

  ctx.shadowBlur = 0;
  ctx.restore();

  // ── Centre hub ────────────────────────────────────────────────────────────
  // Outer hub shadow
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 0.11, 0, Math.PI * 2);
  ctx.fillStyle = '#0d0d18';
  ctx.fill();
  // Hub ring
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 0.09, 0, Math.PI * 2);
  ctx.fillStyle = '#2a2a3a';
  ctx.fill();
  // Hub centre dot
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 0.045, 0, Math.PI * 2);
  ctx.fillStyle = '#ff4422';
  ctx.fill();

  // ── Digital readout ───────────────────────────────────────────────────────
  ctx.fillStyle = '#fff';
  ctx.font = `bold ${Math.round(radius * 0.27)}px 'Segoe UI', sans-serif`;
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

const gearEl         = document.getElementById('gear-display');
const fuelEl         = document.getElementById('fuel-bar');
const throttleEl     = document.getElementById('throttle-bar');
const brakeEl        = document.getElementById('brake-bar');
const clutchEl       = document.getElementById('clutch-bar');
const powerEl        = document.getElementById('power-bar');
const statusEl       = document.getElementById('connection-status');
const airSpeedEl     = document.getElementById('air-speed-value');
const turboEl        = document.getElementById('turbo-value');
const engTempEl      = document.getElementById('eng-temp-value');
const indHandbrakeEl = document.getElementById('ind-handbrake');
const indAbsEl       = document.getElementById('ind-abs');
const indTcEl        = document.getElementById('ind-tc');
const indSigLeftEl   = document.getElementById('ind-signal-left');
const indSigRightEl  = document.getElementById('ind-signal-right');

function gearLabel(g) {
  if (g === 0) return 'R';
  if (g === 1) return 'N';
  return String(g - 1);
}

/**
 * Toggle the "active" CSS class on an indicator element.
 * @param {HTMLElement} el
 * @param {boolean} on
 */
function setIndicator(el, on) {
  if (on) {
    el.classList.add('active');
  } else {
    el.classList.remove('active');
  }
}

// ── Render loop (~60 FPS, driven by requestAnimationFrame) ───────────────────

function render() {
  // Speedometer – fixed scale 0–300 km/h, caution above 200
  const sd = getGaugeDimensions(speedCanvas);
  speedCtx.clearRect(0, 0, sd.w, sd.h);
  drawGauge(speedCtx, sd.cx, sd.cy, sd.r,
            state.speed, 0, 300, 6,
            '#00aaff', 200, null, null);

  // Tachometer – dynamic scale based on vehicle-specific max RPM
  const maxRpmK  = state.maxRpm / 1000;
  const numTicks = Math.round(maxRpmK);   // one major tick per 1000 RPM
  const rd = getGaugeDimensions(rpmCanvas);
  rpmCtx.clearRect(0, 0, rd.w, rd.h);
  drawGauge(rpmCtx, rd.cx, rd.cy, rd.r,
            state.rpm / 1000, 0, maxRpmK, numTicks,
            '#00dd88',
            maxRpmK * 0.75,   // yellow zone at 75 % of max
            maxRpmK * 0.88,   // red zone at 88 % of max
            v => Math.round(v));

  // Gear
  gearEl.textContent = gearLabel(state.gear);

  // Bars (percentage width)
  fuelEl.style.width     = (state.fuel       * 100).toFixed(1) + '%';
  throttleEl.style.width = (state.throttle   * 100).toFixed(1) + '%';
  brakeEl.style.width    = (state.brake      * 100).toFixed(1) + '%';
  clutchEl.style.width   = (state.clutch     * 100).toFixed(1) + '%';
  powerEl.style.width    = (state.wheelPower * 100).toFixed(1) + '%';

  // Air speed readout below speedometer
  airSpeedEl.textContent = Math.round(state.airSpeed);

  // Extra telemetry
  turboEl.textContent    = state.turbo.toFixed(2);
  engTempEl.textContent  = Math.round(state.engTemp);

  // Warning indicators
  setIndicator(indHandbrakeEl, state.handbrake);
  setIndicator(indAbsEl,       state.abs);
  setIndicator(indTcEl,        state.tc);
  setIndicator(indSigLeftEl,   state.signalLeft);
  setIndicator(indSigRightEl,  state.signalRight);

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
      if (typeof data.speed        === 'number')  state.speed        = data.speed;
      if (typeof data.rpm          === 'number')  state.rpm          = data.rpm;
      if (typeof data.gear         === 'number')  state.gear         = data.gear;
      if (typeof data.throttle     === 'number')  state.throttle     = data.throttle;
      if (typeof data.brake        === 'number')  state.brake        = data.brake;
      if (typeof data.fuel         === 'number')  state.fuel         = data.fuel;
      if (typeof data.maxRpm       === 'number')  state.maxRpm       = data.maxRpm;
      if (typeof data.airSpeed     === 'number')  state.airSpeed     = data.airSpeed;
      if (typeof data.clutch       === 'number')  state.clutch       = data.clutch;
      if (typeof data.turbo        === 'number')  state.turbo        = data.turbo;
      if (typeof data.engTemp      === 'number')  state.engTemp      = data.engTemp;
      if (typeof data.wheelPower   === 'number')  state.wheelPower   = data.wheelPower;
      if (typeof data.handbrake    === 'boolean') state.handbrake    = data.handbrake;
      if (typeof data.abs          === 'boolean') state.abs          = data.abs;
      if (typeof data.tc           === 'boolean') state.tc           = data.tc;
      if (typeof data.signalLeft   === 'boolean') state.signalLeft   = data.signalLeft;
      if (typeof data.signalRight  === 'boolean') state.signalRight  = data.signalRight;
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
