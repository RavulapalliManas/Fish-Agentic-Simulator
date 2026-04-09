"""Small vector helpers shared across the simulator."""

from __future__ import annotations

import math

import numpy as np

EPSILON = 1e-8


def normalize(vector: np.ndarray, fallback: np.ndarray | None = None) -> np.ndarray:
    """Return a unit-length copy of *vector*."""
    vec = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(vec))
    if norm < EPSILON:
        if fallback is None:
            return np.zeros_like(vec, dtype=float)
        fallback_vec = np.asarray(fallback, dtype=float)
        fallback_norm = float(np.linalg.norm(fallback_vec))
        if fallback_norm < EPSILON:
            return np.zeros_like(fallback_vec, dtype=float)
        return fallback_vec / fallback_norm
    return vec / norm


def limit_magnitude(vector: np.ndarray, max_value: float) -> np.ndarray:
    """Clamp *vector* to the provided magnitude."""
    vec = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(vec))
    if norm < EPSILON or norm <= float(max_value):
        return vec
    return vec / norm * float(max_value)


def vector_from_angle(angle_radians: float) -> np.ndarray:
    """Return a unit vector that points in *angle_radians*."""
    return np.array([math.cos(angle_radians), math.sin(angle_radians)], dtype=float)


def angle_of(vector: np.ndarray) -> float:
    """Return the heading angle for *vector*."""
    vec = np.asarray(vector, dtype=float)
    return float(math.atan2(vec[1], vec[0]))


def weighted_average(vectors: list[np.ndarray], weights: list[float]) -> np.ndarray:
    """Return the weighted average of the given vectors."""
    if not vectors:
        return np.zeros(2, dtype=float)
    total_weight = float(sum(weights))
    if total_weight < EPSILON:
        return np.mean(np.asarray(vectors, dtype=float), axis=0)
    accumulator = np.zeros(2, dtype=float)
    for vector, weight in zip(vectors, weights):
        accumulator += np.asarray(vector, dtype=float) * float(weight)
    return accumulator / total_weight


def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp *value* into the closed interval [lower, upper]."""
    return float(max(lower, min(upper, value)))


def blend_factor(dt: float, time_constant: float) -> float:
    """Return an exponential blend factor that is stable across FPS values."""
    if time_constant <= 0.0:
        return 1.0
    return 1.0 - math.exp(-float(dt) / float(time_constant))
