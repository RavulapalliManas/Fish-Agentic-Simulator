"""Agent state and shared physics integration."""

from __future__ import annotations

from collections import deque

import numpy as np

from vector_utils import angle_of, limit_magnitude, normalize, vector_from_angle


class FishAgent:
    """Single fish with persistent state and a smooth physics update."""

    def __init__(self, agent_id: int, position, rng: np.random.Generator, config):
        self.id = agent_id
        self.pos = np.asarray(position, dtype=float)
        self.size = int(config.agent_size)
        self.shape = str(config.agent_shape)
        self.base_speed = max(0.6, float(rng.normal(config.speed, config.speed_std)))

        initial_angle = float(rng.uniform(0.0, 2.0 * np.pi))
        initial_speed = self.base_speed * float(rng.uniform(0.75, 1.0))
        self.vel = vector_from_angle(initial_angle) * initial_speed

        self.state = "explore"
        self.group = "school"
        self.noise_vector = vector_from_angle(float(rng.uniform(0.0, 2.0 * np.pi)))
        self.trail = deque(maxlen=int(config.trail_length))
        self.trail.append(self.pos.copy())

    @property
    def speed(self) -> float:
        return float(np.linalg.norm(self.vel))

    @property
    def heading(self) -> float:
        return angle_of(self.vel)

    @property
    def direction(self) -> np.ndarray:
        return normalize(self.vel, fallback=self.noise_vector)

    def apply_appearance(self, size: float, shape: str) -> None:
        """Update size and shape without resetting the simulation."""
        self.size = max(2, int(round(size)))
        self.shape = str(shape)

    def sample_noise(self, rng: np.random.Generator) -> np.ndarray:
        """Generate smooth, correlated noise instead of frame-to-frame jitter."""
        fresh = rng.normal(0.0, 1.0, size=2)
        blended = 0.88 * self.noise_vector + 0.12 * fresh
        self.noise_vector = normalize(blended, fallback=self.noise_vector)
        return self.noise_vector.copy()

    def update_physics(self, acceleration: np.ndarray, global_state) -> None:
        """Apply smooth steering, turning limits, and speed regulation."""
        config = global_state["config"]
        dt = float(global_state["dt"])
        bounds = global_state["bounds"]

        limited_force = limit_magnitude(np.asarray(acceleration, dtype=float), config.max_force)

        current_direction = self.direction
        predicted_velocity = self.vel + limited_force * dt
        desired_direction = normalize(predicted_velocity, fallback=current_direction)

        keep_ratio = float(np.clip(config.persistence, 0.0, 0.98))
        blended_direction = normalize(
            keep_ratio * current_direction + (1.0 - keep_ratio) * desired_direction,
            fallback=current_direction,
        )
        constrained_direction = self._apply_turn_limit(
            current_direction,
            blended_direction,
            np.deg2rad(config.max_turn_degrees),
        )

        target_speed = float(global_state.get("speed_override", self.base_speed))
        predicted_speed = float(np.linalg.norm(predicted_velocity))
        if global_state.get("constant_speed", False):
            new_speed = target_speed
        else:
            if predicted_speed < 0.35 * target_speed:
                predicted_speed = 0.35 * target_speed
            new_speed = predicted_speed + (target_speed - predicted_speed) * config.soft_speed_gain

        self.vel = constrained_direction * max(new_speed, 0.15)
        self.pos = self.pos + self.vel * dt
        self._keep_in_bounds(bounds)
        self.trail.append(self.pos.copy())

    def _apply_turn_limit(
        self,
        current_direction: np.ndarray,
        desired_direction: np.ndarray,
        max_turn_radians: float,
    ) -> np.ndarray:
        """Avoid instant heading jumps by capping the turn angle."""
        current_angle = angle_of(current_direction)
        desired_angle = angle_of(desired_direction)
        angle_diff = np.arctan2(np.sin(desired_angle - current_angle), np.cos(desired_angle - current_angle))
        limited_angle = current_angle + float(np.clip(angle_diff, -max_turn_radians, max_turn_radians))
        return vector_from_angle(limited_angle)

    def _keep_in_bounds(self, bounds: tuple[float, float]) -> None:
        """Apply a gentle boundary clamp if a fish touches the arena edge."""
        width, height = bounds
        min_x = float(self.size)
        max_x = float(width - self.size)
        min_y = float(self.size)
        max_y = float(height - self.size)

        if self.pos[0] < min_x:
            self.pos[0] = min_x
            self.vel[0] = abs(self.vel[0]) * 0.25
        elif self.pos[0] > max_x:
            self.pos[0] = max_x
            self.vel[0] = -abs(self.vel[0]) * 0.25

        if self.pos[1] < min_y:
            self.pos[1] = min_y
            self.vel[1] = abs(self.vel[1]) * 0.25
        elif self.pos[1] > max_y:
            self.pos[1] = max_y
            self.vel[1] = -abs(self.vel[1]) * 0.25

    def snapshot(self) -> dict:
        """Return a compact state summary for metrics and optional logging."""
        return {
            "id": self.id,
            "state": self.state,
            "group": self.group,
            "shape": self.shape,
            "size": self.size,
            "x": float(self.pos[0]),
            "y": float(self.pos[1]),
            "vx": float(self.vel[0]),
            "vy": float(self.vel[1]),
            "speed": self.speed,
            "heading": self.heading,
        }
