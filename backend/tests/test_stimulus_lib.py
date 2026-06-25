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

import cv2  # noqa: E402
import numpy as np  # noqa: E402

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
    assert [layer["stimulus"]["type"] for layer in manifest["scene"]] == ["grating", "rdk"]
    assert manifest["scene"][0]["region"] == "full"
    assert manifest["scene"][0]["compositing"] == "over"
    assert manifest["sync_marker"]["n_bits"] == 12


def test_examples_load_and_render(tmp_path):
    spec = load_spec(EXAMPLES / "looming_on_grating.json")
    spec.render = {**spec.render, "duration_s": 0.1}  # keep the test fast
    result = render_experiment(spec, tmp_path / "ex")
    assert result["n_frames"] == 6
    assert result["manifest"]["qa"]["lossless_verified"] is True
    assert [layer["stimulus"]["type"] for layer in result["manifest"]["scene"]] == ["grating", "looming"]


def test_region_masking_confines(tmp_path):
    """A grating masked to the left hemifield leaves the right hemifield at mean luminance."""
    spec = ExperimentSpec(
        name="region",
        seed=1,
        geometry={"screen_w_px": 200, "screen_h_px": 120},
        render={
            "fps": 30,
            "duration_s": 0.05,
            "codec": "png_sequence",
            "sync_marker": False,
            "gamma_policy": "linear_record_only",
        },
        scene=[{"type": "grating", "spatial_freq_cpd": 0.1, "temporal_freq_hz": 1.0, "contrast": 0.9, "region": "left"}],
    )
    render_experiment(spec, tmp_path / "r", created_utc="2026-01-01T00:00:00+00:00")
    frame = cv2.imread(str(tmp_path / "r" / "frames" / "frame_000000.png"), cv2.IMREAD_UNCHANGED)
    channel = frame[:, :, 0].astype(np.float64)
    width = channel.shape[1]
    left = channel[:, : width // 2 - 5]
    right = channel[:, width // 2 + 5 :]
    assert left.std() > 10.0, "masked-in (left) hemifield should carry the grating"
    assert right.std() < 1.0, "masked-out (right) hemifield should stay at mean luminance"


def test_split_field_is_pure_composition(tmp_path):
    """Split-field = two masked gratings drifting oppositely. No dedicated split type/code."""
    spec = ExperimentSpec(
        name="split",
        seed=2,
        geometry={"screen_w_px": 200, "screen_h_px": 120},
        render={"fps": 30, "duration_s": 0.05, "codec": "png_sequence", "sync_marker": False},
        scene=[
            {"type": "grating", "spatial_freq_cpd": 0.1, "temporal_freq_hz": 2.0, "contrast": 0.9, "direction_deg": 0, "region": "left"},
            {"type": "grating", "spatial_freq_cpd": 0.1, "temporal_freq_hz": -2.0, "contrast": 0.9, "direction_deg": 0, "region": "right"},
        ],
    )
    result = render_experiment(spec, tmp_path / "s")
    scene = result["manifest"]["scene"]
    assert [layer["stimulus"]["type"] for layer in scene] == ["grating", "grating"]
    assert [layer["region"] for layer in scene] == ["left", "right"]
    assert result["manifest"]["qa"]["lossless_verified"] is True


def test_registry_has_full_repertoire():
    from stimulus_lib.stimuli import STIMULUS_REGISTRY

    expected = {"grating", "looming", "rdk", "dark_flash", "bar", "okr", "checkerboard", "prey", "gradient", "conspecific"}
    assert expected <= set(STIMULUS_REGISTRY), set(STIMULUS_REGISTRY)


def test_task_catalog_builds_and_renders(tmp_path):
    from stimulus_lib.tasks import build_task, list_tasks

    assert len(list_tasks()) >= 12
    spec = build_task("split_field_omr", condition="conflict", duration_s=0.1)
    result = render_experiment(spec, tmp_path / "task", created_utc="2026-01-01T00:00:00+00:00")
    assert result["manifest"]["qa"]["lossless_verified"] is True
    assert [layer["region"] for layer in result["manifest"]["scene"]] == ["left", "right"]


def test_sweep_full_factorial_separate_seed():
    from stimulus_lib import expand_sweep

    base = ExperimentSpec(
        name="b", seed=0, geometry={"screen_w_px": 320, "screen_h_px": 200},
        render={"fps": 60, "duration_s": 0.1},
        scene=[{"type": "grating", "spatial_freq_cpd": 0.1, "temporal_freq_hz": 2.0, "contrast": 0.8}],
    )
    axes = [{"path": "scene.0.contrast", "values": [0.2, 0.8]}, {"path": "render.fps", "values": [30, 60]}]
    sweep = expand_sweep(base, axes, presentation_seed=7)
    assert sweep["n_conditions"] == 4 and len(sweep["specs"]) == 4
    assert len({c["config_hash"] for c in sweep["conditions"]}) == 4
    assert sorted(sweep["presentation_order"]) == [0, 1, 2, 3]
    assert expand_sweep(base, axes, presentation_seed=7)["presentation_order"] == sweep["presentation_order"]


def test_calibration_linearize_and_render(tmp_path):
    from stimulus_lib import Calibration, luminance_ramp_levels

    levels = luminance_ramp_levels(33)
    cal = Calibration.from_measurements(levels, [v**2.2 for v in levels], display_id="sim")
    # A measured gamma-2.2 display linearizes to the inverse-gamma encoding.
    assert abs(float(cal.linearize(np.array([0.5]))[0]) - 0.5 ** (1 / 2.2)) < 0.02
    cal_file = tmp_path / "cal.json"
    cal.save(cal_file)
    spec = ExperimentSpec(
        name="cal", seed=0, geometry={"screen_w_px": 160, "screen_h_px": 100},
        render={"fps": 30, "duration_s": 0.05, "codec": "png_sequence", "sync_marker": False,
                "gamma_policy": "measured_lut", "calibration_file": str(cal_file)},
        scene=[{"type": "gradient", "profile": "linear", "low_lum": 0.0, "high_lum": 1.0}],
    )
    result = render_experiment(spec, tmp_path / "r", created_utc="2026-01-01T00:00:00+00:00")
    assert result["manifest"]["calibration"]["display_id"] == "sim"
    assert result["manifest"]["qa"]["lossless_verified"] is True
    assert result["manifest"]["spec"]["scene"][0]["type"] == "gradient"


def test_timing_qa_regression_events(tmp_path):
    from stimulus_lib import events, expand_sweep, qa_report, regression, sync_decode

    spec = ExperimentSpec(
        name="d", seed=1, geometry={"screen_w_px": 320, "screen_h_px": 200},
        render={"fps": 30, "duration_s": 0.3, "codec": "png_sequence", "sync_marker": True},
        scene=[{"type": "grating", "spatial_freq_cpd": 0.1, "temporal_freq_hz": 2.0, "contrast": 0.8}],
    )
    result = render_experiment(spec, tmp_path / "A", created_utc="2026-01-01T00:00:00+00:00")
    n = result["n_frames"]

    decoded = sync_decode.decode_sequence(tmp_path / "A" / "frames")
    assert decoded == list(range(n))
    assert sync_decode.analyze_timing(decoded, expected_n=n)["ok"]
    assert 5 in sync_decode.analyze_timing(decoded[:5] + decoded[6:], expected_n=n)["dropped"]

    html = qa_report.build_qa_report(tmp_path / "A")
    assert Path(html).exists() and result["manifest"]["config_hash"] in Path(html).read_text(encoding="utf-8")

    rep = regression.reproduce(tmp_path / "A" / "d.manifest.json", tmp_path / "B")
    assert rep["config_hash_match"] and rep["frames_hash_match"]

    base = ExperimentSpec(
        name="s", seed=0, geometry={"screen_w_px": 160, "screen_h_px": 100},
        render={"fps": 30, "duration_s": 2.0},
        scene=[{"type": "grating", "spatial_freq_cpd": 0.1, "temporal_freq_hz": 2.0, "contrast": 0.8}],
    )
    design = expand_sweep(base, [{"path": "render.duration_s", "values": [1.0, 3.0]}], presentation_seed=3)
    rows = events.sweep_events(design, iti_s=0.5)
    onsets = [row["onset"] for row in rows]
    assert onsets == sorted(onsets) and len(set(onsets)) == len(onsets)


def test_platform_modules(tmp_path):
    import stimulus_lib.authoring as authoring
    import stimulus_lib.batch as batch
    import stimulus_lib.index as index_mod
    import stimulus_lib.preview as preview
    import stimulus_lib.qa_checks as qa
    import stimulus_lib.realtime as realtime
    import stimulus_lib.session as session
    from stimulus_lib import expand_sweep

    base = ExperimentSpec(
        name="g", seed=0, geometry={"screen_w_px": 160, "screen_h_px": 100},
        render={"fps": 30, "duration_s": 0.1, "codec": "png_sequence", "sync_marker": True},
        scene=[{"type": "grating", "spatial_freq_cpd": 0.1, "temporal_freq_hz": 2.0, "contrast": 0.7}],
    )
    design = expand_sweep(base, [{"path": "scene.0.contrast", "values": [0.3, 0.8]}], presentation_seed=1)
    out_root = tmp_path / "set"

    assert batch.render_batch(design, out_root)["summary"]["done"] == 2
    assert batch.render_batch(design, out_root)["summary"]["skipped"] == 2  # content-hash skip

    idx = index_mod.build_index(out_root)
    assert len(idx) == 2 and len(index_mod.query(idx, **{"scene.0.contrast__ge": 0.5})) == 1

    assert authoring.resolve_inheritance({"a": {"x": 1}}, {"a": {"y": 2}}) == {"a": {"x": 1, "y": 2}}
    assert authoring.dry_validate(design)["n_conditions"] == 2

    assert preview.preview_frame(base).shape == (100, 160, 3)
    name0 = idx[0]["name"]
    assert int(preview.diff_image(out_root / name0, out_root / name0).max()) < 5
    assert qa.batch_qa_report(out_root)["summary"]["passed"] == 2

    sess = session.build_session([{"task": "omr"}, {"task": "looming"}], repeats=2, iti_s=0.5, seed=1)
    onsets = [t["onset"] for t in sess["trials"]]
    assert sess["n_trials"] == 4 and onsets == sorted(onsets)

    traj = [{"x_deg": 20 - 2 * i, "y_deg": 0.0, "heading_deg": 0.0} for i in range(12)]
    loop = realtime.run_closed_loop(
        realtime.ClosedLoopController(base, realtime.looming_on_approach(5.0, 0.06)),
        realtime.SimulatedTracker(traj), n_steps=12, dt=1 / 30,
    )
    assert len(loop["latency_log_ms"]) == 12 and loop["triggered"]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        test_geometry_deg_px_roundtrip()
        test_render_deterministic_and_lossless(base / "det")
        test_nyquist_spatial_rejected(base / "nyq")
        test_manifest_provenance(base / "prov")
        test_examples_load_and_render(base / "examples")
        test_region_masking_confines(base / "region")
        test_split_field_is_pure_composition(base / "split")
        test_registry_has_full_repertoire()
        test_task_catalog_builds_and_renders(base / "task")
        test_sweep_full_factorial_separate_seed()
        test_calibration_linearize_and_render(base / "cal")
        test_timing_qa_regression_events(base / "tqre")
        test_platform_modules(base / "platform")
    print("all stimulus_lib checks passed")
