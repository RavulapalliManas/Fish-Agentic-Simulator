"""Enhanced Boids implementation adapted from the original simulator."""

from __future__ import annotations

import numpy as np

from base_model import BaseModel
from vector_utils import normalize, weighted_average


class BoidsModel(BaseModel):
    """Classic local flocking with smoother, distance-weighted steering."""

    name = "Enhanced Boids"

    def compute_force(self, agent, neighbors, global_state) -> np.ndarray:
        local_force = self.local_boids_force(agent, neighbors, global_state)
        return self.blend_force(local_force, global_state)

    def local_boids_force(
        self,
        agent,
        neighbors,
        global_state,
        cohesion_scale: float = 1.0,
        alignment_scale: float = 1.0,
        separation_scale: float = 1.0,
    ) -> np.ndarray:
        if not neighbors:
            return np.zeros(2, dtype=float)

        config = global_state["config"]
        cohesion = self._cohesion(agent, neighbors, config) * config.cohesion * cohesion_scale
        alignment = self._alignment(agent, neighbors, config) * config.alignment * alignment_scale
        separation = self._separation(agent, neighbors, config) * config.separation * separation_scale
        return cohesion + alignment + separation

    def _distance_weights(self, agent, neighbors, radius: float) -> list[float]:
        weights: list[float] = []
        for neighbor in neighbors:
            distance = float(np.linalg.norm(neighbor.pos - agent.pos))
            closeness = max(0.0, 1.0 - distance / max(radius, 1.0))
            weights.append((closeness + 0.2) / max(distance, 1.0))
        return weights

    def _cohesion(self, agent, neighbors, config) -> np.ndarray:
        weights = self._distance_weights(agent, neighbors, config.neighbor_radius)
        centroid = weighted_average([neighbor.pos for neighbor in neighbors], weights)
        desired = centroid - agent.pos
        if np.linalg.norm(desired) < 1e-8:
            return np.zeros(2, dtype=float)
        desired_velocity = normalize(desired) * agent.base_speed
        return desired_velocity - agent.vel

    def _alignment(self, agent, neighbors, config) -> np.ndarray:
        weights = self._distance_weights(agent, neighbors, config.neighbor_radius)
        mean_velocity = weighted_average([neighbor.vel for neighbor in neighbors], weights)
        desired_velocity = normalize(mean_velocity, fallback=agent.direction) * agent.base_speed
        return desired_velocity - agent.vel

    def _separation(self, agent, neighbors, config) -> np.ndarray:
        repel = np.zeros(2, dtype=float)
        for neighbor in neighbors:
            offset = agent.pos - neighbor.pos
            distance = float(np.linalg.norm(offset))
            if 0.0 < distance < config.separation_radius:
                direction = offset / distance
                repel += direction / max(distance, 1.0)

        if np.linalg.norm(repel) < 1e-8:
            return np.zeros(2, dtype=float)
        desired_velocity = normalize(repel) * agent.base_speed
        return desired_velocity - agent.vel
