"""State-based hybrid model for center, stabilize, and split phases."""

from __future__ import annotations

import numpy as np

from boids_model import BoidsModel


class HybridCognitiveModel(BoidsModel):
    """Switch local rules based on cognitive state and controller phase."""

    name = "Hybrid Cognitive"

    def compute_force(self, agent, neighbors, global_state) -> np.ndarray:
        self._update_state(agent, neighbors, global_state)
        weights = global_state["weights"]
        noise_force = global_state["noise_force"]
        attractor_force = global_state["attractor_force"]
        rotation_force = global_state["rotation_force"]

        if agent.state == "explore":
            local_force = self.local_boids_force(
                agent,
                neighbors,
                global_state,
                cohesion_scale=0.75,
                alignment_scale=0.35,
                separation_scale=1.05,
            )
            return (
                local_force * weights["boids"]
                + noise_force * weights["noise"] * 1.40
                + attractor_force * weights["attractor"] * 0.75
                + rotation_force * weights["rotation"] * 0.45
            )

        if agent.state == "converge":
            local_force = self.local_boids_force(
                agent,
                neighbors,
                global_state,
                cohesion_scale=1.55,
                alignment_scale=0.90,
                separation_scale=0.95,
            )
            return (
                local_force * weights["boids"]
                + noise_force * weights["noise"] * 0.35
                + attractor_force * weights["attractor"] * 1.10
                + rotation_force * weights["rotation"] * 1.05
            )

        local_force = self.local_boids_force(
            agent,
            neighbors,
            global_state,
            cohesion_scale=1.00,
            alignment_scale=1.00,
            separation_scale=1.05,
        )
        return (
            local_force * weights["boids"]
            + noise_force * weights["noise"] * 0.45
            + attractor_force * weights["attractor"] * 1.15
            + rotation_force * weights["rotation"] * 0.85
        )

    def _update_state(self, agent, neighbors, global_state) -> None:
        config = global_state["config"]
        controller_phase = global_state["phase_signal"]

        if controller_phase == "split" or global_state["elapsed_time"] >= config.time_to_split:
            if agent.group == "left":
                agent.state = "split_left"
            elif agent.group == "right":
                agent.state = "split_right"
            return

        if controller_phase == "stabilize" or len(neighbors) >= config.density_threshold:
            agent.state = "converge"
        else:
            agent.state = "explore"
