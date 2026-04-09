"""Deterministic simulation engine for fish-training stimuli."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from agents import FishAgent
from models import build_model
from paradigms import BaseParadigm, SplittingParadigm
from utils.config import StimulusConfig
from utils.vectors import normalize, vector_from_angle


@dataclass
class RenderAgent:
    """Render-friendly snapshot of a single fish."""

    position: np.ndarray
    heading: float
    group: str


@dataclass
class FrameState:
    """Render-ready snapshot for a single video frame."""

    frame_index: int
    time_seconds: float
    phase: str
    agents: list[RenderAgent]
    attractors: dict[str, np.ndarray]
    metrics: dict[str, float | int | str]


class StimulusEngine:
    """Own the agents, model, and paradigm for deterministic fixed-step simulation."""

    def __init__(self, config: StimulusConfig, paradigm: BaseParadigm | None = None):
        self.config = config.copy().validate()
        self.rng = np.random.default_rng(self.config.random_seed)
        self.model = build_model(self.config.model_type)
        self.paradigm = paradigm or SplittingParadigm()
        self.agents: list[FishAgent] = []
        self.phase = "center"
        self.frame_index = 0
        self.time_seconds = 0.0
        self.attractors = {
            "center": self.config.center_attractor,
            "left": self.config.left_attractor,
            "right": self.config.right_attractor,
        }
        self.metrics: dict[str, float | int | str] = {}
        self.reset()

    def reset(self) -> None:
        """Reset agents and paradigm to the same deterministic initial state."""
        self.config.validate()
        self.rng = np.random.default_rng(self.config.random_seed)
        self.model = build_model(self.config.model_type)
        self.paradigm.reset(self.config, self.rng)
        self.agents = self._initialize_agents()
        self.phase = "center"
        self.frame_index = 0
        self.time_seconds = 0.0
        self.attractors = {
            "center": self.config.center_attractor,
            "left": self.config.left_attractor,
            "right": self.config.right_attractor,
        }
        self._update_metrics()

    def step(self) -> None:
        """Advance the engine by one fixed timestep."""
        next_frame_index = self.frame_index + 1
        evaluation_time = next_frame_index * self.config.dt
        paradigm_output = self.paradigm.update(
            self.agents,
            evaluation_time,
            {"config": self.config, "dt": self.config.dt, "rng": self.rng},
        )

        neighbor_map = self._compute_neighbors(paradigm_output.neighbor_mode)
        for agent, neighbors, motion_command, external_force in zip(
            self.agents,
            neighbor_map,
            paradigm_output.motion_commands,
            paradigm_output.external_forces,
        ):
            noise_force = (
                agent.sample_noise(self.config.dt, self.rng)
                * float(self.config.noise)
                * float(motion_command.noise_scale)
                * float(self.config.max_force)
            )
            context = {
                "config": self.config,
                "dt": self.config.dt,
                "noise_force": noise_force,
                "target_speed": motion_command.target_speed,
                "social_multipliers": paradigm_output.social_multipliers,
            }
            model_force = self.model.compute_force(agent, neighbors, context)
            damping_force = -agent.velocity * float(motion_command.damping)
            total_force = model_force + external_force + damping_force + self._wall_force(agent)
            agent.integrate(
                total_force,
                self.config.dt,
                self.config,
                constant_speed=self.model.constant_speed,
                target_speed=motion_command.target_speed,
                min_speed=motion_command.min_speed,
            )

        self.phase = paradigm_output.phase
        self.attractors = paradigm_output.attractors
        self.time_seconds = evaluation_time
        self.frame_index = next_frame_index
        self._update_metrics()

    def current_frame(self) -> FrameState:
        """Return the current render-ready frame state."""
        return FrameState(
            frame_index=self.frame_index,
            time_seconds=self.time_seconds,
            phase=self.phase,
            agents=[
                RenderAgent(position=agent.position.copy(), heading=agent.heading, group=agent.group)
                for agent in self.agents
            ],
            attractors={name: value.copy() for name, value in self.attractors.items()},
            metrics=self.metrics.copy(),
        )

    def _initialize_agents(self) -> list[FishAgent]:
        center = self.config.center_attractor
        width, height = self.config.arena_size
        positions = center + self.rng.normal(0.0, self.config.initial_spread, size=(self.config.number_of_agents, 2))
        positions[:, 0] = np.clip(positions[:, 0], self.config.size + 1.0, width - self.config.size - 1.0)
        positions[:, 1] = np.clip(positions[:, 1], self.config.size + 1.0, height - self.config.size - 1.0)

        headings = -np.pi / 2.0 + self.rng.normal(0.0, 0.25, size=self.config.number_of_agents)
        speed_modulation = self.rng.uniform(0.88, 1.0, size=self.config.number_of_agents)
        velocities = np.asarray(
            [vector_from_angle(angle) * self.config.speed * speed for angle, speed in zip(headings, speed_modulation)],
            dtype=float,
        )
        return [FishAgent(index, positions[index], velocities[index]) for index in range(self.config.number_of_agents)]

    def run_until_time(self, target_time_seconds: float) -> FrameState:
        """Advance until the requested preview/export time and return the current frame."""
        target_time = max(0.0, float(target_time_seconds))
        target_frame = min(
            self.config.total_frames - 1,
            max(0, int(round(target_time * float(self.config.fps)))),
        )
        while self.frame_index < target_frame:
            self.step()
        return self.current_frame()

    def _compute_neighbors(self, neighbor_mode: str) -> list[list[FishAgent]]:
        radius = float(self.config.neighbor_radius)
        cell_size = max(radius, 1.0)
        grid: dict[tuple[int, int], list[int]] = {}

        for index, agent in enumerate(self.agents):
            cell = (int(agent.position[0] // cell_size), int(agent.position[1] // cell_size))
            grid.setdefault(cell, []).append(index)

        neighbors: list[list[FishAgent]] = [[] for _ in self.agents]
        for index, agent in enumerate(self.agents):
            cell_x = int(agent.position[0] // cell_size)
            cell_y = int(agent.position[1] // cell_size)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other_index in grid.get((cell_x + dx, cell_y + dy), []):
                        if other_index == index:
                            continue
                        other = self.agents[other_index]
                        if neighbor_mode == "within_group" and other.group != agent.group:
                            continue
                        distance = float(np.linalg.norm(other.position - agent.position))
                        if distance <= radius:
                            neighbors[index].append(other)
        return neighbors

    def _wall_force(self, agent: FishAgent) -> np.ndarray:
        margin = float(self.config.wall_margin)
        strength = float(self.config.wall_strength)
        width, height = self.config.arena_size
        steer = np.zeros(2, dtype=float)

        if agent.position[0] < margin:
            steer[0] += strength * (margin - agent.position[0]) / margin
        elif agent.position[0] > width - margin:
            steer[0] -= strength * (agent.position[0] - (width - margin)) / margin

        if agent.position[1] < margin:
            steer[1] += strength * (margin - agent.position[1]) / margin
        elif agent.position[1] > height - margin:
            steer[1] -= strength * (agent.position[1] - (height - margin)) / margin

        return steer

    def _update_metrics(self) -> None:
        if not self.agents:
            self.metrics = {
                "phase": self.phase,
                "elapsed_time": self.time_seconds,
                "avg_speed": 0.0,
                "polarization": 0.0,
                "spread": 0.0,
                "school_count": 0,
                "left_count": 0,
                "right_count": 0,
            }
            return

        positions = np.asarray([agent.position for agent in self.agents], dtype=float)
        velocities = np.asarray([agent.velocity for agent in self.agents], dtype=float)
        speeds = np.linalg.norm(velocities, axis=1)
        directions = np.asarray([normalize(velocity) for velocity in velocities], dtype=float)
        center_of_mass = np.mean(positions, axis=0)

        self.metrics = {
            "phase": self.phase,
            "elapsed_time": self.time_seconds,
            "avg_speed": float(np.mean(speeds)),
            "polarization": float(np.linalg.norm(np.mean(directions, axis=0))),
            "spread": float(np.mean(np.linalg.norm(positions - center_of_mass, axis=1))),
            "school_count": sum(1 for agent in self.agents if agent.group == "school"),
            "left_count": sum(1 for agent in self.agents if agent.group == "left"),
            "right_count": sum(1 for agent in self.agents if agent.group == "right"),
        }


def sample_preview_state(config: StimulusConfig, phase: str) -> FrameState:
    """Return a deterministic preview snapshot from the real simulation engine."""
    normalized_phase = phase if phase in {"center", "stabilize", "split"} else "split"
    engine = StimulusEngine(config)
    return engine.run_until_time(_preview_time_for_phase(engine.config, normalized_phase))


def _preview_time_for_phase(config: StimulusConfig, phase: str) -> float:
    if phase == "center":
        return max(config.dt, config.time_in_center * 0.55)

    if phase == "stabilize":
        stabilize_window = max(config.time_to_split - config.time_in_center, config.dt)
        return min(config.video_duration - config.dt, config.time_in_center + stabilize_window * 0.55)

    split_window = max(config.video_duration - config.time_to_split, config.dt)
    return min(config.video_duration - config.dt, config.time_to_split + min(1.6, split_window * 0.72))
