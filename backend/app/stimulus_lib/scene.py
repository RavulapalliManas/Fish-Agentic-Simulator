"""Scene: region-masked, time-scheduled compositing of stimulus layers.

A Layer binds a primitive to (a) a region of the visual field, (b) a compositing
rule, and (c) a timeline (onset/offset with optional fades). The Scene composites
layers in order. This is the architectural payoff: split-field, monocular, conflict,
prey-on-background and surround stimuli are all just layer/region combinations —
no per-paradigm render code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .geometry import DisplayGeometry
from .regions import build_region_mask
from .stimuli.base import Stimulus

COMPOSITING_MODES = ("over", "blend", "occlude")


@dataclass
class Layer:
    """A primitive placed in a region, composited, and scheduled in time."""

    stimulus: Stimulus
    region: object = "full"
    compositing: str = "over"
    onset_s: float = 0.0
    offset_s: float | None = None
    fade_in_s: float = 0.0
    fade_out_s: float = 0.0
    blend_weight: float = 1.0
    _mask: np.ndarray | None = field(default=None, repr=False)

    def prepare(self, geometry: DisplayGeometry, fps: float, n_frames: int, rng: np.random.Generator) -> None:
        if self.compositing not in COMPOSITING_MODES:
            raise ValueError(f"unknown compositing mode {self.compositing!r}; use one of {COMPOSITING_MODES}")
        self.stimulus.prepare(geometry, fps, n_frames, rng)
        self._mask = build_region_mask(self.region, geometry)

    def timeline_gain(self, t: float) -> float:
        if t < self.onset_s:
            return 0.0
        if self.offset_s is not None and t >= self.offset_s:
            return 0.0
        gain = 1.0
        if self.fade_in_s > 0.0 and t < self.onset_s + self.fade_in_s:
            gain = min(gain, (t - self.onset_s) / self.fade_in_s)
        if self.offset_s is not None and self.fade_out_s > 0.0 and t > self.offset_s - self.fade_out_s:
            gain = min(gain, (self.offset_s - t) / self.fade_out_s)
        return max(0.0, gain)

    def describe(self) -> dict:
        return {
            "stimulus": self.stimulus.describe(),
            "region": self.region,
            "compositing": self.compositing,
            "onset_s": self.onset_s,
            "offset_s": self.offset_s,
            "fade_in_s": self.fade_in_s,
            "fade_out_s": self.fade_out_s,
            "blend_weight": self.blend_weight,
        }


class Scene:
    def __init__(self, layers: list[Layer], mean_lum: float = 0.5) -> None:
        self.layers = layers
        self.mean_lum = float(mean_lum)

    def prepare(self, geometry: DisplayGeometry, fps: float, n_frames: int, rng: np.random.Generator) -> None:
        # Layers consume from the shared RNG in order -> deterministic for a fixed
        # seed and layer ordering.
        for layer in self.layers:
            layer.prepare(geometry, fps, n_frames, rng)

    def render(self, frame_index: int, t: float, geometry: DisplayGeometry) -> np.ndarray:
        height, width = geometry.screen_h_px, geometry.screen_w_px
        out = np.full((height, width), self.mean_lum, dtype=np.float32)
        for layer in self.layers:
            gain = layer.timeline_gain(t)
            if gain <= 0.0:
                continue
            lum, alpha = layer.stimulus.render(frame_index, t, geometry)
            coverage = alpha * layer._mask * gain
            if layer.compositing == "over":
                out = out * (1.0 - coverage) + lum * coverage
            elif layer.compositing == "blend":
                weighted = coverage * layer.blend_weight
                out = out * (1.0 - weighted) + lum * weighted
            else:  # occlude: hard replace where the masked layer is opaque
                hard = coverage >= 0.5
                out = np.where(hard, lum, out)
        return np.clip(out, 0.0, 1.0).astype(np.float32)

    def validate(self, geometry: DisplayGeometry, fps: float) -> list[str]:
        errors: list[str] = []
        for layer in self.layers:
            if layer.compositing not in COMPOSITING_MODES:
                errors.append(f"unknown compositing mode {layer.compositing!r}")
            errors.extend(layer.stimulus.validate(geometry, fps))
        return errors

    def describe(self) -> list[dict]:
        return [layer.describe() for layer in self.layers]
