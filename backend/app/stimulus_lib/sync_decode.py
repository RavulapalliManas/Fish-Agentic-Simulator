"""Decode the baked per-frame sync marker and a photodiode trace -> frame timing.

The render pipeline bakes a row of code squares into a screen corner (see
``render._bake_sync_marker``): slot 0 is a CLOCK that flips every frame, and slots
1..n_bits encode the frame index LSB-first (slot 1 = bit 0), each square ``max_level``
for a 1-bit and 0 for a 0-bit. This module reads those squares back out of the written
frames so a recovered frame index can be checked against the manifest, and turns a
photodiode trace of the clock square into measured frame onsets — recovering exact
timing at playback without trusting the OS scheduler.

Everything here is pure and deterministic; it depends only on numpy + cv2.
"""

from __future__ import annotations

import glob
from pathlib import Path

import cv2
import numpy as np

from .render import SYNC_MARKER


def _code_square_mean(frame: np.ndarray, marker: dict, slot: int) -> float:
    """Mean of channel 0 over the code square at ``slot`` (slot 0 = clock)."""
    square = int(marker["square_px"])
    margin = int(marker["margin_px"])
    x0 = margin + slot * square
    y0 = margin
    region = frame[y0 : y0 + square, x0 : x0 + square]
    if region.ndim == 3:
        region = region[:, :, 0]
    return float(region.mean())


def decode_frame_index(frame_rgb: np.ndarray, marker: dict = SYNC_MARKER, max_level: int = 255) -> int:
    """Recover the frame index encoded in one frame's sync marker.

    Samples each code square (slots 1..n_bits; slot 0 is the clock and carries no
    index information), takes the mean of channel 0, and thresholds at
    ``max_level / 2`` to read each bit. Bits are LSB-first: slot ``i`` is bit
    ``i - 1``. Returns ``sum(bit_i << i)``.
    """
    n_bits = int(marker["n_bits"])
    threshold = max_level / 2.0
    index = 0
    for slot in range(1, n_bits + 1):
        bit = 1 if _code_square_mean(frame_rgb, marker, slot) > threshold else 0
        index |= bit << (slot - 1)
    return index


def decode_sequence(frames_dir: str | Path, marker: dict = SYNC_MARKER) -> list[int]:
    """Decode every ``frame_*.png`` in ``frames_dir``, in sorted (frame) order.

    The renderer zero-pads frame numbers (``frame_%06d.png``) so lexical order is
    numeric order. ``max_level`` is inferred from the written bit depth (uint16 ->
    65535, else 255) so 16-bit renders decode correctly too.
    """
    frames_dir = Path(frames_dir)
    paths = sorted(glob.glob(str(frames_dir / "frame_*.png")))
    decoded: list[int] = []
    for path in paths:
        frame = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if frame is None:
            raise ValueError(f"could not read frame {path!r}")
        max_level = 65535 if frame.dtype == np.uint16 else 255
        decoded.append(decode_frame_index(frame, marker=marker, max_level=max_level))
    return decoded


def analyze_timing(decoded: list[int], expected_n: int | None = None) -> dict:
    """Summarise a decoded index sequence: drops, duplicates, ordering, completeness.

    ``dropped`` and ``duplicated`` are reported against the *observed* index range
    (min..max inclusive); ``out_of_order`` counts decreasing steps; ``ok`` requires a
    monotonic, gapless, duplicate-free sequence that matches ``expected_n`` when given.
    """
    n_decoded = len(decoded)
    out_of_order = sum(1 for i in range(1, n_decoded) if decoded[i] < decoded[i - 1])
    monotonic = out_of_order == 0

    if n_decoded:
        observed = range(min(decoded), max(decoded) + 1)
        present = set(decoded)
        dropped = sorted(set(observed) - present)
        counts: dict[int, int] = {}
        for value in decoded:
            counts[value] = counts.get(value, 0) + 1
        duplicated = sorted(value for value, count in counts.items() if count > 1)
    else:
        dropped = []
        duplicated = []

    ok = (
        monotonic
        and not dropped
        and not duplicated
        and (expected_n is None or n_decoded == expected_n)
    )

    return {
        "n_decoded": n_decoded,
        "monotonic": monotonic,
        "dropped": dropped,
        "duplicated": duplicated,
        "out_of_order": out_of_order,
        "expected_n": expected_n,
        "ok": ok,
    }


def decode_photodiode(times, values, threshold: float | None = None) -> dict:
    """Recover frame onsets from a photodiode trace of the clock square.

    The clock square toggles every frame, so *every* frame boundary is a level
    transition (rising on even->odd, falling on odd->even). Each threshold crossing
    in either direction marks a new frame onset. ``threshold`` defaults to the
    midpoint of the trace's min/max. Returns the onset times, their count, and the
    inter-onset interval statistics.
    """
    times = np.asarray(times, dtype=float)
    values = np.asarray(values, dtype=float)

    if threshold is None:
        threshold = float(values.min() + values.max()) / 2.0 if values.size else 0.0
    threshold = float(threshold)

    digital = values > threshold
    # A crossing is any sample whose side of the threshold differs from the previous.
    crossings = np.flatnonzero(digital[1:] != digital[:-1]) + 1 if digital.size > 1 else np.array([], dtype=int)
    onsets = times[crossings]

    if onsets.size >= 2:
        intervals = np.diff(onsets)
        interval_stats = {
            "mean": float(intervals.mean()),
            "std": float(intervals.std()),
            "min": float(intervals.min()),
            "max": float(intervals.max()),
        }
    else:
        interval_stats = {"mean": None, "std": None, "min": None, "max": None}

    return {
        "onsets": [float(t) for t in onsets],
        "n_onsets": int(onsets.size),
        "threshold": threshold,
        "interval_stats": interval_stats,
    }


def load_photodiode_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Load a two-column ``time,value`` photodiode CSV -> (times, values).

    A single non-numeric header row is tolerated and skipped.
    """
    path = Path(path)
    try:
        data = np.loadtxt(path, delimiter=",")
    except ValueError:
        data = np.loadtxt(path, delimiter=",", skiprows=1)
    data = np.atleast_2d(data)
    if data.shape[1] < 2:
        raise ValueError(f"photodiode CSV {str(path)!r} needs at least two columns (time,value)")
    return data[:, 0].astype(float), data[:, 1].astype(float)
