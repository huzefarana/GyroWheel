#!/usr/bin/env python3
"""
Virtual Xbox controller output for Windows via ViGEmBus + vgamepad.

Requirements:
  1. Install ViGEmBus driver: https://github.com/nefarius/ViGEmBus/releases
  2. pip install vgamepad

Maps steering_angle [-1.0, 1.0] to the left thumbstick X axis.
Games that support xinput (most Windows games) will see this as a gamepad.
For ETS2/ATS, bind "Steering" to the left stick X axis in Options -> Controls.
"""
import sys
import time

try:
    import vgamepad as vg
except ImportError:
    print("ERROR: vgamepad not installed.", file=sys.stderr)
    print("Run: pip install vgamepad", file=sys.stderr)
    print("Also install ViGEmBus driver from:", file=sys.stderr)
    print("  https://github.com/nefarius/ViGEmBus/releases", file=sys.stderr)
    sys.exit(1)


class VirtualController:
    """
    Virtual Xbox 360 controller for Windows.
    Uses the left thumbstick X axis for steering.
    Range: -32768 (full left) to 32767 (full right)
    """

    def __init__(self):
        self.gamepad = None
        print("Creating virtual Xbox 360 controller via ViGEmBus...")
        try:
            self.gamepad = vg.VX360Gamepad()
            # Center all axes at startup
            self._sync_initial_state()
            print("Virtual Xbox 360 controller created successfully.")
            print("  -> Bind 'Left Stick X' as your steering axis in-game.")
        except Exception as e:
            print(f"ERROR: Failed to create virtual controller: {e}", file=sys.stderr)
            print("Make sure ViGEmBus driver is installed.", file=sys.stderr)
            raise

    def _sync_initial_state(self):
        """Push zeroed state so games see a valid idle controller."""
        if self.gamepad is None:
            return
        self.gamepad.left_joystick(x_value=0, y_value=0)
        self.gamepad.right_joystick(x_value=0, y_value=0)
        self.gamepad.left_trigger(value=0)
        self.gamepad.right_trigger(value=0)
        self.gamepad.update()

    def update_steering(self, normalized_val: float):
        """
        Update the steering axis.
        normalized_val: float in [-1.0, 1.0]
          -1.0 = full left lock
           0.0 = center
          +1.0 = full right lock
        """
        if self.gamepad is None:
            return

        val = max(-1.0, min(1.0, normalized_val))

        # vgamepad accepts -32768 to 32767
        if val < 0:
            raw = int(val * 32768)
        else:
            raw = int(val * 32767)

        self.gamepad.left_joystick(x_value=raw, y_value=0)
        self.gamepad.update()

    def update_throttle(self, value: float):
        """
        Update the throttle axis (right trigger).
        value: float in [0.0, 1.0] — 1.0 = full throttle
        """
        if self.gamepad is None:
            return
        val = max(0.0, min(1.0, value))
        self.gamepad.right_trigger(value=int(val * 255))
        self.gamepad.update()

    def update_brake(self, value: float):
        """
        Update the brake axis (left trigger).
        value: float in [0.0, 1.0] — 1.0 = full brake
        """
        if self.gamepad is None:
            return
        val = max(0.0, min(1.0, value))
        self.gamepad.left_trigger(value=int(val * 255))
        self.gamepad.update()

    def close(self):
        """Release the virtual controller."""
        if self.gamepad is not None:
            self._sync_initial_state()
            self.gamepad = None
            print("Virtual controller released.")


def print_game_launch_hints():
    print("\n--- Game Setup ---")
    print("1. KnobWheel must be running BEFORE you launch the game.")
    print("2. In ETS2: Options -> Controls -> set input to 'Xbox Controller'")
    print("   Then bind 'Steering' to 'Left Stick X'.")
    print("3. If the game doesn't see the controller, restart it while")
    print("   KnobWheel is already running.")
    print("------------------\n")


if __name__ == "__main__":
    print("--- VirtualController Test ---")
    try:
        ctrl = VirtualController()
        print_game_launch_hints()
        print("Sweeping left stick X from left -> center -> right -> center...")
        for val in [-1.0, -0.5, 0.0, 0.5, 1.0, 0.5, 0.0]:
            print(f"  Steering: {val:+.2f}")
            ctrl.update_steering(val)
            time.sleep(0.6)
        ctrl.close()
        print("Test complete.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
