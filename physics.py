#!/usr/bin/env python3
import sys
import time

class SteeringSimulation:
    """
    Simulates a physical steering rack using a Damped Harmonic Oscillator (Spring-Mass-Damper).
    """
    def __init__(self, centering_force=15.0, damping=8.0, steering_acceleration=4.0):
        # Configuration constants
        self.centering_force = centering_force
        self.damping = damping
        self.steering_acceleration = steering_acceleration

        # State variables
        self.steering_angle = 0.0      # Range: [-1.0, 1.0]
        self.steering_velocity = 0.0   # Angular velocity

    def apply_impulse(self, direction: int, strength: float = 1.0):
        """Apply a rotary step impulse to the steering velocity."""
        self.steering_velocity += direction * self.steering_acceleration * strength

    def recenter(self):
        """Instantly zero out the angle and velocity."""
        self.steering_angle = 0.0
        self.steering_velocity = 0.0

    def update(self, dt: float):
        """Update simulation state by time step dt (in seconds)."""
        if dt <= 0:
            return

        # Centering force pulls velocity back to center (spring effect)
        spring_force = -self.steering_angle * self.centering_force
        self.steering_velocity += spring_force * dt

        # Damping slows down velocity (friction effect)
        self.steering_velocity -= self.steering_velocity * self.damping * dt

        # Update steering angle
        self.steering_angle += self.steering_velocity * dt

        # Hard clamp at limits [-1.0, 1.0] and stop outward velocity
        if self.steering_angle >= 1.0:
            self.steering_angle = 1.0
            if self.steering_velocity > 0:
                self.steering_velocity = 0.0
        elif self.steering_angle <= -1.0:
            self.steering_angle = -1.0
            if self.steering_velocity < 0:
                self.steering_velocity = 0.0

    def get_ascii_visual(self, width: int = 20) -> str:
        """Generate a visual representation of the steering rack."""
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
        if self.steering_angle <= -1.0:
            bar += " LOCK L"
        elif self.steering_angle >= 1.0:
            bar += " LOCK R"
        else:
            bar += "       "
            
        return bar

# --- Terminal keyboard listener fallback for interactive testing ---
# We use standard termios/select to read keys non-blockingly without extra dependencies.
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
    print("--- Steering Physics Engine Test Overlay ---")
    print("Controls:")
    print("  [A] - Turn Left (CCW impulse)")
    print("  [D] - Turn Right (CW impulse)")
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
                        sim.apply_impulse(-1)
                    elif key == 'd':
                        sim.apply_impulse(1)
                    elif key == 'r':
                        sim.recenter()

                # Update physics
                sim.update(dt)
                last_time = now

                # Display stats in place
                sys.stdout.write(
                    f"\r{sim.get_ascii_visual()} | "
                    f"Angle: {sim.steering_angle:+.2f} | "
                    f"Vel: {sim.steering_velocity:+.2f} "
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
