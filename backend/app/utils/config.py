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


@dataclass(frozen=True)
class RecommendedRange:
    """Soft guidance shown to users when a value is technically valid but risky."""

    minimum: float
    maximum: float
    warning: str


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
    target_cluster_radius: float = 104.0
    center_attractor_x: float | None = None
    center_attractor_y: float | None = None
    left_attractor_x: float | None = None
    left_attractor_y: float | None = None
    right_attractor_x: float | None = None
    right_attractor_y: float | None = None

    size: float = 14.0
    shape: str = "circle"

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

    @property
    def minimum_agent_spacing(self) -> float:
        return max(float(self.size) * 1.8, float(self.separation_radius) * 1.05)

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
        self.video_duration = clamp(float(self.video_duration), 0.1, 60.0)
        self.fps = int(clamp(float(self.fps), 1.0, 120.0))
        self.output_width = int(clamp(float(self.output_width), 160.0, 3840.0))
        self.output_height = int(clamp(float(self.output_height), 120.0, 2160.0))
        self.random_seed = int(self.random_seed)

        self.number_of_agents = int(clamp(float(self.number_of_agents), 2.0, 240.0))
        self.noise = clamp(float(self.noise), 0.0, 1.2)
        self.speed = clamp(float(self.speed), 20.0, 240.0)
        self.cohesion = clamp(float(self.cohesion), 0.0, 4.0)
        self.alignment = clamp(float(self.alignment), 0.0, 4.0)
        self.separation = clamp(float(self.separation), 0.0, 4.0)

        self.left_count, self.right_count = self._normalize_split_counts()
        self.time_in_center = clamp(float(self.time_in_center), 0.0, self.video_duration - self.dt)
        self.time_to_split = clamp(float(self.time_to_split), self.time_in_center + self.dt, self.video_duration)
        self.attractor_strength = clamp(float(self.attractor_strength), 0.0, 480.0)
        self.rotation_strength = clamp(float(self.rotation_strength), 0.0, 120.0)

        self.size = clamp(float(self.size), 4.0, 40.0)
        self.target_cluster_radius = clamp(
            float(self.target_cluster_radius),
            max(self.size * 4.6, 42.0),
            min(float(self.output_width), float(self.output_height)) * 0.48,
        )

        self.shape = self.shape if self.shape in SHAPE_OPTIONS else "triangle"
        self.model_type = self.model_type if self.model_type in MODEL_OPTIONS else MODEL_OPTIONS[-1]

        self.grid_spacing = clamp(float(self.grid_spacing), 12.0, max(float(self.output_width), float(self.output_height)))
        self.landmark_radius = clamp(float(self.landmark_radius), 2.0, 120.0)
        self.initial_spread = clamp(float(self.initial_spread), self.size * 1.2, min(float(self.output_width), float(self.output_height)) * 0.35)
        self.neighbor_radius = clamp(float(self.neighbor_radius), 10.0, min(float(self.output_width), float(self.output_height)) * 0.48)
        self.separation_radius = clamp(float(self.separation_radius), max(6.0, self.size * 1.25), self.neighbor_radius)
        self.max_force = clamp(float(self.max_force), 1.0, 1200.0)
        self.max_turn_rate_deg = clamp(float(self.max_turn_rate_deg), 1.0, 720.0)
        self.wall_margin = clamp(float(self.wall_margin), self.size + 2.0, min(float(self.output_width), float(self.output_height)) * 0.45)
        self.wall_strength = clamp(float(self.wall_strength), 0.0, 800.0)
        self.phase_smoothing_time = clamp(float(self.phase_smoothing_time), 0.01, 3.0)

        self.apply_layout_defaults()
        return self

    def sanity_warnings(self) -> list[str]:
        """Return non-blocking warnings for extreme but technically valid settings."""
        warnings: list[str] = []
        recommended = self.recommended_ranges()

        for key, range_info in recommended.items():
            value = float(getattr(self, key))
            if value < range_info.minimum or value > range_info.maximum:
                warnings.append(range_info.warning)

        stabilize_window = float(self.time_to_split - self.time_in_center)
        if stabilize_window < 0.75:
            warnings.append(
                "Stabilization time is very short, so the shoal may begin splitting before the aggregation phase looks settled."
            )
        elif stabilize_window > 5.0:
            warnings.append(
                "Stabilization time is unusually long, which can make the split feel delayed and less interpretable."
            )

        split_window = float(self.video_duration - self.time_to_split)
        if split_window < 1.5:
            warnings.append(
                "The post-split observation window is short; increase video duration or move the split earlier to show stable branch formation."
            )

        horizontal_gap = abs(float(self.right_attractor_x - self.left_attractor_x))
        if horizontal_gap < self.output_width * 0.18:
            warnings.append(
                "The left and right attractors are close together, which can reduce visual separation between the two shoals."
            )

        recommended_packing_radius = float(self.size) * 0.9 * np.sqrt(float(self.number_of_agents) / 0.78)
        if float(self.target_cluster_radius) < recommended_packing_radius:
            warnings.append(
                "Dot size and shoal count are dense for the chosen split tightness; increase split tightness or reduce fish size to avoid visual crowding."
            )

        return _unique_strings(warnings)

    def recommended_ranges(self) -> dict[str, RecommendedRange]:
        """Recommended values for interpretable, biologically plausible stimuli."""
        cluster_max = min(float(self.output_width), float(self.output_height)) * 0.16
        return {
            "number_of_agents": RecommendedRange(
                minimum=16.0,
                maximum=96.0,
                warning="Shoal size is outside the recommended range; very small or very large groups can reduce interpretability in behavioral experiments.",
            ),
            "noise": RecommendedRange(
                minimum=0.04,
                maximum=0.24,
                warning="Noise level is outside the recommended range and may produce non-biological jitter or unusually rigid movement.",
            ),
            "speed": RecommendedRange(
                minimum=80.0,
                maximum=160.0,
                warning="Cruising speed is outside the recommended range and may make the fish look sluggish or unnaturally ballistic.",
            ),
            "cohesion": RecommendedRange(
                minimum=1.1,
                maximum=2.2,
                warning="Cohesion strength is outside the recommended range and may yield either diffuse clouds or unrealistically compressed shoals.",
            ),
            "alignment": RecommendedRange(
                minimum=0.95,
                maximum=1.8,
                warning="Alignment strength is outside the recommended range and may reduce coordinated group travel.",
            ),
            "separation": RecommendedRange(
                minimum=0.55,
                maximum=1.5,
                warning="Separation strength is outside the recommended range and may cause overlap or excessive spreading.",
            ),
            "neighbor_radius": RecommendedRange(
                minimum=48.0,
                maximum=112.0,
                warning="Neighbor radius is outside the recommended range and may make interactions too local or too diffuse.",
            ),
            "separation_radius": RecommendedRange(
                minimum=18.0,
                maximum=34.0,
                warning="Separation radius is outside the recommended range and may either compress the shoal too tightly or broaden it unnecessarily.",
            ),
            "target_cluster_radius": RecommendedRange(
                minimum=max(self.size * 6.2, 86.0),
                maximum=max(max(self.size * 8.6, 128.0), cluster_max),
                warning="Cluster radius is outside the recommended range and may crowd larger markers together or make the branches unnecessarily broad.",
            ),
            "size": RecommendedRange(
                minimum=12.0,
                maximum=18.0,
                warning="Dot size is outside the recommended range and may make the shoal hard to read or visually overcrowded.",
            ),
            "attractor_strength": RecommendedRange(
                minimum=160.0,
                maximum=280.0,
                warning="Attractor strength is outside the recommended range and may cause weak convergence or overly mechanical steering.",
            ),
            "rotation_strength": RecommendedRange(
                minimum=0.0,
                maximum=22.0,
                warning="Rotation strength is high enough to reintroduce circling around attractors.",
            ),
            "time_in_center": RecommendedRange(
                minimum=1.5,
                maximum=4.0,
                warning="Aggregation time is outside the recommended range and may make convergence feel rushed or overly prolonged.",
            ),
            "video_duration": RecommendedRange(
                minimum=6.0,
                maximum=16.0,
                warning="Video duration is outside the recommended range and may be too brief for interpretation or unnecessarily long for stimulus delivery.",
            ),
            "fps": RecommendedRange(
                minimum=24.0,
                maximum=60.0,
                warning="Frame rate is outside the recommended range and may reduce smoothness or create unnecessary compute cost.",
            ),
        }

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


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
