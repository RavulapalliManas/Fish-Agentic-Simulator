"""Research-oriented Boids variant with smooth local steering."""

from __future__ import annotations

import numpy as np

from models.base import BaseModel
from utils.vectors import normalize, weighted_average


class ResearchBoidsModel(BaseModel):
    """Classic local flocking, tuned for dense and interpretable stimuli."""

    name = "Research Boids"

    def compute_force(self, agent, neighbors, context) -> np.ndarray:
        config = context["config"]
        multipliers = context["social_multipliers"]
        target_speed = float(context["target_speed"])
        local_force = (
            self._cohesion(agent, neighbors, config, target_speed) * config.cohesion * multipliers["cohesion"]
            + self._alignment(agent, neighbors, config, target_speed) * config.alignment * multipliers["alignment"]
            + self._separation(agent, neighbors, config, target_speed) * config.separation * multipliers["separation"]
        )
        return local_force + context["noise_force"]

    def _distance_weights(self, agent, neighbors, radius: float) -> list[float]:
        weights: list[float] = []
        for neighbor in neighbors:
            distance = float(np.linalg.norm(neighbor.position - agent.position))
            closeness = max(0.0, 1.0 - distance / max(radius, 1.0))
            weights.append((closeness + 0.2) / max(distance, 1.0))
        return weights

    def _cohesion(self, agent, neighbors, config, target_speed: float) -> np.ndarray:
        if not neighbors:
            return np.zeros(2, dtype=float)
        weights = self._distance_weights(agent, neighbors, config.neighbor_radius)
        centroid = weighted_average([neighbor.position for neighbor in neighbors], weights)
        desired_velocity = normalize(centroid - agent.position, fallback=agent.direction) * target_speed
        return desired_velocity - agent.velocity

    def _alignment(self, agent, neighbors, config, target_speed: float) -> np.ndarray:
        if not neighbors:
            return np.zeros(2, dtype=float)
        weights = self._distance_weights(agent, neighbors, config.neighbor_radius)
        mean_velocity = weighted_average([neighbor.velocity for neighbor in neighbors], weights)
        desired_velocity = normalize(mean_velocity, fallback=agent.direction) * target_speed
        return desired_velocity - agent.velocity

    def _separation(self, agent, neighbors, config, target_speed: float) -> np.ndarray:
        if not neighbors:
            return np.zeros(2, dtype=float)
        repel = np.zeros(2, dtype=float)
        personal_space = max(float(config.separation_radius), float(config.minimum_agent_spacing))
        for neighbor in neighbors:
            offset = agent.position - neighbor.position
            distance = float(np.linalg.norm(offset))
            if 0.0 < distance < personal_space:
                repel += offset / max(distance ** 2, 1.0)
        if np.linalg.norm(repel) < 1e-8:
            return np.zeros(2, dtype=float)
        desired_velocity = normalize(repel, fallback=agent.direction) * target_speed
        return desired_velocity - agent.velocity
