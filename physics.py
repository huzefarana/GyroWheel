#!/usr/bin/env python3
import sys
import time

class SteeringSimulation:
    """
    Simulates a physical steering wheel by accumulating rotary encoder clicks
    directly into absolute position (with zero auto-centering, behaving like a real truck wheel).
    """
    def __init__(self, lock_to_lock_clicks=80, smoothing_speed=15.0):
        # Configuration constants
        self.lock_to_lock_clicks = lock_to_lock_clicks
        self.smoothing_speed = smoothing_speed

        # State variables
        self.accumulated_clicks = 0.0  # Physical position tracker
        self.target_angle = 0.0        # Range: [-1.0, 1.0]
        self.steering_angle = 0.0      # Range: [-1.0, 1.0] (smoothed output)

    def apply_impulse(self, direction: int, strength: float = 1.0):
        """Accumulate a knob click/impulse towards target angle."""
        self.accumulated_clicks += direction * strength
        
        # Hard clamp physical accumulator at locks
        max_clicks = self.lock_to_lock_clicks / 2.0
        self.accumulated_clicks = max(-max_clicks, min(max_clicks, self.accumulated_clicks))
        
        # Compute target angle normalized in range [-1.0, 1.0]
        self.target_angle = self.accumulated_clicks / max_clicks

    def recenter(self):
        """Instantly zero out the accumulated state and angle."""
        self.accumulated_clicks = 0.0
        self.target_angle = 0.0
        self.steering_angle = 0.0

    def update(self, dt: float):
        """Smoothly interpolate steering_angle towards target_angle."""
        if dt <= 0:
            return

        # Smooth glide transition to prevent instant jumps in game axis
        error = self.target_angle - self.steering_angle
        self.steering_angle += error * self.smoothing_speed * dt

        # Hard clamp steering angle to absolute limits
        self.steering_angle = max(-1.0, min(1.0, self.steering_angle))

    def get_ascii_visual(self, width: int = 20) -> str:
        """Generate a visual representation of the steering wheel position."""
        # Represents steering from -1.0 to 1.0
        pos = int(self.steering_angle * width)
        
        left_side = ""
        right_side = ""
        
        if pos < 0:
            # Steering is to the left
            left_side = " " * (width + pos) + "<" * abs(pos)
            right_side = " " * width
        elif pos > 0:
            # Steering is to the right
            left_side = " " * width
            right_side = ">" * pos + " " * (width - pos)
        else:
            # Steering is centered
            left_side = " " * width
            right_side = " " * width
            
        bar = f"[{left_side}|{right_side}]"
        
        # Add lock indicators
        if self.steering_angle <= -0.99:
            bar += " LOCK L"
        elif self.steering_angle >= 0.99:
            bar += " LOCK R"
        else:
            bar += "       "
            
        return bar

# --- Terminal keyboard listener fallback for interactive testing ---
try:
    import select
    import termios
    import tty
    KEYBOARD_SUPPORT = True
except ImportError:
    KEYBOARD_SUPPORT = False

class NonBlockingKeyReader:
    def __init__(self):
        self.old_settings = None
        if KEYBOARD_SUPPORT:
            self.old_settings = termios.tcgetattr(sys.stdin)

    def __enter__(self):
        if KEYBOARD_SUPPORT:
            tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, type, value, traceback):
        if KEYBOARD_SUPPORT and self.old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)

    def get_key(self) -> str | None:
        if not KEYBOARD_SUPPORT:
            return None
        if select.select([sys.stdin], [], [], 0.0)[0] == [sys.stdin]:
            return sys.stdin.read(1)
        return None

def run_test_loop():
    if not KEYBOARD_SUPPORT:
        print("Standard UNIX terminal library (termios/tty) is not supported on this platform.", file=sys.stderr)
        return

    sim = SteeringSimulation()
    print("--- Steering Physics Engine Test Overlay (Direct Mode) ---")
    print("Controls:")
    print("  [A] - Turn Left (CCW step)")
    print("  [D] - Turn Right (CW step)")
    print("  [R] - Instantly Recenter")
    print("  [Q] - Quit")
    print("\nStarting 60Hz physics loop...")
    time.sleep(1.0)

    last_time = time.monotonic()
    tick_rate = 1.0 / 60.0

    with NonBlockingKeyReader() as reader:
        try:
            while True:
                # Calculate delta time
                now = time.monotonic()
                dt = now - last_time
                
                # Check for key presses
                key = reader.get_key()
                if key:
                    key = key.lower()
                    if key == 'q':
                        break
                    elif key == 'a':
                        # Keyboard emulation applies a step in CCW direction
                        sim.apply_impulse(-1, strength=4.0)
                    elif key == 'd':
                        # Keyboard emulation applies a step in CW direction
                        sim.apply_impulse(1, strength=4.0)
                    elif key == 'r':
                        sim.recenter()

                # Update physics
                sim.update(dt)
                last_time = now

                # Display stats in place
                sys.stdout.write(
                    f"\r{sim.get_ascii_visual()} | "
                    f"Angle: {sim.steering_angle:+.2f} | "
                    f"Target: {sim.target_angle:+.2f} | "
                    f"Clicks: {sim.accumulated_clicks:+.1f} "
                )
                sys.stdout.flush()

                # Sleep to maintain 60Hz tick rate
                elapsed = time.monotonic() - now
                sleep_time = max(0.0, tick_rate - elapsed)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            pass
    print("\nPhysics test complete.")

if __name__ == "__main__":
    run_test_loop()
