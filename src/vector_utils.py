"""Small vector helpers shared by the simulator modules."""

from __future__ import annotations

import numpy as np

EPSILON = 1e-8


def magnitude(vector: np.ndarray) -> float:
    """Return the Euclidean magnitude of a vector."""
    return float(np.linalg.norm(vector))


def normalize(vector: np.ndarray, fallback: np.ndarray | None = None) -> np.ndarray:
    """Return a unit-length copy of the vector."""
    vec = np.asarray(vector, dtype=float)
    norm = np.linalg.norm(vec)
    if norm < EPSILON:
        if fallback is None:
            return np.zeros_like(vec, dtype=float)
        fallback_vec = np.asarray(fallback, dtype=float)
        fallback_norm = np.linalg.norm(fallback_vec)
        if fallback_norm < EPSILON:
            return np.zeros_like(fallback_vec, dtype=float)
        return fallback_vec / fallback_norm
    return vec / norm


def limit_magnitude(vector: np.ndarray, max_value: float) -> np.ndarray:
    """Clamp a vector to a maximum magnitude."""
    vec = np.asarray(vector, dtype=float)
    norm = np.linalg.norm(vec)
    if norm <= max_value or norm < EPSILON:
        return vec
    return vec / norm * max_value


def angle_of(vector: np.ndarray) -> float:
    """Return the heading angle of a vector in radians."""
    vec = np.asarray(vector, dtype=float)
    return float(np.arctan2(vec[1], vec[0]))


def vector_from_angle(angle: float) -> np.ndarray:
    """Return a unit vector from an angle in radians."""
    return np.array([np.cos(angle), np.sin(angle)], dtype=float)


def weighted_average(vectors: list[np.ndarray], weights: list[float]) -> np.ndarray:
    """Compute a weighted average for a list of vectors."""
    if not vectors:
        return np.zeros(2, dtype=float)
    total_weight = float(sum(weights))
    if total_weight < EPSILON:
        return np.mean(np.asarray(vectors, dtype=float), axis=0)
    accumulator = np.zeros_like(np.asarray(vectors[0], dtype=float))
    for vector, weight in zip(vectors, weights):
        accumulator += np.asarray(vector, dtype=float) * float(weight)
    return accumulator / total_weight


def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp a scalar value into a closed interval."""
    return float(max(lower, min(upper, value)))
