"""Render pipeline: spec -> linear frames -> gamma -> sync marker -> lossless write + manifest.

The pipeline is deterministic in (spec, seed). Lossless is the default because lossy
codecs inject exactly the structure a vision experiment measures (banding, block edges,
temporal smearing). A rendered-vs-decoded difference is checked and recorded.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .geometry import DisplayGeometry
from .scene import Scene
from .spec import ExperimentSpec, config_hash

# Per-frame sync marker encoding (baked into a screen corner so a photodiode trace
# recovers exact frame timing at playback without trusting the OS scheduler).
SYNC_MARKER = {
    "position": "top-left",
    "square_px": 16,
    "margin_px": 4,
    "n_bits": 12,
    "bit_order": "lsb-first (square 1 = bit 0)",
    "levels": "max=1, min=0",
    "clock": "square 0 alternates every frame; squares 1..n encode frame_index",
}


def _gamma_encode(linear: np.ndarray, gamma: float) -> np.ndarray:
    return np.clip(linear, 0.0, 1.0) ** (1.0 / float(gamma))


def _quantize(values01: np.ndarray, bit_depth: int) -> np.ndarray:
    clipped = np.clip(values01, 0.0, 1.0)
    if bit_depth == 16:
        return (clipped * 65535.0 + 0.5).astype(np.uint16)
    return (clipped * 255.0 + 0.5).astype(np.uint8)


def _bake_sync_marker(frame_rgb: np.ndarray, frame_index: int, max_level: int) -> None:
    square = SYNC_MARKER["square_px"]
    margin = SYNC_MARKER["margin_px"]
    n_bits = SYNC_MARKER["n_bits"]
    for slot in range(n_bits + 1):
        x0 = margin + slot * square
        y0 = margin
        if slot == 0:
            value = max_level if (frame_index % 2 == 0) else 0
        else:
            value = max_level if ((frame_index >> (slot - 1)) & 1) else 0
        frame_rgb[y0 : y0 + square, x0 : x0 + square, :] = value


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parent),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _fps_warnings(geometry: DisplayGeometry, fps: float) -> list[str]:
    refresh = geometry.refresh_hz
    ratio_a = refresh / fps
    ratio_b = fps / refresh
    integer = abs(ratio_a - round(ratio_a)) < 1e-6 or abs(ratio_b - round(ratio_b)) < 1e-6
    if not integer:
        return [
            f"fps {fps} is not an integer multiple/divisor of display refresh {refresh} Hz; "
            "playback will resample into judder. Render natively to the playback rate."
        ]
    return []


def render_experiment(spec: ExperimentSpec, out_dir: str | Path, created_utc: str | None = None) -> dict:
    geometry = spec.display_geometry()
    settings = spec.render_settings()
    fps = float(settings["fps"])
    duration = float(settings["duration_s"])
    bit_depth = int(settings["bit_depth"])
    gamma_policy = str(settings["gamma_policy"])
    codec = str(settings["codec"])
    use_sync = bool(settings["sync_marker"])
    n_frames = max(1, int(round(duration * fps)))

    scene = spec.build_scene()

    errors = scene.validate(geometry, fps)
    if errors:
        raise ValueError("Spec validation failed:\n  - " + "\n  - ".join(errors))
    warnings = _fps_warnings(geometry, fps)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(spec.seed)
    scene.prepare(geometry, fps, n_frames, rng)

    max_level = 65535 if bit_depth == 16 else 255

    frames_dir = None
    ffv1_writer = None
    if codec == "png_sequence":
        frames_dir = out / "frames"
        frames_dir.mkdir(exist_ok=True)
    elif codec == "ffv1":
        import imageio_ffmpeg

        ffv1_writer = imageio_ffmpeg.write_frames(
            str(out / f"{spec.name}.mkv"),
            size=(geometry.screen_w_px, geometry.screen_h_px),
            fps=fps,
            codec="ffv1",
            pix_fmt_in="rgb24",
            macro_block_size=1,
        )
        ffv1_writer.send(None)
    else:
        raise ValueError(f"unknown codec {codec!r} (use 'png_sequence' or 'ffv1')")

    first_frame = None
    first_path = None
    for frame_index in range(n_frames):
        t = frame_index / fps
        composite = scene.render(frame_index, t, geometry)
        if gamma_policy == "encode_into_file":
            display = _gamma_encode(composite, geometry.gamma)
        elif gamma_policy == "linear_record_only":
            display = composite
        else:
            raise ValueError(f"unknown gamma_policy {gamma_policy!r}")

        quantized = _quantize(display, bit_depth)
        frame_rgb = np.repeat(quantized[:, :, None], 3, axis=2)
        if use_sync:
            _bake_sync_marker(frame_rgb, frame_index, max_level)

        if codec == "png_sequence":
            frame_path = frames_dir / f"frame_{frame_index:06d}.png"
            cv2.imwrite(str(frame_path), frame_rgb)
            if frame_index == 0:
                first_frame = frame_rgb.copy()
                first_path = frame_path
        else:
            ffv1_writer.send(np.ascontiguousarray(frame_rgb.astype(np.uint8)))

    if ffv1_writer is not None:
        ffv1_writer.close()

    qa = {"codec": codec, "lossless_verified": None}
    if codec == "png_sequence" and first_path is not None:
        decoded = cv2.imread(str(first_path), cv2.IMREAD_UNCHANGED)
        if decoded.ndim == 2:
            decoded = np.repeat(decoded[:, :, None], 3, axis=2)
        max_abs_diff = int(np.max(np.abs(decoded.astype(np.int64) - first_frame.astype(np.int64))))
        qa["max_abs_diff_frame0"] = max_abs_diff
        qa["lossless_verified"] = max_abs_diff == 0

    manifest = {
        "generator": "fish-stimulus-platform",
        "config_hash": config_hash(spec),
        "git_commit": _git_commit(),
        "created_utc": created_utc or datetime.now(timezone.utc).isoformat(),
        "name": spec.name,
        "seed": spec.seed,
        "fps": fps,
        "n_frames": n_frames,
        "duration_s": duration,
        "bit_depth": bit_depth,
        "gamma_policy": gamma_policy,
        "codec": codec,
        "geometry": geometry.to_dict(),
        "render": settings,
        "scene": scene.describe(),
        "sync_marker": SYNC_MARKER if use_sync else None,
        "validation_warnings": warnings,
        "qa": qa,
    }
    (out / f"{spec.name}.manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {"out_dir": str(out), "n_frames": n_frames, "manifest": manifest}
