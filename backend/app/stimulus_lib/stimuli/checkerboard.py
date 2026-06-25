"""Static or contrast-reversing checkerboard (spatial-frequency / contrast tuning baseline).

A true checker: the sign of a square wave along x times the sign along y. ``check_size_deg``
is the side of one check; a full spatial period is two checks, hence ``period_px`` is twice
the check size in pixels. With ``reversal_hz > 0`` the whole pattern flips polarity at that
rate (``sign(sin(2*pi*f*t))``); ``reversal_hz = 0`` leaves it static. The spatial pattern is
precomputed in ``prepare`` so ``render`` is a pure function of time.
"""

from __future__ import annotations

import numpy as np

from ..geometry import DisplayGeometry
from .base import Stimulus


class Checkerboard(Stimulus):
    type = "checkerboard"

    def __init__(
        self,
        check_size_deg: float,
        contrast: float = 1.0,
        mean_lum: float = 0.5,
        reversal_hz: float = 0.0,
    ) -> None:
        self.check_size_deg = float(check_size_deg)
        self.contrast = float(contrast)
        self.mean_lum = float(mean_lum)
        self.reversal_hz = float(reversal_hz)
        self._pattern: np.ndarray | None = None
        self._shape: tuple[int, int] | None = None

    def prepare(self, geometry, fps, n_frames, rng) -> None:
        self._build_pattern(geometry)

    def _build_pattern(self, geometry: DisplayGeometry) -> None:
        height, width = geometry.screen_h_px, geometry.screen_w_px
        period_px = 2.0 * geometry.deg_to_px(self.check_size_deg)
        xs = np.arange(width, dtype=np.float32)
        ys = np.arange(height, dtype=np.float32)
        grid_x, grid_y = np.meshgrid(xs, ys)
        pattern = np.sign(np.sin(2.0 * np.pi * grid_x / period_px)) * np.sign(
            np.sin(2.0 * np.pi * grid_y / period_px)
        )
        self._pattern = pattern.astype(np.float32)
        self._shape = (height, width)

    def render(self, frame_index, t, geometry):
        if self._pattern is None:
            self._build_pattern(geometry)
        pattern = self._pattern
        if self.reversal_hz > 0.0:
            pattern = pattern * np.sign(np.sin(2.0 * np.pi * self.reversal_hz * float(t)))
        lum = self.mean_lum * (1.0 + self.contrast * pattern)
        lum = np.clip(lum, 0.0, 1.0).astype(np.float32)
        alpha = np.ones(self._shape, dtype=np.float32)
        return lum, alpha

    def validate(self, geometry, fps):
        errors = []
        check_px = geometry.deg_to_px(self.check_size_deg)
        if check_px < 2.0:
            errors.append(
                f"checkerboard check_size {self.check_size_deg} deg = {check_px:.3f} px is below the "
                f"spatial Nyquist floor of 2 px (display resolves checks down to "
                f"{geometry.px_to_deg(2.0):.3f} deg)."
            )
        if self.reversal_hz > 0.0 and self.reversal_hz / float(fps) >= 0.5:
            errors.append(
                f"checkerboard reversal_hz {self.reversal_hz} Hz = {self.reversal_hz / float(fps):.3f} "
                f"cyc/frame >= 0.5 Nyquist at {fps} fps (reversal will alias)."
            )
        return errors

    def describe(self):
        return {
            "type": self.type,
            "check_size_deg": self.check_size_deg,
            "contrast": self.contrast,
            "mean_lum": self.mean_lum,
            "reversal_hz": self.reversal_hz,
        }
