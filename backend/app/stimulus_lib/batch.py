"""Batch rendering of a sweep design with job management.

A :func:`stimulus_lib.expand_sweep` design is a *plan*: N content-addressed
``ExperimentSpec`` objects plus a counterbalanced presentation order. This module
is the *executor* — it turns that plan into rendered output on disk, with the job
hygiene a multi-condition render run needs:

* **Cost up front.** :func:`estimate_cost` predicts frames / bytes / seconds for a
  whole design *without rendering* (frame count from ``duration_s * fps``, bytes
  from the geometry's ``W * H * 3``, seconds from a per-frame constant). It never
  builds a scene or touches the RNG, so it is safe to call on a design that
  contains a condition which will later fail to render.
* **Idempotent skipping.** A condition whose output directory already holds a
  manifest with the *same* ``config_hash`` is skipped, so re-running a partially
  completed (or fully completed) batch is cheap and side-effect-free. ``force``
  overrides this and re-renders.
* **Fault isolation.** Conditions render in parallel on a thread pool; one
  condition raising (e.g. an invalid scene) is caught, recorded as
  ``status="failed"`` with its error string, and never aborts the siblings.
* **Disk guard.** Before any work, the design's estimated byte footprint is
  compared against the free space on ``out_root`` and the run is refused if it
  will not fit (unless ``force``), so a batch fails fast and clean rather than
  half-way through with a full disk.

Only the standard library and the existing :func:`render_experiment` are used; no
new heavy dependency enters here.
"""

from __future__ import annotations

import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from .render import render_experiment
from .spec import ExperimentSpec, config_hash

# Per-frame wall-clock estimate used by :func:`estimate_cost`. This is a coarse
# planning constant, NOT a measurement: it lets ``est_seconds`` scale with the
# work without rendering anything (which would be unsafe to do for a design that
# contains a deliberately failing condition). Tune for the rig if desired.
_SECONDS_PER_FRAME = 0.01


def _frame_count(spec: ExperimentSpec) -> int:
    """Predicted frame count for *spec* — matches ``render_experiment``'s formula.

    Uses ``render_settings()`` (which merges :data:`DEFAULT_RENDER`) rather than
    the raw, possibly-partial ``render`` dict, so authored specs that only
    override a subset of render keys still estimate correctly. The ``max(1, ...)``
    mirrors the renderer: a sub-frame duration still produces one frame.
    """
    settings = spec.render_settings()
    fps = float(settings["fps"])
    duration = float(settings["duration_s"])
    return max(1, int(round(duration * fps)))


def estimate_cost(design: dict, geometry=None) -> dict:
    """Predict the cost of rendering *design* without performing any render.

    Parameters
    ----------
    design:
        A sweep design dict (the return value of
        :func:`stimulus_lib.expand_sweep`); only ``design["specs"]`` is read.
    geometry:
        Optional :class:`~stimulus_lib.geometry.DisplayGeometry` used for the
        pixel dimensions of *every* condition. When ``None`` each spec's own
        ``display_geometry()`` is used (specs may differ in resolution).

    Returns
    -------
    dict with ``n_conditions``, ``total_frames``, ``est_bytes`` and
    ``est_seconds``. ``est_bytes`` is ``frames * W * H * 3`` summed across
    conditions (uncompressed RGB upper bound — real PNG/FFV1 output is smaller, so
    the disk guard errs safe). ``est_seconds`` is ``total_frames *`` a per-frame
    constant.

    This function deliberately never calls ``build_scene``/``validate`` or the
    RNG, so it stays total: a design holding a condition that will fail to render
    still estimates cleanly, which is what makes the pre-render disk guard usable.
    """
    specs = list(design.get("specs") or [])

    total_frames = 0
    est_bytes = 0
    for spec in specs:
        try:
            n_frames = _frame_count(spec)
            geo = geometry if geometry is not None else spec.display_geometry()
            bytes_per_frame = int(geo.screen_w_px) * int(geo.screen_h_px) * 3
        except Exception:
            # A spec that cannot even be measured (e.g. malformed geometry that
            # will not construct) renders zero bytes — it fails per-condition at
            # render time and is isolated there. Counting it as 0 here keeps this
            # function total (its documented promise), so the disk guard still
            # sums the measurable conditions instead of aborting the whole batch
            # on one un-estimatable cell.
            continue
        total_frames += n_frames
        est_bytes += n_frames * bytes_per_frame

    return {
        "n_conditions": len(specs),
        "total_frames": int(total_frames),
        "est_bytes": int(est_bytes),
        "est_seconds": float(total_frames * _SECONDS_PER_FRAME),
    }


def _existing_config_hash(out_dir: Path, name: str) -> str | None:
    """Return the ``config_hash`` recorded in ``out_dir/<name>.manifest.json``.

    Returns ``None`` when the manifest is absent, unreadable, or not valid JSON —
    i.e. "no trustworthy prior render here", which the caller treats as "render
    it", never as an error. Only a manifest that parses *and* carries a hash can
    authorise a skip.
    """
    manifest_path = out_dir / f"{name}.manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = manifest.get("config_hash")
    return str(value) if value is not None else None


def _render_condition(spec: ExperimentSpec, out_root: Path, index: int, force: bool) -> dict:
    """Render a single condition, returning one result record (never raises).

    Resolves the per-condition output directory ``out_root/<spec.name>``, applies
    the skip rule (manifest present with matching ``config_hash`` and not
    *force*), and otherwise renders. Any exception from ``render_experiment`` is
    caught and reported as ``status="failed"`` so one bad condition cannot abort
    the batch.
    """
    out_dir = out_root / spec.name
    spec_hash = config_hash(spec)
    result = {
        "index": index,
        "name": spec.name,
        "config_hash": spec_hash,
        "out_dir": str(out_dir),
    }

    if not force and _existing_config_hash(out_dir, spec.name) == spec_hash:
        result["status"] = "skipped"
        return result

    try:
        render_experiment(spec, out_dir)
        result["status"] = "done"
    except Exception as exc:  # one condition's failure must not abort the batch
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def render_batch(
    design: dict,
    out_root: str | Path,
    force: bool = False,
    max_workers: int | None = None,
    on_progress: Callable[[dict], None] | None = None,
) -> dict:
    """Render every condition of a sweep *design* into ``out_root``.

    Each ``design["specs"][i]`` is rendered to ``out_root/<spec.name>``. A
    condition is **skipped** when that directory already holds a manifest whose
    ``config_hash`` equals the spec's (so re-running a completed batch is a no-op),
    unless *force* re-renders unconditionally. Conditions run on a
    :class:`~concurrent.futures.ThreadPoolExecutor`; a condition that raises is
    caught and recorded ``status="failed"`` without aborting the rest.

    Before any rendering, a disk guard compares :func:`estimate_cost`'s
    ``est_bytes`` to ``shutil.disk_usage(out_root).free`` and raises
    :class:`RuntimeError` if the run will not fit — unless *force*.

    Parameters
    ----------
    design:
        A sweep design dict (see :func:`stimulus_lib.expand_sweep`).
    out_root:
        Root directory for all per-condition output dirs (created if absent).
    force:
        Skip the disk guard and the skip-on-matching-hash rule; re-render all.
    max_workers:
        Thread-pool size; defaults to ``min(8, os.cpu_count() or 1)``.
    on_progress:
        Optional callback invoked once per *completed* condition with that
        condition's result dict, from the main thread (never from a worker), so it
        is safe to update a progress bar or log from it.

    Returns
    -------
    dict with ``results`` (one record per condition, **sorted by ``index``**, each
    ``{index, name, status, out_dir, config_hash}`` plus ``error`` when failed) and
    ``summary`` (``{done, skipped, failed}`` counts).
    """
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    specs = list(design.get("specs") or [])

    # Disk guard: refuse a run that will not fit before doing any work. The
    # estimate is an uncompressed-RGB upper bound, so this errs on the safe side.
    if not force:
        est = estimate_cost(design)
        free = shutil.disk_usage(out_root).free
        if est["est_bytes"] > free:
            raise RuntimeError(
                f"insufficient disk space on {out_root}: estimated {est['est_bytes']} bytes "
                f"for {est['n_conditions']} condition(s) but only {free} free. "
                "Pass force=True to override the disk guard."
            )

    if max_workers is None:
        max_workers = min(8, os.cpu_count() or 1)
    max_workers = max(1, int(max_workers))

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_render_condition, spec, out_root, index, force): index
            for index, spec in enumerate(specs)
        }
        for future in as_completed(futures):
            result = future.result()  # _render_condition never raises
            results.append(result)
            if on_progress is not None:
                on_progress(result)

    # Futures complete out of order; restore generation order so results[i] is
    # deterministic and aligns with design["specs"][i].
    results.sort(key=lambda r: r["index"])

    summary = {"done": 0, "skipped": 0, "failed": 0}
    for result in results:
        summary[result["status"]] += 1

    return {"results": results, "summary": summary}


def render_one(
    design: dict,
    index_or_name: int | str,
    out_root: str | Path,
    force: bool = False,
) -> dict:
    """Render exactly one condition of *design*, selected by index or name.

    *index_or_name* is an ``int`` index into ``design["specs"]`` or the ``str``
    condition name. The same skip / fault-isolation rules as :func:`render_batch`
    apply (a render error becomes ``status="failed"``), but **selection failures
    raise**: an out-of-range index or an unknown name is a programmer error, not a
    failed render, so it surfaces as :class:`IndexError` / :class:`KeyError`.

    Returns the single result record (``{index, name, status, out_dir,
    config_hash}`` plus ``error`` when failed). No disk guard runs for a single
    condition.
    """
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    specs = list(design.get("specs") or [])

    if isinstance(index_or_name, str):
        index = next((i for i, spec in enumerate(specs) if spec.name == index_or_name), None)
        if index is None:
            raise KeyError(
                f"no condition named {index_or_name!r} in design "
                f"(names: {[spec.name for spec in specs]})"
            )
    else:
        index = int(index_or_name)
        if index < 0 or index >= len(specs):
            raise IndexError(
                f"condition index {index} out of range for {len(specs)} condition(s)"
            )

    return _render_condition(specs[index], out_root, index, force)
