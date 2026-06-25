"""Looming disc with explicit l/v ratio (escape / O-bend work)."""

from __future__ import annotations

import math

import cv2
import numpy as np

from .base import Stimulus


class LoomingDisc(Stimulus):
    type = "looming"

    def __init__(
        self,
        l_over_v_s: float,
        t_collision_s: float,
        max_radius_deg: float = 40.0,
        contrast: float = 1.0,
        mean_lum: float = 0.5,
        polarity: str = "dark",
        center_deg: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self.l_over_v_s = float(l_over_v_s)
        self.t_collision_s = float(t_collision_s)
        self.max_radius_deg = float(max_radius_deg)
        self.contrast = float(contrast)
        self.mean_lum = float(mean_lum)
        self.polarity = str(polarity)
        self.center_deg = (float(center_deg[0]), float(center_deg[1]))

    def angular_radius_deg(self, t: float) -> float:
        """Half angular size theta/2 = arctan((l/v) / (t_collision - t))."""
        remaining = self.t_collision_s - float(t)
        if remaining <= 1e-4:
            return self.max_radius_deg
        return min(self.max_radius_deg, math.degrees(math.atan(self.l_over_v_s / remaining)))

    def render(self, frame_index, t, geometry):
        height, width = geometry.screen_h_px, geometry.screen_w_px
        radius_px = max(0.0, geometry.deg_to_px(self.angular_radius_deg(t)))
        center_x = width / 2.0 + geometry.deg_to_px(self.center_deg[0])
        center_y = height / 2.0 + geometry.deg_to_px(self.center_deg[1])

        alpha = np.zeros((height, width), dtype=np.float32)
        if radius_px >= 0.5:
            cv2.circle(
                alpha,
                (int(round(center_x)), int(round(center_y))),
                int(round(radius_px)),
                1.0,
                thickness=-1,
                lineType=cv2.LINE_AA,
            )
        disc = self.mean_lum * (1.0 - self.contrast) if self.polarity == "dark" else self.mean_lum * (1.0 + self.contrast)
        disc = float(np.clip(disc, 0.0, 1.0))
        lum = np.full((height, width), disc, dtype=np.float32)
        return lum, alpha

    def describe(self):
        return {
            "type": self.type,
            "l_over_v_s": self.l_over_v_s,
            "t_collision_s": self.t_collision_s,
            "max_radius_deg": self.max_radius_deg,
            "contrast": self.contrast,
            "mean_lum": self.mean_lum,
            "polarity": self.polarity,
            "center_deg": list(self.center_deg),
        }
