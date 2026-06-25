"""Random-dot kinematogram with a coherence knob.

Trajectories are precomputed deterministically from the seeded RNG in ``prepare``
so ``render`` is a pure function of frame index.
"""

from __future__ import annotations

import cv2
import numpy as np

from .base import Stimulus


class RandomDotKinematogram(Stimulus):
    type = "rdk"

    def __init__(
        self,
        n_dots: int,
        coherence: float,
        speed_dps: float,
        direction_deg: float,
        dot_size_deg: float = 0.3,
        dot_lifetime_s: float = 0.2,
        mean_lum: float = 0.5,
        dot_contrast: float = 1.0,
    ) -> None:
        self.n_dots = int(n_dots)
        self.coherence = float(coherence)
        self.speed_dps = float(speed_dps)
        self.direction_deg = float(direction_deg)
        self.dot_size_deg = float(dot_size_deg)
        self.dot_lifetime_s = float(dot_lifetime_s)
        self.mean_lum = float(mean_lum)
        self.dot_contrast = float(dot_contrast)
        self._frames: np.ndarray | None = None
        self._shape: tuple[int, int] | None = None
        self._radius_px = 1

    def prepare(self, geometry, fps, n_frames, rng) -> None:
        height, width = geometry.screen_h_px, geometry.screen_w_px
        self._shape = (height, width)
        self._radius_px = max(1, int(round(geometry.deg_to_px(self.dot_size_deg) / 2.0)))
        step = geometry.deg_to_px(self.speed_dps) / float(fps)
        lifetime = max(1, int(round(self.dot_lifetime_s * float(fps))))
        n = self.n_dots

        coherent_vec = np.array(
            [np.cos(np.radians(self.direction_deg)), np.sin(np.radians(self.direction_deg))], dtype=np.float64
        )
        pos = rng.uniform([0.0, 0.0], [width, height], size=(n, 2))
        age = rng.integers(0, lifetime, size=n)
        is_coherent = rng.random(n) < self.coherence
        random_dir = rng.uniform(0.0, 2.0 * np.pi, size=n)

        frames = np.empty((n_frames, n, 2), dtype=np.float32)
        for f in range(n_frames):
            frames[f] = pos
            move = np.where(
                is_coherent[:, None],
                coherent_vec[None, :] * step,
                np.stack([np.cos(random_dir), np.sin(random_dir)], axis=1) * step,
            )
            pos = pos + move
            pos[:, 0] %= width
            pos[:, 1] %= height
            age = age + 1
            expired = age >= lifetime
            if expired.any():
                idx = np.where(expired)[0]
                pos[idx] = rng.uniform([0.0, 0.0], [width, height], size=(len(idx), 2))
                is_coherent[idx] = rng.random(len(idx)) < self.coherence
                random_dir[idx] = rng.uniform(0.0, 2.0 * np.pi, size=len(idx))
                age[idx] = 0
        self._frames = frames

    def render(self, frame_index, t, geometry):
        height, width = self._shape
        alpha = np.zeros((height, width), dtype=np.float32)
        for x, y in self._frames[frame_index]:
            cv2.circle(alpha, (int(x), int(y)), self._radius_px, 1.0, thickness=-1, lineType=cv2.LINE_AA)
        dot_value = float(np.clip(self.mean_lum * (1.0 + self.dot_contrast), 0.0, 1.0))
        lum = np.full((height, width), dot_value, dtype=np.float32)
        return lum, alpha

    def validate(self, geometry, fps):
        errors = []
        step_px = geometry.deg_to_px(self.speed_dps) / float(fps)
        dot_px = geometry.deg_to_px(self.dot_size_deg)
        if step_px > max(dot_px, 1.0):
            errors.append(
                f"RDK coherent step {step_px:.2f} px/frame exceeds dot size {dot_px:.2f} px (motion will alias / "
                f"reverse-phi); raise fps or lower speed_dps {self.speed_dps}."
            )
        if not 0.0 <= self.coherence <= 1.0:
            errors.append(f"RDK coherence {self.coherence} must be in [0, 1].")
        return errors

    def describe(self):
        return {
            "type": self.type,
            "n_dots": self.n_dots,
            "coherence": self.coherence,
            "speed_dps": self.speed_dps,
            "direction_deg": self.direction_deg,
            "dot_size_deg": self.dot_size_deg,
            "dot_lifetime_s": self.dot_lifetime_s,
            "mean_lum": self.mean_lum,
            "dot_contrast": self.dot_contrast,
        }
