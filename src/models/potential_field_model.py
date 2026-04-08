"""Goal-directed flocking with smooth potential-field attraction."""

from __future__ import annotations

from boids_model import BoidsModel


class PotentialFieldModel(BoidsModel):
    """Blend local flocking with stronger attraction and orbital guidance."""

    name = "Potential Fields"

    def compute_force(self, agent, neighbors, global_state):
        local_force = self.local_boids_force(agent, neighbors, global_state)
        damped_attractor = global_state["attractor_force"] - 0.12 * agent.vel
        weights = global_state["weights"]
        return (
            local_force * weights["boids"] * 0.82
            + global_state["noise_force"] * weights["noise"] * 0.35
            + damped_attractor * weights["attractor"] * 1.45
            + global_state["rotation_force"] * weights["rotation"] * 1.10
        )
