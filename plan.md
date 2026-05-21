# KnobWheel Implementation Plan

Implement a Linux desktop application called KnobWheel that converts a mechanical keyboard volume knob (rotary encoder) into a virtual analog steering wheel axis using python-evdev and python-uinput.

## User Review Required

> [!IMPORTANT]
> Running raw input monitoring and creating virtual controllers require read/write access to `/dev/input/event*` and `/dev/uinput`. The user will need to run the python scripts with `sudo` or set up appropriate udev rules.
> - **Input access**: User needs read access to `/dev/input/event*` (usually root or `input` group).
> - **Virtual controller creation**: User needs write access to `/dev/uinput` (usually root or `uinput` group).

> [!WARNING]
> **Keyboard Grabbing Danger**: Using `device.grab()` on an input device grabs the entire physical device exclusively. If the volume knob is exposed on the same event device path as the main typing keys/modifiers, grabbing it will lock up the keyboard. Auto-grabbing is disabled by default, and keyboard capabilities will be checked before grabbing is permitted.

## Proposed Changes

We will build the project incrementally in Python, keeping files modular but simple:

1. `input_detector.py` (Phase 1 / Milestone 1)
2. `physics.py` (Phase 2 / Milestone 2)
3. `output_controller.py` (Phase 3 / Milestone 3)
4. `main.py` (Phase 4 & 5 / Milestone 4 & 5)

---

### Phase 1: Raw Input Detection

We will create `input_detector.py` to list and monitor input devices.

#### [NEW] [input_detector.py](file:///home/radioactive/projects/KnobWheel/input_detector.py)
This script will:
- List all available input devices.
- Auto-detect the knob device (often containing "Consumer Control", "Aula", "Keyboard").
- Read and parse raw keypresses (`KEY_VOLUMEUP`, `KEY_VOLUMEDOWN`) or relative events (`REL_DIAL`, `REL_WHEEL`, etc.).
- **Event Normalization Layer**: Convert diverse hardware events into a unified internal representation:
  ```python
  class RotaryEvent:
      direction: int   # -1 (left/CCW) or +1 (right/CW)
      timestamp: float # time.monotonic() timestamp
      strength: float  # default 1.0 (can scale with click speed)
  ```
- **Safe Device Grabbing**: Implement optional `grab` capability. Inspect device capabilities first and warn if grabbing might lock the main typing interface.
- **Debounce & Filtering**: Timestamp-based debounce window using `time.monotonic()` to filter out jittery duplicate events from noisy encoders.

---

### Phase 2: Steering Physics Engine

We will implement the steering state engine in `physics.py`.

#### [NEW] [physics.py](file:///home/radioactive/projects/KnobWheel/physics.py)
This module will simulate a physical steering rack using a **damped spring simulation** (Damped Harmonic Oscillator):
- Maintain `steering_angle` (range `[-1.0, 1.0]` internally) and `steering_velocity`.
- Apply acceleration impulses to `steering_velocity` when a `RotaryEvent` is processed.
- **Damped Spring Update Loop**:
  ```python
  # Centering force acts as a spring pull on velocity, not direct angle damping
  spring_force = -steering_angle * CENTERING_FORCE
  steering_velocity += spring_force * dt
  
  # Apply damping to velocity
  steering_velocity -= steering_velocity * DAMPING * dt
  
  # Update position
  steering_angle += steering_velocity * dt
  ```
- **Monotonic Timing**: Use `time.monotonic()` exclusively for calculating `dt` to avoid clock drift issues.
- **Hard Clamping**: Hard clamp `steering_angle` to `[-1.0, 1.0]` and damp velocity to zero at lock.
- **Configurable Constants**:
  - `CENTERING_FORCE`: Spring constant pulling back to 0.0
  - `DAMPING`: Friction slowing down velocity (crucial to tune to prevent infinite oscillation/wobbling)
  - `STEERING_ACCELERATION`: Impulse added to velocity per click
- **Terminal Debug Overlay**: ASCII representation of steering angle:
  `[<<<|----] Angle: -0.34 | Velocity: 0.12 | Saturation: Normal`
  The indicator shows the position and highlights in red/caps when locked at `-1.0` or `1.0`.
- **Keyboard Fallback & Hotkeys**:
  - `A` / `D` keys to simulate CW/CCW impulses.
  - `R` key to instantly re-center (`steering_angle = 0.0` and `steering_velocity = 0.0`).

---

### Phase 3: Virtual Controller Output

We will implement the virtual input device using `evdev.UInput`.

#### [NEW] [output_controller.py](file:///home/radioactive/projects/KnobWheel/output_controller.py)
This class will:
- Set up a virtual joystick device named `"KnobWheel Virtual Controller"`.
- **InputAbsInfo Configuration**: Configure the virtual axis `ABS_X` using proper `AbsInfo` properties:
  - `min = -32768`
  - `max = 32767`
  - `fuzz = 0`
  - `flat = 0`
- Expose a method `update_axis(normalized_value)` that takes an internal `[-1.0, 1.0]` steering value, scales it to `[-32768, 32767]`, and writes it to the virtual X axis.

---

### Phase 4: Integration and Main Loop

We will create the main entry point integrating all three systems with asynchronous execution.

#### [NEW] [main.py](file:///home/radioactive/projects/KnobWheel/main.py)
This file will tie the inputs, physics, and virtual device output together:
- **Independent Async Tasks**:
  1. **Input Task**: Read input events via evdev's async reader, convert to `RotaryEvent`s, and pass to the simulation.
  2. **Simulation Task**: Tick at 60Hz using monotonic delta time `dt`, updating the physics model and writing the output to `UInput`.
- Clean shutdown on Ctrl+C (releasing grab and closing the virtual device).

---

## Verification Plan & Milestones

### Milestone 1: Raw Input Detection (Phase 1)
- **Verification**: Run `sudo python3 input_detector.py`, spin the knob, and verify unified `RotaryEvent` logging with timestamp/click speed. Verify that volume grab checks work properly.

### Milestone 2: Physics Simulation in Terminal (Phase 2)
- **Verification**: Run `python3 physics.py` and use `A` / `D` / `R` keys to simulate input. Verify the ASCII wheel turns, return-to-center spring works, and it clamps at lock without infinite oscillations.

### Milestone 3: Virtual Joystick Visible (Phase 3)
- **Verification**: Run `sudo python3 main.py` with keyboard controls, and check using `jstest-gtk` or `evtest` that the virtual axis updates.

### Milestone 4: ETS2 Steering Works (Phase 4)
- **Verification**: Open ETS2, navigate to controls, bind "KnobWheel Virtual Controller" as the steering axis, and verify the wheel in game matches the virtual axis movement.

### Milestone 5: Actually Drivable (Tuning Phase)
- **Verification**: Drive a truck, keep it within a lane at speed, perform a turn, and fine-tune `CENTERING_FORCE`, `DAMPING`, and `STEERING_ACCELERATION`.
