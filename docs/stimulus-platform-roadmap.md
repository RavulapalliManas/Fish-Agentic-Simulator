# Stimulus Platform Roadmap

Evolving this repo from a deterministic shoaling→MP4 generator into a **reproducible
zebrafish/larval visual-stimulus platform**. This is a plan, not an implementation.

## Locked decisions (2026-06-25)

| Decision | Choice | Consequence |
|---|---|---|
| Deliverable now | **Roadmap first** | This document; no code until it's agreed. |
| RL objective | **Active / Bayesian psychophysics** | Maximize information about a behavioral threshold (info-gain over a psychometric model). |
| Output target | **Pre-rendered lossless files** for an existing rig/player | We own render + manifest; we do **not** ship a presenter. Codec defaults to lossless. |
| Codebase | **Extend this repo** | Reuse the **infrastructure** (determinism, manifest, render pipeline, UI) as the spine. The shoaling *renderer* (top-down arena) is largely **not** reusable as an eye-view stimulus — see Q5; don't assume the conspecific primitive is near-done. |

### The one tension to resolve explicitly
Active psychophysics is a loop; pre-rendered files are open-loop. **Resolution:** adaptivity
runs at the **trial level over a pre-rendered bank**, not per frame.

- Pre-render a lossless **grid** over the threshold dimension(s) (e.g. contrast ∈ {…}, coherence ∈ {…}).
- An **adaptive selection policy** holds a Bayesian posterior over the psychometric function and
  picks the next condition (= next pre-rendered file) to present.
- Presentation (photons) + behavior tracking stay on the rig. Our system exposes a thin
  **trial API**: `POST outcome → GET next stimulus file`.
- This keeps every presented frame lossless while still being adaptive. On-demand rendering of
  off-grid conditions is a later upgrade if the grid proves too coarse.
- **This is not a compromise.** Info-max adaptive methods (QUEST, the Ψ-method) already operate over
  a **discretized stimulus grid** — computing expected information across enumerated candidate
  intensities is how they work. A pre-rendered bank is the representation the method wants; the only
  real knob is grid resolution.
- **If instead you need per-frame real-time closed-loop**, the output-target decision changes to
  "ship our own player" and Phase 3 below is rewritten. Flag this before P0 if so.

### Storage vs. regeneration (resolve before P0)
Pre-rendered lossless discards the cheap thing we already own — exact reproducibility from
seed+spec — and pays for it in disk. Intra-frame lossless (FFV1, PNG/TIFF) compresses worst on
exactly the noise-heavy stimuli that need it: a lossless high-fps **RDK** is order ~0.2–0.4 MB/frame
× thousands of frames ≈ **1.5–2.5 GB per condition**, and a coherence × direction × repeat grid is
easily **50–150 GB per experiment**.

**Action before P0:** do the worst-case arithmetic (most codec-sensitive primitive × grid ×
counterbalancing) against real disk. If it's prohibitive, revisit the output-target fork toward a
**thin rig-side player that regenerates frames from seed+spec** — trivial given our determinism, and
cheap to choose now but expensive after P0.

---

## Where the current code stands

Keep (already correct for this goal):
- **Determinism** — `np.random.default_rng(seed)` threaded through a fixed-timestep engine
  (`backend/app/simulation.py`). Same seed+config → identical frames.
- **Metadata sidecar** — `renderer/video_exporter._write_metadata` (seed of provenance).
- **Preview-first inspector** — the redesigned canvas UI; extends naturally to any primitive.
- **Shoaling engine** — its determinism and integrator feed the `conspecific` primitive, but the
  *renderer* is a top-down arena, not an eye-view; treat the visuals as net-new (Q5). The real reuse
  is the infrastructure above, not this renderer.

Conflicts with the goal (must change):
- **Codec/colorspace** — `video_exporter.py` renders `libx264 → yuv420p` (OpenCV fallback
  mp4v/avc1). Lossy + 4:2:0 chroma subsampling contaminates gratings/RDK/looming.
- **Pixels, not degrees** — `utils/config.py` is entirely pixel-based; no display geometry.
- **Partial provenance** — sidecar stores config+seed but no config hash, git commit, or geometry.
- **fps not display-pinned, no sync marker** — renderer can emit fps the playback path resamples.

---

## Target architecture (extending `backend/app/`)

```
backend/app/
  geometry/            NEW  display geometry + degrees-of-visual-angle <-> pixels, gamma, refresh
  stimuli/             NEW  primitive library (composable)
    base.py                 Stimulus ABC: param schema + render_layer(t, geometry, rng) -> linear RGBA
    grating.py              drifting gratings (spatial/temporal freq, contrast, orientation, phase)
    looming.py              looming disc, explicit l/v
    rdk.py                  random-dot kinematogram, coherence knob
    prey.py                 small prey-like dots
    dark_flash.py           whole-field luminance step
    bar.py                  moving bars / edges
    conspecific.py          wraps the existing shoaling StimulusEngine
    scene.py                Scene: ordered layers -> superposed composite frame
  render/              REWORK from renderer/
    compositor.py           linear-light float framebuffer -> gamma -> quantize
    writers.py              FFV1/MKV, PNG/TIFF sequence  (H.264 only as explicit preview)
    sync_marker.py          per-frame corner code baked into frames
    qa.py                   rendered-vs-decoded difference-image gate
  specs/               NEW  config-as-code
    spec.py                 ExperimentSpec (YAML/JSON) + validation + config hash
    manifest.py             per-file + batch manifest (provenance)
    batch.py                deterministic batch gen + counterbalancing
  experiment/          NEW (Phase 3) active/Bayesian psychophysics
    psychometric.py         model + posterior update
    policy.py               info-gain selection over the pre-rendered bank
    runner.py               trial API: receive outcome, return next stimulus
  utils/, paradigms/, models/, agents/   reused (shoaling internals)
```

The existing `StimulusConfig` is retained as the **conspecific primitive's** parameter block,
nested inside the new `ExperimentSpec` rather than being the top-level config.

---

## Coordinate spine: degrees of visual angle

A `DisplayGeometry` record is the single source of truth, stored in every manifest:
`viewing_distance_mm`, `screen_w_mm/h_mm`, `screen_w_px/h_px` (→ px/mm, px/deg),
`refresh_hz`, `gamma_target`, and a free-text `display_id` for the measured device.

- All stimulus parameters are authored in **degrees / deg·s⁻¹ / cycles·deg⁻¹**; converted to
  pixels only at render against the stored geometry.
- Pixels never appear in a spec. "Which video was l/v=0.5 at 80% contrast" is a manifest lookup.
- UV caveat recorded, not solved: RGB cannot render what zebrafish UV cones see; manifests state
  this and the channel mapping used. (See "Open questions" for stance.)
- **Planar assumption is explicit, not silent.** `viewing_distance + screen_mm` is a flat,
  fronto-parallel model; degrees of visual angle are not well-defined on a curved dish or
  below-projection without the projection topology. P0 is scoped to **planar**; curved/below
  perspective correction is a tracked `projection` model (Q10), not an omission.

## Render pipeline (the part that quietly invalidates experiments)

1. Each primitive renders into a **linear-light float** framebuffer (no premature 8-bit).
2. `compositor` superposes layers, then applies the **gamma policy** (pre-correct into file for a
   named display, **or** render linear + correct at playback — explicit, recorded either way).
3. Quantize and write **lossless by default**: FFV1 in MKV, or PNG/TIFF frame sequence.
   H.264 remains available but only as a clearly-labeled preview/"visually-lossless" path, never
   the default for a measured condition.
4. **QA gate** (`qa.py`): decode the written file, diff against the rendered frames, fail the
   condition if banding/block error exceeds threshold. Banding in smooth gradients is the silent one.
5. **fps discipline**: output fps is pinned and checked against `refresh_hz` (integer
   multiple/divisor); warn loudly otherwise. Target ≥100 Hz where hardware allows (CFF).
6. **Sync marker**: a corner patch encodes per-frame index (binary code) baked into the frames so a
   photodiode trace recovers exact timing at playback. Encoding documented in the manifest.

## Config-as-code & provenance

- `ExperimentSpec` authored as YAML/JSON, validated, hashed (`config_hash`).
- **Validation includes stimulus-level Nyquist gates** (correctness, not style): reject spatial
  frequencies finer than the display can resolve (~2 px/cycle, a function of px/deg) and temporal
  motion exceeding ~0.5 cycle (or dot-step) per frame (aliasing / reverse-phi). These sit next to
  the geometry layer — the fps section only handles *display* sync, not *stimulus* temporal Nyquist.
- Per-file **manifest** sidecar: `config_hash`, `git_commit`, full resolved params, `DisplayGeometry`,
  gamma policy, codec, fps, seed(s), sync-marker encoding, QA result. Extends the existing sidecar.
- **Batch**: one master spec → deterministic regeneration of a full counterbalanced set + a set
  manifest. **Presentation order is randomized with a separate seed**, independent of generation
  order, so we're never locked into render order.

## Active / Bayesian psychophysics (Phase 3)

- `psychometric.py`: parametric psychometric model (e.g. Weibull/logistic) + Bayesian posterior.
- `policy.py`: pick the next condition to **maximize expected information** about the threshold,
  selecting from the pre-rendered bank.
- `runner.py`: trial API the rig calls — `POST /trial {condition_id, outcome}` updates the
  posterior; `GET /next` returns the next stimulus file + manifest ref. Seeded and logged per trial.
- **Integration boundary = the behavior signal.** Its source/format (correct/incorrect, response
  magnitude/latency, tracking) lives on the rig and must be specified before Phase 3 (see below).

## Logging & QA

- Every session emits a structured **event log**: condition, file, manifest hash, intended vs
  actual onset (from the sync decode), trial outcome.
- **Fish's-eye inspector**: the redesigned canvas extends to preview any primitive/scene before
  committing animal time.
- A **photodiode-decode utility** recovers true frame timing from a recorded trace.

---

## Phased plan

**P0 — Foundation (retrofit-expensive; build first).** `geometry/`, lossless `writers.py` +
`qa.py` diff gate, sync marker, `ExperimentSpec` + `manifest.py` (hash + commit + geometry), fps
discipline. *Done when:* a shoaling render round-trips as FFV1 with a full manifest and passes the
diff gate; one parameter is authored in degrees.

**P1 — Primitives.** `stimuli/base.py` + grating, looming, RDK first (highest-value, codec-sensitive),
then prey/dark-flash/bar; `conspecific.py` wraps the existing engine; `scene.py` superposition.
*Done when:* a grating and a looming disc render losslessly from a spec, and a prey-dot-on-grating
scene composites correctly, all in degrees.

**P2 — Batch & counterbalancing.** `batch.py` + set manifest + separate presentation-order seed; UI
to define a sweep. *Done when:* a master spec regenerates a balanced set deterministically with a
verifiable set manifest.

**P3 — Active psychophysics.** `experiment/` model + policy + trial API over the P2 bank, once the
behavior-signal protocol is fixed. *Done when:* a simulated observer drives the adaptive loop to a
threshold estimate in fewer trials than a fixed staircase.

---

## Open questions (need answers before the relevant phase)

1. **Gamma**: pre-correct into files for one measured display, or render linear and correct at
   playback on the rig? (P0)
2. **Lossless default**: FFV1/MKV vs PNG/TIFF frame sequence — depends on what the rig player ingests. (P0)
3. **Display(s)**: target refresh, resolution, viewing distance, measured gamma, and `display_id`. (P0)
4. **UV stance**: document-only, or add a UV-channel abstraction for a UV-capable projector later? (P1)
5. **Conspecific fidelity**: is the current top-down arena acceptable as a social stimulus, or does
   the conspecific primitive need an eye-view / tail-beat-and-bout kinematic model? (P1)
6. **Behavior-signal protocol**: source, format, and transport of trial outcomes from the rig. (P3)
7. **Active-mode rendering**: pre-rendered grid only, or on-demand render of off-grid conditions? (P3)
8. **Presentation framework**: does the rig already use PsychoPy/Bonsai/Stytra (sets manifest format),
   or is presentation bespoke? (P2/P3)
9. **Storage budget vs. regenerate-on-rig**: is pre-rendered lossless affordable at your real grid
   size, or should presentation regenerate from seed+spec on the rig? This can flip the
   output-target fork. (**before P0**)
10. **Projection topology**: flat screen, or curved dish / below-projection needing perspective
    correction? Determines whether the geometry layer needs a `projection`/warp model. (P0/P1)
