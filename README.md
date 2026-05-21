# KnobWheel
# KnobWheel Walkthrough

I have implemented the complete functional codebase for KnobWheel. It is structured cleanly, decoupling physical events from physics simulations and virtual controller output.

## Changes Made

1. **[input_detector.py](file:///home/radioactive/projects/KnobWheel/input_detector.py)** [NEW]
   - Scans and lists input devices under `/dev/input/`.
   - Normalizes volume events (`KEY_VOLUMEUP`, `KEY_VOLUMEDOWN`) and relative wheel axes into a standard `RotaryEvent` structure.
   - Provides safe device grab checks to ensure the user does not accidentally lock their main typing keyboard.
   - Implements a monotonic time-based debounce filter.

2. **[physics.py](file:///home/radioactive/projects/KnobWheel/physics.py)** [NEW]
   - Implements a spring-damper model (`SteeringSimulation`) to update the virtual steering angle.
   - Implements frame-rate independent physics updates (`dt`-based).
   - Clamps the normalized steering angle to `[-1.0, 1.0]`.
   - Displays a live-updating ASCII visual overlay (e.g. `[<<<<|----]`) when executed.
   - Integrates keyboard fallback input (`A`/`D` keys) and a re-center hotkey (`R`).

3. **[output_controller.py](file:///home/radioactive/projects/KnobWheel/output_controller.py)** [NEW]
   - Exposes a virtual joystick device named `"KnobWheel Virtual Controller"` using `evdev.UInput`.
   - Defines the axis bounds using a proper absolute `AbsInfo` configuration with range `[-32768, 32767]`.

4. **[main.py](file:///home/radioactive/projects/KnobWheel/main.py)** [NEW]
   - Connects all components using `asyncio`.
   - Decouples input collection from the 60Hz physics update loop so that auto-centering and spring return forces run smoothly even in the absence of incoming knob events.
   - Provides CLI flags to configure centering force, damping, acceleration, debouncing window, and fallback modes.

---

## Verification Instructions

Since the execution environment prevents terminal shell access, you can run and verify each milestone on your system.

### Install Dependencies
Ensure you have `python-evdev` installed:
```bash
pip install evdev
```

And install Linux input testing tools if not present:
```bash
sudo apt install evtest jstest-gtk
```

---

### Step 1: Verify Input Detection (Milestone 1)
Run the input detector to list and listen to devices:
```bash
sudo python3 input_detector.py
```
- Select your mechanical keyboard device (often labeled "Consumer Control").
- Turn the knob. You should see `RotaryEvent` lines printing `CW` or `CCW` along with click speeds.

---

### Step 2: Verify Physics Model (Milestone 2)
Test the physics loop and ASCII overlay in keyboard-only mode:
```bash
python3 physics.py
```
- Press `A` and `D` to spin the virtual wheel left and right.
- Watch it spring back to center when you release.
- Press `R` to instantly snap back to center.
- Verify that it stops exactly at `LOCK L` and `LOCK R` without escaping `[-1.0, 1.0]` or oscillating infinitely.

---

### Step 3: Verify Virtual Controller (Milestone 3)
Run the output controller test to create a virtual device:
```bash
sudo python3 output_controller.py
```
- Open another terminal and run `evtest` or open `jstest-gtk` to verify that `"KnobWheel Virtual Controller"` is registered and that the X-axis moves.

---

### Step 4: Run the Full Integration (Milestone 4 & 5)
Run the primary application:
```bash
sudo python3 main.py
```
- Turn your volume knob to steer!
- Check `jstest-gtk` to ensure turning the physical knob moves the virtual joystick smoothly.
- **No-Sudo Demo**: If you want to check the physics and keyboard inputs without creating a virtual device or using sudo:
  ```bash
  python3 main.py --keyboard --no-uinput
  ```

### Tuning Constants
You can tweak the physics feel on-the-fly using CLI arguments:
```bash
sudo python3 main.py --centering 12.0 --damping 6.5 --accel 3.0
```
- Higher `--centering` pulls the wheel back to center faster.
- Higher `--damping` stops oscillations but makes the steering feel heavier/slower.
- Higher `--accel` makes each click of the knob turn the wheel faster.
