"""Small prey-like moving spot (hunting / J-turn work).

A sub-degree disc drifts across the field along a chosen trajectory. The full
per-frame position track is precomputed deterministically from the seeded RNG in
``prepare`` so ``render`` is a pure function of frame index. Trajectories:
``linear`` (constant velocity), ``brownian`` (gaussian random walk scaled to
speed), and ``saltatory`` (paramecium-like burst-and-coast: short fast runs then
pauses, with occasional random turns).
"""

from __future__ import annotations

import cv2
import numpy as np

from ..geometry import DisplayGeometry
from .base import Stimulus

TRAJECTORIES = ("linear", "brownian", "saltatory")

# Saltatory bursts run at this multiple of the nominal per-frame step; used both
# by the trajectory generator and the Nyquist check in ``validate`` so the two
# never drift apart.
_SALTATORY_RUN_GAIN = 3.0


class PreyDot(Stimulus):
    type = "prey"

    def __init__(
        self,
        size_deg: float = 0.5,
        speed_dps: float = 10.0,
        trajectory: str = "saltatory",
        direction_deg: float = 0.0,
        polarity: str = "dark",
        mean_lum: float = 0.5,
        contrast: float = 1.0,
        start_deg: tuple[float, float] = (-10.0, 0.0),
    ) -> None:
        self.size_deg = float(size_deg)
        self.speed_dps = float(speed_dps)
        self.trajectory = str(trajectory)
        self.direction_deg = float(direction_deg)
        self.polarity = str(polarity)
        self.mean_lum = float(mean_lum)
        self.contrast = float(contrast)
        self.start_deg = (float(start_deg[0]), float(start_deg[1]))
        self._track: np.ndarray | None = None
        self._shape: tuple[int, int] | None = None
        self._radius_px = 1

    def prepare(self, geometry, fps, n_frames, rng) -> None:
        height, width = geometry.screen_h_px, geometry.screen_w_px
        self._shape = (height, width)
        self._radius_px = max(1, int(round(geometry.deg_to_px(self.size_deg) / 2.0)))
        step = geometry.deg_to_px(self.speed_dps) / float(fps)

        # Start from screen centre offset by start_deg (origin = centre, +x right, +y down).
        pos = np.array(
            [
                width / 2.0 + geometry.deg_to_px(self.start_deg[0]),
                height / 2.0 + geometry.deg_to_px(self.start_deg[1]),
            ],
            dtype=np.float64,
        )

        if self.trajectory == "brownian":
            track = self._brownian(pos, step, n_frames, rng)
        elif self.trajectory == "saltatory":
            track = self._saltatory(pos, step, fps, n_frames, rng)
        else:  # linear
            track = self._linear(pos, step, n_frames)

        lo = np.array([self._radius_px, self._radius_px], dtype=np.float64)
        hi = np.array([width - self._radius_px, height - self._radius_px], dtype=np.float64)
        np.clip(track, lo, hi, out=track)
        self._track = track.astype(np.float32)

    def _linear(self, pos, step, n_frames) -> np.ndarray:
        theta = np.radians(self.direction_deg)
        vel = np.array([np.cos(theta), np.sin(theta)], dtype=np.float64) * step
        offsets = np.arange(n_frames, dtype=np.float64)[:, None] * vel[None, :]
        return pos[None, :] + offsets

    def _brownian(self, pos, step, n_frames, rng) -> np.ndarray:
        # Gaussian random walk; per-axis sigma chosen so the expected per-frame
        # step length matches the speed-derived step (E|N(0, s^2 I_2)| ~= s for
        # s = step / sqrt(2)).
        sigma = step / np.sqrt(2.0)
        steps = rng.normal(0.0, sigma, size=(n_frames, 2))
        steps[0] = 0.0
        return pos[None, :] + np.cumsum(steps, axis=0)

    def _saltatory(self, pos, step, fps, n_frames, rng) -> np.ndarray:
        # Paramecium-like burst-and-coast: short fast runs (~3x mean speed) then
        # pauses, with a random heading reorientation at the start of each run.
        run_speed = step * _SALTATORY_RUN_GAIN
        run_frames = max(1, int(round(0.15 * float(fps))))   # ~150 ms bursts
        pause_frames = max(1, int(round(0.25 * float(fps))))  # ~250 ms coasts/pauses
        theta = np.radians(self.direction_deg)

        track = np.empty((n_frames, 2), dtype=np.float64)
        cur = pos.copy()
        f = 0
        while f < n_frames:
            # Reorient: occasional large random turn, otherwise small jitter
            # around the nominal heading (mimics paramecium turn statistics).
            if rng.random() < 0.5:
                theta = rng.uniform(0.0, 2.0 * np.pi)
            else:
                theta = theta + rng.normal(0.0, np.radians(20.0))
            vel = np.array([np.cos(theta), np.sin(theta)], dtype=np.float64) * run_speed

            for _ in range(run_frames):
                if f >= n_frames:
                    break
                cur = cur + vel
                track[f] = cur
                f += 1
            for _ in range(pause_frames):
                if f >= n_frames:
                    break
                track[f] = cur
                f += 1
        return track

    def render(self, frame_index, t, geometry):
        height, width = self._shape
        alpha = np.zeros((height, width), dtype=np.float32)
        x, y = self._track[frame_index]
        cv2.circle(alpha, (int(round(x)), int(round(y))), self._radius_px, 1.0, thickness=-1, lineType=cv2.LINE_AA)
        spot = self.mean_lum * (1.0 - self.contrast) if self.polarity == "dark" else self.mean_lum * (1.0 + self.contrast)
        spot = float(np.clip(spot, 0.0, 1.0))
        lum = np.full((height, width), spot, dtype=np.float32)
        return lum, alpha

    def validate(self, geometry, fps):
        errors = []
        if self.trajectory not in TRAJECTORIES:
            errors.append(f"prey trajectory {self.trajectory!r} must be one of {TRAJECTORIES}.")
        if self.polarity not in ("dark", "bright"):
            errors.append(f"prey polarity {self.polarity!r} must be 'dark' or 'bright'.")
        spot_px = geometry.deg_to_px(self.size_deg)
        if spot_px <= 0.0:
            errors.append(f"prey size_deg {self.size_deg} resolves to {spot_px:.2f} px (must be > 0).")
        step_px = geometry.deg_to_px(self.speed_dps) / float(fps)
        # Saltatory bursts move at _SALTATORY_RUN_GAIN x the nominal step, so the
        # per-frame displacement that can actually alias is larger than ``step_px``.
        effective_step_px = step_px * (_SALTATORY_RUN_GAIN if self.trajectory == "saltatory" else 1.0)
        if effective_step_px > max(spot_px, 1.0):
            errors.append(
                f"prey step {effective_step_px:.2f} px/frame exceeds spot size {spot_px:.2f} px "
                f"(motion will alias / skip); raise fps or lower speed_dps {self.speed_dps}."
            )
        return errors

    def describe(self):
        return {
            "type": self.type,
            "size_deg": self.size_deg,
            "speed_dps": self.speed_dps,
            "trajectory": self.trajectory,
            "direction_deg": self.direction_deg,
            "polarity": self.polarity,
            "mean_lum": self.mean_lum,
            "contrast": self.contrast,
            "start_deg": list(self.start_deg),
        }
