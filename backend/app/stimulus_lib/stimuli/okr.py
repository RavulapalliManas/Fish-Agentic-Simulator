"""Rigidly rotating grating about a center point (optokinetic response, OKR).

A sinusoidal or square-wave grating is sampled along an axis that rotates rigidly
about ``center_deg`` at ``angular_velocity_dps``. Unlike the drifting grating, the
carrier does not translate; the whole pattern spins, which is the canonical drive
for the optokinetic eye-tracking reflex. The centered grid is precomputed in
``prepare``; only the rotation angle depends on time, so ``render`` stays a pure
function of frame index / time.
"""

from __future__ import annotations

import numpy as np

from ..geometry import DisplayGeometry
from .base import Stimulus


class RotatingGrating(Stimulus):
    type = "okr"

    def __init__(
        self,
        spatial_freq_cpd: float,
        angular_velocity_dps: float,
        contrast: float = 1.0,
        center_deg: tuple[float, float] = (0.0, 0.0),
        initial_angle_deg: float = 0.0,
        mean_lum: float = 0.5,
        waveform: str = "sine",
    ) -> None:
        self.spatial_freq_cpd = float(spatial_freq_cpd)
        self.angular_velocity_dps = float(angular_velocity_dps)
        self.contrast = float(contrast)
        self.center_deg = (float(center_deg[0]), float(center_deg[1]))
        self.initial_angle_deg = float(initial_angle_deg)
        self.mean_lum = float(mean_lum)
        self.waveform = str(waveform)

        self._xc: np.ndarray | None = None
        self._yc: np.ndarray | None = None
        self._shape: tuple[int, int] | None = None

    def prepare(self, geometry, fps, n_frames, rng) -> None:
        self._build_grid(geometry)

    def _build_grid(self, geometry: DisplayGeometry) -> None:
        height, width = geometry.screen_h_px, geometry.screen_w_px
        cx = width / 2.0 + geometry.deg_to_px(self.center_deg[0])
        cy = height / 2.0 + geometry.deg_to_px(self.center_deg[1])
        xs = np.arange(width, dtype=np.float32)
        ys = np.arange(height, dtype=np.float32)
        grid_x, grid_y = np.meshgrid(xs, ys)
        self._xc = (grid_x - cx).astype(np.float32)
        self._yc = (grid_y - cy).astype(np.float32)
        self._shape = (height, width)

    def render(self, frame_index, t, geometry):
        if self._xc is None:
            self._build_grid(geometry)
        theta = np.radians(self.initial_angle_deg) + np.radians(self.angular_velocity_dps) * float(t)
        proj = self._xc * np.cos(theta) + self._yc * np.sin(theta)
        cyc_per_px = geometry.cpd_to_cyc_per_px(self.spatial_freq_cpd)
        angle = 2.0 * np.pi * cyc_per_px * proj
        carrier = np.sign(np.sin(angle)) if self.waveform == "square" else np.sin(angle)
        lum = self.mean_lum * (1.0 + self.contrast * carrier)
        lum = np.clip(lum, 0.0, 1.0).astype(np.float32)
        alpha = np.ones(self._shape, dtype=np.float32)
        return lum, alpha

    def validate(self, geometry, fps):
        errors = []
        cyc_per_px = geometry.cpd_to_cyc_per_px(self.spatial_freq_cpd)
        if cyc_per_px > 0.5:
            errors.append(
                f"okr spatial_freq {self.spatial_freq_cpd} cpd = {cyc_per_px:.3f} cyc/px exceeds the "
                f"Nyquist limit of 0.5 (display can resolve up to {geometry.max_cpd:.2f} cpd)."
            )
        height, width = geometry.screen_h_px, geometry.screen_w_px
        cx = width / 2.0 + geometry.deg_to_px(self.center_deg[0])
        cy = height / 2.0 + geometry.deg_to_px(self.center_deg[1])
        corners = ((0.0, 0.0), (width, 0.0), (0.0, height), (width, height))
        largest_radius_px = max(np.hypot(x - cx, y - cy) for x, y in corners)
        omega = abs(np.radians(self.angular_velocity_dps))
        rim_temporal_hz = omega * largest_radius_px * cyc_per_px
        if rim_temporal_hz >= 0.5 * float(fps):
            errors.append(
                f"okr rim temporal_freq {rim_temporal_hz:.3f} Hz at radius {largest_radius_px:.1f} px >= 0.5 "
                f"Nyquist at {fps} fps (rotation will alias at the rim); lower angular_velocity_dps "
                f"{self.angular_velocity_dps} or spatial_freq."
            )
        return errors

    def describe(self):
        return {
            "type": self.type,
            "spatial_freq_cpd": self.spatial_freq_cpd,
            "angular_velocity_dps": self.angular_velocity_dps,
            "contrast": self.contrast,
            "center_deg": list(self.center_deg),
            "initial_angle_deg": self.initial_angle_deg,
            "mean_lum": self.mean_lum,
            "waveform": self.waveform,
        }
