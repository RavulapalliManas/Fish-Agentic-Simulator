"""Static spatial luminance field for phototaxis / scototaxis (light-dark preference).

Time-invariant: the field is precomputed once in ``prepare`` and returned unchanged
every frame. ``profile`` selects how luminance ramps from ``low_lum`` to ``high_lum``
across the field. Combined with region masks (e.g. left/right hemifields) this also
builds split light/dark fields; a constant field (``low_lum == high_lum``) is the
degenerate case used as one half of such a split.

Spatial params are authored in degrees of visual angle (origin = screen centre,
+x right, +y down) and converted to pixels via ``geometry.deg_to_px``.
"""

from __future__ import annotations

import numpy as np

from ..geometry import DisplayGeometry
from .base import Stimulus


class LuminanceGradient(Stimulus):
    type = "gradient"

    def __init__(
        self,
        profile: str = "linear",
        axis_deg: float = 0.0,
        low_lum: float = 0.1,
        high_lum: float = 0.9,
        center_deg: tuple[float, float] = (0.0, 0.0),
        width_deg: float = 20.0,
    ) -> None:
        self.profile = str(profile)
        self.axis_deg = float(axis_deg)
        self.low_lum = float(low_lum)
        self.high_lum = float(high_lum)
        self.center_deg = (float(center_deg[0]), float(center_deg[1]))
        self.width_deg = float(width_deg)
        self._field: np.ndarray | None = None
        self._shape: tuple[int, int] | None = None

    def prepare(self, geometry, fps, n_frames, rng) -> None:
        self._build_field(geometry)

    def _build_field(self, geometry: DisplayGeometry) -> None:
        height, width = geometry.screen_h_px, geometry.screen_w_px
        xs = np.arange(width, dtype=np.float32) - width / 2.0
        ys = np.arange(height, dtype=np.float32) - height / 2.0
        grid_x, grid_y = np.meshgrid(xs, ys)
        cx = geometry.deg_to_px(self.center_deg[0])
        cy = geometry.deg_to_px(self.center_deg[1])
        span = self.high_lum - self.low_lum

        if self.profile == "radial":
            width_px = max(geometry.deg_to_px(self.width_deg), 1e-6)
            dist = np.sqrt((grid_x - cx) ** 2 + (grid_y - cy) ** 2)
            frac = np.clip(dist / width_px, 0.0, 1.0)
            field = self.low_lum + span * frac
        elif self.profile == "sigmoid":
            scale = max(geometry.deg_to_px(self.width_deg), 1e-6)
            theta = np.radians(self.axis_deg)
            proj = grid_x * np.cos(theta) + grid_y * np.sin(theta)
            proj_center = cx * np.cos(theta) + cy * np.sin(theta)
            field = self.low_lum + span / (1.0 + np.exp(-(proj - proj_center) / scale))
        else:  # "linear": ramp low->high along axis_deg across the field extent
            theta = np.radians(self.axis_deg)
            proj = grid_x * np.cos(theta) + grid_y * np.sin(theta)
            extent = float(proj.max() - proj.min())
            frac = (proj - proj.min()) / extent if extent > 0.0 else np.zeros_like(proj)
            field = self.low_lum + span * frac

        self._field = np.clip(field, 0.0, 1.0).astype(np.float32)
        self._shape = (height, width)

    def render(self, frame_index, t, geometry):
        if self._field is None:
            self._build_field(geometry)
        lum = self._field
        alpha = np.ones(self._shape, dtype=np.float32)
        return lum, alpha

    def validate(self, geometry, fps):
        return []

    def describe(self):
        return {
            "type": self.type,
            "profile": self.profile,
            "axis_deg": self.axis_deg,
            "low_lum": self.low_lum,
            "high_lum": self.high_lum,
            "center_deg": list(self.center_deg),
            "width_deg": self.width_deg,
        }
