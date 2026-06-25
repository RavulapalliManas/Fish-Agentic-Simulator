"""Moving bar / edge sweeping across the field."""

from __future__ import annotations

import numpy as np

from ..geometry import DisplayGeometry
from .base import Stimulus


class MovingBar(Stimulus):
    type = "bar"

    def __init__(
        self,
        width_deg: float,
        speed_dps: float,
        direction_deg: float,
        contrast: float = 1.0,
        mean_lum: float = 0.5,
        polarity: str = "dark",
        start_offset_deg: float = 0.0,
    ) -> None:
        self.width_deg = float(width_deg)
        self.speed_dps = float(speed_dps)
        self.direction_deg = float(direction_deg)
        self.contrast = float(contrast)
        self.mean_lum = float(mean_lum)
        self.polarity = str(polarity)
        self.start_offset_deg = float(start_offset_deg)
        self._proj: np.ndarray | None = None
        self._proj_min = 0.0
        self._shape: tuple[int, int] | None = None

    def prepare(self, geometry, fps, n_frames, rng) -> None:
        self._build_proj(geometry)

    def _build_proj(self, geometry: DisplayGeometry) -> None:
        height, width = geometry.screen_h_px, geometry.screen_w_px
        xs = np.arange(width, dtype=np.float32)
        ys = np.arange(height, dtype=np.float32)
        grid_x, grid_y = np.meshgrid(xs, ys)
        theta = np.radians(self.direction_deg)
        proj = grid_x * np.cos(theta) + grid_y * np.sin(theta)
        self._proj = proj.astype(np.float32)
        self._proj_min = float(proj.min())
        self._shape = (height, width)

    def render(self, frame_index, t, geometry):
        if self._proj is None:
            self._build_proj(geometry)
        half = geometry.deg_to_px(self.width_deg) / 2.0
        start = self._proj_min - half - geometry.deg_to_px(self.start_offset_deg)
        center = start + geometry.deg_to_px(self.speed_dps) * float(t)
        alpha = (np.abs(self._proj - center) <= half).astype(np.float32)
        bar = self.mean_lum * (1.0 - self.contrast) if self.polarity == "dark" else self.mean_lum * (1.0 + self.contrast)
        bar = float(np.clip(bar, 0.0, 1.0))
        lum = np.full(self._shape, bar, dtype=np.float32)
        return lum, alpha

    def describe(self):
        return {
            "type": self.type,
            "width_deg": self.width_deg,
            "speed_dps": self.speed_dps,
            "direction_deg": self.direction_deg,
            "contrast": self.contrast,
            "mean_lum": self.mean_lum,
            "polarity": self.polarity,
            "start_offset_deg": self.start_offset_deg,
        }
