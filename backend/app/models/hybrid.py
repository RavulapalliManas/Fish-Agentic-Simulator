"""Hybrid consensus model for stable, experiment-friendly splits."""

from __future__ import annotations

import numpy as np

from models.boids import ResearchBoidsModel
from utils.vectors import normalize


class HybridConsensusModel(ResearchBoidsModel):
    """Blend centroid, velocity consensus, and mild noise for clean branching."""

    name = "Hybrid Consensus"

    def compute_force(self, agent, neighbors, context) -> np.ndarray:
        config = context["config"]
        multipliers = context["social_multipliers"]
        target_speed = float(context["target_speed"])
        boids_force = super().compute_force(agent, neighbors, context)

        if neighbors:
            headings = [normalize(neighbor.velocity, fallback=agent.direction) for neighbor in neighbors]
            consensus = normalize(np.mean(np.asarray(headings), axis=0), fallback=agent.direction)
        else:
            consensus = agent.direction

        consensus_force = consensus * target_speed - agent.velocity
        return boids_force * 0.78 + consensus_force * config.alignment * 0.42 * multipliers["alignment"]
