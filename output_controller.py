#!/usr/bin/env python3
"""Virtual racing-wheel device exposed via Linux uinput.

KnobWheel advertises a steering-wheel-class device (ABS_WHEEL + GAS + BRAKE + HAT)
rather than a gamepad, because games like ETS2 classify devices by their axis set:
gamepads with ABS_X/Y are treated as thumbsticks and rejected for steering, while
ABS_WHEEL is the canonical steering axis evdev defines for racing wheels.
"""
import sys
import time
import evdev
from evdev import ecodes, AbsInfo

# Generic USB IDs — not spoofing a real wheel, but enough that SDL/games treat it
# as a real USB device rather than something unidentifiable.
VENDOR_ID = 0x046d   # Logitech vendor space; helps games' built-in wheel heuristics
PRODUCT_ID = 0xc294  # generic placeholder in Logitech's wheel range


def find_joystick_path(event_path: str, device_name: str | None = None) -> str | None:
    """Return /dev/input/jsN for an event node, if the kernel created one."""
    event_node = event_path.rsplit("/", 1)[-1]
    try:
        with open("/proc/bus/input/devices", encoding="utf-8") as f:
            blocks = f.read().split("\n\n")
    except OSError:
        return None

    for block in blocks:
        if event_node not in block and (not device_name or device_name not in block):
            continue
        for line in block.splitlines():
            if line.startswith("H: Handlers="):
                for token in line.split("Handlers=")[1].split():
                    if token.startswith("js"):
                        return f"/dev/input/{token}"
    return None


def _wheel_axis() -> AbsInfo:
    return AbsInfo(value=0, min=-32768, max=32767, fuzz=0, flat=128, resolution=0)


def _pedal_axis() -> AbsInfo:
    return AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)


def _hat_axis() -> AbsInfo:
    return AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)


class VirtualJoystick:
    """
    Virtual steering wheel device.

    Layout matches a typical force-feedback wheel as evdev sees it:
      - ABS_WHEEL  : steering (driven by the knob)
      - ABS_GAS    : throttle pedal (idle, present so games classify it as a wheel)
      - ABS_BRAKE  : brake pedal   (idle)
      - ABS_HAT0X / ABS_HAT0Y : dpad
      - BTN_TRIGGER, BTN_THUMB, BTN_THUMB2, BTN_TOP, BTN_TOP2, BTN_PINKIE,
        BTN_BASE..BTN_BASE4 : wheel buttons (idle)
    """
    def __init__(self, name="KnobWheel Racing Wheel"):
        self.name = name
        self.ui = None
        self.event_path = None
        self.js_path = None

        capabilities = {
            ecodes.EV_KEY: [
                ecodes.BTN_TRIGGER,
                ecodes.BTN_THUMB,
                ecodes.BTN_THUMB2,
                ecodes.BTN_TOP,
                ecodes.BTN_TOP2,
                ecodes.BTN_PINKIE,
                ecodes.BTN_BASE,
                ecodes.BTN_BASE2,
                ecodes.BTN_BASE3,
                ecodes.BTN_BASE4,
            ],
            ecodes.EV_ABS: [
                (ecodes.ABS_WHEEL, _wheel_axis()),
                (ecodes.ABS_GAS, _pedal_axis()),
                (ecodes.ABS_BRAKE, _pedal_axis()),
                (ecodes.ABS_HAT0X, _hat_axis()),
                (ecodes.ABS_HAT0Y, _hat_axis()),
            ],
        }

        try:
            self.ui = evdev.UInput(
                capabilities,
                name=self.name,
                vendor=VENDOR_ID,
                product=PRODUCT_ID,
                version=0x0110,
                bustype=ecodes.BUS_USB,
            )
            time.sleep(0.15)

            if self.ui.device:
                self.event_path = self.ui.device.path
                self.js_path = find_joystick_path(self.event_path, self.name)

            print(f"Successfully created virtual racing wheel: '{self.name}'")
            if self.event_path:
                print(f"  Event node: {self.event_path}")
            if self.js_path:
                print(f"  Joystick node: {self.js_path}")

            self._sync_initial_state()
        except PermissionError:
            print("Error: Permission denied when attempting to create uinput device.", file=sys.stderr)
            print("Please run with 'sudo' or configure udev rules for /dev/uinput.", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Failed to create virtual racing wheel: {e}", file=sys.stderr)
            raise

    def _sync_initial_state(self):
        """Center all axes so listeners see a valid idle state."""
        if self.ui is None:
            return
        self.ui.write(ecodes.EV_ABS, ecodes.ABS_WHEEL, 0)
        self.ui.write(ecodes.EV_ABS, ecodes.ABS_GAS, 0)
        self.ui.write(ecodes.EV_ABS, ecodes.ABS_BRAKE, 0)
        self.ui.write(ecodes.EV_ABS, ecodes.ABS_HAT0X, 0)
        self.ui.write(ecodes.EV_ABS, ecodes.ABS_HAT0Y, 0)
        self.ui.syn()

    def update_steering(self, normalized_val: float):
        """
        Update the steering axis.
        Input: normalized value in range [-1.0, 1.0]
        """
        if self.ui is None:
            return

        val = max(-1.0, min(1.0, normalized_val))

        if val < 0:
            integer_val = int(val * 32768)
        else:
            integer_val = int(val * 32767)

        self.ui.write(ecodes.EV_ABS, ecodes.ABS_WHEEL, integer_val)
        self.ui.syn()

    def close(self):
        """Release the uinput device."""
        if self.ui is not None:
            self.ui.close()
            print("Closed virtual racing wheel.")
            self.ui = None


def print_game_launch_hints(joystick: VirtualJoystick | None):
    """Print Steam/ETS2 startup guidance — uinput devices are not hotplugged by Steam."""
    if joystick is None:
        return
    print("\n--- Game launch (important) ---")
    print("Steam does NOT hotplug uinput devices. Use this order:")
    print("  1. Keep KnobWheel running (this terminal)")
    print("  2. Start Steam / ETS2 AFTER KnobWheel is active")
    print("     (or fully restart Steam if it was already open)")
    print("  3. Prefer the NATIVE LINUX build of ETS2 (Compatibility -> do NOT force Proton).")
    print("  4. In ETS2: Options -> Controls. The 'Steering' axis should auto-bind.")
    print("     If not, click 'Steer left' or the steering axis and turn the knob.")
    if joystick.js_path:
        print(f"\nIf ETS2 still ignores it, try launching with:")
        print(f"  SDL_JOYSTICK_DEVICE={joystick.js_path} steam -applaunch 227300")
    print("-------------------------------\n")


if __name__ == "__main__":
    print("--- KnobWheel Output Controller Test ---")
    try:
        controller = VirtualJoystick()
        print("Device is registered. Verify with 'jstest-gtk' or 'evtest'.")

        print("Simulating steering movement...")
        for val in [0.0, -0.5, -1.0, 0.0, 0.5, 1.0, 0.0]:
            print(f"Setting axis value to: {val:+.2f}")
            controller.update_steering(val)
            time.sleep(0.5)

        controller.close()
        print("Test complete.")
    except PermissionError:
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
