"""Base interface for experiment paradigms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class ParadigmOutput:
    """Per-frame paradigm output consumed by the deterministic engine."""

    phase: str
    attractors: dict[str, np.ndarray]
    external_forces: list[np.ndarray]
    social_multipliers: dict[str, float]
    neighbor_mode: str


class BaseParadigm(ABC):
    """Paradigm logic stays independent of the motion model and renderer."""

    def reset(self, config, rng) -> None:
        """Reset internal state for a fresh simulation."""

    @abstractmethod
    def update(self, agents, time, global_state) -> ParadigmOutput:
        """Return phase-specific forces and social tuning for the current time."""
