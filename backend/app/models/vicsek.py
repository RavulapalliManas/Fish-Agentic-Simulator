"""Vicsek-inspired consensus model."""

from __future__ import annotations

import numpy as np

from models.base import BaseModel
from utils.vectors import normalize


class VicsekConsensusModel(BaseModel):
    """Constant-speed angular consensus with low-frequency noise."""

    name = "Vicsek Consensus"
    constant_speed = True

    def compute_force(self, agent, neighbors, context) -> np.ndarray:
        config = context["config"]
        multipliers = context["social_multipliers"]
        target_speed = float(context["target_speed"])
        current_direction = agent.direction

        if neighbors:
            neighbor_directions = [normalize(neighbor.velocity, fallback=current_direction) for neighbor in neighbors]
            consensus_direction = normalize(np.mean(np.asarray(neighbor_directions), axis=0), fallback=current_direction)
        else:
            consensus_direction = current_direction

        cohesion = np.zeros(2, dtype=float)
        if neighbors:
            centroid = np.mean(np.asarray([neighbor.position for neighbor in neighbors], dtype=float), axis=0)
            cohesion = normalize(centroid - agent.position, fallback=current_direction) * target_speed - agent.velocity

        separation = np.zeros(2, dtype=float)
        for neighbor in neighbors:
            offset = agent.position - neighbor.position
            distance = float(np.linalg.norm(offset))
            if 0.0 < distance < config.separation_radius:
                separation += offset / max(distance ** 2, 1.0)

        consensus_force = consensus_direction * target_speed - agent.velocity
        if np.linalg.norm(separation) > 1e-8:
            separation = normalize(separation, fallback=current_direction) * target_speed - agent.velocity

        return (
            consensus_force * config.alignment * multipliers["alignment"]
            + cohesion * config.cohesion * 0.35 * multipliers["cohesion"]
            + separation * config.separation * multipliers["separation"]
            + context["noise_force"] * 0.70
        )
