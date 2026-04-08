"""Core splitting paradigm for fish-training stimuli."""

from __future__ import annotations

import numpy as np

from paradigms.base import BaseParadigm, ParadigmOutput
from utils.vectors import blend_factor, normalize


class SplittingParadigm(BaseParadigm):
    """T-maze-style center, stabilize, then split choreography."""

    PHASE_PROFILES = {
        "center": {
            "cohesion": 1.35,
            "alignment": 1.10,
            "separation": 0.82,
            "attractor": 1.55,
            "rotation": 0.08,
        },
        "stabilize": {
            "cohesion": 1.24,
            "alignment": 1.18,
            "separation": 0.88,
            "attractor": 1.05,
            "rotation": 0.36,
        },
        "split": {
            "cohesion": 1.05,
            "alignment": 1.02,
            "separation": 1.10,
            "attractor": 1.26,
            "rotation": 1.00,
        },
    }

    def __init__(self) -> None:
        self._smoothed_profile = self.PHASE_PROFILES["center"].copy()
        self._split_assigned = False
        self._rng = None

    def reset(self, config, rng) -> None:
        self._smoothed_profile = self.PHASE_PROFILES["center"].copy()
        self._split_assigned = False
        self._rng = rng
        for agent in getattr(config, "_transient_agents", []):
            agent.group = "school"

    def update(self, agents, time, global_state) -> ParadigmOutput:
        config = global_state["config"]
        dt = global_state["dt"]

        phase = self._phase_for_time(config, float(time))
        if phase == "split":
            if not self._split_assigned:
                self._assign_split_groups(agents, config)
        else:
            self._reset_to_school(agents)

        target_profile = self.PHASE_PROFILES[phase]
        alpha = blend_factor(dt, config.phase_smoothing_time)
        for key, value in target_profile.items():
            self._smoothed_profile[key] += (float(value) - self._smoothed_profile[key]) * alpha

        attractors = {
            "center": config.center_attractor,
            "left": config.left_attractor,
            "right": config.right_attractor,
        }
        external_forces = [
            self._external_force(agent, self._active_attractor(agent, phase, attractors), config)
            for agent in agents
        ]
        return ParadigmOutput(
            phase=phase,
            attractors=attractors,
            external_forces=external_forces,
            social_multipliers={
                "cohesion": self._smoothed_profile["cohesion"],
                "alignment": self._smoothed_profile["alignment"],
                "separation": self._smoothed_profile["separation"],
            },
            neighbor_mode="within_group" if phase == "split" else "all",
        )

    def _phase_for_time(self, config, time_seconds: float) -> str:
        if time_seconds < config.time_in_center:
            return "center"
        if time_seconds < config.time_to_split:
            return "stabilize"
        return "split"

    def _assign_split_groups(self, agents, config) -> None:
        if self._rng is None:
            return

        indices = np.arange(len(agents))
        self._rng.shuffle(indices)
        left_count = int(round(len(indices) * float(config.split_ratio)))
        left_cutoff = max(0, min(len(indices), left_count))

        for offset, agent_index in enumerate(indices):
            agents[int(agent_index)].group = "left" if offset < left_cutoff else "right"

        self._split_assigned = True

    def _reset_to_school(self, agents) -> None:
        self._split_assigned = False
        for agent in agents:
            agent.group = "school"

    def _active_attractor(self, agent, phase: str, attractors: dict[str, np.ndarray]) -> np.ndarray:
        if phase != "split":
            return attractors["center"]
        return attractors["left"] if agent.group == "left" else attractors["right"]

    def _external_force(self, agent, attractor: np.ndarray, config) -> np.ndarray:
        displacement = attractor - agent.position
        distance = float(np.linalg.norm(displacement))
        direction = normalize(displacement, fallback=agent.direction)

        # Strong, interpretable pull toward the active target with gentle tapering near the center.
        attract_scale = min(1.0, distance / max(config.size * 8.0, 1.0))
        attract_force = direction * float(config.attractor_strength) * self._smoothed_profile["attractor"] * attract_scale

        # Mandatory tangential rotation for realistic orbital motion around the attractor.
        radial_vector = agent.position - attractor
        tangent = np.array([-radial_vector[1], radial_vector[0]], dtype=float)
        tangent_direction = normalize(tangent, fallback=np.zeros(2, dtype=float))
        rotation_scale = min(1.0, distance / max(config.size * 6.0, 1.0))
        rotation_force = (
            tangent_direction
            * float(config.rotation_strength)
            * self._smoothed_profile["rotation"]
            * rotation_scale
        )

        return attract_force + rotation_force
