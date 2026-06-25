"""Kinematic biological-motion conspecific fish (social / shoaling assays).

EXPLICIT FIRST-PASS kinematic model. This is a hand-built, geometric caricature of
a swimming fish, NOT a validated biological-motion stimulus: the body is a tapered
polygon whose tail bends with a sinusoidal tail-beat, and locomotion follows a
burst-and-glide bout schedule. It is intended as a placeholder conspecific for
social/shoaling paradigms while a tracked / point-light biological-motion model is
developed. Do not treat its kinematics as quantitatively matched to real larvae.

Per-agent trajectories (positions, headings, body-phase) are precomputed
deterministically from the seeded RNG in ``prepare`` so ``render`` is a pure
function of frame index.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..geometry import DisplayGeometry
from .base import Stimulus


class Conspecific(Stimulus):
    type = "conspecific"

    def __init__(
        self,
        n_agents: int = 1,
        body_size_deg: float = 2.0,
        tail_beat_hz: float = 20.0,
        bout_period_s: float = 1.0,
        bout_duty: float = 0.4,
        speed_dps: float = 8.0,
        schooling: str = "school",
        polarity: str = "dark",
        mean_lum: float = 0.5,
        contrast: float = 1.0,
    ) -> None:
        self.n_agents = int(n_agents)
        self.body_size_deg = float(body_size_deg)
        self.tail_beat_hz = float(tail_beat_hz)
        self.bout_period_s = float(bout_period_s)
        self.bout_duty = float(bout_duty)
        self.speed_dps = float(speed_dps)
        self.schooling = str(schooling)
        self.polarity = str(polarity)
        self.mean_lum = float(mean_lum)
        self.contrast = float(contrast)
        self._pos: np.ndarray | None = None  # (n_frames, n_agents, 2) in px
        self._heading: np.ndarray | None = None  # (n_frames, n_agents) radians
        self._phase: np.ndarray | None = None  # (n_frames, n_agents) tail-beat radians
        self._shape: tuple[int, int] | None = None
        self._length_px = 1.0

    def prepare(self, geometry, fps, n_frames, rng) -> None:
        height, width = geometry.screen_h_px, geometry.screen_w_px
        self._shape = (height, width)
        self._length_px = max(1.0, geometry.deg_to_px(self.body_size_deg))
        n = self.n_agents
        glide_factor = 0.15  # residual speed fraction during the glide phase

        # Per-frame burst-and-glide speed gate: active for bout_duty of each period.
        step_active = geometry.deg_to_px(self.speed_dps) / float(fps)
        # Per-agent bout phase offset so the school does not pulse in lock-step.
        bout_offset = rng.uniform(0.0, self.bout_period_s, size=n)

        # Initial positions / headings. "school" clusters a tight blob with a
        # shared mean heading; "random" scatters agents with independent headings.
        if self.schooling == "school":
            center = rng.uniform([0.25 * width, 0.25 * height], [0.75 * width, 0.75 * height])
            spread = 0.12 * min(width, height)
            pos = center[None, :] + rng.normal(0.0, spread, size=(n, 2))
            mean_heading = rng.uniform(0.0, 2.0 * np.pi)
            heading = mean_heading + rng.normal(0.0, np.radians(15.0), size=n)
            turn_sigma = np.radians(3.0)  # cohesive: small per-frame heading jitter
        else:
            pos = rng.uniform([0.0, 0.0], [width, height], size=(n, 2))
            heading = rng.uniform(0.0, 2.0 * np.pi, size=n)
            turn_sigma = np.radians(8.0)  # independent random walk in heading

        # Per-agent tail-beat phase offset so beats are not synchronized.
        tail_phase0 = rng.uniform(0.0, 2.0 * np.pi, size=n)

        pos = pos.astype(np.float64)
        heading = heading.astype(np.float64)
        positions = np.empty((n_frames, n, 2), dtype=np.float32)
        headings = np.empty((n_frames, n), dtype=np.float32)
        phases = np.empty((n_frames, n), dtype=np.float32)

        for f in range(n_frames):
            t = f / float(fps)
            positions[f] = pos
            headings[f] = heading
            phases[f] = tail_phase0 + 2.0 * np.pi * self.tail_beat_hz * t

            # Bout schedule: active fraction of each period bursts, else glides.
            cycle_phase = ((t + bout_offset) % self.bout_period_s) / self.bout_period_s
            active = cycle_phase < self.bout_duty
            speed = np.where(active, step_active, step_active * glide_factor)

            # Advance heading by a small random walk, then translate along it.
            heading = heading + rng.normal(0.0, turn_sigma, size=n)
            pos[:, 0] += np.cos(heading) * speed
            pos[:, 1] += np.sin(heading) * speed
            pos[:, 0] %= width
            pos[:, 1] %= height

        self._pos = positions
        self._heading = headings
        self._phase = phases

    def _body_polygon(self, center: np.ndarray, heading: float, phase: float) -> np.ndarray:
        """Tapered, tail-bent fish outline (px, int32) for ``cv2.fillPoly``.

        The body is sampled along its midline from snout (s=+0.5) to tail tip
        (s=-0.5). Half-width tapers to a near-point at both ends and is widest just
        behind the head. The midline is laterally displaced by a tail-beat
        oscillation that grows toward the tail, bending the posterior body.
        """
        length = self._length_px
        n_seg = 9
        s = np.linspace(0.5, -0.5, n_seg)  # head (+) -> tail (-), fraction of length

        # Tapered half-width profile (fraction of length), fat midbody to thin tail.
        half_w = 0.18 * length * np.clip(1.0 - (2.0 * (s - 0.1)) ** 2, 0.02, 1.0)
        half_w[0] = 0.01 * length  # sharp snout
        half_w[-1] = 0.01 * length  # tail tip

        # Lateral midline displacement: grows toward the tail (posterior bending).
        tail_weight = np.clip(0.5 - s, 0.0, 1.0) ** 2
        lateral = 0.22 * length * np.sin(phase) * tail_weight

        # Body-frame axes: forward along heading, lateral perpendicular to it.
        fwd = np.array([np.cos(heading), np.sin(heading)], dtype=np.float64)
        perp = np.array([-np.sin(heading), np.cos(heading)], dtype=np.float64)

        midline = center[None, :] + (s * length)[:, None] * fwd[None, :] + lateral[:, None] * perp[None, :]
        left = midline + half_w[:, None] * perp[None, :]
        right = midline - half_w[:, None] * perp[None, :]
        # Walk one side head->tail, return the other tail->head to close the loop.
        outline = np.concatenate([left, right[::-1]], axis=0)
        return np.round(outline).astype(np.int32)

    def render(self, frame_index, t, geometry):
        height, width = self._shape
        alpha = np.zeros((height, width), dtype=np.float32)
        positions = self._pos[frame_index]
        headings = self._heading[frame_index]
        phases = self._phase[frame_index]
        for agent in range(self.n_agents):
            poly = self._body_polygon(positions[agent].astype(np.float64), float(headings[agent]), float(phases[agent]))
            # Accumulate coverage; max keeps alpha in [0, 1] where bodies overlap.
            fish = np.zeros((height, width), dtype=np.float32)
            cv2.fillPoly(fish, [poly], 1.0, lineType=cv2.LINE_AA)
            np.maximum(alpha, fish, out=alpha)

        body = (
            self.mean_lum * (1.0 - self.contrast)
            if self.polarity == "dark"
            else self.mean_lum * (1.0 + self.contrast)
        )
        body = float(np.clip(body, 0.0, 1.0))
        lum = np.full((height, width), body, dtype=np.float32)
        return lum, alpha

    def validate(self, geometry, fps):
        errors = []
        if self.n_agents < 1:
            errors.append(f"conspecific n_agents {self.n_agents} must be >= 1.")
        if not 0.0 < self.bout_duty <= 1.0:
            errors.append(f"conspecific bout_duty {self.bout_duty} must be in (0, 1].")
        if self.bout_period_s <= 0.0:
            errors.append(f"conspecific bout_period_s {self.bout_period_s} must be > 0.")
        if self.schooling not in ("school", "random"):
            errors.append(f"conspecific schooling {self.schooling!r} must be 'school' or 'random'.")
        if self.polarity not in ("dark", "light"):
            errors.append(f"conspecific polarity {self.polarity!r} must be 'dark' or 'light'.")
        # Tail-beat Nyquist: need >= 2 frames per beat to avoid temporal aliasing.
        if self.tail_beat_hz >= 0.5 * float(fps):
            errors.append(
                f"conspecific tail_beat_hz {self.tail_beat_hz} >= Nyquist 0.5*fps "
                f"({0.5 * float(fps):.1f} Hz at {fps} fps); tail-beat will alias."
            )
        return errors

    def describe(self):
        return {
            "type": self.type,
            "n_agents": self.n_agents,
            "body_size_deg": self.body_size_deg,
            "tail_beat_hz": self.tail_beat_hz,
            "bout_period_s": self.bout_period_s,
            "bout_duty": self.bout_duty,
            "speed_dps": self.speed_dps,
            "schooling": self.schooling,
            "polarity": self.polarity,
            "mean_lum": self.mean_lum,
            "contrast": self.contrast,
        }
