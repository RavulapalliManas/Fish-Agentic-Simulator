"""Stimulus primitive contract.

A primitive renders a single layer as (luminance, alpha) in linear light, both
float32 in [0, 1] and shaped (H, W). The Scene composites layers with standard
over-compositing so primitives superpose (e.g. a prey dot over a drifting grating).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..geometry import DisplayGeometry


class Stimulus(ABC):
    """Base class for all visual primitives."""

    type: str = "stimulus"

    def prepare(self, geometry: DisplayGeometry, fps: float, n_frames: int, rng: np.random.Generator) -> None:
        """Optional one-shot precomputation (e.g. seeded RDK trajectories)."""

    @abstractmethod
    def render(self, frame_index: int, t: float, geometry: DisplayGeometry) -> tuple[np.ndarray, np.ndarray]:
        """Return (luminance, alpha), each float32 (H, W) in [0, 1]."""

    def validate(self, geometry: DisplayGeometry, fps: float) -> list[str]:
        """Return blocking error strings (e.g. Nyquist violations). Empty = ok."""
        return []

    def describe(self) -> dict:
        """Parameters for the provenance manifest."""
        return {"type": self.type}
