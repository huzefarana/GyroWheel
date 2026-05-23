#!/usr/bin/env python3
"""
Gyroscope input server for KnobWheel (Windows).

Receives tilt data from the Android phone web app over WebSocket (local WiFi).
Converts device tilt angles into steering/throttle/brake values for landscape mode.

Protocol (phone -> PC):
  JSON message: {"gamma": <float>, "beta": <float>, "alpha": <float>}

  LANDSCAPE hold (the phone is rotated 90°, so the device axes are swapped
  relative to portrait):
  beta:  device roll in landscape (-180 to +180) → steering
         negative = tilt left, positive = tilt right
  gamma: device pitch in landscape (-90 to +90)  → throttle/brake
         positive gamma = lean forward  = throttle
         negative gamma = lean backward = brake
  alpha: compass heading (0 to 360)
"""
import asyncio
import json
import time
import sys
from dataclasses import dataclass


@dataclass
class GyroState:
    """Latest tilt angles from the phone, in degrees."""
    gamma: float = 0.0   # Landscape pitch (-90..+90) → throttle/brake
    beta: float = 0.0    # Landscape roll (-180..+180) → steering
    alpha: float = 0.0   # Compass
    connected: bool = False
    last_update: float = 0.0


# Shared state between WebSocket handler and the simulation loop
gyro_state = GyroState()


async def gyro_ws_handler(websocket):
    """Handle an incoming WebSocket connection from the phone."""
    peer = websocket.remote_address
    print(f"\n[Gyro] Phone connected from {peer}")
    gyro_state.connected = True

    try:
        async for raw_msg in websocket:
            try:
                data = json.loads(raw_msg)
                gyro_state.gamma = float(data.get("gamma", 0.0))
                gyro_state.beta = float(data.get("beta", 0.0))
                gyro_state.alpha = float(data.get("alpha", 0.0))
                gyro_state.last_update = time.monotonic()
            except (json.JSONDecodeError, ValueError, TypeError):
                pass  # Ignore malformed packets silently
    except Exception:
        pass
    finally:
        gyro_state.connected = False
        gyro_state.gamma = 0.0
        gyro_state.beta = 0.0
        print(f"[Gyro] Phone disconnected ({peer})")


def get_steering_from_gyro(
    deadzone_deg: float = 5.0,
    max_tilt_deg: float = 45.0,
) -> float:
    """
    Convert beta (device roll in landscape) to normalized steering [-1.0, 1.0].
    In landscape the roll axis is independent of the forward/back lean used for
    throttle/brake, so steering stays stable while pedaling.

    deadzone_deg: tilt within this range from center is treated as 0
    max_tilt_deg: tilt at this angle = full lock (1.0 or -1.0)
    """
    beta = gyro_state.beta

    if abs(beta) < deadzone_deg:
        return 0.0

    sign = 1.0 if beta > 0 else -1.0
    adjusted = abs(beta) - deadzone_deg
    usable_range = max_tilt_deg - deadzone_deg

    return min(adjusted / usable_range, 1.0) * sign


def get_throttle_from_gyro(
    deadzone_deg: float = 5.0,
    max_tilt_deg: float = 30.0,
) -> float:
    """
    Convert forward lean (positive gamma in landscape) to throttle [0.0, 1.0].

    deadzone_deg: lean within this range is treated as 0
    max_tilt_deg: lean at this angle = full throttle (1.0)
    """
    gamma = gyro_state.gamma

    if gamma < deadzone_deg:
        return 0.0

    adjusted = gamma - deadzone_deg
    usable_range = max_tilt_deg - deadzone_deg

    return min(adjusted / usable_range, 1.0)


def get_brake_from_gyro(
    deadzone_deg: float = 5.0,
    max_tilt_deg: float = 30.0,
) -> float:
    """
    Convert backward lean (negative gamma in landscape) to brake [0.0, 1.0].

    deadzone_deg: lean within this range is treated as 0
    max_tilt_deg: lean at this angle = full brake (1.0)
    """
    gamma = gyro_state.gamma

    if gamma > -deadzone_deg:
        return 0.0

    adjusted = abs(gamma) - deadzone_deg
    usable_range = max_tilt_deg - deadzone_deg

    return min(adjusted / usable_range, 1.0)


async def start_gyro_server(host: str = "0.0.0.0", port: int = 8765):
    """Start the WebSocket server and return it (caller awaits serve_forever)."""
    try:
        import websockets
    except ImportError:
        print("ERROR: websockets not installed.", file=sys.stderr)
        print("Run: pip install websockets", file=sys.stderr)
        sys.exit(1)

    server = await websockets.serve(gyro_ws_handler, host, port)
    return server
