#!/usr/bin/env python3
import sys
import evdev
from evdev import ecodes, AbsInfo

class VirtualJoystick:
    """
    Handles creating and writing to a virtual Linux joystick using uinput.
    """
    def __init__(self, name="KnobWheel Virtual Controller"):
        self.name = name
        self.ui = None

        # Setup axis range and properties
        # ABS_X is standard for steering / primary horizontal axis.
        abs_info = AbsInfo(
            value=0,
            min=-32768,
            max=32767,
            fuzz=0,
            flat=0,
            resolution=0
        )

        capabilities = {
            ecodes.EV_ABS: [
                (ecodes.ABS_X, abs_info)
            ],
            # BTN_JOYSTICK ensures the device is recognized as an active game controller
            ecodes.EV_KEY: [ecodes.BTN_JOYSTICK]
        }

        try:
            self.ui = evdev.UInput(capabilities, name=self.name)
            print(f"Successfully created virtual joystick device: '{self.name}'")
        except PermissionError:
            print("Error: Permission denied when attempting to create uinput device.", file=sys.stderr)
            print("Please run with 'sudo' or configure udev rules for /dev/uinput.", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Failed to create virtual joystick: {e}", file=sys.stderr)
            raise

    def update_steering(self, normalized_val: float):
        """
        Update the ABS_X steering axis.
        Input: normalized value in range [-1.0, 1.0]
        """
        if self.ui is None:
            return

        # Hard clamp input value
        val = max(-1.0, min(1.0, normalized_val))

        # Scale -1.0 -> 1.0 into -32768 -> 32767
        if val < 0:
            integer_val = int(val * 32768)
        else:
            integer_val = int(val * 32767)

        # Write absolute X axis event and sync
        self.ui.write(ecodes.EV_ABS, ecodes.ABS_X, integer_val)
        self.ui.syn()

    def close(self):
        """Release the uinput device."""
        if self.ui is not None:
            self.ui.close()
            print("Closed virtual joystick device.")
            self.ui = None

if __name__ == "__main__":
    print("--- KnobWheel Output Controller Test ---")
    try:
        controller = VirtualJoystick()
        print("Device is registered. You can verify it exists using 'ls /dev/input/' or 'jstest-gtk'.")
        
        # Write center, left, right to test
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
