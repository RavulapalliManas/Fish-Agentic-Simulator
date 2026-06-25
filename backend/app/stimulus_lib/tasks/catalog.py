"""Task catalog — named paradigms users choose from.

Each task is a thin builder that assembles primitives + regions + timeline into a
ready-to-render ExperimentSpec from a few high-level, documented parameters. Split
paradigms are just two region-masked layers (no dedicated split code). Parameter
metadata travels with each task so a CLI or UI can present the choices.
"""

from __future__ import annotations

from ..spec import ExperimentSpec

_GEOMETRY = {
    "viewing_distance_mm": 30.0,
    "screen_w_mm": 68.0,
    "screen_h_mm": 38.0,
    "screen_w_px": 1280,
    "screen_h_px": 720,
    "refresh_hz": 60.0,
    "gamma": 2.2,
    "projection": "planar",
    "display_id": "bench-demo",
}


def _spec(name: str, seed: int, scene: list, duration_s: float, render_overrides: dict | None = None) -> ExperimentSpec:
    render = {
        "fps": 60,
        "duration_s": float(duration_s),
        "bit_depth": 8,
        "gamma_policy": "encode_into_file",
        "sync_marker": True,
        "codec": "png_sequence",
        "mean_lum": 0.5,
    }
    if render_overrides:
        render.update(render_overrides)
    return ExperimentSpec(name=name, seed=int(seed), geometry=dict(_GEOMETRY), render=render, scene=scene)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #

def omr(direction_deg=0.0, spatial_freq_cpd=0.08, temporal_freq_hz=2.0, contrast=0.9, waveform="sine", duration_s=10.0, seed=0):
    scene = [{"type": "grating", "spatial_freq_cpd": spatial_freq_cpd, "temporal_freq_hz": temporal_freq_hz,
              "contrast": contrast, "direction_deg": direction_deg, "waveform": waveform}]
    return _spec("omr", seed, scene, duration_s)


def okr(spatial_freq_cpd=0.08, angular_velocity_dps=30.0, contrast=0.9, waveform="sine", duration_s=10.0, seed=0):
    scene = [{"type": "okr", "spatial_freq_cpd": spatial_freq_cpd, "angular_velocity_dps": angular_velocity_dps,
              "contrast": contrast, "waveform": waveform}]
    return _spec("okr", seed, scene, duration_s)


def rdk(coherence=0.5, n_dots=200, speed_dps=10.0, direction_deg=0.0, dot_size_deg=0.3, dot_lifetime_s=0.2, duration_s=10.0, seed=0):
    scene = [{"type": "rdk", "n_dots": n_dots, "coherence": coherence, "speed_dps": speed_dps,
              "direction_deg": direction_deg, "dot_size_deg": dot_size_deg, "dot_lifetime_s": dot_lifetime_s}]
    return _spec("rdk", seed, scene, duration_s)


def split_field_omr(condition="conflict", spatial_freq_cpd=0.08, temporal_freq_hz=2.0, contrast=0.9, waveform="square", duration_s=10.0, seed=0):
    """Split-field OMR via masking. condition: congruent | conflict | monocular_left | monocular_right."""
    left_tf = temporal_freq_hz
    right_tf = temporal_freq_hz if condition == "congruent" else -temporal_freq_hz

    def grating(region, tf):
        return {"type": "grating", "region": region, "spatial_freq_cpd": spatial_freq_cpd,
                "temporal_freq_hz": tf, "contrast": contrast, "direction_deg": 0.0, "waveform": waveform}

    scene = []
    if condition != "monocular_right":
        scene.append(grating("left", left_tf))
    if condition != "monocular_left":
        scene.append(grating("right", right_tf))
    return _spec(f"split_field_omr_{condition}", seed, scene, duration_s)


def looming(l_over_v_s=0.06, max_radius_deg=35.0, polarity="dark", contrast=1.0, t_collision_s=None, duration_s=4.0, seed=0):
    collision = (duration_s - 0.1) if t_collision_s is None else t_collision_s
    scene = [{"type": "looming", "l_over_v_s": l_over_v_s, "t_collision_s": collision,
              "max_radius_deg": max_radius_deg, "polarity": polarity, "contrast": contrast}]
    return _spec("looming", seed, scene, duration_s)


def dark_flash(baseline_lum=0.5, flash_lum=0.0, onset_s=2.0, flash_duration_s=0.5, duration_s=6.0, seed=0):
    scene = [{"type": "dark_flash", "baseline_lum": baseline_lum, "flash_lum": flash_lum,
              "onset_s": onset_s, "duration_s": flash_duration_s}]
    return _spec("dark_flash", seed, scene, duration_s)


def prey(size_deg=0.5, speed_dps=8.0, trajectory="saltatory", polarity="dark", contrast=1.0, duration_s=10.0, seed=0):
    scene = [{"type": "prey", "size_deg": size_deg, "speed_dps": speed_dps, "trajectory": trajectory,
              "polarity": polarity, "contrast": contrast}]
    return _spec("prey", seed, scene, duration_s)


def moving_bar(width_deg=4.0, speed_dps=20.0, direction_deg=0.0, polarity="dark", contrast=1.0, duration_s=6.0, seed=0):
    scene = [{"type": "bar", "width_deg": width_deg, "speed_dps": speed_dps, "direction_deg": direction_deg,
              "polarity": polarity, "contrast": contrast}]
    return _spec("moving_bar", seed, scene, duration_s)


def static_grating(spatial_freq_cpd=0.1, contrast=0.9, direction_deg=0.0, waveform="sine", duration_s=4.0, seed=0):
    scene = [{"type": "grating", "spatial_freq_cpd": spatial_freq_cpd, "temporal_freq_hz": 0.0,
              "contrast": contrast, "direction_deg": direction_deg, "waveform": waveform}]
    return _spec("static_grating", seed, scene, duration_s)


def checkerboard(check_size_deg=5.0, contrast=0.9, reversal_hz=2.0, duration_s=6.0, seed=0):
    scene = [{"type": "checkerboard", "check_size_deg": check_size_deg, "contrast": contrast, "reversal_hz": reversal_hz}]
    return _spec("checkerboard", seed, scene, duration_s)


def light_dark_preference(mode="split", low_lum=0.05, high_lum=0.95, axis_deg=0.0, duration_s=10.0, seed=0):
    """Scototaxis / phototaxis. mode: split (dark vs light hemifields) | gradient (smooth ramp)."""
    if mode == "split":
        scene = [
            {"type": "gradient", "region": "left", "profile": "linear", "low_lum": low_lum, "high_lum": low_lum},
            {"type": "gradient", "region": "right", "profile": "linear", "low_lum": high_lum, "high_lum": high_lum},
        ]
    else:
        scene = [{"type": "gradient", "profile": "linear", "axis_deg": axis_deg, "low_lum": low_lum, "high_lum": high_lum}]
    return _spec(f"light_dark_{mode}", seed, scene, duration_s)


def social(n_agents=6, body_size_deg=2.0, tail_beat_hz=20.0, bout_period_s=1.0, bout_duty=0.4, speed_dps=8.0, schooling="school", duration_s=12.0, seed=0):
    scene = [{"type": "conspecific", "n_agents": n_agents, "body_size_deg": body_size_deg, "tail_beat_hz": tail_beat_hz,
              "bout_period_s": bout_period_s, "bout_duty": bout_duty, "speed_dps": speed_dps, "schooling": schooling}]
    return _spec("social", seed, scene, duration_s)


# --------------------------------------------------------------------------- #
# Registry + parameter metadata (so a CLI or UI can present the choices)
# --------------------------------------------------------------------------- #

def _f(default, lo, hi, help):
    return {"type": "float", "default": default, "min": lo, "max": hi, "help": help}


def _i(default, lo, hi, help):
    return {"type": "int", "default": default, "min": lo, "max": hi, "help": help}


def _c(default, choices, help):
    return {"type": "choice", "default": default, "choices": choices, "help": help}


TASK_REGISTRY: dict[str, dict] = {
    "omr": {
        "description": "Optomotor response — whole-field drifting grating.",
        "builder": omr,
        "params": {
            "direction_deg": _f(0.0, 0.0, 360.0, "Drift direction (deg)."),
            "spatial_freq_cpd": _f(0.08, 0.005, 1.0, "Spatial frequency (cycles/deg)."),
            "temporal_freq_hz": _f(2.0, -20.0, 20.0, "Temporal frequency (Hz); sign sets direction."),
            "contrast": _f(0.9, 0.0, 1.0, "Michelson contrast."),
            "waveform": _c("sine", ["sine", "square"], "Grating profile."),
            "duration_s": _f(10.0, 0.5, 180.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
    "okr": {
        "description": "Optokinetic response — grating rotating about center.",
        "builder": okr,
        "params": {
            "spatial_freq_cpd": _f(0.08, 0.005, 1.0, "Spatial frequency (cycles/deg)."),
            "angular_velocity_dps": _f(30.0, -180.0, 180.0, "Rotation speed (deg/s)."),
            "contrast": _f(0.9, 0.0, 1.0, "Michelson contrast."),
            "waveform": _c("sine", ["sine", "square"], "Grating profile."),
            "duration_s": _f(10.0, 0.5, 180.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
    "rdk": {
        "description": "Random-dot kinematogram — motion-coherence threshold.",
        "builder": rdk,
        "params": {
            "coherence": _f(0.5, 0.0, 1.0, "Fraction of coherently moving dots."),
            "n_dots": _i(200, 10, 2000, "Dot count."),
            "speed_dps": _f(10.0, 0.5, 60.0, "Dot speed (deg/s)."),
            "direction_deg": _f(0.0, 0.0, 360.0, "Coherent motion direction (deg)."),
            "dot_size_deg": _f(0.3, 0.05, 2.0, "Dot diameter (deg)."),
            "dot_lifetime_s": _f(0.2, 0.05, 2.0, "Dot lifetime (s)."),
            "duration_s": _f(10.0, 0.5, 180.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
    "split_field_omr": {
        "description": "Split-field OMR — independent grating per hemifield (binocular integration / conflict / monocular).",
        "builder": split_field_omr,
        "params": {
            "condition": _c("conflict", ["congruent", "conflict", "monocular_left", "monocular_right"], "Hemifield relationship."),
            "spatial_freq_cpd": _f(0.08, 0.005, 1.0, "Spatial frequency (cycles/deg)."),
            "temporal_freq_hz": _f(2.0, 0.1, 20.0, "Temporal frequency magnitude (Hz)."),
            "contrast": _f(0.9, 0.0, 1.0, "Michelson contrast."),
            "waveform": _c("square", ["sine", "square"], "Grating profile."),
            "duration_s": _f(10.0, 0.5, 180.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
    "looming": {
        "description": "Looming disc — escape / O-bend, parametric l/v.",
        "builder": looming,
        "params": {
            "l_over_v_s": _f(0.06, 0.005, 0.5, "Object half-size over approach speed (s)."),
            "max_radius_deg": _f(35.0, 5.0, 90.0, "Max angular radius (deg)."),
            "polarity": _c("dark", ["dark", "light"], "Disc polarity."),
            "contrast": _f(1.0, 0.0, 1.0, "Disc contrast."),
            "duration_s": _f(4.0, 0.5, 30.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
    "dark_flash": {
        "description": "Whole-field dark flash — luminance step.",
        "builder": dark_flash,
        "params": {
            "baseline_lum": _f(0.5, 0.0, 1.0, "Pre/post luminance."),
            "flash_lum": _f(0.0, 0.0, 1.0, "Flash luminance."),
            "onset_s": _f(2.0, 0.0, 60.0, "Flash onset (s)."),
            "flash_duration_s": _f(0.5, 0.02, 10.0, "Flash duration (s)."),
            "duration_s": _f(6.0, 0.5, 60.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
    "prey": {
        "description": "Prey-like moving dot — hunting / J-turns.",
        "builder": prey,
        "params": {
            "size_deg": _f(0.5, 0.05, 3.0, "Dot diameter (deg)."),
            "speed_dps": _f(8.0, 0.5, 60.0, "Dot speed (deg/s); saltatory bursts move 3x this."),
            "trajectory": _c("saltatory", ["linear", "brownian", "saltatory"], "Motion type."),
            "polarity": _c("dark", ["dark", "light"], "Contrast polarity."),
            "contrast": _f(1.0, 0.0, 1.0, "Contrast."),
            "duration_s": _f(10.0, 0.5, 180.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
    "moving_bar": {
        "description": "Moving bar / edge — direction & RF tuning.",
        "builder": moving_bar,
        "params": {
            "width_deg": _f(4.0, 0.2, 40.0, "Bar width (deg)."),
            "speed_dps": _f(20.0, 0.5, 120.0, "Sweep speed (deg/s)."),
            "direction_deg": _f(0.0, 0.0, 360.0, "Sweep direction (deg)."),
            "polarity": _c("dark", ["dark", "light"], "Bar polarity."),
            "contrast": _f(1.0, 0.0, 1.0, "Contrast."),
            "duration_s": _f(6.0, 0.5, 60.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
    "static_grating": {
        "description": "Static grating — contrast / spatial-frequency tuning baseline.",
        "builder": static_grating,
        "params": {
            "spatial_freq_cpd": _f(0.1, 0.005, 1.0, "Spatial frequency (cycles/deg)."),
            "contrast": _f(0.9, 0.0, 1.0, "Michelson contrast."),
            "direction_deg": _f(0.0, 0.0, 360.0, "Carrier orientation (deg)."),
            "waveform": _c("sine", ["sine", "square"], "Grating profile."),
            "duration_s": _f(4.0, 0.5, 60.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
    "checkerboard": {
        "description": "Static or contrast-reversing checkerboard.",
        "builder": checkerboard,
        "params": {
            "check_size_deg": _f(5.0, 0.2, 40.0, "Check size (deg)."),
            "contrast": _f(0.9, 0.0, 1.0, "Contrast."),
            "reversal_hz": _f(2.0, 0.0, 30.0, "Contrast-reversal rate (Hz); 0 = static."),
            "duration_s": _f(6.0, 0.5, 60.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
    "light_dark_preference": {
        "description": "Scototaxis / phototaxis — split or gradient luminance field.",
        "builder": light_dark_preference,
        "params": {
            "mode": _c("split", ["split", "gradient"], "Split hemifields or smooth gradient."),
            "low_lum": _f(0.05, 0.0, 1.0, "Dark luminance."),
            "high_lum": _f(0.95, 0.0, 1.0, "Light luminance."),
            "axis_deg": _f(0.0, 0.0, 360.0, "Gradient axis (gradient mode)."),
            "duration_s": _f(10.0, 0.5, 180.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
    "social": {
        "description": "Animated conspecific(s) — social / shoaling (first-pass kinematic model).",
        "builder": social,
        "params": {
            "n_agents": _i(6, 1, 30, "Number of fish."),
            "body_size_deg": _f(2.0, 0.5, 10.0, "Body length (deg)."),
            "tail_beat_hz": _f(20.0, 1.0, 60.0, "Tail-beat frequency (Hz)."),
            "bout_period_s": _f(1.0, 0.2, 5.0, "Burst-and-glide period (s)."),
            "bout_duty": _f(0.4, 0.05, 1.0, "Active fraction per bout."),
            "speed_dps": _f(8.0, 0.5, 40.0, "Swim speed (deg/s)."),
            "schooling": _c("school", ["school", "random"], "Group geometry."),
            "duration_s": _f(12.0, 0.5, 180.0, "Clip duration (s)."),
            "seed": _i(0, 0, 999999, "Deterministic seed."),
        },
    },
}


def list_tasks() -> list[dict]:
    """Catalog metadata for selection (name, description, tunable params)."""
    return [{"name": name, "description": entry["description"], "params": entry["params"]} for name, entry in TASK_REGISTRY.items()]


def _coerce(meta: dict, raw):
    if meta["type"] == "int":
        return int(float(raw))
    if meta["type"] == "float":
        return float(raw)
    return str(raw)


def build_task(name: str, **overrides) -> ExperimentSpec:
    """Build an ExperimentSpec for a named task, coercing/validating overrides."""
    entry = TASK_REGISTRY.get(name)
    if entry is None:
        raise ValueError(f"unknown task {name!r}; known: {sorted(TASK_REGISTRY)}")
    params = entry["params"]
    kwargs = {}
    for key, value in overrides.items():
        if key not in params:
            raise ValueError(f"task {name!r} has no parameter {key!r}; valid: {sorted(params)}")
        coerced = _coerce(params[key], value)
        meta = params[key]
        if meta["type"] == "choice" and coerced not in meta["choices"]:
            raise ValueError(f"parameter {key!r} must be one of {meta['choices']}")
        kwargs[key] = coerced
    return entry["builder"](**kwargs)
