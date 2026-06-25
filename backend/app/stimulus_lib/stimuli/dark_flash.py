"""Whole-field dark flash (luminance step)."""

from __future__ import annotations

import numpy as np

from .base import Stimulus


class DarkFlash(Stimulus):
    type = "dark_flash"

    def __init__(
        self,
        baseline_lum: float = 0.5,
        flash_lum: float = 0.0,
        onset_s: float = 0.5,
        duration_s: float = 0.1,
    ) -> None:
        self.baseline_lum = float(baseline_lum)
        self.flash_lum = float(flash_lum)
        self.onset_s = float(onset_s)
        self.duration_s = float(duration_s)

    def render(self, frame_index, t, geometry):
        height, width = geometry.screen_h_px, geometry.screen_w_px
        in_flash = self.onset_s <= float(t) < self.onset_s + self.duration_s
        value = self.flash_lum if in_flash else self.baseline_lum
        lum = np.full((height, width), float(np.clip(value, 0.0, 1.0)), dtype=np.float32)
        alpha = np.ones((height, width), dtype=np.float32)
        return lum, alpha

    def describe(self):
        return {
            "type": self.type,
            "baseline_lum": self.baseline_lum,
            "flash_lum": self.flash_lum,
            "onset_s": self.onset_s,
            "duration_s": self.duration_s,
        }
