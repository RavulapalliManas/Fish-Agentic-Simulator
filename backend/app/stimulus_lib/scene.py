"""Scene: superpose ordered stimulus layers into one composite frame."""

from __future__ import annotations

import numpy as np

from .geometry import DisplayGeometry
from .stimuli.base import Stimulus


class Scene:
    """Composite of layers, rendered with standard over-compositing on a mean field."""

    def __init__(self, layers: list[Stimulus], mean_lum: float = 0.5) -> None:
        self.layers = layers
        self.mean_lum = float(mean_lum)

    def prepare(self, geometry: DisplayGeometry, fps: float, n_frames: int, rng: np.random.Generator) -> None:
        # Layers consume from the shared RNG in order, so the result is deterministic
        # for a fixed seed and layer ordering.
        for layer in self.layers:
            layer.prepare(geometry, fps, n_frames, rng)

    def render(self, frame_index: int, t: float, geometry: DisplayGeometry) -> np.ndarray:
        height, width = geometry.screen_h_px, geometry.screen_w_px
        out = np.full((height, width), self.mean_lum, dtype=np.float32)
        for layer in self.layers:
            lum, alpha = layer.render(frame_index, t, geometry)
            out = out * (1.0 - alpha) + lum * alpha
        return np.clip(out, 0.0, 1.0).astype(np.float32)

    def validate(self, geometry: DisplayGeometry, fps: float) -> list[str]:
        errors: list[str] = []
        for layer in self.layers:
            errors.extend(layer.validate(geometry, fps))
        return errors

    def describe(self) -> list[dict]:
        return [layer.describe() for layer in self.layers]
