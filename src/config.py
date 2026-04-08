"""Configuration objects and defaults for the fish simulator."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

MODEL_OPTIONS = (
    "Enhanced Boids",
    "Active Matter",
    "Potential Fields",
    "Hybrid Cognitive",
)

AGENT_SHAPES = (
    "circle",
    "triangle",
    "square",
    "arrow",
)


@dataclass
class SimulationConfig:
    """User-facing parameters shared by the controller, models, and GUI."""

    arena_width: int = 900
    arena_height: int = 620
    fps: int = 60
    agent_count: int = 40
    agent_size: int = 8
    agent_shape: str = "triangle"
    initial_spread: float = 28.0
    speed: float = 2.2
    speed_std: float = 0.25
    cohesion: float = 0.95
    alignment: float = 1.05
    separation: float = 1.70
    noise: float = 0.30
    persistence: float = 0.84
    attractor_strength: float = 0.72
    rotation_strength: float = 0.48
    split_ratio: float = 0.70
    time_in_center: float = 5.0
    time_to_split: float = 10.0
    neighbor_radius: float = 95.0
    separation_radius: float = 26.0
    max_force: float = 0.18
    max_turn_degrees: float = 14.0
    soft_speed_gain: float = 0.16
    wall_margin: float = 62.0
    wall_strength: float = 1.10
    density_threshold: int = 8
    phase_smoothing: float = 0.09
    split_offset: float = 220.0
    trail_length: int = 18
    show_trails: bool = True
    show_center_of_mass: bool = True
    model_name: str = "Hybrid Cognitive"
    auto_start: bool = False

    @property
    def arena_size(self) -> tuple[int, int]:
        return self.arena_width, self.arena_height

    @property
    def center(self) -> np.ndarray:
        return np.array([self.arena_width / 2.0, self.arena_height / 2.0], dtype=float)

    @property
    def split_time(self) -> float:
        """Compatibility alias for older model code."""
        return self.time_to_split

    def copy(self) -> "SimulationConfig":
        return replace(self)


DEFAULT_CONFIG = SimulationConfig()


def generate_initial_positions(
    count: int,
    center: np.ndarray,
    spread: float,
    rng: np.random.Generator,
) -> list[np.ndarray]:
    """Create a compact starting school near the arena center."""
    positions: list[np.ndarray] = []
    for _ in range(count):
        offset = rng.normal(0.0, spread, size=2)
        positions.append(np.asarray(center, dtype=float) + offset)
    return positions
