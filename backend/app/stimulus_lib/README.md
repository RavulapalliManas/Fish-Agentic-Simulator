# stimulus_lib — reproducible zebrafish visual-stimulus platform

Degrees-of-visual-angle, config-as-code stimulus generator. Renders **deterministic,
lossless** frame sequences with a **provenance manifest**, a **baked per-frame sync
marker**, and **stimulus-level Nyquist validation**. The shoaling app elsewhere in
`backend/app/` is untouched. Design rationale: `docs/stimulus-platform-roadmap.md`.

## Usage

```bash
# from the backend/ directory
python -m app.stimulus_lib.cli list-tasks
python -m app.stimulus_lib.cli make-task split_field_omr --param condition=conflict --param duration_s=10
python -m app.stimulus_lib.cli render app/stimulus_lib/examples/split_field_omr_conflict.json --out output/stimuli/demo
```

Outputs into `--out`: a lossless PNG sequence (`frames/`) or a single `.mkv` (`codec: ffv1`),
plus `<name>.manifest.json` (config hash, git commit, geometry, resolved layers/regions, gamma
policy, codec, fps, seed, sync-marker encoding, round-trip QA).

## Architecture: split falls out of masking

A scene is a list of **layers**; each layer = a **primitive** placed in a **region**, with a
**compositing** rule and a **timeline**. There is no per-paradigm render code — split-field,
monocular, conflict, prey-on-background, and surround stimuli are all layer/region combinations.

```jsonc
"scene": [
  { "type": "grating", "region": "left",  "spatial_freq_cpd": 0.08, "temporal_freq_hz":  2.0 },
  { "type": "grating", "region": "right", "spatial_freq_cpd": 0.08, "temporal_freq_hz": -2.0 }
]   // <- split-field OMR conflict. No "split" primitive exists.
```

- **Regions** (in degrees): `full`, `left`, `right`, `top`, `bottom`, `quadrant`, `circle`,
  `annulus`, `rect` (+ `invert`, `boundary_deg`, `center_deg`, …).
- **Compositing**: `over` (default), `blend` (weighted, for transparency/conflict), `occlude` (hard).
- **Timeline**: `onset_s`, `offset_s`, `fade_in_s`, `fade_out_s` per layer.

All optional — a bare `{"type": ...}` entry is full-field, `over`, always-on.

## Primitives

| type | key params |
|---|---|
| `grating` | spatial_freq_cpd, temporal_freq_hz / velocity_dps, contrast, direction_deg, waveform |
| `okr` | spatial_freq_cpd, angular_velocity_dps, contrast, center_deg, waveform |
| `checkerboard` | check_size_deg, contrast, reversal_hz |
| `rdk` | n_dots, coherence, speed_dps, direction_deg, dot_size_deg, dot_lifetime_s |
| `looming` | l_over_v_s, t_collision_s, max_radius_deg, contrast, polarity, center_deg |
| `dark_flash` | baseline_lum, flash_lum, onset_s, duration_s |
| `prey` | size_deg, speed_dps, trajectory (linear/brownian/saltatory), polarity |
| `bar` | width_deg, speed_dps, direction_deg, contrast, polarity |
| `gradient` | profile (linear/radial/sigmoid), axis_deg, low_lum, high_lum, center_deg, width_deg |
| `conspecific` | n_agents, body_size_deg, tail_beat_hz, bout_period_s, bout_duty, speed_dps, schooling — *first-pass kinematic model* |

## Tasks (paradigm catalog — "choose what to generate")

`list-tasks` returns each task's tunable parameters (defaults / ranges / choices) so a CLI or UI
can present them. `make-task <name> [--param k=v ...]` builds and renders it. Tasks: `omr`, `okr`,
`rdk`, `split_field_omr` {congruent/conflict/monocular_left/monocular_right}, `looming`,
`dark_flash`, `prey`, `moving_bar`, `static_grating`, `checkerboard`, `light_dark_preference`
{split/gradient}, `social`.

## Batch sweep + counterbalancing

```python
from stimulus_lib import expand_sweep
design = expand_sweep(base_spec,
    axes=[{"path": "scene.0.contrast", "values": [0.2, 0.5, 0.8]},
          {"path": "scene.0.temporal_freq_hz", "values": [1, 2, 4]}],
    presentation_seed=7)
# -> full-factorial conditions (each config-hashed) + a presentation_order randomized on a
#    SEPARATE seed, independent of generation order.
```

## Validation (correctness gates)

Render is refused if a layer violates Nyquist: spatial frequency past 0.5 cyc/px; grating/OKR/
checkerboard temporal motion ≥ 0.5 cycle/frame (reverse-phi); RDK/prey step larger than a dot per
frame; conspecific tail-beat ≥ 0.5·fps. A non-fatal warning is recorded if `fps` is not an integer
multiple/divisor of the display refresh.

## Defaults (configurable in every spec)

Generic planar rig (30 mm, 68×38 mm / 1280×720, 60 Hz, γ=2.2); `gamma_policy` `encode_into_file`;
`codec` `png_sequence` (lossless, round-trip verified). Replace geometry with your measured display.
Curved-dish / below-projection is not supported yet.

## Reproducibility & QA tooling

```bash
python -m app.stimulus_lib.cli calibration-ramp                       # levels to display for measurement
python -m app.stimulus_lib.cli calibrate meas.csv --out cal.json --display-id rig-A
python -m app.stimulus_lib.cli qa            output/stimuli/demo      # -> demo.qa.html
python -m app.stimulus_lib.cli decode-timing output/stimuli/demo      # sync-marker frame timing
python -m app.stimulus_lib.cli verify        output/stimuli/demo --write-golden golden.json
python -m app.stimulus_lib.cli verify        output/stimuli/demo --golden golden.json
python -m app.stimulus_lib.cli reproduce     output/stimuli/demo/demo.manifest.json --out repro
python -m app.stimulus_lib.cli export-events  spec.json --out events.tsv
```

- **Calibration** — `gamma_policy: "measured_lut"` + `render.calibration_file` linearizes against a
  measured luminance curve (recorded in the manifest); `Calibration.to_cd_m2()` gives physical units.
- **Timing** — `sync_decode` recovers frame onsets from the baked marker (and a photodiode trace) and
  flags dropped / duplicated frames.
- **QA** — `qa` writes a self-contained HTML sheet (provenance, luminance + Michelson contrast,
  Nyquist, lossless gate, thumbnails).
- **Regression** — `verify` fingerprints a render; `reproduce` rebuilds from a manifest and checks
  config-hash **and** frame-hash match (so an update can't silently change a stimulus).
- **Events** — `export-events` / `events.sweep_events` emit a BIDS-style `events.tsv` for merging
  with behavior / imaging data.

The manifest is self-contained (authored spec + config hash + git commit + geometry + calibration),
so any render is reproducible from its manifest alone.

## Deferred (see roadmap)

Projector / perspective warp for curved-dish or below-projection; closed-loop real-time presenter;
active/Bayesian (QUEST/Ψ) adaptive selection over the sweep grid; frontend task picker + session
builder; NWB export.
