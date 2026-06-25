"""Golden-frame regression + reproduce-from-manifest.

A render is content-addressed two ways: ``config_hash`` over the *authored* spec
(what the experimenter wrote) and ``frames_hash`` over the *rendered bytes* (what the
fish actually saw). A golden record pins both, so a refactor that changes the spec
schema, the render math, or the codec can never silently alter a published stimulus —
the hash moves and the regression check fails loudly.

``reproduce`` closes the loop the other direction: rebuild the spec from a manifest,
re-render it, and confirm the new ``config_hash`` (and, when the original frames sit
beside the manifest, the ``frames_hash``) match. Determinism in (spec, seed) means a
faithful pipeline reproduces a stimulus bit-for-bit from its manifest alone.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .render import render_experiment
from .spec import ExperimentSpec


def _find_manifest(render_out_dir: str | Path) -> Path:
    """The single ``*.manifest.json`` a render directory owns."""
    out = Path(render_out_dir)
    matches = sorted(out.glob("*.manifest.json"))
    if not matches:
        raise FileNotFoundError(f"no *.manifest.json in {out}")
    if len(matches) > 1:
        raise ValueError(f"multiple manifests in {out}: {[m.name for m in matches]}")
    return matches[0]


def frames_hash(frames_dir: str | Path) -> str:
    """SHA-256 over the concatenated raw bytes of the sorted ``frame_*.png`` files.

    Hashes file *contents* only (not names); ``frame_%06d`` padding makes lexicographic
    order match frame order, but the sort is explicit so it never depends on the
    filesystem's directory ordering.
    """
    directory = Path(frames_dir)
    frame_paths = sorted(directory.glob("frame_*.png"))
    digest = hashlib.sha256()
    for path in frame_paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _spec_from_manifest(manifest: dict) -> ExperimentSpec:
    """Rebuild the authored spec from ``manifest["spec"]`` (the canonical dict).

    Uses the authored ``geometry``/``render``/``scene`` — *not* the enriched
    top-level manifest copies — so the recomputed ``config_hash`` matches.
    """
    spec_dict = manifest["spec"]
    return ExperimentSpec(
        name=spec_dict["name"],
        seed=spec_dict["seed"],
        geometry=dict(spec_dict.get("geometry") or {}),
        render=dict(spec_dict.get("render") or {}),
        scene=list(spec_dict.get("scene") or []),
    )


def write_golden(render_out_dir: str | Path, golden_path: str | Path) -> dict:
    """Pin a render: record its name, config hash, frames hash, and frame count."""
    out = Path(render_out_dir)
    manifest = json.loads(_find_manifest(out).read_text(encoding="utf-8"))
    golden = {
        "name": manifest["name"],
        "config_hash": manifest["config_hash"],
        "frames_hash": frames_hash(out / "frames"),
        "n_frames": int(manifest["n_frames"]),
    }
    Path(golden_path).write_text(json.dumps(golden, indent=2), encoding="utf-8")
    return golden


def verify_against_golden(render_out_dir: str | Path, golden_path: str | Path) -> dict:
    """Check a render directory against a golden record.

    Returns ``{config_hash_match, frames_hash_match, ok}``; ``ok`` is True only when
    both the authored spec and the rendered bytes are unchanged.
    """
    out = Path(render_out_dir)
    golden = json.loads(Path(golden_path).read_text(encoding="utf-8"))
    manifest = json.loads(_find_manifest(out).read_text(encoding="utf-8"))

    config_hash_match = manifest["config_hash"] == golden["config_hash"]
    frames_hash_match = frames_hash(out / "frames") == golden["frames_hash"]
    return {
        "config_hash_match": config_hash_match,
        "frames_hash_match": frames_hash_match,
        "ok": config_hash_match and frames_hash_match,
    }


def reproduce(manifest_path: str | Path, out_dir: str | Path) -> dict:
    """Rebuild a stimulus from its manifest and confirm it reproduces.

    Loads the manifest, rebuilds the spec from ``manifest["spec"]``, re-renders to
    ``out_dir``, and checks the new ``config_hash`` against the recorded one. If the
    original frames sit beside the manifest, also compares ``frames_hash`` (same
    seed + spec must yield byte-identical frames); otherwise ``frames_hash_match`` is
    ``None`` and ``ok`` rests on the config hash alone.
    """
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    spec = _spec_from_manifest(manifest)
    result = render_experiment(spec, out_dir)
    new_config_hash = result["manifest"]["config_hash"]
    config_hash_match = new_config_hash == manifest["config_hash"]

    original_frames = manifest_file.parent / "frames"
    if original_frames.is_dir():
        frames_hash_match = frames_hash(Path(out_dir) / "frames") == frames_hash(original_frames)
        ok = config_hash_match and frames_hash_match
    else:
        frames_hash_match = None
        ok = config_hash_match

    return {
        "config_hash_match": config_hash_match,
        "frames_hash_match": frames_hash_match,
        "ok": ok,
    }
