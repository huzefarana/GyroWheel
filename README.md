# KnobWheel

Turn a mechanical keyboard volume knob into a virtual analog steering wheel for driving games on Linux.

KnobWheel reads rotary encoder events from your keyboard (volume up/down, dial axes, and similar), maps them to a smooth steering position, and exposes a virtual joystick axis that games like **Euro Truck Simulator 2** can bind as steering input.

> **Origin story:** This started with an [Aula F75](https://www.aula.com/) keyboard and a simple idea: *what if the volume knob was a steering wheel?* The project is intentionally experimental—feel and controllability matter more than polish.

## How it works

```
Rotary encoder (keyboard knob)
        ↓
Event normalization (RotaryEvent)
        ↓
Steering simulation (accumulated clicks → angle)
        ↓
Virtual joystick X axis (uinput)
        ↓
Game (ETS2, etc.)
```

KnobWheel is **not** a key remapper. It does not send `A`/`D` or volume keys to the game. It creates a **virtual input device** (`KnobWheel Virtual Controller`) with a continuous analog axis—closer to a software steering rack than a macro.

The steering model uses **direct position mapping**: each detent adds to an accumulated click count (with lock-to-lock limits), the wheel stays where you leave it (no auto-centering), and output is smoothed so the in-game axis does not step harshly.

## Features

- Detects knob rotation from Linux `evdev` devices (volume keys, `REL_DIAL`, `REL_WHEEL`, etc.)
- Debouncing for noisy encoders
- Safe optional device grab (warns if grabbing might lock your main keyboard)
- Virtual joystick via `uinput` for game binding
- Configurable lock-to-lock click count and smoothing
- Keyboard fallback (`A` / `D` / `R` / `Q`) for testing without hardware
- Standalone tools to verify input, physics, and virtual device output

## Requirements

- **OS:** Linux (Ubuntu and similar distros tested conceptually; Windows is out of scope for now)
- **Python:** 3.10+ recommended
- **Permissions:** Read access to `/dev/input/event*`; write access to `/dev/uinput` for the virtual controller
- **Optional tools:** `evtest`, `jstest-gtk` (for verifying devices)

## Fresh machine setup

After cloning on a new Linux machine, run these steps from the project directory:

```bash
git clone https://github.com/Shahzaibalikhawaja/KnobWheel.git
cd KnobWheel

# 1. Create a virtual environment
python3 -m venv .venv

# 2. Activate it (needed for pip install)
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run KnobWheel (use the venv Python with sudo — activation does not apply to sudo)
sudo .venv/bin/python main.py
```

Use `sudo .venv/bin/python` for other scripts that need input/uinput access as well (for example `input_detector.py`).

On Debian/Ubuntu, install helpers if needed:

```bash
sudo apt install python3-venv evtest jstest-gtk
```

### Permissions (recommended)

Running with `sudo` works for a quick test, but for daily use add your user to the `input` and `uinput` groups (then log out and back in):

```bash
sudo usermod -aG input,uinput "$USER"
```

You still need read access to the specific event node your knob appears on; use `input_detector.py` to find the right `/dev/input/eventN` path.

## Quick start

### 1. Find your knob device

```bash
sudo .venv/bin/python input_detector.py
```

Select the device that reports events when you turn the knob (often named *Consumer Control* or similar—not always the main keyboard node).

### 2. Run KnobWheel

```bash
sudo .venv/bin/python main.py
```

Or point at a device explicitly:

```bash
sudo .venv/bin/python main.py --device /dev/input/event10
```

**Demo without sudo** (physics + keyboard only, no virtual joystick):

```bash
.venv/bin/python main.py --keyboard --no-uinput
```

### 3. Verify the virtual controller

In another terminal:

```bash
jstest-gtk
# or
evtest
```

Look for **KnobWheel Virtual Controller** and confirm the X axis moves when you turn the knob.

### 4. Bind in your game

In ETS2 (or similar):

1. Open **Settings → Controls → Steering**.
2. Assign steering to **KnobWheel Virtual Controller** (joystick X axis).
3. Tune in-game deadzone and sensitivity if needed.
4. Adjust `--clicks` and `--smoothing` in KnobWheel until lane keeping feels right.

**Success looks like:** keeping a truck in a lane at speed—not just seeing axis movement in a test tool.

## Configuration

| Flag | Default | Description |
|------|---------|-------------|
| `--device` | *(interactive)* | Input device path |
| `--clicks` | `80.0` | Detents from full left lock to full right lock (~1200° with 24 detents/rev) |
| `--smoothing` | `15.0` | How quickly the reported angle catches up to the target |
| `--debounce` | `8.0` | Minimum milliseconds between accepted knob events |
| `--grab` | off | Exclusive grab (see warning below) |
| `--keyboard` | off | Use `A`/`D` instead of hardware knob |
| `--no-uinput` | off | Skip virtual joystick (terminal demo) |

Examples:

```bash
# ~900° lock-to-lock (60 detents)
sudo .venv/bin/python main.py --clicks 60

# ~600° lock-to-lock (40 detents)
sudo .venv/bin/python main.py --clicks 40

# Heavier smoothing
sudo .venv/bin/python main.py --smoothing 10
```

**Hotkeys** (when terminal keyboard support is available): `A` / `D` steer, `R` re-center, `Q` quit.

## Project layout

| File | Role |
|------|------|
| `input_detector.py` | List devices, parse knob events, debounce, grab safety |
| `physics.py` | Steering simulation and ASCII debug overlay |
| `output_controller.py` | Virtual joystick (`uinput`) |
| `main.py` | Async integration loop (~60 Hz) |
| `plan.md` | Implementation plan and milestones |
| `Initial Idea.txt` | Original goals and development philosophy |

## Development milestones

The project was built in vertical slices (see `plan.md`):

1. **Raw input** — reliable `RotaryEvent` logging  
2. **Steering state** — accumulated position and smoothing  
3. **Virtual controller** — visible in `jstest-gtk` / `evtest`  
4. **Game integration** — ETS2 steering bind  
5. **Tuning** — drivable lane keeping  

The golden rule during development: *Can I test this in ETS2 today?* If not, the task was probably too abstract.

## Safety notes

- **Device grab:** `--grab` takes exclusive control of an input node. If the knob shares a device with your typing keys, grabbing can lock your keyboard. KnobWheel checks capabilities and warns; prefer the consumer-control event device when possible.
- **Do not map knob to keys for steering** — digital left/right keys feel twitchy; use the virtual analog axis.
- **Encoder jitter** is normal; use `--debounce` if you see duplicate events.

## Roadmap

Roughly aligned with `Initial Idea.txt` and `plan.md`:

- [x] Linux input detection and normalization  
- [x] Steering simulation and virtual joystick  
- [x] ETS2-oriented integration path  
- [ ] Broader keyboard/hardware compatibility (avoid hardcoded vendor IDs)  
- [ ] Steering feel tuning presets  
- [ ] GUI (after feel is solid—PySide6 suggested in planning docs)  
- [ ] Windows support (non-trivial; Linux first by design)  

## Contributing

Contributions are welcome—issues, tuning presets for specific keyboards, documentation, and tests in real games are especially helpful.

1. Fork the repository and create a branch.  
2. Keep changes focused; match existing Python style and module boundaries.  
3. Verify with `input_detector.py`, `physics.py`, and `main.py` before opening a PR.  
4. Describe your keyboard model and game when reporting feel issues.  

For architecture and milestone context, read `plan.md` and `Initial Idea.txt`.

## License

A license file will be added before or as part of the public release. Until then, treat the repository as source-available for review and feedback; do not redistribute without the maintainer’s permission.

## Acknowledgments

Built for Linux with [python-evdev](https://python-evdev.readthedocs.io/). Inspired by anyone who looked at a volume knob and thought it deserved more responsibility.
