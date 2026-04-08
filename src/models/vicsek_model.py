"""Vicsek-style stochastic active matter model."""

from __future__ import annotations

import numpy as np

from base_model import BaseModel
from vector_utils import angle_of, normalize, vector_from_angle


class VicsekModel(BaseModel):
    """Constant-speed angular alignment with Gaussian turning noise."""

    name = "Active Matter"
    constant_speed = True

    def compute_force(self, agent, neighbors, global_state) -> np.ndarray:
        config = global_state["config"]
        current_direction = normalize(agent.vel, fallback=agent.noise_vector)

        if neighbors:
            neighbor_dirs = [normalize(neighbor.vel, fallback=current_direction) for neighbor in neighbors]
            mean_direction = normalize(np.mean(np.asarray(neighbor_dirs), axis=0), fallback=current_direction)
        else:
            mean_direction = current_direction

        angular_noise = float(global_state["rng"].normal(0.0, max(config.noise * 0.7, 0.01)))
        noisy_direction = vector_from_angle(angle_of(mean_direction) + angular_noise)
        persistent_direction = normalize(
            config.persistence * current_direction + (1.0 - config.persistence) * noisy_direction,
            fallback=current_direction,
        )

        desired_velocity = persistent_direction * agent.base_speed
        local_force = desired_velocity - agent.vel
        return self.blend_force(local_force, global_state, noise_scale=0.2, attractor_scale=0.75, rotation_scale=0.75)
