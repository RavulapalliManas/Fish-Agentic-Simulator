"""Shared interface for all motion models."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class BaseModel(ABC):
    """Common interface for all simulation models."""

    name = "Base Model"
    constant_speed = False

    def reset(self) -> None:
        """Hook for models that keep state across runs."""

    @abstractmethod
    def compute_force(self, agent, neighbors, global_state) -> np.ndarray:
        """Return an acceleration vector for a single agent."""

    def blend_force(
        self,
        local_force: np.ndarray,
        global_state,
        noise_scale: float = 1.0,
        attractor_scale: float = 1.0,
        rotation_scale: float = 1.0,
    ) -> np.ndarray:
        """Blend local motion with noise, attraction, and rotation."""
        weights = global_state["weights"]
        return (
            local_force * weights["boids"]
            + global_state["noise_force"] * weights["noise"] * noise_scale
            + global_state["attractor_force"] * weights["attractor"] * attractor_scale
            + global_state["rotation_force"] * weights["rotation"] * rotation_scale
        )
