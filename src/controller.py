"""Global simulation controller and phase logic."""

from __future__ import annotations

import time
from typing import Dict, List

import numpy as np

from agent import FishAgent
from boids_model import BoidsModel
from config import DEFAULT_CONFIG, MODEL_OPTIONS, SimulationConfig, generate_initial_positions
from models import HybridCognitiveModel, PotentialFieldModel, VicsekModel
from vector_utils import normalize

MODEL_REGISTRY = {
    MODEL_OPTIONS[0]: BoidsModel,
    MODEL_OPTIONS[1]: VicsekModel,
    MODEL_OPTIONS[2]: PotentialFieldModel,
    MODEL_OPTIONS[3]: HybridCognitiveModel,
}


class SimulationController:
    """Owns the agent list, simulation state, timing, and force blending."""

    PHASE_FORCE_TARGETS = {
        "center": {"boids": 0.78, "noise": 0.22, "attractor": 0.95, "rotation": 0.18},
        "stabilize": {"boids": 0.98, "noise": 0.14, "attractor": 0.72, "rotation": 0.95},
        "split": {"boids": 1.00, "noise": 0.10, "attractor": 0.88, "rotation": 0.62},
    }

    def __init__(self, config: SimulationConfig | None = None):
        self.config = config or DEFAULT_CONFIG.copy()
        self.rng = np.random.default_rng()
        self.dt = 1.0
        self.frame = 0
        self.elapsed_time = 0.0
        self.phase = "center"
        self.phase_signal = "center"
        self.simulation_state = "stopped"
        self.weights = self.PHASE_FORCE_TARGETS["center"].copy()
        self.attractors = self._build_attractors()
        self.model = self._create_model(self.config.model_name)
        self.split_assigned = False
        self.start_time: float | None = None
        self.pause_started_at: float | None = None
        self.paused_duration = 0.0
        self.agents: List[FishAgent] = []
        self.metrics: Dict[str, float | int | np.ndarray | str] = {}
        self.reset()

    @property
    def frame_delay_ms(self) -> int:
        return max(1, int(round(1000 / self.config.fps)))

    def start(self, current_time: float | None = None) -> None:
        """Start or resume the simulation."""
        if self.simulation_state == "running":
            return

        timestamp = self._resolve_time(current_time)
        if self.simulation_state == "stopped" or self.start_time is None:
            self.start_time = timestamp
            self.paused_duration = 0.0
            self.elapsed_time = 0.0
        elif self.simulation_state == "paused" and self.pause_started_at is not None:
            self.paused_duration += timestamp - self.pause_started_at

        self.pause_started_at = None
        self.simulation_state = "running"
        self._update_metrics()

    def pause(self, current_time: float | None = None) -> None:
        """Pause the simulation without resetting positions."""
        if self.simulation_state != "running":
            return
        self.pause_started_at = self._resolve_time(current_time)
        self.simulation_state = "paused"
        self._update_metrics()

    def reset(self) -> None:
        """Reinitialize the simulation and return to the stopped state."""
        self.sync_live_config()
        self.model = self._create_model(self.config.model_name)
        self.model.reset()
        self.phase = "center"
        self.phase_signal = "center"
        self.weights = self.PHASE_FORCE_TARGETS["center"].copy()
        self.frame = 0
        self.elapsed_time = 0.0
        self.simulation_state = "stopped"
        self.split_assigned = False
        self.start_time = None
        self.pause_started_at = None
        self.paused_duration = 0.0

        positions = generate_initial_positions(
            self.config.agent_count,
            self.config.center,
            self.config.initial_spread,
            self.rng,
        )
        self.agents = [FishAgent(agent_id=index, position=pos, rng=self.rng, config=self.config) for index, pos in enumerate(positions)]
        self.sync_live_config()
        self._update_metrics()

    def step(self, current_time: float | None = None) -> bool:
        """Advance the simulation by one frame if it is running."""
        if self.simulation_state != "running":
            return False

        self.sync_live_config()
        self.elapsed_time = self._elapsed_from_clock(current_time)
        self._update_phase()
        self._smooth_force_weights()

        neighbors_map = self._compute_neighbors()
        average_density = float(np.mean([len(neighbors) for neighbors in neighbors_map])) if neighbors_map else 0.0

        for agent, neighbors in zip(self.agents, neighbors_map):
            context = self._build_agent_context(agent, average_density)
            total_force = self.model.compute_force(agent, neighbors, context)
            total_force += self._wall_force(agent)
            agent.update_physics(total_force, context)

        self.frame += 1
        self._update_metrics()
        return True

    def set_model(self, model_name: str) -> None:
        """Switch to another motion model without resetting the school."""
        self.config.model_name = model_name
        self.model = self._create_model(model_name)
        self.model.reset()

    def rescale_agent_speed(self, new_speed: float, old_speed: float) -> None:
        """Apply speed slider changes without forcing an immediate reset."""
        safe_old = max(old_speed, 0.1)
        scale = new_speed / safe_old
        for agent in self.agents:
            agent.base_speed = max(0.5, agent.base_speed * scale)
            agent.vel = agent.vel * scale

    def sync_live_config(self) -> None:
        """Apply non-destructive live config changes to existing agents."""
        self.config.agent_shape = str(self.config.agent_shape).lower()
        self.config.time_to_split = max(self.config.time_to_split, self.config.time_in_center + 0.1)
        self.attractors = self._build_attractors()
        for agent in self.agents:
            agent.apply_appearance(self.config.agent_size, self.config.agent_shape)

    def _create_model(self, model_name: str):
        model_class = MODEL_REGISTRY.get(model_name, HybridCognitiveModel)
        return model_class()

    def _resolve_time(self, current_time: float | None) -> float:
        return float(time.perf_counter() if current_time is None else current_time)

    def _elapsed_from_clock(self, current_time: float | None) -> float:
        if self.start_time is None:
            return 0.0
        return max(0.0, self._resolve_time(current_time) - self.start_time - self.paused_duration)

    def _compute_neighbors(self) -> List[List[FishAgent]]:
        neighbors: List[List[FishAgent]] = [[] for _ in self.agents]
        radius = float(self.config.neighbor_radius)

        for index, agent in enumerate(self.agents):
            for other_index in range(index + 1, len(self.agents)):
                other = self.agents[other_index]
                if not self._share_local_group(agent, other):
                    continue

                distance = float(np.linalg.norm(agent.pos - other.pos))
                if distance <= radius:
                    neighbors[index].append(other)
                    neighbors[other_index].append(agent)

        return neighbors

    def _share_local_group(self, first: FishAgent, second: FishAgent) -> bool:
        if self.phase != "split":
            return True
        return first.group == second.group

    def _update_phase(self) -> None:
        if self.elapsed_time < self.config.time_in_center:
            self.phase = "center"
            self.phase_signal = "center"
            return

        if self.elapsed_time < self.config.time_to_split:
            self.phase = "stabilize"
            self.phase_signal = "stabilize"
            return

        self.phase = "split"
        self.phase_signal = "split"
        if not self.split_assigned:
            self._assign_split_groups()

    def _assign_split_groups(self) -> None:
        indices = list(range(len(self.agents)))
        self.rng.shuffle(indices)
        left_count = int(round(len(indices) * self.config.split_ratio))

        for offset, agent_index in enumerate(indices):
            agent = self.agents[agent_index]
            if offset < left_count:
                agent.group = "left"
                agent.state = "split_left"
            else:
                agent.group = "right"
                agent.state = "split_right"

        self.split_assigned = True

    def _smooth_force_weights(self) -> None:
        target = self.PHASE_FORCE_TARGETS[self.phase]
        alpha = float(np.clip(self.config.phase_smoothing, 0.01, 1.0))
        for key, goal in target.items():
            self.weights[key] += (goal - self.weights[key]) * alpha

    def _build_agent_context(self, agent: FishAgent, average_density: float) -> dict:
        attractor_position = self._current_attractor(agent)
        return {
            "config": self.config,
            "dt": self.dt,
            "bounds": self.config.arena_size,
            "elapsed_time": self.elapsed_time,
            "phase": self.phase,
            "phase_signal": self.phase_signal,
            "weights": self.weights,
            "rng": self.rng,
            "average_density": average_density,
            "noise_force": agent.sample_noise(self.rng) * self.config.noise,
            "attractor_force": self._attractor_force(agent, attractor_position),
            "rotation_force": self._rotation_force(agent, attractor_position),
            "current_attractor": attractor_position,
            "constant_speed": getattr(self.model, "constant_speed", False),
            "speed_override": agent.base_speed,
        }

    def _current_attractor(self, agent: FishAgent) -> np.ndarray:
        if self.phase == "split":
            return self.attractors["left" if agent.group == "left" else "right"]
        return self.attractors["center"]

    def _attractor_force(self, agent: FishAgent, attractor_position: np.ndarray) -> np.ndarray:
        displacement = attractor_position - agent.pos
        scale = max(self.config.split_offset, 1.0)
        return displacement / scale * self.config.attractor_strength

    def _rotation_force(self, agent: FishAgent, attractor_position: np.ndarray) -> np.ndarray:
        """Apply a tangential force so fish orbit smoothly around active attractors."""
        radial_vector = agent.pos - attractor_position
        tangent = np.array([-radial_vector[1], radial_vector[0]], dtype=float)
        tangent_direction = normalize(tangent)
        radial_distance = float(np.linalg.norm(radial_vector))
        if radial_distance < 1e-8:
            return np.zeros(2, dtype=float)

        # Taper the force near the attractor so orbits stay smooth instead of twitchy.
        orbit_ramp = min(radial_distance / max(self.config.agent_size * 6.0, 1.0), 1.0)
        return tangent_direction * self.config.rotation_strength * orbit_ramp

    def _wall_force(self, agent: FishAgent) -> np.ndarray:
        margin = float(self.config.wall_margin)
        strength = float(self.config.wall_strength)
        width, height = self.config.arena_size

        steer = np.zeros(2, dtype=float)
        if agent.pos[0] < margin:
            steer[0] += strength * (margin - agent.pos[0]) / margin
        if agent.pos[0] > width - margin:
            steer[0] -= strength * (agent.pos[0] - (width - margin)) / margin
        if agent.pos[1] < margin:
            steer[1] += strength * (margin - agent.pos[1]) / margin
        if agent.pos[1] > height - margin:
            steer[1] -= strength * (agent.pos[1] - (height - margin)) / margin

        return steer

    def _build_attractors(self) -> Dict[str, np.ndarray]:
        center = self.config.center
        left = np.array([center[0] - self.config.split_offset, center[1]], dtype=float)
        right = np.array([center[0] + self.config.split_offset, center[1]], dtype=float)
        return {"center": center, "left": left, "right": right}

    def _update_metrics(self) -> None:
        if not self.agents:
            self.metrics = {
                "simulation_state": self.simulation_state,
                "phase": self.phase,
                "elapsed_time": self.elapsed_time,
                "avg_speed": 0.0,
                "polarization": 0.0,
                "spread": 0.0,
                "school_count": 0,
                "left_count": 0,
                "right_count": 0,
                "center_of_mass": self.config.center,
            }
            return

        positions = np.asarray([agent.pos for agent in self.agents], dtype=float)
        velocities = np.asarray([agent.vel for agent in self.agents], dtype=float)
        speeds = np.linalg.norm(velocities, axis=1)
        directions = np.asarray([normalize(velocity) for velocity in velocities], dtype=float)
        center_of_mass = np.mean(positions, axis=0)

        school_count = sum(1 for agent in self.agents if agent.group == "school")
        left_count = sum(1 for agent in self.agents if agent.group == "left")
        right_count = sum(1 for agent in self.agents if agent.group == "right")

        self.metrics = {
            "simulation_state": self.simulation_state,
            "phase": self.phase,
            "elapsed_time": self.elapsed_time,
            "avg_speed": float(np.mean(speeds)),
            "polarization": float(np.linalg.norm(np.mean(directions, axis=0))),
            "spread": float(np.mean(np.linalg.norm(positions - center_of_mass, axis=1))),
            "school_count": school_count,
            "left_count": left_count,
            "right_count": right_count,
            "center_of_mass": center_of_mass,
        }
