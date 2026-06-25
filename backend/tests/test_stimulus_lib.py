"""Tests for the reproducible stimulus platform (stimulus_lib).

Runnable under pytest, or directly: ``python backend/tests/test_stimulus_lib.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from stimulus_lib import DisplayGeometry, ExperimentSpec, config_hash, render_experiment  # noqa: E402
from stimulus_lib.spec import load_spec  # noqa: E402

EXAMPLES = APP_DIR / "stimulus_lib" / "examples"


def _short_spec(**render_overrides) -> ExperimentSpec:
    render = {"fps": 60, "duration_s": 0.2, "codec": "png_sequence", **render_overrides}
    return ExperimentSpec(
        name="unit",
        seed=42,
        geometry={"screen_w_px": 320, "screen_h_px": 200},
        render=render,
        scene=[
            {"type": "grating", "spatial_freq_cpd": 0.08, "temporal_freq_hz": 2.0, "contrast": 0.8},
            {"type": "rdk", "n_dots": 40, "coherence": 0.5, "speed_dps": 4.0, "direction_deg": 0.0},
        ],
    )


def _frame_bytes(run_dir: Path) -> list[bytes]:
    return [p.read_bytes() for p in sorted((run_dir / "frames").glob("frame_*.png"))]


def test_geometry_deg_px_roundtrip():
    geometry = DisplayGeometry()
    assert geometry.deg_to_px(1.0) == geometry.px_per_deg
    assert abs(geometry.px_to_deg(geometry.px_per_deg) - 1.0) < 1e-9
    assert geometry.max_cpd == 0.5 * geometry.px_per_deg


def test_render_deterministic_and_lossless(tmp_path):
    spec = _short_spec()
    result_a = render_experiment(spec, tmp_path / "a", created_utc="2026-01-01T00:00:00+00:00")
    result_b = render_experiment(spec, tmp_path / "b", created_utc="2026-01-01T00:00:00+00:00")

    frames_a = _frame_bytes(tmp_path / "a")
    frames_b = _frame_bytes(tmp_path / "b")
    assert len(frames_a) == result_a["n_frames"] == 12
    assert frames_a == frames_b, "same seed+spec must produce byte-identical frames"
    assert result_a["manifest"]["qa"]["lossless_verified"] is True
    assert result_b["manifest"]["qa"]["max_abs_diff_frame0"] == 0


def test_nyquist_spatial_rejected(tmp_path):
    spec = _short_spec()
    spec.scene = [{"type": "grating", "spatial_freq_cpd": 8.0, "temporal_freq_hz": 1.0, "contrast": 0.8}]
    raised = False
    try:
        render_experiment(spec, tmp_path / "bad")
    except ValueError as exc:
        raised = True
        assert "Nyquist" in str(exc)
    assert raised, "a spatial frequency past Nyquist must be rejected"


def test_manifest_provenance(tmp_path):
    spec = _short_spec()
    render_experiment(spec, tmp_path / "m", created_utc="2026-01-01T00:00:00+00:00")
    manifest = json.loads((tmp_path / "m" / "unit.manifest.json").read_text())
    assert manifest["config_hash"] == config_hash(spec)
    assert "git_commit" in manifest
    assert manifest["geometry"]["px_per_deg"] > 0
    assert [layer["type"] for layer in manifest["scene"]] == ["grating", "rdk"]
    assert manifest["sync_marker"]["n_bits"] == 12


def test_examples_load_and_render(tmp_path):
    spec = load_spec(EXAMPLES / "looming_on_grating.json")
    spec.render = {**spec.render, "duration_s": 0.1}  # keep the test fast
    result = render_experiment(spec, tmp_path / "ex")
    assert result["n_frames"] == 6
    assert result["manifest"]["qa"]["lossless_verified"] is True
    assert [layer["type"] for layer in result["manifest"]["scene"]] == ["grating", "looming"]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        test_geometry_deg_px_roundtrip()
        test_render_deterministic_and_lossless(base / "det")
        test_nyquist_spatial_rejected(base / "nyq")
        test_manifest_provenance(base / "prov")
        test_examples_load_and_render(base / "examples")
    print("all stimulus_lib checks passed")
