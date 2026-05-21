#!/usr/bin/env python3
import sys
import time
import evdev
from evdev import ecodes

class RotaryEvent:
    """Unified representation of a knob rotation step."""
    def __init__(self, direction: int, timestamp: float, strength: float = 1.0):
        self.direction = direction  # -1 for CCW (left), +1 for CW (right)
        self.timestamp = timestamp  # time.monotonic()
        self.strength = strength

    def __str__(self):
        dir_str = "CW" if self.direction > 0 else "CCW"
        return f"RotaryEvent({dir_str}, time={self.timestamp:.4f}, strength={self.strength:.2f})"

def list_devices():
    """List all available input devices."""
    try:
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        return devices
    except Exception as e:
        print(f"Error listing input devices: {e}", file=sys.stderr)
        return []

def check_grab_safety(device) -> bool:
    """
    Check if a device is safe to grab exclusively.
    If the device reports capabilities of a standard keyboard (many character keys),
    grabbing it exclusively will lock the user out of typing.
    """
    caps = device.capabilities()
    if ecodes.EV_KEY in caps:
        keys = caps[ecodes.EV_KEY]
        # Check for standard alphanumeric keys (e.g., KEY_A, KEY_Z, KEY_ENTER)
        common_typing_keys = [ecodes.KEY_A, ecodes.KEY_Z, ecodes.KEY_ENTER, ecodes.KEY_SPACE]
        key_count = sum(1 for k in common_typing_keys if k in keys)
        if key_count >= 3:
            print(f"\n[WARNING] Device '{device.name}' appears to be your primary typing keyboard!")
            print("Grabbing this device exclusively will DISABLE your keyboard keys while running.")
            print("It is highly recommended NOT to grab this device.")
            return False
    return True

def parse_event(event) -> tuple[int, float] | None:
    """
    Parse a raw evdev event into (direction, strength) if it matches knob controls.
    Returns None if the event is not relevant.
    """
    # Keypress events (e.g. Media/Volume buttons)
    if event.type == ecodes.EV_KEY:
        # event.value: 1 for keydown, 2 for keyhold, 0 for keyup.
        # We only trigger on press/hold.
        if event.value in (1, 2):
            if event.code in (ecodes.KEY_VOLUMEUP, ecodes.KEY_NEXTSONG):
                return 1, 1.0
            elif event.code in (ecodes.KEY_VOLUMEDOWN, ecodes.KEY_PREVIOUSSONG):
                return -1, 1.0

    # Relative axis events (e.g. Dial, Wheel, HWheel)
    elif event.type == ecodes.EV_REL:
        if event.code in (ecodes.REL_DIAL, ecodes.REL_WHEEL, ecodes.REL_HWHEEL):
            direction = 1 if event.value > 0 else -1
            strength = abs(event.value)
            return direction, strength

    return None

def monitor_device(device_path: str, grab: bool = False, debounce_ms: float = 8.0):
    """
    Monitor the specified input device for rotary/volume knob events,
    applying normalization and debouncing.
    """
    try:
        device = evdev.InputDevice(device_path)
    except PermissionError:
        print(f"Error: Permission denied accessing {device_path}.", file=sys.stderr)
        print("Please run with sudo or check device permissions.", file=sys.stderr)
        return
    except Exception as e:
        print(f"Error opening device {device_path}: {e}", file=sys.stderr)
        return

    print(f"Monitoring: {device.name} ({device.path})")
    
    if grab:
        safe = check_grab_safety(device)
        if not safe:
            confirm = input("Are you sure you want to grab this device? [y/N]: ").strip().lower()
            if confirm != 'y':
                grab = False
        
        if grab:
            try:
                device.grab()
                print("Successfully grabbed device exclusively.")
            except Exception as e:
                print(f"Warning: Failed to grab device exclusively: {e}", file=sys.stderr)

    last_event_time = 0.0
    last_direction = 0

    try:
        for event in device.read_loop():
            parsed = parse_event(event)
            if parsed is None:
                continue
            
            direction, strength = parsed
            now = time.monotonic()
            
            # Simple debounce logic
            # Ignore events in the same/opposite direction if they occur within the debounce window
            # to filter out noisy encoder bounces.
            time_delta = now - last_event_time
            if time_delta < (debounce_ms / 1000.0):
                # Optionally check if it's a bounce (opposite direction immediately after)
                continue
                
            # Calculate click speed (clicks per second, approximate)
            cps = 1.0 / time_delta if last_event_time > 0 else 0.0
            
            last_event_time = now
            last_direction = direction
            
            # Create and print the normalized event
            rot_event = RotaryEvent(direction, now, strength)
            print(f"{rot_event} | Click Speed: {cps:.1f} CPS")

    except KeyboardInterrupt:
        print("\nStopping monitoring...")
    finally:
        if grab:
            try:
                device.ungrab()
                print("Released exclusive device grab.")
            except Exception:
                pass

if __name__ == "__main__":
    print("--- KnobWheel Input Detector Utility ---")
    devices = list_devices()
    if not devices:
        print("No input devices found or unable to access /dev/input/.", file=sys.stderr)
        print("Try running with 'sudo'.", file=sys.stderr)
        sys.exit(1)

    print("\nAvailable Input Devices:")
    for idx, dev in enumerate(devices):
        print(f"[{idx}] {dev.path} - {dev.name} ({dev.phys})")

    # Try to auto-select a device containing typical knob terms
    suggested_idx = None
    for idx, dev in enumerate(devices):
        name_lower = dev.name.lower()
        if "aula" in name_lower or "consumer" in name_lower or "control" in name_lower or "knob" in name_lower:
            suggested_idx = idx
            break

    prompt = f"\nSelect device index [0-{len(devices)-1}]"
    if suggested_idx is not None:
        prompt += f" (default suggested: {suggested_idx})"
    prompt += ": "

    choice = input(prompt).strip()
    if not choice and suggested_idx is not None:
        selected_idx = suggested_idx
    else:
        try:
            selected_idx = int(choice)
            if selected_idx < 0 or selected_idx >= len(devices):
                raise ValueError()
        except ValueError:
            print("Invalid selection.", file=sys.stderr)
            sys.exit(1)

    selected_dev = devices[selected_idx]
    
    grab_input = input("Grab device exclusively? (Prevents keys from triggering system volume changes) [y/N]: ").strip().lower()
    should_grab = (grab_input == 'y')

    monitor_device(selected_dev.path, grab=should_grab)
