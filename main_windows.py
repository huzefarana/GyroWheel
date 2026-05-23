#!/usr/bin/env python3
"""
KnobWheel for Windows — Gyroscope Steering
==========================================

Tilt your Android phone to steer in driving games.

Requirements:
  pip install vgamepad websockets

  ViGEmBus driver (one-time install):
  https://github.com/nefarius/ViGEmBus/releases

Usage:
  python main_windows.py

Then open the URL printed on screen in your Android phone's browser (same WiFi).

Optional flags:
  --port 8765          WebSocket port (default 8765)
  --deadzone 5.0       Center deadzone in degrees (default 5.0)
  --max-tilt 45.0      Degrees of tilt = full lock (default 45.0)
  --smoothing 15.0     Physics smoothing speed (default 15.0)
  --no-controller      Skip vgamepad (debug / no ViGEm installed)
"""
import sys
import asyncio
import argparse
import time
import socket

# Physics engine is platform-agnostic — reuse as-is from the Linux version
from physics import SteeringSimulation

from gyro_server import gyro_state, get_steering_from_gyro, get_throttle_from_gyro, get_brake_from_gyro, start_gyro_server
from output_controller_windows import VirtualController, print_game_launch_hints
from phone_server import serve_phone_app


def get_local_ip() -> str:
    """Best-effort: find the LAN IP so we can print the phone URL."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "YOUR_PC_IP"


async def simulation_loop(
    sim: SteeringSimulation,
    controller,
    shutdown_event: asyncio.Event,
    deadzone_deg: float,
    max_tilt_deg: float,
    throttle_tilt_deg: float,
):
    """60 Hz physics + output loop."""
    tick_rate = 1.0 / 60.0
    last_time = time.monotonic()

    print("\n--- KnobWheel Active (Windows / Gyro Mode) ---")
    print("Hold phone LANDSCAPE (screen facing you).")
    print("Tilt phone LEFT/RIGHT → steer")
    print("Lean phone FORWARD    → throttle")
    print("Lean phone BACKWARD   → brake")
    print("Press Ctrl+C to quit.\n")

    try:
        while not shutdown_event.is_set():
            now = time.monotonic()
            dt = now - last_time
            last_time = now

            # --- Input: convert gyro tilt to steering/throttle/brake ---
            if gyro_state.connected:
                target = get_steering_from_gyro(
                    deadzone_deg=deadzone_deg,
                    max_tilt_deg=max_tilt_deg,
                )
                # Drive simulation directly — gyro is absolute, not incremental
                sim.target_angle = target
                sim.accumulated_clicks = target * (sim.lock_to_lock_clicks / 2.0)
                throttle = get_throttle_from_gyro(
                    deadzone_deg=deadzone_deg,
                    max_tilt_deg=throttle_tilt_deg,
                )
                brake = get_brake_from_gyro(
                    deadzone_deg=deadzone_deg,
                    max_tilt_deg=throttle_tilt_deg,
                )
            else:
                # No phone: drift back to center, release pedals
                sim.target_angle = 0.0
                throttle = 0.0
                brake = 0.0

            # --- Physics update ---
            sim.update(dt)

            # --- Controller output ---
            if controller is not None:
                controller.update_steering(sim.steering_angle)
                controller.update_throttle(throttle)
                controller.update_brake(brake)

            # --- Terminal status ---
            status = "CONNECTED" if gyro_state.connected else "waiting for phone..."
            sys.stdout.write(
                f"\r{sim.get_ascii_visual()} | "
                f"Steer: {sim.steering_angle:+.2f} | "
                f"Thr: {throttle:.2f} | "
                f"Brk: {brake:.2f} | "
                f"Phone: {status}   "
            )
            sys.stdout.flush()

            elapsed = time.monotonic() - now
            await asyncio.sleep(max(0.0, tick_rate - elapsed))

    except asyncio.CancelledError:
        pass
    finally:
        print()


async def main():
    parser = argparse.ArgumentParser(
        description="KnobWheel Windows — steer with your phone's gyroscope."
    )
    parser.add_argument("--port", type=int, default=8765,
                        help="WebSocket port (default 8765). Phone app served on port+1.")
    parser.add_argument("--deadzone", type=float, default=5.0,
                        help="Center deadzone in degrees (default 5.0)")
    parser.add_argument("--max-tilt", type=float, default=45.0,
                        help="Full-lock tilt angle in degrees (default 45.0)")
    parser.add_argument("--smoothing", type=float, default=15.0,
                        help="Steering smoothing speed (default 15.0)")
    parser.add_argument("--throttle-tilt", type=float, default=30.0,
                        help="Forward/back tilt degrees for full throttle/brake (default 30.0)")
    parser.add_argument("--no-controller", action="store_true",
                        help="Disable vgamepad output (no ViGEm required)")
    args = parser.parse_args()

    ws_port   = args.port
    http_port = args.port + 1
    local_ip  = get_local_ip()

    # --- Virtual controller ---
    controller = None
    if not args.no_controller:
        try:
            controller = VirtualController()
            print_game_launch_hints()
        except Exception:
            print("WARNING: Could not create virtual controller. Running in display-only mode.", file=sys.stderr)
            print("Use --no-controller to suppress this warning.\n", file=sys.stderr)

    # --- Physics ---
    sim = SteeringSimulation(
        lock_to_lock_clicks=80.0,
        smoothing_speed=args.smoothing,
    )

    # --- Phone web app (HTTP) ---
    serve_phone_app(http_port=http_port, ws_port=ws_port)
    print(f"\n[Phone App] Open this URL on your Android (same WiFi):")
    print(f"\n    http://{local_ip}:{http_port}\n")

    # --- WebSocket server ---
    print(f"[WebSocket] Gyro receiver on ws://{local_ip}:{ws_port}")
    ws_server = await start_gyro_server(host="0.0.0.0", port=ws_port)

    shutdown_event = asyncio.Event()
    sim_task = asyncio.create_task(
        simulation_loop(sim, controller, shutdown_event, args.deadzone, args.max_tilt, args.throttle_tilt)
    )

    try:
        await asyncio.gather(sim_task)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        shutdown_event.set()
        sim_task.cancel()
        await asyncio.gather(sim_task, return_exceptions=True)
        ws_server.close()
        await ws_server.wait_closed()
        if controller:
            controller.close()
        print("KnobWheel terminated.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
