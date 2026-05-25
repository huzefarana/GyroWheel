# GyroWheel

Steer in driving games by **tilting your Android phone**. GyroWheel reads your phone's motion sensor in the browser, streams the tilt to your PC over local WiFi, and feeds a virtual Xbox controller that games like **Euro Truck Simulator 2** can bind as steering, throttle, and brake.

No app to install on the phone — it is just a web page. No special hardware — your phone is the wheel.

> **Where the name comes from:** GyroWheel evolved from KnobWheel, an experiment that turned a mechanical keyboard's volume knob into a steering wheel. The knob is long gone — your phone's gyroscope *is* the wheel now — and the new name finally says so.

## How it works

```
Android phone (browser web app)
  • reads the gravity vector (devicemotion)
  • converts it to tilt angles, sends ~60×/sec
        │   WebSocket   { beta, gamma, alpha }
        ▼
gyro_server.py        receives packets, keeps the latest tilt (GyroState),
        │             converts tilt → steering / throttle / brake values
        ▼
physics.py            smooths the raw steering target into a wheel position
        │
        ▼
output_controller_windows.py   virtual Xbox 360 pad (ViGEmBus / vgamepad)
        │             steering → left stick X, throttle → RT, brake → LT
        ▼
Game (ETS2 / ATS / any XInput game)
```

`phone_server.py` is what the phone first talks to: it serves the controller web page over HTTP on port `WS_PORT + 1` (default `8766`), so the phone only needs one URL. `main_windows.py` wires the whole chain together in a ~60 Hz async loop.

GyroWheel creates a **virtual gamepad**, not key presses — games see a continuous analog axis, closer to a software steering rack than a macro.

| File | Role |
|------|------|
| `phone_server.py` | Serves the phone web app (HTML/JS gravity reader) over HTTP |
| `gyro_server.py` | WebSocket server; turns tilt angles into steering / throttle / brake |
| `physics.py` | Smooths the steering position |
| `output_controller_windows.py` | Virtual Xbox 360 controller via `vgamepad` |
| `main_windows.py` | 60 Hz loop tying input → physics → output together |

## The math behind it

Four small steps turn a phone wobble into a clean steering axis.

**1. Gravity → tilt angle.**
The phone always feels gravity pulling "down". By measuring how that pull is split across the phone's three axes (`gx`, `gy`, `gz`), we can work out how far it is tilted. We use `atan2`, a function that gives an angle from two side lengths:

```
steering tilt = atan2(gy, hypot(gx, gz))   // rolling the phone left/right
pedal tilt    = atan2(gx, hypot(gy, gz))   // leaning it forward/back
```

We deliberately use the gravity vector instead of the phone's built-in orientation angles, because those orientation angles "flip" to wild values at certain tilts (a problem called *gimbal lock*). Gravity-based angles stay smooth, and the two axes stay independent — so pressing the gas no longer yanks the steering sideways.

**2. Smooth out the shakes (low-pass filter).**
Raw sensor readings jitter. We blend each new reading with the previous one instead of trusting it fully:

```
filtered = filtered + LP × (raw − filtered)
```

`LP` near `0` is very smooth but laggy; near `1` is instant but jumpy. We use about `0.65`.

**3. Deadzone + full-lock scaling.**
A tilt angle becomes a tidy control value — `[-1, 1]` for steering, `[0, 1]` for pedals:

```
value = clamp( (|angle| − deadzone) / (maxTilt − deadzone), 0, 1 ) × direction
```

- **deadzone** (≈5°): ignore tiny tilts so the wheel does not drift while you hold still.
- **maxTilt** (≈45° steering, ≈30° pedals): the angle at which you reach full lock / full pedal.

**4. Ease into position (steering smoothing).**
The wheel does not snap to the target; it glides toward it a little each frame:

```
angle += (target − angle) × smoothing × dt
```

A higher `smoothing` value reaches the target faster and feels more direct (we use `10`). This is exactly what the `--smoothing` flag tunes.

Finally the `[-1, 1]` / `[0, 1]` values are scaled to the controller's raw ranges: steering → left-stick X (`−32768…32767`), throttle → right trigger and brake → left trigger (`0…255`).

## Requirements

- **OS:** Windows 10 / 11
- **Python:** 3.10+
- **ViGEmBus driver:** [install once](https://github.com/nefarius/ViGEmBus/releases) — this provides the virtual Xbox controller
- **Phone:** Android with a browser, on the **same WiFi** as the PC, with motion sensors enabled

## Setup

```powershell
# 1. Install dependencies (vgamepad + websockets)
pip install -r requirements_windows.txt

# 2. Install the ViGEmBus driver (one time)
#    https://github.com/nefarius/ViGEmBus/releases

# 3. Run GyroWheel
python main_windows.py
```

On launch the terminal prints a URL like `http://192.168.x.x:8766`. Open it in your phone's browser (same WiFi). Tap **Enable Gyroscope** if prompted (iOS asks; Android usually does not).

## Quick start

1. Start `python main_windows.py` on the PC.
2. Open the printed URL on your phone and grant motion access.
3. Hold the phone in **landscape** (screen facing you):
   - tilt **left / right** → steer
   - lean **forward** → throttle
   - lean **backward** → brake
4. In your game's controller settings, bind:
   - **Steering** → Left Stick X
   - **Throttle** → Right Trigger
   - **Brake** → Left Trigger
5. Launch the game **after** KnobWheel is already running so it detects the controller.

**Display-only test (no driver needed):** `python main_windows.py --no-controller` prints steering / throttle / brake in the terminal without creating a virtual pad — handy for checking your phone connection.

## Configuration

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | `8765` | WebSocket port. The phone web app is served on `port + 1`. |
| `--deadzone` | `5.0` | Tilt (degrees) around center that is ignored, so the wheel does not drift. |
| `--max-tilt` | `45.0` | Tilt angle that equals full steering lock. |
| `--throttle-tilt` | `30.0` | Forward / back lean angle that equals full throttle / brake. |
| `--smoothing` | `15.0` | How quickly the wheel catches up to your tilt (higher = snappier). |
| `--no-controller` | off | Skip the virtual controller (terminal display only). |

Examples:

```powershell
# Snappier steering
python main_windows.py --smoothing 14

# Bigger deadzone, gentler full-lock
python main_windows.py --deadzone 8 --max-tilt 55
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Phone page won't load | PC and phone must be on the same WiFi. Check the printed IP and that Windows Firewall is not blocking the port. |
| "Enable Gyroscope" does nothing (iOS) | Some iOS versions only grant motion access over HTTPS. On Android it works over plain HTTP. |
| Steering drifts while holding still | Increase `--deadzone`. |
| Throttle pins steering to a lock | Make sure you are in **landscape** — the gravity-based tilt keeps the steer and pedal axes separate (see the math section). |
| A control is reversed | Flip `STEER_SIGN` or `PEDAL_SIGN` near the top of the `<script>` in `phone_server.py`. |
| Game doesn't see the controller | Start KnobWheel first, then launch the game. Restart the game if it was already open. |
| Steering feels too twitchy / too slow | Lower / raise `--smoothing`. |

## Roadmap

- [x] Phone gyroscope steering over WebSocket
- [x] Throttle + brake via forward / back lean (landscape)
- [x] Gravity-vector tilt sensing (no gimbal-lock flips)
- [ ] On-screen calibration / re-center button
- [ ] Adjustable steering curves (linear vs. eased)
- [ ] Cross-platform controller output (Linux virtual gamepad)

## Contributing

Contributions are welcome — issues, tuning presets, documentation, and tests in real games are especially helpful.

1. Fork the repository and create a branch.
2. Keep changes focused; match the existing Python style and module boundaries.
3. Test with `python main_windows.py --no-controller` (connection + tilt) and in an actual game before opening a PR.
4. Describe your phone model and the game when reporting feel issues.

## License

A license file will be added before or as part of the public release. Until then, treat the repository as source-available for review and feedback; do not redistribute without the maintainer's permission.

## Acknowledgments

Built with [vgamepad](https://github.com/yannbouteiller/vgamepad) + [ViGEmBus](https://github.com/nefarius/ViGEmBus) for the virtual controller and [websockets](https://websockets.readthedocs.io/) for the phone link. Inspired by anyone who looked at a volume knob and thought it deserved more responsibility.
