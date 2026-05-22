#!/usr/bin/env python3
import sys
import time
import evdev
from evdev import ecodes, AbsInfo

# Generic USB gamepad IDs — helps SDL and games classify the device as a controller.
VENDOR_ID = 0x0079
PRODUCT_ID = 0x0006


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


class VirtualJoystick:
    """
    Handles creating and writing to a virtual Linux gamepad using uinput.
    Exposes ABS_X as the steering axis with a standard gamepad capability set
    so games and SDL are more likely to detect it than a bare 1-axis device.
    """
    def __init__(self, name="KnobWheel Gamepad"):
        self.name = name
        self.ui = None
        self.event_path = None
        self.js_path = None

        axis_info = AbsInfo(
            value=0,
            min=-32768,
            max=32767,
            fuzz=0,
            flat=128,
            resolution=0,
        )

        capabilities = {
            ecodes.EV_KEY: [
                ecodes.BTN_SOUTH,
                ecodes.BTN_EAST,
                ecodes.BTN_WEST,
                ecodes.BTN_NORTH,
                ecodes.BTN_TL,
                ecodes.BTN_TR,
                ecodes.BTN_SELECT,
                ecodes.BTN_START,
            ],
            ecodes.EV_ABS: [
                (ecodes.ABS_X, axis_info),
                (ecodes.ABS_Y, axis_info),
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

            print(f"Successfully created virtual gamepad: '{self.name}'")
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
            print(f"Failed to create virtual gamepad: {e}", file=sys.stderr)
            raise

    def _sync_initial_state(self):
        """Center all axes so listeners see a valid idle state."""
        if self.ui is None:
            return
        self.ui.write(ecodes.EV_ABS, ecodes.ABS_X, 0)
        self.ui.write(ecodes.EV_ABS, ecodes.ABS_Y, 0)
        self.ui.syn()

    def update_steering(self, normalized_val: float):
        """
        Update the ABS_X steering axis.
        Input: normalized value in range [-1.0, 1.0]
        """
        if self.ui is None:
            return

        val = max(-1.0, min(1.0, normalized_val))

        if val < 0:
            integer_val = int(val * 32768)
        else:
            integer_val = int(val * 32767)

        self.ui.write(ecodes.EV_ABS, ecodes.ABS_X, integer_val)
        self.ui.syn()

    def close(self):
        """Release the uinput device."""
        if self.ui is not None:
            self.ui.close()
            print("Closed virtual gamepad.")
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
    print("  3. In ETS2: Options → Controls → bind Steering axis X")
    print("     Ignore 'no steering wheel' — bind the joystick axis manually.")
    if joystick.js_path:
        print(f"\nIf ETS2 still ignores it, try launching with:")
        print(f"  SDL_JOYSTICK_DEVICE={joystick.js_path} steam -applaunch 227300")
    print("-------------------------------\n")


if __name__ == "__main__":
    print("--- KnobWheel Output Controller Test ---")
    try:
        controller = VirtualJoystick()
        print("Device is registered. Verify with 'jstest-gtk' or 'evtest'.")

        import time
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
