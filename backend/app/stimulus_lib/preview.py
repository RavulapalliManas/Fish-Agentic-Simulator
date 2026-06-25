"""Fast inspection without a full encode: frames, contact sheets, galleries, diffs.

The render pipeline writes a lossless PNG sequence plus a manifest — the right
artifact to *archive*, the wrong one to *glance at* while authoring a spec or
scanning a sweep. This module is the eyeball layer: it drives the exact same
``Scene`` + gamma path as :mod:`stimulus_lib.render` but keeps every result in
memory as a plain ``numpy`` RGB array, so nothing here touches the filesystem
unless you explicitly :func:`save_image`.

Two ways a thumbnail is sourced:

* from a **spec** — rendered on the fly through the real pipeline (same gamma
  policy, same sync marker, same quantisation), so a preview is bit-faithful to
  what a full render would write;
* from a render **out_dir** — the already-written ``frames/*.png`` are read back,
  so you can inspect an archived render with no re-render cost.

Helpers build on each other: :func:`preview_frame` renders one frame,
:func:`contact_sheet` tiles a handful across time, :func:`gallery` stacks one
contact-sheet row per condition over a whole output tree, and
:func:`diff_image` amplifies the per-pixel difference between two renders so a
regression is visible at a glance. numpy + OpenCV + the existing render only.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .render import _gamma_encode, _quantize, _bake_sync_marker, SYNC_MARKER
from .spec import ExperimentSpec

# A preview tile is downscaled to this width by default so a six-up sheet stays
# small; the helpers never go below a single pixel.
_THUMB_WIDTH_PX = 240


# --------------------------------------------------------------------------- #
# Single-frame rendering through the real Scene + gamma path
# --------------------------------------------------------------------------- #

def _display_from_composite(composite: np.ndarray, geometry, settings: dict) -> np.ndarray:
    """Apply the render's gamma policy to a linear composite -> display values in [0, 1].

    Mirrors the policy switch in :func:`render.render_experiment` so a preview is
    photometrically identical to a full render: ``encode_into_file`` bakes the
    display gamma, ``linear_record_only`` passes linear, ``measured_lut``
    linearises through the measured calibration LUT.
    """
    policy = str(settings["gamma_policy"])
    if policy == "encode_into_file":
        return _gamma_encode(composite, geometry.gamma)
    if policy == "linear_record_only":
        return composite
    if policy == "measured_lut":
        from .calibration import Calibration

        cal_path = settings.get("calibration_file")
        if not cal_path:
            raise ValueError("gamma_policy 'measured_lut' requires render.calibration_file")
        return Calibration.load(cal_path).linearize(composite)
    raise ValueError(f"unknown gamma_policy {policy!r}")


def preview_frame(spec: ExperimentSpec, t: float | None = None) -> np.ndarray:
    """Render ONE frame of *spec* at time *t* and return it as an ``(H, W, 3)`` uint8 array.

    No file is written. The frame goes through the identical pipeline a full
    render uses — ``Scene.render`` -> gamma policy -> quantise -> RGB replicate ->
    optional baked sync marker. For an 8-bit render the returned pixels match
    ``frames/frame_NNNNNN.png`` exactly for the corresponding frame index; a
    16-bit render is rendered at full precision and then downscaled to 8-bit for
    inspection (the contact sheet / gallery / save path is 8-bit throughout).

    Parameters
    ----------
    spec:
        The experiment spec to render.
    t:
        Time in seconds. ``None`` (default) renders the mid-clip frame
        (``n_frames // 2``). Otherwise *t* is snapped to the nearest frame on the
        spec's ``fps`` grid and clamped into ``[0, n_frames - 1]`` so the sync
        marker and motion phase line up with a real frame.

    Returns
    -------
    np.ndarray
        ``(screen_h_px, screen_w_px, 3)`` uint8, in OpenCV-friendly
        channel-replicated form.
    """
    geometry = spec.display_geometry()
    settings = spec.render_settings()
    fps = float(settings["fps"])
    duration = float(settings["duration_s"])
    bit_depth = int(settings["bit_depth"])
    use_sync = bool(settings["sync_marker"])
    n_frames = max(1, int(round(duration * fps)))
    max_level = 65535 if bit_depth == 16 else 255

    if t is None:
        frame_index = n_frames // 2
    else:
        frame_index = int(round(float(t) * fps))
    frame_index = max(0, min(n_frames - 1, frame_index))
    t_eff = frame_index / fps

    scene = spec.build_scene()
    errors = scene.validate(geometry, fps)
    if errors:
        raise ValueError("Spec validation failed:\n  - " + "\n  - ".join(errors))

    rng = np.random.default_rng(spec.seed)
    scene.prepare(geometry, fps, n_frames, rng)

    composite = scene.render(frame_index, t_eff, geometry)
    display = _display_from_composite(composite, geometry, settings)
    quantized = _quantize(display, bit_depth)
    frame_rgb = np.repeat(quantized[:, :, None], 3, axis=2)
    if use_sync:
        _bake_sync_marker(frame_rgb, frame_index, max_level)
    # The contract is a uint8 (H, W, 3); a 16-bit render is downscaled here so the
    # whole preview surface (sheets, gallery, diffs, save) is 8-bit throughout.
    return _to_uint8(frame_rgb)


def preview_lowres(
    spec: ExperimentSpec,
    scale: float = 0.25,
    fps: float = 10.0,
    max_frames: int = 30,
) -> list[np.ndarray]:
    """Render a downscaled, low-frame-rate clip of *spec* — no encode, no files.

    Samples the spec's full duration at the requested *fps* (an inspection rate,
    not the spec's render rate), renders each sampled instant through
    :func:`preview_frame`, and downscales by *scale*. Useful to scrub motion or
    drift while authoring without paying for a full lossless render.

    Parameters
    ----------
    scale:
        Linear downscale factor in ``(0, 1]`` applied to both axes
        (``cv2.INTER_AREA``). ``1.0`` keeps full resolution.
    fps:
        Sampling rate over the clip duration. Capped so at most *max_frames*
        frames are produced.
    max_frames:
        Hard ceiling on the number of returned frames.

    Returns
    -------
    list[np.ndarray]
        Downscaled ``(h, w, 3)`` uint8 frames in time order.
    """
    if not 0.0 < scale <= 1.0:
        raise ValueError(f"scale must be in (0, 1], got {scale}")
    if fps <= 0.0:
        raise ValueError(f"fps must be > 0, got {fps}")
    if max_frames < 1:
        raise ValueError(f"max_frames must be >= 1, got {max_frames}")

    settings = spec.render_settings()
    duration = float(settings["duration_s"])

    n = int(np.floor(duration * fps)) + 1
    n = max(1, min(int(max_frames), n))
    times = np.linspace(0.0, duration, n, endpoint=False) if n > 1 else np.array([duration / 2.0])

    frames: list[np.ndarray] = []
    for t in times:
        frame = preview_frame(spec, float(t))
        frames.append(_downscale(frame, scale))
    return frames


# --------------------------------------------------------------------------- #
# Reading already-rendered frames
# --------------------------------------------------------------------------- #

def _frame_paths(out_dir: Path) -> list[Path]:
    return sorted((out_dir / "frames").glob("frame_*.png"))


def _read_frame_rgb(path: Path) -> np.ndarray:
    """Load a written frame as an ``(H, W, 3)`` array (channel-replicate if grayscale)."""
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"could not read frame {path}")
    if img.ndim == 2:
        img = np.repeat(img[:, :, None], 3, axis=2)
    return img


def _to_uint8(img: np.ndarray) -> np.ndarray:
    """Bring a frame down to 8-bit (16-bit renders are scaled by 1/257)."""
    if img.dtype == np.uint16:
        return (img.astype(np.float64) / 257.0).round().clip(0, 255).astype(np.uint8)
    return img.astype(np.uint8)


# --------------------------------------------------------------------------- #
# Image ops (downscale, label, tile)
# --------------------------------------------------------------------------- #

def _downscale(img: np.ndarray, scale: float) -> np.ndarray:
    if scale >= 1.0:
        return img
    h, w = img.shape[:2]
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _resize_to_width(img: np.ndarray, width: int) -> np.ndarray:
    h, w = img.shape[:2]
    if w == width:
        return img
    scale = width / float(w)
    new_h = max(1, int(round(h * scale)))
    interp = cv2.INTER_AREA if width < w else cv2.INTER_NEAREST
    return cv2.resize(img, (width, new_h), interpolation=interp)


def _label(img: np.ndarray, text: str) -> np.ndarray:
    """Draw a small caption strip along the top of a tile (8-bit RGB in/out)."""
    img = _to_uint8(img).copy()
    if img.ndim == 2:
        img = np.repeat(img[:, :, None], 3, axis=2)
    h, w = img.shape[:2]
    bar_h = max(14, h // 12)
    cv2.rectangle(img, (0, 0), (w, bar_h), (0, 0, 0), thickness=-1)
    font_scale = max(0.32, min(0.6, w / 480.0))
    cv2.putText(
        img,
        text,
        (4, bar_h - 4),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return img


def _tile_row(tiles: list[np.ndarray], pad: int = 4, bg: int = 32) -> np.ndarray:
    """Lay a list of equal-height tiles into a single horizontal strip with padding."""
    if not tiles:
        raise ValueError("cannot tile an empty list of frames")
    h = max(t.shape[0] for t in tiles)
    norm = [_pad_to_height(_to_uint8(t), h) for t in tiles]
    sep = np.full((h, pad, 3), bg, dtype=np.uint8)
    pieces: list[np.ndarray] = []
    for i, tile in enumerate(norm):
        if i:
            pieces.append(sep)
        pieces.append(tile)
    return np.concatenate(pieces, axis=1)


def _pad_to_height(img: np.ndarray, height: int, bg: int = 32) -> np.ndarray:
    h = img.shape[0]
    if h == height:
        return img
    pad = np.full((height - h, img.shape[1], 3), bg, dtype=np.uint8)
    return np.concatenate([img, pad], axis=0)


def _pad_to_width(img: np.ndarray, width: int, bg: int = 32) -> np.ndarray:
    w = img.shape[1]
    if w == width:
        return img
    pad = np.full((img.shape[0], width - w, 3), bg, dtype=np.uint8)
    return np.concatenate([img, pad], axis=1)


def _grid(tiles: list[np.ndarray], cols: int, pad: int = 4, bg: int = 32) -> np.ndarray:
    """Tile thumbnails into a ``cols``-wide grid (last row left-padded with bg)."""
    if not tiles:
        raise ValueError("cannot build a grid from an empty list of tiles")
    cols = max(1, int(cols))
    tiles = [_to_uint8(t) for t in tiles]
    rows: list[np.ndarray] = []
    for start in range(0, len(tiles), cols):
        chunk = tiles[start : start + cols]
        rows.append(_tile_row(chunk, pad=pad, bg=bg))
    width = max(r.shape[1] for r in rows)
    rows = [_pad_to_width(r, width, bg=bg) for r in rows]
    sep = np.full((pad, width, 3), bg, dtype=np.uint8)
    pieces: list[np.ndarray] = []
    for i, row in enumerate(rows):
        if i:
            pieces.append(sep)
        pieces.append(row)
    return np.concatenate(pieces, axis=0)


# --------------------------------------------------------------------------- #
# Sampling timepoints / frames from a source
# --------------------------------------------------------------------------- #

def _evenly_spaced(n_available: int, n_pick: int) -> list[int]:
    """Pick *n_pick* evenly spaced indices from ``range(n_available)`` (deduped)."""
    if n_available <= 0:
        return []
    n_pick = max(1, int(n_pick))
    if n_pick >= n_available:
        return list(range(n_available))
    idx = np.linspace(0, n_available - 1, n_pick)
    return sorted({int(round(i)) for i in idx})


def _thumbs_from_spec(spec: ExperimentSpec, n: int, width: int) -> list[np.ndarray]:
    """Render *n* evenly spaced frames of *spec* across its duration, as labelled thumbs."""
    settings = spec.render_settings()
    fps = float(settings["fps"])
    duration = float(settings["duration_s"])
    n_frames = max(1, int(round(duration * fps)))
    indices = _evenly_spaced(n_frames, n)
    thumbs: list[np.ndarray] = []
    for idx in indices:
        t = idx / fps
        frame = preview_frame(spec, t)
        thumb = _resize_to_width(_to_uint8(frame), width)
        thumbs.append(_label(thumb, f"t={t:.2f}s"))
    return thumbs


def _thumbs_from_dir(out_dir: Path, n: int, width: int) -> list[np.ndarray]:
    """Read *n* evenly spaced written frames from a render directory, as labelled thumbs."""
    paths = _frame_paths(out_dir)
    if not paths:
        raise FileNotFoundError(f"no frames/frame_*.png found in {out_dir}")
    indices = _evenly_spaced(len(paths), n)
    thumbs: list[np.ndarray] = []
    for idx in indices:
        frame = _read_frame_rgb(paths[idx])
        thumb = _resize_to_width(_to_uint8(frame), width)
        thumbs.append(_label(thumb, f"f={idx}"))
    return thumbs


def _is_render_dir(path: Path) -> bool:
    return path.is_dir() and (path / "frames").is_dir()


# --------------------------------------------------------------------------- #
# Public: contact sheet, gallery, diff, save
# --------------------------------------------------------------------------- #

def contact_sheet(source, n: int = 6, cols: int = 6) -> np.ndarray:
    """Tile *n* thumbnails sampled across time into one image.

    Parameters
    ----------
    source:
        Either a render **out_dir** (path-like containing ``frames/frame_*.png``,
        read back) or an :class:`ExperimentSpec` (rendered on the fly via
        :func:`preview_frame`). Timepoints are evenly spaced across the available
        frames / the spec duration.
    n:
        Number of thumbnails to sample.
    cols:
        Columns in the tiled grid; rows wrap as needed.

    Returns
    -------
    np.ndarray
        An ``(H, W, 3)`` uint8 tiled image, wider than a single thumbnail
        whenever ``n > 1``.
    """
    if isinstance(source, ExperimentSpec):
        thumbs = _thumbs_from_spec(source, n, _THUMB_WIDTH_PX)
    else:
        out_dir = Path(source)
        if not _is_render_dir(out_dir):
            raise ValueError(
                f"contact_sheet source {out_dir} is neither an ExperimentSpec nor a "
                "render directory containing frames/"
            )
        thumbs = _thumbs_from_dir(out_dir, n, _THUMB_WIDTH_PX)
    return _grid(thumbs, cols=cols)


def _iter_manifest_dirs(out_root: Path) -> list[Path]:
    """All render directories under *out_root* that own a manifest, in sorted order."""
    manifests = sorted(out_root.rglob("*.manifest.json"))
    seen: list[Path] = []
    for m in manifests:
        parent = m.parent
        if parent not in seen:
            seen.append(parent)
    return seen


def gallery(out_root, n_per: int = 1, cols: int = 4) -> np.ndarray:
    """Stack one contact-sheet row per condition into a grid across an output tree.

    Walks *out_root* for every render directory (one ``*.manifest.json`` apiece),
    builds a small ``n_per``-wide contact-sheet row for each — labelled with the
    condition name from its manifest — and stacks the rows into a single image.
    The cross-condition overview a sweep produces, in one picture.

    Parameters
    ----------
    out_root:
        Directory containing one or more render output directories (searched
        recursively for manifests).
    n_per:
        Thumbnails sampled per condition (the width of each condition's row).
    cols:
        Columns used when tiling each condition's thumbnails (rows wrap if
        ``n_per > cols``).

    Returns
    -------
    np.ndarray
        A non-empty ``(H, W, 3)`` uint8 image: condition rows stacked vertically,
        each padded to a common width.
    """
    root = Path(out_root)
    dirs = _iter_manifest_dirs(root)
    if not dirs:
        raise FileNotFoundError(f"no *.manifest.json found anywhere under {root}")

    rows: list[np.ndarray] = []
    for d in dirs:
        try:
            manifest = json.loads(next(d.glob("*.manifest.json")).read_text(encoding="utf-8"))
            name = manifest.get("name") or d.name
        except Exception:
            name = d.name
        thumbs = _thumbs_from_dir(d, n_per, _THUMB_WIDTH_PX)
        sheet = _grid(thumbs, cols=cols)
        rows.append(_label(sheet, name))

    width = max(r.shape[1] for r in rows)
    rows = [_pad_to_width(r, width) for r in rows]
    sep = np.full((6, width, 3), 32, dtype=np.uint8)
    pieces: list[np.ndarray] = []
    for i, row in enumerate(rows):
        if i:
            pieces.append(sep)
        pieces.append(row)
    return np.concatenate(pieces, axis=0)


def diff_image(dir_a, dir_b, frame_index: int = 0) -> np.ndarray:
    """Absolute difference of matching frames from two renders, amplified for visibility.

    Reads ``frames/frame_{frame_index:06d}.png`` (falling back to positional
    indexing) from each directory, takes the per-pixel absolute difference, and
    scales it so even a one-code difference is visible. Identical renders yield a
    near-black image (max code < 2); a regression lights up where the pixels
    diverged.

    Parameters
    ----------
    dir_a, dir_b:
        Two render output directories to compare.
    frame_index:
        Which frame to diff (matched by index in each sequence).

    Returns
    -------
    np.ndarray
        An ``(H, W, 3)`` uint8 amplified-difference image.
    """
    a = _read_frame_at(Path(dir_a), frame_index)
    b = _read_frame_at(Path(dir_b), frame_index)
    if a.shape != b.shape:
        raise ValueError(
            f"frame shapes differ between renders: {a.shape} vs {b.shape}; cannot diff"
        )
    diff = np.abs(_to_uint8(a).astype(np.int16) - _to_uint8(b).astype(np.int16))
    # Amplify so sub-perceptual differences are visible, then clamp at white.
    amplified = np.clip(diff * 8, 0, 255).astype(np.uint8)
    return amplified


def _read_frame_at(out_dir: Path, frame_index: int) -> np.ndarray:
    """Load ``frame_{index:06d}.png`` if present, else the *frame_index*-th sorted frame."""
    direct = out_dir / "frames" / f"frame_{frame_index:06d}.png"
    if direct.is_file():
        return _read_frame_rgb(direct)
    paths = _frame_paths(out_dir)
    if not paths:
        raise FileNotFoundError(f"no frames/frame_*.png found in {out_dir}")
    if not 0 <= frame_index < len(paths):
        raise IndexError(
            f"frame_index {frame_index} out of range for {len(paths)} frames in {out_dir}"
        )
    return _read_frame_rgb(paths[frame_index])


def save_image(img: np.ndarray, path: str | Path) -> str:
    """Write *img* (an ``(H, W, 3)`` array from any helper here) to *path* as PNG/JPEG.

    The parent directory is created if needed. Returns the absolute path written.
    OpenCV writes BGR-ordered bytes; the channel-replicated grayscale frames this
    module produces are order-agnostic, and difference/label colours are
    intentionally neutral, so no BGR<->RGB swap is applied.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), np.ascontiguousarray(img)):
        raise RuntimeError(f"cv2.imwrite failed for {out}")
    return str(out.resolve())
