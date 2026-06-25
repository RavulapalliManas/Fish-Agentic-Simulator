"""Per-render QA sheet: provenance + luminance/contrast + Nyquist + lossless gate -> HTML.

A render is only reproducible if you can *see*, in one place, what produced it and
whether it survived the lossless gate. This module reads a render directory's
manifest, re-measures the rendered frames it actually wrote (first/middle/last),
and emits a single self-contained ``<name>.qa.html`` — no external assets, so the
sheet can be archived next to a paper figure or attached to a lab notebook.

It re-derives nothing the render already decided: provenance (name, config hash,
git commit, calibration), geometry (px/deg, max_cpd, display), the resolved
per-layer scene, and the round-trip lossless QA all come straight from the
manifest. What it *adds* is an empirical look at the pixels: a luminance
histogram, min/max/mean and Michelson contrast on the middle frame (with the
baked sync-marker corner masked out so it does not bias the statistics), and
base64-embedded thumbnails of the three sampled frames.

    from stimulus_lib.qa_report import build_qa_report
    html_path = build_qa_report("output/stimuli/demo")

numpy + OpenCV only; the HTML is assembled by string so the module has no template
dependency. The Nyquist ceiling (``max_cpd``) is reported alongside the geometry so
a reviewer can sanity-check spatial frequencies without re-running validation.
"""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

import cv2
import numpy as np

from .render import SYNC_MARKER
from .spec import ExperimentSpec, config_hash  # noqa: F401  (provenance recompute / API parity)

# Frames are sampled at three positions so the sheet captures onset, mid-clip and
# tail without embedding the whole sequence.
_THUMB_WIDTH_PX = 240
_HIST_BINS = 32


def _find_manifest(out_dir: Path) -> Path:
    """Return the single ``*.manifest.json`` in *out_dir* (error if not exactly one)."""
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


def _sample_indices(n: int) -> list[int]:
    """First / middle / last indices for a sequence of length *n* (deduped, ordered)."""
    if n <= 0:
        return []
    picks = sorted({0, n // 2, n - 1})
    return picks


def _read_gray(path: Path) -> np.ndarray:
    """Load a frame and return channel 0 as float (the render writes a grayscale value
    replicated across RGB, so channel 0 is the luminance code)."""
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"could not read frame {path}")
    if img.ndim == 2:
        return img.astype(np.float64)
    return img[:, :, 0].astype(np.float64)


def _sync_marker_box() -> tuple[int, int]:
    """Pixel extent (rows, cols) of the top-left sync-marker block to exclude.

    Mirrors ``render._bake_sync_marker``: ``n_bits + 1`` squares laid out from a
    margin, plus a one-square pad so anti-marker bleed never enters the stats.
    """
    square = int(SYNC_MARKER["square_px"])
    margin = int(SYNC_MARKER["margin_px"])
    n_bits = int(SYNC_MARKER["n_bits"])
    cols = margin + (n_bits + 1) * square + square  # +square pad
    rows = margin + square + square
    return rows, cols


def _luminance_stats(gray: np.ndarray, bit_depth: int, sync_present: bool) -> dict:
    """min/max/mean, 32-bin histogram and Michelson contrast over *gray*.

    When the sync marker is baked into the top-left corner its hard 0/max squares
    are excluded so they do not dominate the histogram or the contrast.
    """
    max_level = 65535.0 if bit_depth == 16 else 255.0
    sampled = gray
    if sync_present:
        rows, cols = _sync_marker_box()
        rows = min(rows, gray.shape[0])
        cols = min(cols, gray.shape[1])
        mask = np.ones(gray.shape, dtype=bool)
        mask[:rows, :cols] = False
        sampled = gray[mask]
    sampled = np.asarray(sampled, dtype=np.float64).ravel()
    if sampled.size == 0:  # degenerate (e.g. marker covers the whole frame)
        sampled = np.asarray(gray, dtype=np.float64).ravel()

    norm = sampled / max_level  # luminance code -> [0, 1]
    vmin = float(norm.min())
    vmax = float(norm.max())
    vmean = float(norm.mean())
    michelson = (vmax - vmin) / (vmax + vmin + 1e-9)

    counts, edges = np.histogram(norm, bins=_HIST_BINS, range=(0.0, 1.0))
    return {
        "min": vmin,
        "max": vmax,
        "mean": vmean,
        "michelson_contrast": float(michelson),
        "hist_counts": [int(c) for c in counts],
        "hist_edges": [float(e) for e in edges],
        "n_pixels": int(sampled.size),
        "bit_depth": int(bit_depth),
        "sync_excluded": bool(sync_present),
    }


def _thumbnail_data_uri(path: Path, width: int = _THUMB_WIDTH_PX) -> str:
    """Downscale a frame to ~*width* px wide and return a base64 PNG data URI."""
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"could not read frame {path}")
    h, w = img.shape[:2]
    if w > width:
        scale = width / float(w)
        new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
        img = cv2.resize(img, new_size, interpolation=cv2.INTER_AREA)
    # 16-bit frames must be brought down to 8-bit for a browser-displayable PNG.
    if img.dtype == np.uint16:
        img = (img.astype(np.float64) / 257.0).round().clip(0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError(f"cv2.imencode failed for {path}")
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# --------------------------------------------------------------------------- #
# HTML assembly (by string; no template dependency)
# --------------------------------------------------------------------------- #

def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _kv_rows(pairs: list[tuple[str, object]]) -> str:
    rows = []
    for label, value in pairs:
        rows.append(f"<tr><th>{_esc(label)}</th><td>{_esc(value)}</td></tr>")
    return "\n".join(rows)


def _pass_fail_badge(ok: object) -> str:
    if ok is True:
        return '<span class="badge pass">PASS</span>'
    if ok is False:
        return '<span class="badge fail">FAIL</span>'
    return '<span class="badge unknown">N/A</span>'


def _provenance_section(manifest: dict) -> str:
    cal = manifest.get("calibration")
    if cal:
        cal_str = (
            f"display_id={cal.get('display_id')}, instrument={cal.get('instrument')}, "
            f"hash={cal.get('calibration_hash')}, max_lum={cal.get('max_luminance')}"
        )
    else:
        cal_str = "none (gamma policy: " + str(manifest.get("gamma_policy")) + ")"
    rows = _kv_rows(
        [
            ("name", manifest.get("name")),
            ("generator", manifest.get("generator")),
            ("config_hash", manifest.get("config_hash")),
            ("git_commit", manifest.get("git_commit")),
            ("created_utc", manifest.get("created_utc")),
            ("seed", manifest.get("seed")),
            ("calibration", cal_str),
        ]
    )
    return f'<section><h2>Provenance</h2><table class="kv">{rows}</table></section>'


def _geometry_section(manifest: dict) -> str:
    geo = manifest.get("geometry") or {}
    rows = _kv_rows(
        [
            ("display_id", geo.get("display_id")),
            ("px_per_deg", geo.get("px_per_deg")),
            ("max_cpd (Nyquist ceiling, cyc/deg)", geo.get("max_cpd")),
            ("screen (px)", f"{geo.get('screen_w_px')} x {geo.get('screen_h_px')}"),
            ("screen (mm)", f"{geo.get('screen_w_mm')} x {geo.get('screen_h_mm')}"),
            ("viewing_distance_mm", geo.get("viewing_distance_mm")),
            ("refresh_hz", geo.get("refresh_hz")),
            ("gamma", geo.get("gamma")),
            ("projection", geo.get("projection")),
        ]
    )
    return f'<section><h2>Geometry &amp; Nyquist</h2><table class="kv">{rows}</table></section>'


def _render_section(manifest: dict) -> str:
    render = manifest.get("render") or {}
    rows = _kv_rows(
        [
            ("fps", manifest.get("fps")),
            ("n_frames", manifest.get("n_frames")),
            ("duration_s", manifest.get("duration_s")),
            ("bit_depth", manifest.get("bit_depth")),
            ("gamma_policy", manifest.get("gamma_policy")),
            ("codec", manifest.get("codec")),
            ("mean_lum", render.get("mean_lum")),
            ("sync_marker", "baked" if manifest.get("sync_marker") else "off"),
        ]
    )
    return f'<section><h2>Render settings</h2><table class="kv">{rows}</table></section>'


def _lossless_section(manifest: dict) -> str:
    qa = manifest.get("qa") or {}
    verified = qa.get("lossless_verified")
    max_diff = qa.get("max_abs_diff_frame0")
    badge = _pass_fail_badge(verified)
    rows = _kv_rows(
        [
            ("codec", qa.get("codec")),
            ("max_abs_diff_frame0 (rendered vs decoded)", max_diff),
            ("lossless_verified", verified),
        ]
    )
    note = ""
    if verified is None:
        note = (
            '<p class="note">Round-trip diff is only computed for the <code>png_sequence</code> '
            "codec; <code>ffv1</code> renders report N/A here.</p>"
        )
    return (
        f'<section><h2>Lossless gate {badge}</h2>'
        f'<table class="kv">{rows}</table>{note}</section>'
    )


def _warnings_section(manifest: dict) -> str:
    warnings = manifest.get("validation_warnings") or []
    if not warnings:
        body = '<p class="ok">No validation warnings.</p>'
    else:
        items = "\n".join(f"<li>{_esc(w)}</li>" for w in warnings)
        body = f'<ul class="warnings">{items}</ul>'
    return f"<section><h2>Validation warnings</h2>{body}</section>"


def _scene_section(manifest: dict) -> str:
    scene = manifest.get("scene") or []
    head = (
        "<tr><th>#</th><th>type</th><th>region</th><th>compositing</th>"
        "<th>onset_s</th><th>offset_s</th><th>blend_w</th><th>key params</th></tr>"
    )
    rows = [head]
    for i, layer in enumerate(scene):
        stim = layer.get("stimulus") or {}
        stim_type = stim.get("type")
        # Surface the stimulus parameters minus its own "type" key.
        params = {k: v for k, v in stim.items() if k != "type"}
        param_str = ", ".join(f"{k}={v}" for k, v in params.items())
        region = layer.get("region")
        if isinstance(region, dict):
            region = json.dumps(region, separators=(",", ":"))
        rows.append(
            "<tr>"
            f"<td>{i}</td>"
            f"<td>{_esc(stim_type)}</td>"
            f"<td>{_esc(region)}</td>"
            f"<td>{_esc(layer.get('compositing'))}</td>"
            f"<td>{_esc(layer.get('onset_s'))}</td>"
            f"<td>{_esc(layer.get('offset_s'))}</td>"
            f"<td>{_esc(layer.get('blend_weight'))}</td>"
            f"<td class='params'>{_esc(param_str)}</td>"
            "</tr>"
        )
    table = '<table class="scene">' + "\n".join(rows) + "</table>"
    return f"<section><h2>Scene ({len(scene)} layer{'s' if len(scene) != 1 else ''})</h2>{table}</section>"


def _histogram_html(stats: dict) -> str:
    counts = stats["hist_counts"]
    edges = stats["hist_edges"]
    peak = max(counts) if counts else 0
    bars = []
    for i, c in enumerate(counts):
        frac = (c / peak) if peak > 0 else 0.0
        height_pct = max(1.0, frac * 100.0) if c > 0 else 0.0
        lo = edges[i]
        hi = edges[i + 1]
        title = f"[{lo:.3f}, {hi:.3f}): {c} px"
        bars.append(
            f'<div class="bar" style="height:{height_pct:.1f}%" title="{_esc(title)}"></div>'
        )
    bar_html = "".join(bars)
    return (
        '<div class="hist">'
        f'<div class="hist-bars">{bar_html}</div>'
        '<div class="hist-axis"><span>0.0</span><span>luminance (normalised)</span><span>1.0</span></div>'
        "</div>"
    )


def _luminance_section(stats: dict) -> str:
    excl = (
        " (sync-marker corner excluded)" if stats.get("sync_excluded") else ""
    )
    rows = _kv_rows(
        [
            ("min", f"{stats['min']:.4f}"),
            ("max", f"{stats['max']:.4f}"),
            ("mean", f"{stats['mean']:.4f}"),
            ("Michelson contrast (max-min)/(max+min)", f"{stats['michelson_contrast']:.4f}"),
            ("pixels measured", stats["n_pixels"]),
            ("bit_depth", stats["bit_depth"]),
        ]
    )
    hist = _histogram_html(stats)
    return (
        f"<section><h2>Luminance &amp; contrast — middle frame{excl}</h2>"
        f'<table class="kv">{rows}</table>'
        f"<h3>Luminance histogram ({_HIST_BINS} bins)</h3>{hist}</section>"
    )


def _thumbnails_section(thumbs: list[tuple[str, int, str]]) -> str:
    cards = []
    for label, frame_index, uri in thumbs:
        cards.append(
            '<figure class="thumb">'
            f'<img src="{uri}" alt="{_esc(label)} frame {frame_index}">'
            f"<figcaption>{_esc(label)} (frame {frame_index})</figcaption>"
            "</figure>"
        )
    return f'<section><h2>Thumbnails</h2><div class="thumbs">{"".join(cards)}</div></section>'


def _timing_section(timing: dict) -> str:
    rows = _kv_rows([(k, v) for k, v in timing.items()])
    return (
        "<section><h2>Timing</h2>"
        '<p class="note">Photodiode/TTL timing summary supplied to the report.</p>'
        f'<table class="kv">{rows}</table></section>'
    )


_STYLE = """
:root { color-scheme: light dark; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
       margin: 0; padding: 1.5rem 2rem; line-height: 1.45; color: #1a1a1a;
       background: #fafafa; }
h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
.subtitle { color: #555; margin: 0 0 1.5rem; font-size: .9rem; }
.subtitle code { font-size: .85rem; }
section { background: #fff; border: 1px solid #e2e2e2; border-radius: 8px;
          padding: 1rem 1.25rem; margin-bottom: 1.25rem; }
h2 { font-size: 1.1rem; margin: 0 0 .75rem; border-bottom: 1px solid #eee;
     padding-bottom: .4rem; }
h3 { font-size: .95rem; margin: 1rem 0 .5rem; }
table { border-collapse: collapse; width: 100%; font-size: .88rem; }
table.kv th { text-align: left; width: 42%; font-weight: 600; color: #333;
              vertical-align: top; padding: .25rem .5rem; }
table.kv td { padding: .25rem .5rem; font-family: ui-monospace, SFMono-Regular,
              Menlo, monospace; word-break: break-all; }
table.kv tr:nth-child(odd) { background: #f7f7f7; }
table.scene { font-size: .82rem; }
table.scene th, table.scene td { border: 1px solid #e6e6e6; padding: .3rem .5rem;
                                 text-align: left; vertical-align: top; }
table.scene th { background: #f0f0f0; }
table.scene td.params { font-family: ui-monospace, monospace; max-width: 28rem;
                        word-break: break-word; }
.badge { font-size: .75rem; padding: .15rem .55rem; border-radius: 999px;
         font-weight: 700; vertical-align: middle; }
.badge.pass { background: #1f8b4c; color: #fff; }
.badge.fail { background: #c0392b; color: #fff; }
.badge.unknown { background: #888; color: #fff; }
.note { color: #666; font-size: .82rem; margin: .5rem 0 0; }
.ok { color: #1f8b4c; font-size: .88rem; margin: 0; }
ul.warnings { margin: 0; padding-left: 1.2rem; }
ul.warnings li { color: #9a6700; margin: .2rem 0; }
.hist { margin-top: .5rem; }
.hist-bars { display: flex; align-items: flex-end; gap: 1px; height: 140px;
             background: #fbfbfb; border: 1px solid #eee; padding: 2px;
             border-radius: 4px; }
.hist-bars .bar { flex: 1 1 0; background: linear-gradient(#4a78c8, #21457f);
                  min-height: 0; border-radius: 1px 1px 0 0; }
.hist-axis { display: flex; justify-content: space-between; font-size: .72rem;
             color: #777; margin-top: .25rem; }
.thumbs { display: flex; gap: 1rem; flex-wrap: wrap; }
.thumb { margin: 0; border: 1px solid #ddd; border-radius: 6px; padding: .35rem;
         background: #fff; text-align: center; }
.thumb img { display: block; image-rendering: pixelated; max-width: 240px; }
.thumb figcaption { font-size: .75rem; color: #555; margin-top: .35rem; }
""".strip()


def build_qa_report(render_out_dir, timing: dict | None = None) -> str:
    """Build a self-contained QA HTML sheet for one render directory.

    Parameters
    ----------
    render_out_dir:
        A render output directory containing exactly one ``*.manifest.json`` and a
        ``frames/`` PNG sequence (the ``png_sequence`` codec). The manifest carries
        all provenance/geometry/QA; this function re-measures the written frames.
    timing:
        Optional dict of photodiode/TTL timing summary fields; if given, a Timing
        section is appended verbatim.

    Returns
    -------
    str
        Absolute path to the written ``<name>.qa.html`` file (also inside
        *render_out_dir*).
    """
    out_dir = Path(render_out_dir)
    manifest_path = _find_manifest(out_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    name = manifest.get("name") or manifest_path.stem.replace(".manifest", "")
    bit_depth = int(manifest.get("bit_depth", 8))
    sync_present = bool(manifest.get("sync_marker"))

    frames = _frame_paths(out_dir)
    sections: list[str] = []
    sections.append(_provenance_section(manifest))
    sections.append(_geometry_section(manifest))
    sections.append(_render_section(manifest))
    sections.append(_lossless_section(manifest))
    sections.append(_warnings_section(manifest))
    sections.append(_scene_section(manifest))

    if frames:
        indices = _sample_indices(len(frames))
        labels = {0: "first", 1: "middle", 2: "last"}
        # Middle of the *sampled* triple is the luminance-stats frame.
        mid_pos = len(indices) // 2
        mid_index = indices[mid_pos]
        gray = _read_gray(frames[mid_index])
        stats = _luminance_stats(gray, bit_depth, sync_present)
        sections.append(_luminance_section(stats))

        thumbs: list[tuple[str, int, str]] = []
        for slot, idx in enumerate(indices):
            label = labels.get(slot, f"sample {slot}")
            if len(indices) == 1:
                label = "only"
            thumbs.append((label, idx, _thumbnail_data_uri(frames[idx])))
        sections.append(_thumbnails_section(thumbs))
    else:
        sections.append(
            '<section><h2>Frames</h2><p class="note">No PNG frames found in '
            "<code>frames/</code> (an <code>ffv1</code> render stores a single "
            ".mkv); luminance stats and thumbnails are unavailable.</p></section>"
        )

    if timing:
        sections.append(_timing_section(timing))

    subtitle = (
        f'config_hash <code>{_esc(manifest.get("config_hash"))}</code> &middot; '
        f'git <code>{_esc(manifest.get("git_commit"))}</code>'
    )
    doc = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>QA report — {_esc(name)}</title>\n"
        f"<style>{_STYLE}</style>\n</head>\n<body>\n"
        f"<h1>QA report — {_esc(name)}</h1>\n"
        f'<p class="subtitle">{subtitle}</p>\n'
        + "\n".join(sections)
        + "\n</body>\n</html>\n"
    )

    html_path = out_dir / f"{name}.qa.html"
    html_path.write_text(doc, encoding="utf-8")
    return str(html_path.resolve())
