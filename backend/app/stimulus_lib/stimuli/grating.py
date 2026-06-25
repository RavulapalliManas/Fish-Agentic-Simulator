"""Drifting sinusoidal grating (OMR / OKR)."""

from __future__ import annotations

import numpy as np

from ..geometry import DisplayGeometry
from .base import Stimulus


class Grating(Stimulus):
    type = "grating"

    def __init__(
        self,
        spatial_freq_cpd: float,
        temporal_freq_hz: float,
        contrast: float,
        orientation_deg: float = 0.0,
        phase_deg: float = 0.0,
        mean_lum: float = 0.5,
    ) -> None:
        self.spatial_freq_cpd = float(spatial_freq_cpd)
        self.temporal_freq_hz = float(temporal_freq_hz)
        self.contrast = float(contrast)
        self.orientation_deg = float(orientation_deg)
        self.phase_deg = float(phase_deg)
        self.mean_lum = float(mean_lum)
        self._proj: np.ndarray | None = None
        self._shape: tuple[int, int] | None = None

    def prepare(self, geometry, fps, n_frames, rng) -> None:
        self._build_proj(geometry)

    def _build_proj(self, geometry: DisplayGeometry) -> None:
        height, width = geometry.screen_h_px, geometry.screen_w_px
        xs = np.arange(width, dtype=np.float32)
        ys = np.arange(height, dtype=np.float32)
        grid_x, grid_y = np.meshgrid(xs, ys)
        theta = np.radians(self.orientation_deg)
        self._proj = (grid_x * np.cos(theta) + grid_y * np.sin(theta)).astype(np.float32)
        self._shape = (height, width)

    def render(self, frame_index, t, geometry):
        if self._proj is None:
            self._build_proj(geometry)
        cyc_per_px = geometry.cpd_to_cyc_per_px(self.spatial_freq_cpd)
        phase = np.radians(self.phase_deg) + 2.0 * np.pi * self.temporal_freq_hz * float(t)
        lum = self.mean_lum * (1.0 + self.contrast * np.sin(2.0 * np.pi * cyc_per_px * self._proj - phase))
        lum = np.clip(lum, 0.0, 1.0).astype(np.float32)
        alpha = np.ones(self._shape, dtype=np.float32)
        return lum, alpha

    def validate(self, geometry, fps):
        errors = []
        cyc_per_px = geometry.cpd_to_cyc_per_px(self.spatial_freq_cpd)
        if cyc_per_px > 0.5:
            errors.append(
                f"grating spatial_freq {self.spatial_freq_cpd} cpd = {cyc_per_px:.3f} cyc/px exceeds the "
                f"Nyquist limit of 0.5 (display can resolve up to {geometry.max_cpd:.2f} cpd)."
            )
        cyc_per_frame = abs(self.temporal_freq_hz) / float(fps)
        if cyc_per_frame >= 0.5:
            errors.append(
                f"grating temporal_freq {self.temporal_freq_hz} Hz = {cyc_per_frame:.3f} cyc/frame >= 0.5 "
                f"Nyquist at {fps} fps (motion will alias / reverse-phi)."
            )
        return errors

    def describe(self):
        return {
            "type": self.type,
            "spatial_freq_cpd": self.spatial_freq_cpd,
            "temporal_freq_hz": self.temporal_freq_hz,
            "contrast": self.contrast,
            "orientation_deg": self.orientation_deg,
            "phase_deg": self.phase_deg,
            "mean_lum": self.mean_lum,
        }
