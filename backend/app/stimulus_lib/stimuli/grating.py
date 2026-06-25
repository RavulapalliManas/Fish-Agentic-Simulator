"""Drifting / static sinusoidal or square-wave grating (OMR, tuning baselines).

Spatial and temporal frequency are decoupled and both exposable; ``velocity_dps``
is an alternative way to set drift (temporal_freq = velocity * spatial_freq). Drift
``direction_deg`` is explicit. ``orientation_deg`` is accepted as a backward-compatible
alias for the carrier/drift axis.
"""

from __future__ import annotations

import numpy as np

from ..geometry import DisplayGeometry
from .base import Stimulus


class Grating(Stimulus):
    type = "grating"

    def __init__(
        self,
        spatial_freq_cpd: float,
        temporal_freq_hz: float | None = None,
        contrast: float = 1.0,
        direction_deg: float | None = None,
        phase_deg: float = 0.0,
        mean_lum: float = 0.5,
        velocity_dps: float | None = None,
        waveform: str = "sine",
        orientation_deg: float | None = None,
    ) -> None:
        self.spatial_freq_cpd = float(spatial_freq_cpd)
        self.contrast = float(contrast)
        self.phase_deg = float(phase_deg)
        self.mean_lum = float(mean_lum)
        self.waveform = str(waveform)
        self.velocity_dps = None if velocity_dps is None else float(velocity_dps)

        if direction_deg is not None:
            self.direction_deg = float(direction_deg)
        elif orientation_deg is not None:
            self.direction_deg = float(orientation_deg)
        else:
            self.direction_deg = 0.0

        if self.velocity_dps is not None:
            self.temporal_freq_hz = self.velocity_dps * self.spatial_freq_cpd
        elif temporal_freq_hz is not None:
            self.temporal_freq_hz = float(temporal_freq_hz)
        else:
            self.temporal_freq_hz = 0.0

        self._proj: np.ndarray | None = None
        self._shape: tuple[int, int] | None = None

    def prepare(self, geometry, fps, n_frames, rng) -> None:
        self._build_proj(geometry)

    def _build_proj(self, geometry: DisplayGeometry) -> None:
        height, width = geometry.screen_h_px, geometry.screen_w_px
        xs = np.arange(width, dtype=np.float32)
        ys = np.arange(height, dtype=np.float32)
        grid_x, grid_y = np.meshgrid(xs, ys)
        theta = np.radians(self.direction_deg)
        self._proj = (grid_x * np.cos(theta) + grid_y * np.sin(theta)).astype(np.float32)
        self._shape = (height, width)

    def render(self, frame_index, t, geometry):
        if self._proj is None:
            self._build_proj(geometry)
        cyc_per_px = geometry.cpd_to_cyc_per_px(self.spatial_freq_cpd)
        angle = 2.0 * np.pi * cyc_per_px * self._proj - 2.0 * np.pi * self.temporal_freq_hz * float(t)
        angle = angle + np.radians(self.phase_deg)
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
                f"grating spatial_freq {self.spatial_freq_cpd} cpd = {cyc_per_px:.3f} cyc/px exceeds the "
                f"Nyquist limit of 0.5 (display can resolve up to {geometry.max_cpd:.2f} cpd)."
            )
        cyc_per_frame = abs(self.temporal_freq_hz) / float(fps)
        if cyc_per_frame >= 0.5:
            errors.append(
                f"grating temporal_freq {self.temporal_freq_hz:.3f} Hz = {cyc_per_frame:.3f} cyc/frame >= 0.5 "
                f"Nyquist at {fps} fps (motion will alias / reverse-phi)."
            )
        return errors

    def describe(self):
        return {
            "type": self.type,
            "spatial_freq_cpd": self.spatial_freq_cpd,
            "temporal_freq_hz": self.temporal_freq_hz,
            "velocity_dps": self.velocity_dps,
            "contrast": self.contrast,
            "direction_deg": self.direction_deg,
            "phase_deg": self.phase_deg,
            "waveform": self.waveform,
            "mean_lum": self.mean_lum,
        }
