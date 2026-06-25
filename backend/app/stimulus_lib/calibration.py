"""Measured display calibration — linearize against a photometer, not a guessed gamma.

Display a luminance ramp (``luminance_ramp_levels``), measure each level with a
photometer, and build a :class:`Calibration`. ``linearize`` then maps a desired
*linear* luminance in [0, 1] to the encoded pixel value that actually produces it on
that measured display — the inverse of the measured response curve. This is the real
version of the ``gamma`` number in :class:`DisplayGeometry`.

A calibration is stored as JSON and referenced from a spec via
``render.calibration_file`` with ``render.gamma_policy = "measured_lut"``; its identity
is recorded in every manifest so a render is tied to the display it was corrected for.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def luminance_ramp_levels(n: int = 17) -> list[float]:
    """Evenly spaced pixel levels in [0, 1] to display for measurement."""
    return [i / (n - 1) for i in range(n)]


@dataclass
class Calibration:
    """A measured input-level -> luminance response for one display."""

    input_levels: list[float]
    measured_luminance: list[float]
    display_id: str = "unspecified-display"
    instrument: str = "unspecified"
    measured_utc: str | None = None

    def __post_init__(self) -> None:
        levels = np.asarray(self.input_levels, dtype=float)
        luminance = np.asarray(self.measured_luminance, dtype=float)
        if levels.shape != luminance.shape or levels.size < 2:
            raise ValueError("calibration needs matching input_levels and measured_luminance, length >= 2")
        order = np.argsort(levels)
        self._levels = levels[order]
        self._lum = luminance[order]
        self._lmin = float(self._lum.min())
        self._lmax = float(self._lum.max())
        # Normalised, monotonic-non-decreasing measured response in [0, 1].
        span = max(self._lmax - self._lmin, 1e-12)
        self._norm = np.maximum.accumulate((self._lum - self._lmin) / span)

    @property
    def max_luminance(self) -> float:
        return self._lmax

    def linearize(self, linear01: np.ndarray) -> np.ndarray:
        """Map desired linear luminance [0, 1] -> encoded pixel value [0, 1]."""
        target = np.clip(linear01, 0.0, 1.0)
        encoded = np.interp(target, self._norm, self._levels)
        return np.clip(encoded, 0.0, 1.0).astype(np.float32)

    def to_cd_m2(self, linear01: np.ndarray) -> np.ndarray:
        """Physical luminance (measured units) a linear value maps to on this display."""
        target = np.clip(linear01, 0.0, 1.0)
        return (self._lmin + target * (self._lmax - self._lmin)).astype(np.float32)

    def identity_hash(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "input_levels": [float(v) for v in self._levels],
            "measured_luminance": [float(v) for v in self._lum],
            "display_id": self.display_id,
            "instrument": self.instrument,
            "measured_utc": self.measured_utc,
            "max_luminance": self._lmax,
        }

    def manifest_record(self) -> dict:
        return {
            "display_id": self.display_id,
            "instrument": self.instrument,
            "measured_utc": self.measured_utc,
            "max_luminance": self._lmax,
            "calibration_hash": self.identity_hash(),
        }

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def from_measurements(cls, input_levels, measured_luminance, **meta) -> "Calibration":
        return cls(input_levels=list(input_levels), measured_luminance=list(measured_luminance), **meta)

    @classmethod
    def from_dict(cls, data: dict) -> "Calibration":
        return cls(
            input_levels=list(data["input_levels"]),
            measured_luminance=list(data["measured_luminance"]),
            display_id=data.get("display_id", "unspecified-display"),
            instrument=data.get("instrument", "unspecified"),
            measured_utc=data.get("measured_utc"),
        )

    @classmethod
    def load(cls, path: str | Path) -> "Calibration":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
