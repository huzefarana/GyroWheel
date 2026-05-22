#!/usr/bin/env python3
import sys
import time
import argparse
import asyncio

# Import modules from our project
from input_detector import (
    RotaryEvent,
    list_devices,
    check_grab_safety,
    parse_event,
    suggest_knob_device,
    is_virtual_output_device,
)
from physics import SteeringSimulation, NonBlockingKeyReader, KEYBOARD_SUPPORT
from output_controller import VirtualJoystick, print_game_launch_hints

async def keyboard_input_task(queue: asyncio.Queue, shutdown_event: asyncio.Event):
    """Monitor keyboard input for fallback controls and hotkeys."""
    if not KEYBOARD_SUPPORT:
        print("Keyboard support unavailable (missing termios/tty).", file=sys.stderr)
        return

    with NonBlockingKeyReader() as reader:
        while not shutdown_event.is_set():
            # Run non-blocking stdin read
            key = reader.get_key()
            if key:
                key = key.lower()
                if key == 'q':
                    shutdown_event.set()
                    break
                elif key == 'a':
                    # Simulate counter-clockwise (left) impulse
                    await queue.put(RotaryEvent(-1, time.monotonic(), strength=4.0))
                elif key == 'd':
                    # Simulate clockwise (right) impulse
                    await queue.put(RotaryEvent(1, time.monotonic(), strength=4.0))
                elif key == 'r':
                    # Recenter hotkey
                    await queue.put('RECENTER')
            
            # Yield control to allow other tasks to run
            await asyncio.sleep(0.01)

async def evdev_input_task(device_path: str, grab: bool, queue: asyncio.Queue, shutdown_event: asyncio.Event, debounce_ms: float):
    """Read knob/volume events from the physical input device."""
    import evdev
    try:
        device = evdev.InputDevice(device_path)
    except PermissionError:
        print(f"\nError: Permission denied accessing {device_path}.", file=sys.stderr)
        print("Please run with 'sudo' or add your user to the 'input' group.", file=sys.stderr)
        shutdown_event.set()
        return
    except Exception as e:
        print(f"\nError opening device {device_path}: {e}", file=sys.stderr)
        shutdown_event.set()
        return

    # Check and warn before grab
    if grab:
        if not check_grab_safety(device):
            print("Skipping exclusive grab because device capabilities suggest it is a primary typing keyboard.")
            grab = False
        else:
            try:
                device.grab()
                print(f"Exclusively grabbed device '{device.name}'")
            except Exception as e:
                print(f"Warning: Failed to grab device exclusively: {e}", file=sys.stderr)
                grab = False

    last_event_time = 0.0
    try:
        async for event in device.async_read_loop():
            if shutdown_event.is_set():
                break
            
            parsed = parse_event(event)
            if parsed is None:
                continue

            direction, strength = parsed
            now = time.monotonic()

            # Debouncing
            if now - last_event_time < (debounce_ms / 1000.0):
                continue

            last_event_time = now
            await queue.put(RotaryEvent(direction, now, strength))

    except Exception as e:
        print(f"\nError reading from input device: {e}", file=sys.stderr)
    finally:
        if grab:
            try:
                device.ungrab()
                print("Released exclusive device grab.")
            except Exception:
                pass
        shutdown_event.set()

async def simulation_loop(sim: SteeringSimulation, joystick: VirtualJoystick | None, queue: asyncio.Queue, shutdown_event: asyncio.Event):
    """Run physics simulation at 60Hz and update virtual controller output."""
    last_time = time.monotonic()
    tick_rate = 1.0 / 60.0

    print("\n--- KnobWheel Active ---")
    print("Controls:")
    print("  [A] - Turn Left (Fallback)")
    print("  [D] - Turn Right (Fallback)")
    print("  [R] - Recenter Wheel")
    print("  [Q] - Quit")
    print("------------------------")

    try:
        while not shutdown_event.is_set():
            now = time.monotonic()
            dt = now - last_time
            last_time = now

            # Process all pending input events
            while not queue.empty():
                event = queue.get_nowait()
                if event == 'RECENTER':
                    sim.recenter()
                elif isinstance(event, RotaryEvent):
                    sim.apply_impulse(event.direction, event.strength)

            # Update physics state
            sim.update(dt)

            # Update virtual controller axis
            if joystick is not None:
                try:
                    joystick.update_steering(sim.steering_angle)
                except Exception as e:
                    print(f"\nError writing to virtual controller: {e}", file=sys.stderr)
                    shutdown_event.set()
                    break

            # Print status overlay
            sys.stdout.write(
                f"\r{sim.get_ascii_visual()} | "
                f"Angle: {sim.steering_angle:+.2f} | "
                f"Target: {sim.target_angle:+.2f} | "
                f"Clicks: {sim.accumulated_clicks:+.1f} | "
                f"uinput: {'Active' if joystick else 'Disabled'} "
            )
            sys.stdout.flush()

            # Sleep to maintain ~60Hz simulation frequency
            elapsed = time.monotonic() - now
            sleep_time = max(0.0, tick_rate - elapsed)
            await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        pass
    finally:
        # Clean terminal output line
        print()

async def main():
    parser = argparse.ArgumentParser(description="KnobWheel: Turn your keyboard volume knob into a virtual steering wheel.")
    parser.add_argument("--device", type=str, help="Path to input device (e.g. /dev/input/event10)")
    parser.add_argument("--keyboard", action="store_true", help="Keyboard-only mode (uses A/D keys for testing)")
    parser.add_argument("--grab", action="store_true", help="Attempt exclusive grab on the input device")
    parser.add_argument("--no-uinput", action="store_true", help="Disable uinput virtual controller output (physics demo only)")
    parser.add_argument("--debounce", type=float, default=8.0, help="Debounce window in milliseconds (default: 8.0)")
    
    # Direct mode settings
    parser.add_argument("--clicks", type=float, default=80.0, help="Total clicks lock-to-lock (default: 80.0, approx 1200 degrees)")
    parser.add_argument("--smoothing", type=float, default=15.0, help="Smoothing speed factor (default: 15.0)")

    args = parser.parse_args()

    # Initialize Direct Position Mapping Engine
    sim = SteeringSimulation(
        lock_to_lock_clicks=args.clicks,
        smoothing_speed=args.smoothing
    )

    # Pick physical input device before creating the virtual gamepad (keeps the list clean)
    device_path = args.device
    should_grab = args.grab
    if not args.keyboard and not device_path:
        devices = list_devices()
        if not devices:
            print("\nError: No input devices found. Try running with 'sudo' or check permissions.", file=sys.stderr)
            sys.exit(1)

        suggested_idx = suggest_knob_device(devices)

        print("\nAvailable Input Devices:")
        for idx, dev in enumerate(devices):
            marker = "[*] " if idx == suggested_idx else "    "
            skip = " (virtual — do not select)" if is_virtual_output_device(dev) else ""
            print(f"{marker}[{idx}] {dev.path} - {dev.name} ({dev.phys}){skip}")

        choice_prompt = "\nSelect device index"
        if suggested_idx is not None:
            choice_prompt += f" (suggested: {suggested_idx})"
        choice_prompt += ": "

        choice = input(choice_prompt).strip()
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

        if is_virtual_output_device(devices[selected_idx]):
            print("\nError: That is KnobWheel's own virtual output device, not your keyboard knob.", file=sys.stderr)
            print("Pick the 'Consumer Control' device for your keyboard instead.", file=sys.stderr)
            sys.exit(1)

        device_path = devices[selected_idx].path

        if not args.grab:
            grab_input = input("Grab device exclusively? (Prevents keys from triggering system volume changes) [y/N]: ").strip().lower()
            should_grab = (grab_input == 'y')
        else:
            should_grab = True

    # Create virtual gamepad after input selection so it does not pollute the device list
    joystick = None
    if not args.no_uinput:
        try:
            joystick = VirtualJoystick()
            print_game_launch_hints(joystick)
        except PermissionError:
            print("\nCritical: Please run with sudo to enable uinput virtual controller, or use --no-uinput for a CLI simulation demo.", file=sys.stderr)
            sys.exit(1)
        except Exception:
            sys.exit(1)

    # Setup Async Tasks
    queue = asyncio.Queue()
    shutdown_event = asyncio.Event()

    tasks = []
    
    # Keyboard fallback/hotkey task is always active if terminal keyboard libraries are supported
    if KEYBOARD_SUPPORT:
        tasks.append(asyncio.create_task(keyboard_input_task(queue, shutdown_event)))

    # Device polling task (if not in keyboard-only mode)
    if device_path:
        tasks.append(asyncio.create_task(
            evdev_input_task(device_path, should_grab, queue, shutdown_event, args.debounce)
        ))

    # Physics & output loop task
    tasks.append(asyncio.create_task(
        simulation_loop(sim, joystick, queue, shutdown_event)
    ))

    # Wait for shutdown signal (e.g. Q key pressed or device closed or Ctrl+C)
    try:
        # Run until the shutdown event is flagged
        while not shutdown_event.is_set():
            await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
    finally:
        # Signal all tasks to terminate
        shutdown_event.set()
        for t in tasks:
            t.cancel()
        
        # Wait briefly for tasks to cancel cleanly
        await asyncio.gather(*tasks, return_exceptions=True)

        if joystick:
            joystick.close()

if __name__ == "__main__":
    # Ensure terminal stdin configuration is restored under any circumstance
    old_stdin_settings = None
    if KEYBOARD_SUPPORT:
        import termios
        try:
            old_stdin_settings = termios.tcgetattr(sys.stdin)
        except Exception:
            pass

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        if KEYBOARD_SUPPORT and old_stdin_settings:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_stdin_settings)
            except Exception:
                pass
        print("KnobWheel terminated.")
