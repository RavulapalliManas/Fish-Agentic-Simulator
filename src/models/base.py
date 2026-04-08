"""Shared model interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class BaseModel(ABC):
    """Local interaction model used by the fixed-timestep engine."""

    name = "Base Model"
    constant_speed = False

    @abstractmethod
    def compute_force(self, agent, neighbors, context) -> np.ndarray:
        """Return the model-specific steering force for one agent."""
