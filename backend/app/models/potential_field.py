"""Potential-field model for strong grouping and gentle split guidance."""

from __future__ import annotations

import numpy as np

from models.boids import ResearchBoidsModel
from utils.vectors import normalize


class PotentialFieldModel(ResearchBoidsModel):
    """Smooth gradient-based flocking with stronger long-range cohesion."""

    name = "Potential Field"

    def compute_force(self, agent, neighbors, context) -> np.ndarray:
        config = context["config"]
        multipliers = context["social_multipliers"]
        target_speed = float(context["target_speed"])
        if not neighbors:
            return context["noise_force"] * 0.45

        centroid = np.mean(np.asarray([neighbor.position for neighbor in neighbors], dtype=float), axis=0)
        long_range_pull = normalize(centroid - agent.position, fallback=agent.direction) * target_speed - agent.velocity

        repel = np.zeros(2, dtype=float)
        for neighbor in neighbors:
            offset = agent.position - neighbor.position
            distance = float(np.linalg.norm(offset))
            if distance > 0.0:
                repel += offset / max(distance ** 1.7, 1.0)

        repulsion = np.zeros(2, dtype=float)
        if np.linalg.norm(repel) > 1e-8:
            repulsion = normalize(repel, fallback=agent.direction) * target_speed - agent.velocity

        alignment = self._alignment(agent, neighbors, config, target_speed)
        return (
            long_range_pull * config.cohesion * 1.35 * multipliers["cohesion"]
            + alignment * config.alignment * 0.90 * multipliers["alignment"]
            + repulsion * config.separation * 1.05 * multipliers["separation"]
            + context["noise_force"] * 0.45
        )
