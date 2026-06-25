"""Extra pixel-level QA checks + batch QA aggregation across many renders.

``qa_report.build_qa_report`` produces one rich per-render *sheet*; this module is
its terser, machine-readable sibling. It adds two pixel pathologies the sheet does
not score — **banding** (quantisation plateaus / a combed histogram in a region that
should be a smooth gradient) and **clipping** (a frame pinned at code 0 or full
scale) — plus a luminance-match check used to confirm a looming stimulus and its
dimming control deliver the same mean light. It then rolls a one-line pass/fail
*card* per render and aggregates every render under a tree into a single batch HTML.

Why these live here and not in the renderer: a lossless render can still *look*
wrong. Banding betrays an under-bit-depth gradient or a lossy round-trip; clipping
betrays a stimulus authored past the displayable range; a luminance mismatch
silently confounds a looming/dimming comparison. None of these move the lossless
gate, so they need their own eyes on the actual pixels.

    from stimulus_lib.qa_checks import qa_card, batch_qa_report
    card = qa_card("output/stimuli/demo")          # one render -> pass/fail card
    summary = batch_qa_report("output/stimuli")    # many renders -> batch_qa.html

numpy + cv2 + json only; the HTML is assembled by string so there is no template
dependency (matching ``qa_report``'s house style). The card reads the manifest for
provenance/lossless/Nyquist and re-measures a mid frame for clipping/banding.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import cv2
import numpy as np

from .render import SYNC_MARKER

# A "combed" histogram is the signature of banding: occupied code levels separated
# by empty ones. We also look at how often neighbouring pixels share an identical
# code along a smooth ramp — long flats are quantisation plateaus.
_BANDING_BINS = 256
# Above this score a frame's smooth regions are judged visibly banded. Posterised
# (few-level) content lands well above; a full-range smooth gradient well below.
_BANDING_THRESHOLD = 0.30
# Clipping is only flagged when a non-trivial fraction of the frame is pinned.
_CLIP_FRAC_THRESHOLD = 0.02
# Two renders' mean luminance count as matched within this absolute [0,1] gap.
_LUMINANCE_MATCH_TOL = 0.02


# --------------------------------------------------------------------------- #
# Pixel-level primitives (operate on a single grayscale frame, any dtype)
# --------------------------------------------------------------------------- #

def detect_banding(gray: np.ndarray) -> dict:
    """Score quantisation banding in a (ideally smooth) grayscale frame.

    Two cheap, complementary signatures are combined:

    * **Combed histogram** — in a smoothly varying region the occupied code levels
      should be contiguous; banding leaves *empty* levels wedged between occupied
      ones. We measure the fraction of empty bins that fall strictly between the
      lowest and highest occupied level (interior gaps only, so a frame that simply
      does not span the full range is not penalised).
    * **Adjacent-equal runs** — along a true gradient consecutive pixels rarely hold
      the *exact* same code; a posterised ramp holds each plateau for many pixels.
      We take the fraction of horizontally adjacent pixel pairs that are equal.

    ``banding_score`` is the larger of the two (each in ``[0, 1]``); ``banded`` is
    ``True`` once it clears the module threshold. Higher = more banded, so a
    posterised gradient scores strictly above the smooth gradient it was made from.
    """
    arr = np.asarray(gray)
    if arr.ndim == 3:
        arr = arr[:, :, 0]
    flat = arr.astype(np.float64).ravel()
    if flat.size == 0:
        return {"banding_score": 0.0, "banded": False}

    # Normalise to 0..255 codes so the histogram comb is bit-depth independent.
    vmin = float(flat.min())
    vmax = float(flat.max())
    span = vmax - vmin
    if span <= 0:  # a flat frame has no gradient to band
        return {
            "banding_score": 0.0,
            "banded": False,
            "comb_score": 0.0,
            "adjacent_equal_frac": 0.0,
        }
    codes = np.round((flat - vmin) / span * (_BANDING_BINS - 1)).astype(np.int64)

    counts = np.bincount(codes, minlength=_BANDING_BINS)
    occupied = np.flatnonzero(counts > 0)
    lo, hi = int(occupied[0]), int(occupied[-1])
    interior = counts[lo : hi + 1]
    interior_levels = interior.size
    empty_interior = int(np.count_nonzero(interior == 0))
    # Fraction of the occupied code *range* that is empty -> the comb's gappiness.
    comb_score = empty_interior / float(interior_levels) if interior_levels > 0 else 0.0

    # Adjacent-equal fraction along rows (the gradient direction for a ramp; for a
    # 2-D gradient either axis works, rows are sufficient and cheap).
    if arr.shape[-1] >= 2:
        row_codes = np.round((arr.astype(np.float64) - vmin) / span * (_BANDING_BINS - 1))
        equal = row_codes[..., 1:] == row_codes[..., :-1]
        adjacent_equal_frac = float(np.count_nonzero(equal)) / float(equal.size)
    else:
        adjacent_equal_frac = 0.0

    banding_score = max(comb_score, adjacent_equal_frac)
    return {
        "banding_score": float(banding_score),
        "banded": bool(banding_score >= _BANDING_THRESHOLD),
        "comb_score": float(comb_score),
        "adjacent_equal_frac": float(adjacent_equal_frac),
    }


def clipping_report(gray: np.ndarray, bit_depth: int = 8) -> dict:
    """Fraction of pixels pinned at the min (code 0) or max (full scale) level.

    A stimulus authored past the displayable range clips, destroying contrast at the
    extremes; this reports how much of the frame sits on each rail. ``clips`` is
    ``True`` when either rail holds more than a small fraction of the frame. On a
    0..255 ramp both fractions are ~1/256; on an all-zero frame ``frac_at_min`` is
    exactly ``1.0``.
    """
    arr = np.asarray(gray)
    if arr.ndim == 3:
        arr = arr[:, :, 0]
    flat = arr.ravel()
    n = flat.size
    if n == 0:
        return {"frac_at_min": 0.0, "frac_at_max": 0.0, "clips": False}

    max_level = 65535 if int(bit_depth) == 16 else 255
    frac_at_min = float(np.count_nonzero(flat <= 0)) / n
    frac_at_max = float(np.count_nonzero(flat >= max_level)) / n
    clips = (frac_at_min > _CLIP_FRAC_THRESHOLD) or (frac_at_max > _CLIP_FRAC_THRESHOLD)
    return {
        "frac_at_min": frac_at_min,
        "frac_at_max": frac_at_max,
        "clips": bool(clips),
        "bit_depth": int(bit_depth),
    }


# --------------------------------------------------------------------------- #
# Frame / manifest access (mirrors qa_report's conventions, kept local so this
# module edits no other file)
# --------------------------------------------------------------------------- #

def _find_manifest(out_dir: Path) -> Path:
    """The single ``*.manifest.json`` a render directory owns (error otherwise)."""
    manifests = sorted(out_dir.glob("*.manifest.json"))
    if not manifests:
        raise FileNotFoundError(f"no *.manifest.json found in {out_dir}")
    if len(manifests) > 1:
        raise ValueError(
            f"expected exactly one *.manifest.json in {out_dir}, found {len(manifests)}: "
            + ", ".join(m.name for m in manifests)
        )
    return manifests[0]


def _frame_paths(out_dir: Path) -> list[Path]:
    return sorted((out_dir / "frames").glob("frame_*.png"))


def _read_gray(path: Path) -> np.ndarray:
    """Load a frame and return channel 0 as float (the render writes a grayscale
    value replicated across RGB, so channel 0 carries the luminance code)."""
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"could not read frame {path}")
    if img.ndim == 2:
        return img.astype(np.float64)
    return img[:, :, 0].astype(np.float64)


def _sync_marker_box() -> tuple[int, int]:
    """Pixel extent (rows, cols) of the top-left sync-marker block to exclude.

    Mirrors ``render._bake_sync_marker``: ``n_bits + 1`` squares from a margin, plus
    a one-square pad so anti-marker edges never enter the stats. The marker's hard
    0/max squares would otherwise read as both clipping *and* banding.
    """
    square = int(SYNC_MARKER["square_px"])
    margin = int(SYNC_MARKER["margin_px"])
    n_bits = int(SYNC_MARKER["n_bits"])
    cols = margin + (n_bits + 1) * square + square  # +square pad
    rows = margin + square + square
    return rows, cols


def _mask_sync_corner(gray: np.ndarray, sync_present: bool) -> np.ndarray:
    """Return *gray* with the sync-marker corner blanked to its own median.

    Clipping/banding are measured over a region that should be smooth; the baked
    marker is neither, so we overwrite that corner with the frame's median code
    (a value that neither clips nor adds a histogram spike) rather than dropping
    pixels, so the array stays 2-D for the adjacent-equal pass.
    """
    if not sync_present:
        return gray
    rows, cols = _sync_marker_box()
    rows = min(rows, gray.shape[0])
    cols = min(cols, gray.shape[1])
    if rows <= 0 or cols <= 0:
        return gray
    out = gray.copy()
    fill = float(np.median(gray))
    out[:rows, :cols] = fill
    return out


def _mid_frame_index(n: int) -> int:
    return n // 2 if n > 0 else 0


# --------------------------------------------------------------------------- #
# Nyquist re-check from the manifest (the renderer already rejects past-Nyquist
# specs; here we re-confirm from the authored scene + geometry for the card)
# --------------------------------------------------------------------------- #

def _nyquist_ok(manifest: dict) -> tuple[bool, list[dict]]:
    """Re-verify every spatial-frequency-bearing layer sits under the display's
    Nyquist ceiling (``geometry.max_cpd``).

    A successful render already passed ``Scene.validate``; this is a cheap,
    self-contained confirmation for the card so a hand-edited manifest cannot claim
    a clean render past Nyquist. Returns ``(ok, offenders)``.
    """
    geo = manifest.get("geometry") or {}
    max_cpd = geo.get("max_cpd")
    scene = manifest.get("scene") or []
    offenders: list[dict] = []
    if max_cpd is None:
        return True, offenders  # no ceiling recorded -> cannot judge, do not fail
    max_cpd = float(max_cpd)
    for i, layer in enumerate(scene):
        stim = layer.get("stimulus") or {}
        # Any key whose name carries a cycles-per-degree spatial frequency.
        for key, value in stim.items():
            if "cpd" in key and isinstance(value, (int, float)):
                if float(value) > max_cpd + 1e-9:
                    offenders.append(
                        {"layer": i, "type": stim.get("type"), key: float(value), "max_cpd": max_cpd}
                    )
    return (len(offenders) == 0), offenders


# --------------------------------------------------------------------------- #
# Luminance match (looming vs dimming control)
# --------------------------------------------------------------------------- #

def _mean_luminance(out_dir: Path) -> tuple[float, int]:
    """Mean normalised luminance over all frames of a render (sync corner masked).

    Returns ``(mean01, n_frames)``. The mean is taken in normalised ``[0, 1]`` so
    8- and 16-bit renders are directly comparable.
    """
    out_dir = Path(out_dir)
    manifest = json.loads(_find_manifest(out_dir).read_text(encoding="utf-8"))
    bit_depth = int(manifest.get("bit_depth", 8))
    sync_present = bool(manifest.get("sync_marker"))
    max_level = 65535.0 if bit_depth == 16 else 255.0

    frames = _frame_paths(out_dir)
    if not frames:
        raise FileNotFoundError(f"no frames/ PNG sequence in {out_dir} (ffv1 renders are not supported here)")

    rows, cols = _sync_marker_box() if sync_present else (0, 0)
    total = 0.0
    count = 0
    for path in frames:
        gray = _read_gray(path)
        if sync_present:
            r = min(rows, gray.shape[0])
            c = min(cols, gray.shape[1])
            mask = np.ones(gray.shape, dtype=bool)
            mask[:r, :c] = False
            sampled = gray[mask]
            if sampled.size == 0:
                sampled = gray.ravel()
        else:
            sampled = gray.ravel()
        total += float(sampled.sum())
        count += int(sampled.size)
    mean01 = (total / count) / max_level if count else 0.0
    return mean01, len(frames)


def luminance_match_report(dir_a, dir_b) -> dict:
    """Compare the mean luminance of two renders (e.g. looming vs its dimming control).

    A looming/dimming comparison is only clean if both deliver the same average
    light; a mismatch confounds the contrast of the two conditions. Returns the two
    means (normalised ``[0, 1]``), their absolute difference, and ``matched`` (within
    the module tolerance).
    """
    mean_a, n_a = _mean_luminance(Path(dir_a))
    mean_b, n_b = _mean_luminance(Path(dir_b))
    abs_diff = abs(mean_a - mean_b)
    return {
        "mean_a": float(mean_a),
        "mean_b": float(mean_b),
        "abs_diff": float(abs_diff),
        "matched": bool(abs_diff <= _LUMINANCE_MATCH_TOL),
        "n_frames_a": int(n_a),
        "n_frames_b": int(n_b),
    }


# --------------------------------------------------------------------------- #
# Per-render pass/fail card
# --------------------------------------------------------------------------- #

def qa_card(out_dir) -> dict:
    """Produce a compact pass/fail QA card for one render directory.

    Reads the manifest for provenance + the lossless gate, re-derives the Nyquist
    check from the authored scene, and re-measures a mid frame for clipping and
    banding. Each entry in ``checks`` is ``{passed: bool, ...detail}``; the card's
    top-level ``passed`` is the conjunction of every check.

    Notes
    -----
    * ``lossless`` and ``nyquist_ok`` are the *hard gates* — they encode
      reproducibility (byte round-trip) and physical validity (no aliasing), which a
      correct render must satisfy regardless of content.
    * ``clip`` and ``banding`` are **advisory**: they are measured and reported but do
      not sink the card, because a legitimate high-contrast stimulus is *meant* to hit
      the rails (a dark looming disc or dark flash reaches code 0) and a hard-edged
      grating/checkerboard is intrinsically "banded". They flag *unexpected* clipping
      or banding for a human to eyeball, not an automatic failure.
    * ``lossless`` is ``N/A`` (passed True) for ``ffv1`` renders, whose round-trip
      diff the manifest records as ``None`` — matching the renderer's own policy.
    """
    out_dir = Path(out_dir)
    manifest_path = _find_manifest(out_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    name = manifest.get("name") or manifest_path.stem.replace(".manifest", "")
    bit_depth = int(manifest.get("bit_depth", 8))
    sync_present = bool(manifest.get("sync_marker"))

    checks: dict[str, dict] = {}

    # --- lossless gate (straight from the manifest) ---
    qa = manifest.get("qa") or {}
    lossless_verified = qa.get("lossless_verified")
    checks["lossless"] = {
        # ffv1 reports None -> not a failure, just unverifiable here.
        "passed": lossless_verified is not False,
        "lossless_verified": lossless_verified,
        "max_abs_diff_frame0": qa.get("max_abs_diff_frame0"),
        "codec": qa.get("codec") or manifest.get("codec"),
    }

    # --- Nyquist re-check (authored scene vs display ceiling) ---
    nyq_ok, offenders = _nyquist_ok(manifest)
    checks["nyquist_ok"] = {
        "passed": bool(nyq_ok),
        "max_cpd": (manifest.get("geometry") or {}).get("max_cpd"),
        "offenders": offenders,
    }

    # --- pixel checks on a mid frame ---
    frames = _frame_paths(out_dir)
    if frames:
        mid = frames[_mid_frame_index(len(frames))]
        gray = _read_gray(mid)
        smooth = _mask_sync_corner(gray, sync_present)
        clip = clipping_report(smooth, bit_depth=bit_depth)
        band = detect_banding(smooth)
        # clip + banding are advisory: legitimate high-contrast / hard-edged stimuli
        # hit the rails and look "banded", so they are reported, not gated.
        checks["clip"] = {"passed": True, "advisory": True, **clip}
        checks["banding"] = {"passed": True, "advisory": True, **band}
        checks["frames_present"] = {"passed": True, "n_frames": len(frames)}
    else:
        # No PNG sequence (e.g. an ffv1 .mkv render): pixel checks unavailable.
        checks["clip"] = {"passed": True, "advisory": True, "note": "no frames/ PNG sequence (ffv1?)"}
        checks["banding"] = {"passed": True, "advisory": True, "note": "no frames/ PNG sequence (ffv1?)"}
        checks["frames_present"] = {"passed": True, "n_frames": 0, "note": "ffv1 render or empty"}

    passed = all(c.get("passed", False) for c in checks.values())
    return {
        "name": name,
        "config_hash": manifest.get("config_hash"),
        "out_dir": str(out_dir.resolve()),
        "checks": checks,
        "passed": bool(passed),
    }


# --------------------------------------------------------------------------- #
# Batch aggregation -> HTML
# --------------------------------------------------------------------------- #

def _find_render_dirs(out_root: Path) -> list[Path]:
    """Every render directory under *out_root*: a directory holding exactly one
    ``*.manifest.json``. Sorted by path for deterministic batch order."""
    out_root = Path(out_root)
    dirs = {p.parent for p in out_root.rglob("*.manifest.json")}
    return sorted(dirs)


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _badge(ok: object) -> str:
    if ok is True:
        return '<span class="badge pass">PASS</span>'
    if ok is False:
        return '<span class="badge fail">FAIL</span>'
    return '<span class="badge unknown">N/A</span>'


def _check_cell(check: dict) -> str:
    """Render one check as a small badge + its salient number(s)."""
    if not isinstance(check, dict):
        return _esc(check)
    badge = _badge(check.get("passed"))
    detail_keys = (
        "lossless_verified",
        "max_cpd",
        "frac_at_min",
        "frac_at_max",
        "banding_score",
        "n_frames",
    )
    bits = []
    for key in detail_keys:
        if key in check and check[key] is not None:
            val = check[key]
            if isinstance(val, float):
                bits.append(f"{key}={val:.4g}")
            else:
                bits.append(f"{key}={val}")
    detail = ("<br><span class='detail'>" + _esc(", ".join(bits)) + "</span>") if bits else ""
    advisory = " <span class='detail'>(advisory)</span>" if check.get("advisory") else ""
    return f"{badge}{advisory}{detail}"


def _batch_html(cards: list[dict], summary: dict) -> str:
    check_names: list[str] = []
    for card in cards:
        for key in card.get("checks", {}):
            if key not in check_names:
                check_names.append(key)

    head = "<tr><th>render</th><th>config_hash</th><th>overall</th>"
    head += "".join(f"<th>{_esc(c)}</th>" for c in check_names) + "</tr>"

    rows = [head]
    for card in cards:
        checks = card.get("checks", {})
        cells = [
            f"<td class='name'>{_esc(card.get('name'))}</td>",
            f"<td class='hash' title='{_esc(card.get('out_dir'))}'>{_esc((card.get('config_hash') or '')[:12])}</td>",
            f"<td>{_badge(card.get('passed'))}</td>",
        ]
        for cname in check_names:
            cells.append(f"<td>{_check_cell(checks.get(cname, {'passed': None}))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    table = "<table class='cards'>" + "\n".join(rows) + "</table>"

    n_total = summary["passed"] + summary["failed"]
    overall = _badge(summary["failed"] == 0 and n_total > 0)
    style = """
:root { color-scheme: light dark; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
       margin: 0; padding: 1.5rem 2rem; color: #1a1a1a; background: #fafafa; }
h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
.subtitle { color: #555; margin: 0 0 1.25rem; font-size: .9rem; }
table.cards { border-collapse: collapse; width: 100%; font-size: .85rem;
              background: #fff; }
table.cards th, table.cards td { border: 1px solid #e3e3e3; padding: .4rem .55rem;
                                 text-align: left; vertical-align: top; }
table.cards th { background: #f0f0f0; position: sticky; top: 0; }
td.name { font-weight: 600; }
td.hash { font-family: ui-monospace, monospace; color: #555; }
.detail { color: #777; font-size: .75rem; font-family: ui-monospace, monospace; }
.badge { font-size: .72rem; padding: .12rem .5rem; border-radius: 999px;
         font-weight: 700; }
.badge.pass { background: #1f8b4c; color: #fff; }
.badge.fail { background: #c0392b; color: #fff; }
.badge.unknown { background: #888; color: #fff; }
.summary { font-size: 1rem; margin: 0 0 1.25rem; }
""".strip()

    return (
        "<!DOCTYPE html>\n<html lang='en'>\n<head>\n<meta charset='utf-8'>\n"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>\n"
        "<title>Batch QA report</title>\n"
        f"<style>{style}</style>\n</head>\n<body>\n"
        "<h1>Batch QA report</h1>\n"
        f"<p class='subtitle'>{len(cards)} render(s) aggregated</p>\n"
        f"<p class='summary'>{overall} &nbsp; passed "
        f"<b>{summary['passed']}</b> &middot; failed <b>{summary['failed']}</b></p>\n"
        f"{table}\n</body>\n</html>\n"
    )


def batch_qa_report(out_root) -> dict:
    """Aggregate :func:`qa_card` over every render under *out_root* and write a
    batch HTML at ``out_root/batch_qa.html``.

    Walks *out_root* recursively for every directory owning a ``*.manifest.json``,
    cards each one, and tabulates the per-check pass/fail into a single self-contained
    HTML. A directory whose card raises (e.g. a malformed manifest) is recorded as a
    failed card with an ``error`` field rather than aborting the whole batch.

    Returns ``{cards, summary: {passed, failed}, html_path}``.
    """
    out_root = Path(out_root)
    render_dirs = _find_render_dirs(out_root)

    cards: list[dict] = []
    for d in render_dirs:
        try:
            cards.append(qa_card(d))
        except Exception as exc:  # one bad render must not sink the batch
            cards.append(
                {
                    "name": d.name,
                    "config_hash": None,
                    "out_dir": str(d.resolve()),
                    "checks": {"error": {"passed": False, "note": str(exc)}},
                    "passed": False,
                    "error": str(exc),
                }
            )

    passed = sum(1 for c in cards if c.get("passed"))
    failed = len(cards) - passed
    summary = {"passed": passed, "failed": failed}

    out_root.mkdir(parents=True, exist_ok=True)
    html_path = out_root / "batch_qa.html"
    html_path.write_text(_batch_html(cards, summary), encoding="utf-8")

    return {"cards": cards, "summary": summary, "html_path": str(html_path.resolve())}
