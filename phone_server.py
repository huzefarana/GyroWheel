#!/usr/bin/env python3
"""
phone_server.py — serves the Android controller web app over HTTP.

Run alongside main_windows.py (it imports and calls serve_phone_app).
Listens on port WS_PORT+1 (default 8766) so the phone just needs one URL.
"""
import asyncio
from http.server import BaseHTTPRequestHandler
import threading
import socket


PHONE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>KnobWheel</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: #0a0a0f;
    color: #e8e8e8;
    font-family: 'Courier New', monospace;
    height: 100dvh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
  }

  /* Background grid */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(255,255,255,.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
  }

  #status-bar {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    background: rgba(255,255,255,.04);
    border-bottom: 1px solid rgba(255,255,255,.08);
    font-size: 11px;
    letter-spacing: .12em;
    text-transform: uppercase;
  }

  #conn-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #ff3b3b;
    box-shadow: 0 0 8px #ff3b3b;
    transition: all .3s;
    flex-shrink: 0;
  }
  #conn-dot.connected { background: #00ff88; box-shadow: 0 0 12px #00ff88; }

  #conn-label { color: rgba(255,255,255,.5); }

  /* Main wheel arc visualizer */
  #wheel-wrap {
    position: relative;
    width: min(80vw, 300px);
    aspect-ratio: 1;
  }

  #wheel-svg { width: 100%; height: 100%; }

  #tilt-label {
    position: absolute;
    bottom: -28px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 13px;
    letter-spacing: .1em;
    color: rgba(255,255,255,.4);
    white-space: nowrap;
  }

  /* Pedal bars (throttle + brake) */
  #pedal-bars {
    display: flex;
    gap: 30px;
    margin-top: 48px;
  }

  .pedal-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }

  .pedal-track {
    width: 28px;
    height: 70px;
    background: rgba(255,255,255,.06);
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 4px;
    position: relative;
    overflow: hidden;
    display: flex;
    align-items: flex-end;
  }

  .pedal-fill {
    width: 100%;
    height: 0%;
    border-radius: 4px;
    transition: height .05s linear;
  }

  #throttle-fill {
    background: #00ff88;
    box-shadow: 0 0 10px rgba(0,255,136,.6);
  }

  #brake-fill {
    background: #ff5555;
    box-shadow: 0 0 10px rgba(255,85,85,.6);
  }

  .pedal-label {
    font-size: 9px;
    letter-spacing: .12em;
    color: rgba(255,255,255,.35);
    text-transform: uppercase;
  }

  /* Bottom bar */
  #bottom-bar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    padding: 16px 20px 28px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    background: rgba(0,0,0,.5);
    backdrop-filter: blur(8px);
  }

  .stat-row {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    letter-spacing: .08em;
    color: rgba(255,255,255,.35);
  }
  .stat-row span:last-child { color: rgba(255,255,255,.7); }

  #permission-btn {
    margin-top: 20px;
    padding: 16px 40px;
    background: transparent;
    border: 1px solid rgba(255,255,255,.2);
    border-radius: 4px;
    color: #e8e8e8;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    letter-spacing: .15em;
    text-transform: uppercase;
    cursor: pointer;
    transition: all .2s;
  }
  #permission-btn:active {
    background: rgba(255,255,255,.08);
    border-color: rgba(255,255,255,.4);
  }
  #permission-btn.hidden { display: none; }

  #hold-instruction {
    font-size: 11px;
    letter-spacing: .1em;
    color: rgba(255,255,255,.25);
    text-transform: uppercase;
    text-align: center;
    margin-top: 24px;
  }

  /* Center content wrapper */
  #center-row {
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  /* Landscape: wheel and pedal bars side by side */
  @media (orientation: landscape) {
    #center-row {
      flex-direction: row;
      align-items: center;
      gap: 36px;
    }
    #wheel-wrap {
      width: min(55vh, 240px);
    }
    #pedal-bars {
      margin-top: 0;
    }
    .pedal-track {
      height: min(38vh, 150px);
    }
    #bottom-bar {
      padding: 8px 20px 14px;
      gap: 6px;
    }
    #hold-instruction {
      margin-top: 8px;
    }
  }
</style>
</head>
<body>

<div id="status-bar">
  <div style="display:flex;align-items:center;gap:10px">
    <div id="conn-dot"></div>
    <span id="conn-label">Disconnected</span>
  </div>
  <span>KnobWheel</span>
  <span id="fps-counter">-- Hz</span>
</div>

<div id="center-row">
  <div id="wheel-wrap">
    <svg id="wheel-svg" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
      <!-- Track arc -->
      <circle cx="100" cy="100" r="80"
        fill="none" stroke="rgba(255,255,255,.06)" stroke-width="12"/>
      <!-- Active arc (steering indicator) -->
      <circle id="active-arc" cx="100" cy="100" r="80"
        fill="none" stroke="#00ff88" stroke-width="12"
        stroke-linecap="round"
        stroke-dasharray="0 502"
        transform="rotate(-90 100 100)"
        style="transition: stroke-dasharray .05s linear, stroke .15s;"/>
      <!-- Center dot -->
      <circle cx="100" cy="100" r="6" fill="rgba(255,255,255,.15)"/>
      <!-- Needle -->
      <line id="needle" x1="100" y1="100" x2="100" y2="26"
        stroke="#00ff88" stroke-width="3" stroke-linecap="round"
        style="transform-origin: 100px 100px; transition: transform .05s linear;"/>
      <!-- Lock markers -->
      <line x1="20" y1="100" x2="30" y2="100"
        stroke="rgba(255,80,80,.5)" stroke-width="2"/>
      <line x1="170" y1="100" x2="180" y2="100"
        stroke="rgba(255,80,80,.5)" stroke-width="2"/>
    </svg>
    <div id="tilt-label">steer: 0.0°</div>
  </div>

  <div id="pedal-bars">
    <div class="pedal-col">
      <div class="pedal-track">
        <div class="pedal-fill" id="throttle-fill"></div>
      </div>
      <div class="pedal-label">Throttle</div>
    </div>
    <div class="pedal-col">
      <div class="pedal-track">
        <div class="pedal-fill" id="brake-fill"></div>
      </div>
      <div class="pedal-label">Brake</div>
    </div>
  </div>
</div>

<button id="permission-btn">Enable Gyroscope</button>
<p id="hold-instruction">Landscape · tilt L/R to steer · lean fwd throttle · lean back brake</p>

<div id="bottom-bar">
  <div class="stat-row">
    <span>Beta (steering)</span>
    <span id="stat-beta">0.0°</span>
  </div>
  <div class="stat-row">
    <span>Throttle / Brake</span>
    <span id="stat-pedals">0% / 0%</span>
  </div>
  <div class="stat-row">
    <span>Packets sent</span>
    <span id="stat-packets">0</span>
  </div>
</div>

<script>
  // ── Config ──────────────────────────────────────────────────────
  const WS_HOST = location.hostname;
  const WS_PORT = __WS_PORT__;          // injected by Python server
  const SEND_HZ = 60;
  const DEADZONE = 5;
  const MAX_TILT = 45;
  const THROTTLE_MAX_TILT = 30;

  // ── State ────────────────────────────────────────────────────────
  let gamma = 0, beta = 0, alpha = 0;
  let ws = null;
  let packets = 0;
  let lastFpsTime = performance.now();
  let frameCount = 0;
  let gyroGranted = false;

  // ── DOM refs ─────────────────────────────────────────────────────
  const connDot      = document.getElementById('conn-dot');
  const connLabel    = document.getElementById('conn-label');
  const fpsCounter   = document.getElementById('fps-counter');
  const needle       = document.getElementById('needle');
  const activeArc    = document.getElementById('active-arc');
  const tiltLabel    = document.getElementById('tilt-label');
  const statBeta     = document.getElementById('stat-beta');
  const statPedals   = document.getElementById('stat-pedals');
  const statPkts     = document.getElementById('stat-packets');
  const permBtn      = document.getElementById('permission-btn');
  const throttleFill = document.getElementById('throttle-fill');
  const brakeFill    = document.getElementById('brake-fill');

  // ── WebSocket ────────────────────────────────────────────────────
  function connect() {
    ws = new WebSocket(`ws://${WS_HOST}:${WS_PORT}`);
    ws.onopen = () => {
      connDot.classList.add('connected');
      connLabel.textContent = 'Connected';
    };
    ws.onclose = ws.onerror = () => {
      connDot.classList.remove('connected');
      connLabel.textContent = 'Reconnecting…';
      setTimeout(connect, 1500);
    };
  }
  connect();

  // ── Sign flips (change to -1 if a control is reversed on your phone) ──
  const STEER_SIGN = 1;   // -1 if tilting LEFT steers RIGHT
  const PEDAL_SIGN = 1;   // -1 if leaning FORWARD brakes instead of throttles

  // ── Tilt sensing via gravity vector ──────────────────────────────
  // We derive tilt from the gravity vector (devicemotion) rather than the
  // OS Euler angles (deviceorientation). Euler beta/gamma suffer gimbal
  // flips — leaning forward in landscape makes the steering axis jump to an
  // extreme. atan2 of two gravity components is continuous and decoupled, so
  // pedaling no longer corrupts steering.
  let fx = 0, fy = 0, fz = 0;       // low-pass filtered gravity
  const LP = 0.70;                  // smoothing factor (higher = snappier)

  function startGyro() {
    window.addEventListener('devicemotion', (e) => {
      const g = e.accelerationIncludingGravity;
      if (!g || g.x == null) return;
      fx += LP * (g.x - fx);
      fy += LP * (g.y - fy);
      fz += LP * (g.z - fz);
      const RAD = 180 / Math.PI;
      // beta  = steering: elevation of device Y axis (roll left/right)
      // gamma = throttle/brake: elevation of device X axis (lean fwd/back)
      beta  = STEER_SIGN * Math.atan2(fy, Math.hypot(fx, fz)) * RAD;
      gamma = PEDAL_SIGN * Math.atan2(fx, Math.hypot(fy, fz)) * RAD;
      alpha = 0;
      gyroGranted = true;
      permBtn.classList.add('hidden');
    }, true);
  }

  // iOS 13+ requires explicit permission for motion sensors
  if (typeof DeviceMotionEvent !== 'undefined' &&
      typeof DeviceMotionEvent.requestPermission === 'function') {
    permBtn.classList.remove('hidden');
    permBtn.addEventListener('click', async () => {
      try {
        const resp = await DeviceMotionEvent.requestPermission();
        if (resp === 'granted') startGyro();
      } catch (_) {}
    });
  } else {
    permBtn.classList.add('hidden');
    startGyro();
  }

  // ── Send loop (60 Hz) ────────────────────────────────────────────
  let lastSend = 0;
  const sendInterval = 1000 / SEND_HZ;

  function sendLoop(ts) {
    requestAnimationFrame(sendLoop);

    // FPS counter
    frameCount++;
    if (ts - lastFpsTime >= 1000) {
      fpsCounter.textContent = frameCount + ' Hz';
      frameCount = 0;
      lastFpsTime = ts;
    }

    if (ts - lastSend < sendInterval) return;
    lastSend = ts;

    // Send to PC
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ gamma, beta, alpha }));
      packets++;
    }

    // ── UI update ────────────────────────────────────────────────
    // Steering: beta (landscape roll, stable during forward/back lean)
    let norm = 0;
    if (Math.abs(beta) > DEADZONE) {
      const sign = beta > 0 ? 1 : -1;
      norm = Math.min((Math.abs(beta) - DEADZONE) / (MAX_TILT - DEADZONE), 1) * sign;
    }

    // Needle rotation: -90° to +90° maps to -90° to +90° rotation
    const deg = norm * 90;
    needle.style.transform = `rotate(${deg}deg)`;

    // Arc: circumference = 2π×80 ≈ 502
    const circ = 502;
    const arcLen = Math.abs(norm) * (circ / 4); // max 90° of arc
    const gap = circ - arcLen;

    // Offset the dash so it starts from top (270° offset already via rotate(-90))
    if (norm < 0) {
      activeArc.style.transform = `rotate(${-90 + deg}deg)`;
    } else {
      activeArc.style.transform = `rotate(-90deg)`;
    }
    activeArc.setAttribute('stroke-dasharray', `${arcLen} ${gap}`);
    activeArc.style.stroke = Math.abs(norm) > 0.85 ? '#ff5555' : '#00ff88';

    tiltLabel.textContent = `steer: ${beta.toFixed(1)}°`;

    // Throttle: forward lean (positive gamma)
    let throttleNorm = 0;
    if (gamma > DEADZONE) {
      throttleNorm = Math.min((gamma - DEADZONE) / (THROTTLE_MAX_TILT - DEADZONE), 1);
    }

    // Brake: backward lean (negative gamma)
    let brakeNorm = 0;
    if (gamma < -DEADZONE) {
      brakeNorm = Math.min((-gamma - DEADZONE) / (THROTTLE_MAX_TILT - DEADZONE), 1);
    }

    throttleFill.style.height = (throttleNorm * 100).toFixed(1) + '%';
    brakeFill.style.height    = (brakeNorm * 100).toFixed(1) + '%';

    statBeta.textContent   = beta.toFixed(1) + '°';
    statPedals.textContent = Math.round(throttleNorm * 100) + '% / ' + Math.round(brakeNorm * 100) + '%';
    statPkts.textContent   = packets;
  }
  requestAnimationFrame(sendLoop);
</script>
</body>
</html>
"""


def build_html(ws_port: int) -> str:
    return PHONE_HTML.replace("__WS_PORT__", str(ws_port))


class _Handler(BaseHTTPRequestHandler):
    ws_port: int = 8765

    def do_GET(self):
        body = build_html(self.ws_port).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # Suppress per-request noise


def serve_phone_app(http_port: int, ws_port: int):
    """
    Serve the phone web app in a background thread.
    http_port: the port browsers hit (ws_port + 1 by convention)
    ws_port:   injected into the HTML so the phone JS knows where to connect
    """
    import http.server

    class _BoundHandler(_Handler):
        pass

    _BoundHandler.ws_port = ws_port
    server = http.server.HTTPServer(("0.0.0.0", http_port), _BoundHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
