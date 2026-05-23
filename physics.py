#!/usr/bin/env python3


class SteeringSimulation:
    """
    Smoothly interpolates a steering angle toward a target each frame.
    target_angle is set directly from gyro input [-1.0, 1.0];
    steering_angle is the smoothed output sent to the controller.
    """
    def __init__(self, lock_to_lock_clicks=80, smoothing_speed=15.0):
        self.lock_to_lock_clicks = lock_to_lock_clicks
        self.smoothing_speed = smoothing_speed

        self.accumulated_clicks = 0.0
        self.target_angle = 0.0
        self.steering_angle = 0.0

    def update(self, dt: float):
        """Smoothly interpolate steering_angle towards target_angle."""
        if dt <= 0:
            return
        error = self.target_angle - self.steering_angle
        self.steering_angle += error * self.smoothing_speed * dt
        self.steering_angle = max(-1.0, min(1.0, self.steering_angle))

    def get_ascii_visual(self, width: int = 20) -> str:
        """Terminal bar showing current steering position."""
        pos = int(self.steering_angle * width)

        if pos < 0:
            left_side  = " " * (width + pos) + "<" * abs(pos)
            right_side = " " * width
        elif pos > 0:
            left_side  = " " * width
            right_side = ">" * pos + " " * (width - pos)
        else:
            left_side  = " " * width
            right_side = " " * width

        bar = f"[{left_side}|{right_side}]"

        if self.steering_angle <= -0.99:
            bar += " LOCK L"
        elif self.steering_angle >= 0.99:
            bar += " LOCK R"
        else:
            bar += "       "

        return bar
