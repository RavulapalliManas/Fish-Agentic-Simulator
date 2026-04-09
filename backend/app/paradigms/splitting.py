"""Core splitting paradigm for deterministic collective-motion stimuli."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from paradigms.base import AgentMotionCommand, BaseParadigm, ParadigmOutput
from utils.vectors import blend_factor, clamp, normalize


@dataclass(frozen=True)
class PhaseProfile:
    """Behavioral targets that are smoothed across phase boundaries."""

    cohesion: float
    alignment: float
    separation: float
    attractor: float
    rotation: float
    restore: float
    noise: float
    speed: float
    min_speed: float
    damping: float
    arrival_speed: float
    arrival_damping: float


class SplittingParadigm(BaseParadigm):
    """Aggregation, stabilization, then deterministic left/right split."""

    PHASE_PROFILES = {
        "center": PhaseProfile(
            cohesion=1.24,
            alignment=1.16,
            separation=0.88,
            attractor=1.32,
            rotation=0.08,
            restore=1.08,
            noise=0.56,
            speed=0.96,
            min_speed=0.18,
            damping=0.16,
            arrival_speed=0.44,
            arrival_damping=0.42,
        ),
        "stabilize": PhaseProfile(
            cohesion=1.42,
            alignment=1.30,
            separation=0.76,
            attractor=1.18,
            rotation=0.02,
            restore=1.34,
            noise=0.14,
            speed=0.42,
            min_speed=0.06,
            damping=0.56,
            arrival_speed=0.12,
            arrival_damping=0.96,
        ),
        "split": PhaseProfile(
            cohesion=1.36,
            alignment=1.24,
            separation=0.84,
            attractor=1.36,
            rotation=0.0,
            restore=1.58,
            noise=0.12,
            speed=0.84,
            min_speed=0.06,
            damping=0.24,
            arrival_speed=0.16,
            arrival_damping=0.90,
        ),
    }

    def __init__(self) -> None:
        self._smoothed_profile = self._profile_to_dict(self.PHASE_PROFILES["center"])
        self._split_assigned = False
        self._assignment: dict[int, str] = {}

    def reset(self, config, rng) -> None:
        del rng
        self._smoothed_profile = self._profile_to_dict(self.PHASE_PROFILES["center"])
        self._split_assigned = False
        self._assignment = self._build_assignment(config)
        for agent in getattr(config, "_transient_agents", []):
            agent.group = "school"

    def update(self, agents, time, global_state) -> ParadigmOutput:
        config = global_state["config"]
        dt = global_state["dt"]

        phase = self._phase_for_time(config, float(time))
        if phase == "split":
            if not self._split_assigned:
                self._assign_split_groups(agents)
        else:
            self._reset_to_school(agents)

        target_profile = self._profile_to_dict(self.PHASE_PROFILES[phase])
        alpha = blend_factor(dt, config.phase_smoothing_time)
        for key, value in target_profile.items():
            self._smoothed_profile[key] += (float(value) - self._smoothed_profile[key]) * alpha

        attractors = {
            "center": config.center_attractor,
            "left": config.left_attractor,
            "right": config.right_attractor,
        }
        motion_commands = [
            self._motion_command(agent, self._active_attractor(agent, phase, attractors), config)
            for agent in agents
        ]
        external_forces = [
            self._external_force(agent, self._active_attractor(agent, phase, attractors), config)
            for agent in agents
        ]
        return ParadigmOutput(
            phase=phase,
            attractors=attractors,
            external_forces=external_forces,
            motion_commands=motion_commands,
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

    def _build_assignment(self, config) -> dict[int, str]:
        ordered_ids = np.random.default_rng(config.random_seed + 17).permutation(config.number_of_agents).tolist()
        left_ids = {int(agent_id) for agent_id in ordered_ids[: config.left_count]}
        return {
            agent_id: "left" if agent_id in left_ids else "right"
            for agent_id in range(config.number_of_agents)
        }

    def _assign_split_groups(self, agents) -> None:
        for agent in agents:
            agent.group = self._assignment.get(agent.id, "right")
        self._split_assigned = True

    def _reset_to_school(self, agents) -> None:
        self._split_assigned = False
        for agent in agents:
            agent.group = "school"

    def _active_attractor(self, agent, phase: str, attractors: dict[str, np.ndarray]) -> np.ndarray:
        if phase != "split":
            return attractors["center"]
        return attractors["left"] if agent.group == "left" else attractors["right"]

    def _motion_command(self, agent, attractor: np.ndarray, config) -> AgentMotionCommand:
        distance = float(np.linalg.norm(attractor - agent.position))
        arrival_band = max(config.target_cluster_radius * 1.9, config.size * 8.0)
        far_ratio = clamp(distance / arrival_band, 0.0, 1.0)
        target_speed_scale = self._smoothed_profile["arrival_speed"] + (
            self._smoothed_profile["speed"] - self._smoothed_profile["arrival_speed"]
        ) * far_ratio
        damping = self._smoothed_profile["arrival_damping"] + (
            self._smoothed_profile["damping"] - self._smoothed_profile["arrival_damping"]
        ) * far_ratio
        noise_scale = self._smoothed_profile["noise"] * (0.38 + 0.62 * far_ratio)
        min_speed = float(config.speed) * self._smoothed_profile["min_speed"] * (0.45 + 0.55 * far_ratio)

        return AgentMotionCommand(
            target_speed=float(config.speed) * target_speed_scale,
            min_speed=min_speed,
            noise_scale=noise_scale,
            damping=damping,
        )

    def _external_force(self, agent, attractor: np.ndarray, config) -> np.ndarray:
        displacement = attractor - agent.position
        distance = float(np.linalg.norm(displacement))
        direction = normalize(displacement, fallback=agent.direction)

        attract_scale = min(1.0, distance / max(config.target_cluster_radius * 1.35, config.size * 6.0))
        attract_force = direction * float(config.attractor_strength) * self._smoothed_profile["attractor"] * attract_scale

        overflow = max(0.0, distance - float(config.target_cluster_radius))
        restore_force = np.zeros(2, dtype=float)
        if overflow > 0.0:
            overflow_ratio = overflow / max(float(config.target_cluster_radius), 1.0)
            restore_force = (
                direction
                * float(config.attractor_strength)
                * self._smoothed_profile["restore"]
                * overflow_ratio
                * overflow_ratio
            )

        tangent_force = np.zeros(2, dtype=float)
        if self._smoothed_profile["rotation"] > 0.0 and distance > config.target_cluster_radius * 0.5:
            radial_vector = agent.position - attractor
            tangent = np.array([-radial_vector[1], radial_vector[0]], dtype=float)
            tangent_direction = normalize(tangent, fallback=np.zeros(2, dtype=float))
            tangent_scale = clamp(
                (distance - config.target_cluster_radius * 0.5) / max(config.target_cluster_radius, 1.0),
                0.0,
                1.0,
            )
            tangent_force = (
                tangent_direction
                * float(config.rotation_strength)
                * self._smoothed_profile["rotation"]
                * tangent_scale
            )

        return attract_force + restore_force + tangent_force

    def _profile_to_dict(self, profile: PhaseProfile) -> dict[str, float]:
        return {
            "cohesion": profile.cohesion,
            "alignment": profile.alignment,
            "separation": profile.separation,
            "attractor": profile.attractor,
            "rotation": profile.rotation,
            "restore": profile.restore,
            "noise": profile.noise,
            "speed": profile.speed,
            "min_speed": profile.min_speed,
            "damping": profile.damping,
            "arrival_speed": profile.arrival_speed,
            "arrival_damping": profile.arrival_damping,
        }
