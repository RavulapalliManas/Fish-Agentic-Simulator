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


@dataclass
class PreviewClip:
    """Lightweight preview sequence sampled from the deterministic engine."""

    phase: str
    preview_fps: int
    loop_duration_seconds: float
    preview_agent_count: int
    frames: list[FrameState]
    warnings: list[str]


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
        self._resolve_agent_overlaps(passes=6)
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
        self._resolve_agent_overlaps()
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
        positions = self._initial_positions(center, width, height)

        headings = -np.pi / 2.0 + self.rng.normal(0.0, 0.25, size=self.config.number_of_agents)
        speed_modulation = self.rng.uniform(0.88, 1.0, size=self.config.number_of_agents)
        velocities = np.asarray(
            [vector_from_angle(angle) * self.config.speed * speed for angle, speed in zip(headings, speed_modulation)],
            dtype=float,
        )
        return [FishAgent(index, positions[index], velocities[index]) for index in range(self.config.number_of_agents)]

    def _initial_positions(self, center: np.ndarray, width: int, height: int) -> np.ndarray:
        margin = float(self.config.size) + 1.0
        minimum_spacing = max(self.config.minimum_agent_spacing * 0.86, float(self.config.size) * 1.55)
        spread = max(float(self.config.initial_spread), minimum_spacing)
        positions: list[np.ndarray] = []

        for index in range(self.config.number_of_agents):
            placed = False
            for _ in range(96):
                candidate = center + self.rng.normal(0.0, spread, size=2)
                candidate[0] = np.clip(candidate[0], margin, width - margin)
                candidate[1] = np.clip(candidate[1], margin, height - margin)
                if all(float(np.linalg.norm(candidate - other)) >= minimum_spacing for other in positions):
                    positions.append(candidate)
                    placed = True
                    break

            if placed:
                continue

            fallback_angle = (2.0 * np.pi * index) / max(self.config.number_of_agents, 1)
            fallback_radius = minimum_spacing * (1.0 + 0.18 * (index // 8))
            candidate = center + vector_from_angle(fallback_angle) * fallback_radius
            candidate[0] = np.clip(candidate[0], margin, width - margin)
            candidate[1] = np.clip(candidate[1], margin, height - margin)
            positions.append(candidate)

        return np.asarray(positions, dtype=float)

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

    def _resolve_agent_overlaps(self, passes: int = 2) -> None:
        minimum_spacing = float(self.config.minimum_agent_spacing)
        if minimum_spacing <= 0.0 or len(self.agents) < 2:
            return

        cell_size = max(minimum_spacing, 1.0)
        within_group_only = self.phase == "split"
        for _ in range(max(1, passes)):
            grid: dict[tuple[int, int], list[int]] = {}
            for index, agent in enumerate(self.agents):
                cell = (int(agent.position[0] // cell_size), int(agent.position[1] // cell_size))
                grid.setdefault(cell, []).append(index)

            adjusted = False
            for index, agent in enumerate(self.agents):
                cell_x = int(agent.position[0] // cell_size)
                cell_y = int(agent.position[1] // cell_size)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for other_index in grid.get((cell_x + dx, cell_y + dy), []):
                            if other_index <= index:
                                continue
                            other = self.agents[other_index]
                            if within_group_only and other.group != agent.group:
                                continue
                            offset = agent.position - other.position
                            distance = float(np.linalg.norm(offset))
                            if distance >= minimum_spacing:
                                continue

                            if distance < 1e-8:
                                normal = vector_from_angle((2.0 * np.pi * (index + 1)) / max(len(self.agents), 1))
                                distance = 1.0
                            else:
                                normal = offset / distance

                            overlap = minimum_spacing - distance
                            correction = normal * (overlap * 0.5)
                            agent.position = agent.position + correction
                            other.position = other.position - correction
                            self._clip_agent_to_bounds(agent)
                            self._clip_agent_to_bounds(other)

                            relative_velocity = agent.velocity - other.velocity
                            normal_speed = float(np.dot(relative_velocity, normal))
                            if normal_speed < 0.0:
                                impulse = normal * (normal_speed * 0.5)
                                agent.velocity = agent.velocity - impulse
                                other.velocity = other.velocity + impulse
                            adjusted = True

            if not adjusted:
                break

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

    def _clip_agent_to_bounds(self, agent: FishAgent) -> None:
        width, height = self.config.arena_size
        margin = float(self.config.size) + 1.0
        agent.position[0] = float(np.clip(agent.position[0], margin, float(width) - margin))
        agent.position[1] = float(np.clip(agent.position[1], margin, float(height) - margin))

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


def build_preview_clip(config: StimulusConfig, phase: str) -> PreviewClip:
    """Return a short deterministic clip for the requested phase."""
    normalized_phase = phase if phase in {"center", "stabilize", "split"} else "split"
    preview_config = _preview_config(config)
    preview_engine = StimulusEngine(preview_config)
    start_time, end_time = _preview_window(preview_config, normalized_phase)

    sample_count = max(18, int(round((end_time - start_time) * float(preview_config.fps))) + 1)
    times = np.linspace(start_time, end_time, num=sample_count, endpoint=True)
    frames = [preview_engine.run_until_time(float(time_value)) for time_value in times]

    return PreviewClip(
        phase=normalized_phase,
        preview_fps=preview_config.fps,
        loop_duration_seconds=max(preview_config.dt, end_time - start_time),
        preview_agent_count=preview_config.number_of_agents,
        frames=frames,
        warnings=config.copy().validate().sanity_warnings(),
    )


def _preview_time_for_phase(config: StimulusConfig, phase: str) -> float:
    if phase == "center":
        return max(config.dt, config.time_in_center * 0.55)

    if phase == "stabilize":
        stabilize_window = max(config.time_to_split - config.time_in_center, config.dt)
        return min(config.video_duration - config.dt, config.time_in_center + stabilize_window * 0.55)

    split_window = max(config.video_duration - config.time_to_split, config.dt)
    return min(config.video_duration - config.dt, config.time_to_split + min(1.6, split_window * 0.72))


def _preview_config(config: StimulusConfig) -> StimulusConfig:
    preview_config = config.copy().validate()
    preview_total_agents = _preview_agent_count(preview_config.number_of_agents)
    preview_left, preview_right = _scaled_split_counts(preview_config, preview_total_agents)

    preview_config.number_of_agents = preview_total_agents
    preview_config.left_count = preview_left
    preview_config.right_count = preview_right
    preview_config.fps = int(max(16, min(preview_config.fps, 24)))
    preview_config.video_duration = max(preview_config.video_duration, preview_config.time_to_split + 2.0)
    preview_duration_cap = 18.0
    if preview_config.video_duration > preview_duration_cap:
        schedule_scale = preview_duration_cap / float(preview_config.video_duration)
        preview_config.time_in_center *= schedule_scale
        preview_config.time_to_split *= schedule_scale
        preview_config.video_duration = preview_duration_cap
    preview_config.save_metadata_json = False
    return preview_config.validate()


def _preview_agent_count(total_agents: int) -> int:
    if total_agents < 20:
        return total_agents
    return int(np.clip(total_agents, 20, 50))


def _scaled_split_counts(config: StimulusConfig, total_agents: int) -> tuple[int, int]:
    if total_agents == config.number_of_agents:
        return config.left_count, config.right_count

    if config.number_of_agents <= 0:
        return total_agents // 2, total_agents - (total_agents // 2)

    left_ratio = config.left_count / float(config.number_of_agents)
    left_count = int(round(total_agents * left_ratio))
    left_count = int(np.clip(left_count, 0, total_agents))

    if config.left_count > 0 and config.right_count > 0 and total_agents >= 2:
        left_count = int(np.clip(left_count, 1, total_agents - 1))

    return left_count, total_agents - left_count


def _preview_window(config: StimulusConfig, phase: str) -> tuple[float, float]:
    clip_duration = 4.0
    preview_floor = max(config.dt * 6.0, 1.2)

    if phase == "center":
        start_time = 0.0
        phase_end = max(start_time + config.dt, config.time_in_center - config.dt)
        end_time = min(phase_end, max(preview_floor, min(phase_end, clip_duration)))
        return start_time, max(start_time + config.dt, end_time)

    if phase == "stabilize":
        start_time = max(config.time_in_center, config.dt)
        phase_end = max(start_time + config.dt, config.time_to_split - config.dt)
        end_time = min(phase_end, max(start_time + preview_floor, min(phase_end, start_time + clip_duration)))
        return start_time, max(start_time + config.dt, end_time)

    start_time = max(config.time_to_split + config.dt, config.dt)
    end_time = min(config.video_duration - config.dt, max(start_time + preview_floor, min(config.video_duration, start_time + clip_duration)))
    return start_time, max(start_time + config.dt, end_time)
