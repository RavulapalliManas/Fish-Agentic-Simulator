# stimulus_lib — reproducible visual-stimulus platform (P0 + core primitives)

Degrees-of-visual-angle, config-as-code stimulus generator. Renders **deterministic,
lossless** frame sequences with a **provenance manifest**, a **baked per-frame sync
marker**, and **stimulus-level Nyquist validation**. The shoaling app elsewhere in
`backend/app/` is untouched. Design rationale: `docs/stimulus-platform-roadmap.md`.

## Usage

```bash
# from the backend/ directory
python -m app.stimulus_lib.cli render app/stimulus_lib/examples/grating_omr.json --out output/stimuli/grating_omr
```

Outputs into the `--out` directory:
- `frames/frame_000000.png …` — lossless PNG sequence (or a single `.mkv` with `codec: "ffv1"`)
- `<name>.manifest.json` — provenance: config hash, git commit, geometry, resolved params,
  gamma policy, codec, fps, seed, sync-marker encoding, and the round-trip QA result.

## Spec format (JSON or YAML)

```jsonc
{
  "name": "grating_omr",
  "seed": 1234,
  "geometry": { "viewing_distance_mm": 30, "screen_w_mm": 68, "screen_h_mm": 38,
                "screen_w_px": 1280, "screen_h_px": 720, "refresh_hz": 60, "gamma": 2.2,
                "projection": "planar", "display_id": "bench-demo" },
  "render":   { "fps": 60, "duration_s": 2.0, "bit_depth": 8,
                "gamma_policy": "encode_into_file", "sync_marker": true,
                "codec": "png_sequence", "mean_lum": 0.5 },
  "scene":    [ { "type": "grating", "spatial_freq_cpd": 0.08, "temporal_freq_hz": 2.0,
                  "contrast": 0.9, "orientation_deg": 90 } ]
}
```

All spatial parameters are in **degrees of visual angle** (cycles/deg, deg/s); they are
converted to pixels against `geometry`. Layers in `scene` superpose (e.g. a looming disc
over a drifting grating — see `examples/looming_on_grating.json`).

## Primitives (P1 core)

| type | key params |
|---|---|
| `grating` | `spatial_freq_cpd`, `temporal_freq_hz`, `contrast`, `orientation_deg`, `phase_deg`, `mean_lum` |
| `looming` | `l_over_v_s`, `t_collision_s`, `max_radius_deg`, `contrast`, `polarity`, `center_deg` |
| `rdk` | `n_dots`, `coherence`, `speed_dps`, `direction_deg`, `dot_size_deg`, `dot_lifetime_s` |
| `dark_flash` | `baseline_lum`, `flash_lum`, `onset_s`, `duration_s` |
| `bar` | `width_deg`, `speed_dps`, `direction_deg`, `contrast`, `polarity` |

## Defaults chosen (configurable in every spec)

- **Geometry**: a generic small planar rig (30 mm distance, 68×38 mm / 1280×720, 60 Hz, γ=2.2).
  Replace with your measured display. Curved-dish / below-projection is **not** supported yet.
- **gamma_policy** `encode_into_file` (frames are display-ready for γ=2.2). Use
  `linear_record_only` to store linear and let the rig correct at playback.
- **codec** `png_sequence` (lossless, round-trip verified). `ffv1` writes a single lossless MKV.

## Validation (correctness gates, not style)

`render_experiment` refuses to render if a layer violates Nyquist:
- spatial frequency finer than the display resolves (> 0.5 cyc/px),
- grating motion ≥ 0.5 cycle/frame (aliasing / reverse-phi),
- RDK coherent step larger than a dot per frame.

A non-fatal warning is recorded if `fps` is not an integer multiple/divisor of the refresh rate.

## Deferred (next phases — see roadmap)

- **P2** batch generation + counterbalancing (presentation order randomized separately).
- **P3** active/Bayesian psychophysics — pending the rig's behavior-signal protocol.
- Conspecific primitive as an eye-view stimulus (the shoaling renderer is top-down).
- Frontend integration of the new primitives into the inspector UI.
