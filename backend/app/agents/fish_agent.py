"""Agent state and deterministic physics integration."""

from __future__ import annotations

import numpy as np

from utils.vectors import angle_of, blend_factor, limit_magnitude, normalize, vector_from_angle


class FishAgent:
    """Single fish with smooth steering and deterministic state."""

    def __init__(self, agent_id: int, position: np.ndarray, velocity: np.ndarray):
        self.id = int(agent_id)
        self.position = np.asarray(position, dtype=float)
        self.velocity = np.asarray(velocity, dtype=float)
        self.group = "school"
        self.noise_direction = normalize(self.velocity, fallback=vector_from_angle(-np.pi / 2.0))

    @property
    def heading(self) -> float:
        return angle_of(self.velocity)

    @property
    def direction(self) -> np.ndarray:
        return normalize(self.velocity, fallback=self.noise_direction)

    @property
    def speed(self) -> float:
        return float(np.linalg.norm(self.velocity))

    def sample_noise(self, dt: float, rng: np.random.Generator) -> np.ndarray:
        """Sample correlated steering noise that remains stable across FPS values."""
        alpha = 1.0 - blend_factor(dt, 0.24)
        fresh = rng.normal(0.0, 1.0, size=2)
        blended = alpha * self.noise_direction + (1.0 - alpha) * fresh
        self.noise_direction = normalize(blended, fallback=self.noise_direction)
        return self.noise_direction.copy()

    def integrate(self, total_force: np.ndarray, dt: float, config, constant_speed: bool = False) -> None:
        """Advance the fish by one fixed-timestep update."""
        acceleration = limit_magnitude(np.asarray(total_force, dtype=float), config.max_force)
        current_direction = self.direction
        predicted_velocity = self.velocity + acceleration * float(dt)
        desired_direction = normalize(predicted_velocity, fallback=current_direction)
        turn_limited_direction = self._apply_turn_limit(
            current_direction=current_direction,
            desired_direction=desired_direction,
            max_turn_radians=np.deg2rad(config.max_turn_rate_deg) * float(dt),
        )

        if constant_speed:
            new_speed = float(config.speed)
        else:
            predicted_speed = max(float(np.linalg.norm(predicted_velocity)), float(config.speed) * 0.25)
            speed_blend = min(1.0, 4.0 * float(dt))
            new_speed = predicted_speed + (float(config.speed) - predicted_speed) * speed_blend

        self.velocity = turn_limited_direction * new_speed
        self.position = self.position + self.velocity * float(dt)
        self._keep_in_bounds(config)

    def _apply_turn_limit(
        self,
        current_direction: np.ndarray,
        desired_direction: np.ndarray,
        max_turn_radians: float,
    ) -> np.ndarray:
        current_angle = angle_of(current_direction)
        desired_angle = angle_of(desired_direction)
        angle_delta = np.arctan2(np.sin(desired_angle - current_angle), np.cos(desired_angle - current_angle))
        return vector_from_angle(current_angle + float(np.clip(angle_delta, -max_turn_radians, max_turn_radians)))

    def _keep_in_bounds(self, config) -> None:
        width, height = config.arena_size
        margin = float(config.size) + 1.0

        min_x = margin
        max_x = float(width) - margin
        min_y = margin
        max_y = float(height) - margin

        if self.position[0] < min_x:
            self.position[0] = min_x
            self.velocity[0] = abs(self.velocity[0]) * 0.25
        elif self.position[0] > max_x:
            self.position[0] = max_x
            self.velocity[0] = -abs(self.velocity[0]) * 0.25

        if self.position[1] < min_y:
            self.position[1] = min_y
            self.velocity[1] = abs(self.velocity[1]) * 0.25
        elif self.position[1] > max_y:
            self.position[1] = max_y
            self.velocity[1] = -abs(self.velocity[1]) * 0.25
