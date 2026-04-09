"""Configuration and defaults for the fish stimulus generator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np

from utils.vectors import clamp

MODEL_OPTIONS = (
    "Research Boids",
    "Vicsek Consensus",
    "Potential Field",
    "Hybrid Consensus",
)

SHAPE_OPTIONS = (
    "circle",
    "triangle",
    "square",
    "arrow",
)


@dataclass
class StimulusConfig:
    """User-controlled parameters for the deterministic stimulus generator."""

    video_duration: float = 10.0
    fps: int = 60
    output_width: int = 1280
    output_height: int = 720
    random_seed: int = 2024

    number_of_agents: int = 48
    model_type: str = "Hybrid Consensus"
    noise: float = 0.14
    speed: float = 132.0
    cohesion: float = 1.55
    alignment: float = 1.28
    separation: float = 1.18

    left_count: int | None = None
    right_count: int | None = None
    time_in_center: float = 2.8
    time_to_split: float = 5.0
    attractor_strength: float = 210.0
    rotation_strength: float = 18.0
    target_cluster_radius: float = 78.0
    center_attractor_x: float | None = None
    center_attractor_y: float | None = None
    left_attractor_x: float | None = None
    left_attractor_y: float | None = None
    right_attractor_x: float | None = None
    right_attractor_y: float | None = None

    size: float = 12.0
    shape: str = "triangle"

    background_color: str = "#F4FBFF"
    grid_enabled: bool = False
    landmark_enabled: bool = False
    grid_spacing: float = 96.0
    landmark_radius: float = 18.0
    landmark_left_x: float | None = None
    landmark_left_y: float | None = None
    landmark_right_x: float | None = None
    landmark_right_y: float | None = None

    initial_spread: float = 22.0
    neighbor_radius: float = 88.0
    separation_radius: float = 24.0
    max_force: float = 240.0
    max_turn_rate_deg: float = 320.0
    wall_margin: float = 52.0
    wall_strength: float = 200.0
    phase_smoothing_time: float = 0.28
    save_metadata_json: bool = True

    def __post_init__(self) -> None:
        self.validate()

    @property
    def dt(self) -> float:
        return 1.0 / float(self.fps)

    @property
    def total_frames(self) -> int:
        return max(1, int(round(float(self.video_duration) * float(self.fps))))

    @property
    def resolution(self) -> tuple[int, int]:
        return int(self.output_width), int(self.output_height)

    @property
    def arena_size(self) -> tuple[int, int]:
        return self.resolution

    @property
    def center_attractor(self) -> np.ndarray:
        return np.array([self.center_attractor_x, self.center_attractor_y], dtype=float)

    @property
    def left_attractor(self) -> np.ndarray:
        return np.array([self.left_attractor_x, self.left_attractor_y], dtype=float)

    @property
    def right_attractor(self) -> np.ndarray:
        return np.array([self.right_attractor_x, self.right_attractor_y], dtype=float)

    @property
    def landmark_left(self) -> np.ndarray:
        return np.array([self.landmark_left_x, self.landmark_left_y], dtype=float)

    @property
    def landmark_right(self) -> np.ndarray:
        return np.array([self.landmark_right_x, self.landmark_right_y], dtype=float)

    def copy(self) -> "StimulusConfig":
        return replace(self)

    def apply_layout_defaults(self, force: bool = False) -> None:
        """Fill in layout-dependent defaults, optionally overwriting current values."""
        width = float(self.output_width)
        height = float(self.output_height)

        if force or self.center_attractor_x is None:
            self.center_attractor_x = width * 0.50
        if force or self.center_attractor_y is None:
            self.center_attractor_y = height * 0.62

        if force or self.left_attractor_x is None:
            self.left_attractor_x = width * 0.31
        if force or self.left_attractor_y is None:
            self.left_attractor_y = height * 0.30

        if force or self.right_attractor_x is None:
            self.right_attractor_x = width * 0.69
        if force or self.right_attractor_y is None:
            self.right_attractor_y = height * 0.30

        if force or self.landmark_left_x is None:
            self.landmark_left_x = width * 0.24
        if force or self.landmark_left_y is None:
            self.landmark_left_y = height * 0.22

        if force or self.landmark_right_x is None:
            self.landmark_right_x = width * 0.76
        if force or self.landmark_right_y is None:
            self.landmark_right_y = height * 0.22

    def validate(self) -> "StimulusConfig":
        """Normalize the configuration so it is safe to simulate and render."""
        self.video_duration = max(0.1, float(self.video_duration))
        self.fps = max(1, int(self.fps))
        self.output_width = max(160, int(self.output_width))
        self.output_height = max(120, int(self.output_height))
        self.random_seed = int(self.random_seed)

        self.number_of_agents = max(2, int(self.number_of_agents))
        self.noise = clamp(float(self.noise), 0.0, 2.0)
        self.speed = max(1.0, float(self.speed))
        self.cohesion = max(0.0, float(self.cohesion))
        self.alignment = max(0.0, float(self.alignment))
        self.separation = max(0.0, float(self.separation))

        self.left_count, self.right_count = self._normalize_split_counts()
        self.time_in_center = max(0.0, float(self.time_in_center))
        self.time_to_split = max(self.time_in_center + self.dt, float(self.time_to_split))
        self.attractor_strength = max(0.0, float(self.attractor_strength))
        self.rotation_strength = max(0.0, float(self.rotation_strength))

        self.size = max(2.0, float(self.size))
        self.target_cluster_radius = clamp(
            float(self.target_cluster_radius),
            max(self.size * 3.0, 24.0),
            min(float(self.output_width), float(self.output_height)) * 0.48,
        )

        self.shape = self.shape if self.shape in SHAPE_OPTIONS else "triangle"
        self.model_type = self.model_type if self.model_type in MODEL_OPTIONS else MODEL_OPTIONS[-1]

        self.grid_spacing = max(12.0, float(self.grid_spacing))
        self.landmark_radius = max(2.0, float(self.landmark_radius))
        self.initial_spread = max(0.0, float(self.initial_spread))
        self.neighbor_radius = max(10.0, float(self.neighbor_radius))
        self.separation_radius = clamp(float(self.separation_radius), 2.0, self.neighbor_radius)
        self.max_force = max(1.0, float(self.max_force))
        self.max_turn_rate_deg = max(1.0, float(self.max_turn_rate_deg))
        self.wall_margin = max(self.size + 2.0, float(self.wall_margin))
        self.wall_strength = max(0.0, float(self.wall_strength))
        self.phase_smoothing_time = max(0.01, float(self.phase_smoothing_time))

        self.apply_layout_defaults()
        return self

    def _normalize_split_counts(self) -> tuple[int, int]:
        if self.left_count is None and self.right_count is None:
            left_count = int(self.number_of_agents // 2)
            return left_count, int(self.number_of_agents - left_count)

        if self.left_count is None:
            right_count = int(self.right_count)
            if right_count < 0 or right_count > self.number_of_agents:
                raise ValueError("right_count must stay within the total number of agents")
            return int(self.number_of_agents - right_count), right_count

        if self.right_count is None:
            left_count = int(self.left_count)
            if left_count < 0 or left_count > self.number_of_agents:
                raise ValueError("left_count must stay within the total number of agents")
            return left_count, int(self.number_of_agents - left_count)

        left_count = int(self.left_count)
        right_count = int(self.right_count)
        if left_count < 0 or right_count < 0:
            raise ValueError("left_count and right_count must be non-negative")
        if left_count + right_count != self.number_of_agents:
            raise ValueError("left_count + right_count must equal number_of_agents")
        return left_count, right_count

    def to_dict(self) -> dict:
        self.validate()
        return asdict(self)
