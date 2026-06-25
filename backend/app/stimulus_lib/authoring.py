"""Spec authoring helpers: inheritance, diff, dry-validate, linked params.

These sit one level *above* :class:`ExperimentSpec`: they help an author compose,
compare, and pre-flight specs (and whole sweep designs) before a single frame is
rendered, and they encode the experimental-design knowledge that one stimulus
implies a particular control.

Nothing here renders. ``dry_validate`` deliberately runs the same
``Scene.validate`` the real pipeline runs (so a Nyquist-violating spec is caught
identically) but never calls :func:`render_experiment` and never writes to disk.

Conventions match the rest of the package: dotted paths follow ``set_path`` /
``expand_sweep`` (``scene.0.contrast``, ``render.fps``), canonical dicts are the
shape produced by :meth:`ExperimentSpec.to_canonical_dict`, and frame counts use
the exact ``max(1, round(duration_s * fps))`` formula from ``render.py`` so the
estimates line up with what an actual render would produce.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from .spec import ExperimentSpec

# Mirrors render.py: per-frame storage is HxW gray repeated to 3 channels, at 1
# byte/sample for 8-bit and 2 for 16-bit. PNG/FFV1 compress this, so the estimate
# is a deliberate raw upper bound.
_BYTES_PER_SAMPLE = {8: 1, 16: 2}


def resolve_inheritance(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict:
    """Deep-merge *override* onto a deep copy of *base*.

    Nested dicts merge recursively; lists and scalars from *override* replace the
    corresponding value in *base* wholesale (a list is treated as an opaque leaf,
    never element-wise merged). Neither input is mutated -- the result and every
    value taken from *override* are deep-copied.

    Example::

        resolve_inheritance({"a": {"x": 1, "y": 2}}, {"a": {"y": 9}})
        # -> {"a": {"x": 1, "y": 9}}
    """
    merged = copy.deepcopy(dict(base))
    for key, override_value in override.items():
        base_value = merged.get(key)
        if (
            key in merged
            and isinstance(base_value, dict)
            and isinstance(override_value, dict)
        ):
            merged[key] = resolve_inheritance(base_value, override_value)
        else:
            merged[key] = copy.deepcopy(override_value)
    return merged


def _as_canonical(obj: Any) -> dict:
    """Coerce an :class:`ExperimentSpec` (or already-canonical dict) to a dict."""
    if isinstance(obj, ExperimentSpec):
        return obj.to_canonical_dict()
    return obj


def _flatten(node: Any, prefix: str, out: dict[str, Any]) -> None:
    """Flatten *node* to ``{dotted_path: leaf_value}`` matching ``set_path``.

    Recurses through ``dict`` keys and ``list`` indices (so ``scene.0.contrast``
    is a path); anything else (scalars, tuples, None) is a leaf. The container
    *itself* is never emitted as a leaf, so two specs differing inside ``scene``
    diff at the precise nested path rather than reporting the whole list changed.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            _flatten(value, child, out)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child = f"{prefix}.{index}" if prefix else str(index)
            _flatten(value, child, out)
    else:
        out[prefix] = node


def config_diff(a: Any, b: Any) -> dict:
    """Diff two specs/canonical dicts at leaf granularity.

    Either argument may be an :class:`ExperimentSpec` or an already-canonical
    dict. Both are flattened to dotted leaf paths and compared:

    * ``changed`` -- paths present in both with differing values, mapped to
      ``[a_value, b_value]``.
    * ``added``   -- paths present only in *b*, mapped to the *b* value.
    * ``removed`` -- paths present only in *a*, mapped to the *a* value.

    A change to a single nested scene parameter therefore reports exactly that
    one path (e.g. ``scene.0.contrast``), never the enclosing list.
    """
    flat_a: dict[str, Any] = {}
    flat_b: dict[str, Any] = {}
    _flatten(_as_canonical(a), "", flat_a)
    _flatten(_as_canonical(b), "", flat_b)

    changed: dict[str, list] = {}
    removed: dict[str, Any] = {}
    for path, value in flat_a.items():
        if path not in flat_b:
            removed[path] = value
        elif flat_b[path] != value:
            changed[path] = [value, flat_b[path]]

    added = {path: value for path, value in flat_b.items() if path not in flat_a}

    return {"changed": changed, "added": added, "removed": removed}


def _frames_for(spec: ExperimentSpec) -> int:
    """Frame count a real render would produce: ``max(1, round(dur * fps))``."""
    settings = spec.render_settings()
    fps = float(settings["fps"])
    duration = float(settings["duration_s"])
    return max(1, int(round(duration * fps)))


def _bytes_for(spec: ExperimentSpec, n_frames: int) -> int:
    """Raw upper-bound byte estimate: ``n_frames * H * W * 3 * bytes/sample``."""
    geometry = spec.display_geometry()
    settings = spec.render_settings()
    bit_depth = int(settings["bit_depth"])
    per_sample = _BYTES_PER_SAMPLE.get(bit_depth, 1)
    pixels = geometry.screen_h_px * geometry.screen_w_px
    return n_frames * pixels * 3 * per_sample


def dry_validate(spec_or_design: Any) -> dict:
    """Pre-flight a single spec or a whole sweep design without rendering.

    Accepts either a single :class:`ExperimentSpec` (treated as one condition) or
    an :func:`expand_sweep` design dict (with ``specs`` / ``n_conditions``). For
    every condition it builds the :class:`Scene`, runs ``scene.validate`` against
    the spec's geometry and fps (the same blocking checks the real pipeline runs,
    e.g. Nyquist), and accumulates frame/byte/second estimates. Build or
    validation failures are captured as error strings rather than raised, so a
    malformed spec yields a non-empty ``errors`` list instead of crashing.

    Renders nothing and writes nothing.

    Returns a dict with ``n_conditions``, ``total_frames``, ``est_seconds``
    (summed playback duration), ``est_bytes`` (summed raw upper bound), and
    ``errors`` (flat list, each prefixed with its condition name).
    """
    if isinstance(spec_or_design, ExperimentSpec):
        specs = [spec_or_design]
        n_conditions = 1
    elif isinstance(spec_or_design, Mapping) and "specs" in spec_or_design:
        specs = list(spec_or_design["specs"])
        n_conditions = int(spec_or_design.get("n_conditions", len(specs)))
    else:
        raise TypeError(
            "dry_validate expects an ExperimentSpec or an expand_sweep design dict "
            "(with a 'specs' key)"
        )

    total_frames = 0
    est_seconds = 0.0
    est_bytes = 0
    errors: list[str] = []

    for index, spec in enumerate(specs):
        label = getattr(spec, "name", None) or f"cond{index:03d}"
        try:
            settings = spec.render_settings()
            fps = float(settings["fps"])
            geometry = spec.display_geometry()
            scene = spec.build_scene()
            condition_errors = scene.validate(geometry, fps)
        except Exception as exc:  # malformed spec -> error, never a crash
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
            continue

        errors.extend(f"{label}: {message}" for message in condition_errors)

        n_frames = _frames_for(spec)
        total_frames += n_frames
        est_seconds += float(settings["duration_s"])
        est_bytes += _bytes_for(spec, n_frames)

    return {
        "n_conditions": n_conditions,
        "total_frames": total_frames,
        "est_seconds": est_seconds,
        "est_bytes": est_bytes,
        "errors": errors,
    }


# Looming primitive defaults (see stimuli/looming.py). Scene dicts may omit these
# keys, so the dimming control reads them with the primitive's own defaults to
# stay luminance-matched.
_LOOMING_DEFAULTS = {"mean_lum": 0.5, "contrast": 1.0, "polarity": "dark"}


def _disc_luminance(mean_lum: float, contrast: float, polarity: str) -> float:
    """The looming disc's luminance -- copied bit-for-bit from looming.py.

    ``dark`` -> ``mean*(1-contrast)``; otherwise ``mean*(1+contrast)``; clipped to
    [0, 1]. Reused verbatim so the dimming flash matches the disc exactly.
    """
    disc = mean_lum * (1.0 - contrast) if polarity == "dark" else mean_lum * (1.0 + contrast)
    return float(min(1.0, max(0.0, disc)))


def add_dimming_controls(specs: list[ExperimentSpec]) -> list[ExperimentSpec]:
    """Append a luminance-matched dimming control after each looming spec.

    Linked-parameter helper: a looming disc confounds *looming motion* with the
    *whole-field luminance drop* it causes. For every spec whose scene contains a
    looming layer, this appends a control spec -- a whole-field ``dark_flash``
    whose ``baseline_lum`` is the looming background mean and whose ``flash_lum``
    is the disc's own luminance -- so the luminance transient is reproduced with
    no motion. The control is named ``<name>__dimming`` and inherits the parent's
    seed, geometry, and render settings so it is frame-aligned and renderable.

    Specs without a looming layer pass through unchanged. The first looming layer
    of a spec drives the control (one control per spec). Originals are preserved
    in order, each control inserted immediately after its parent; a one-looming
    list therefore returns ``[original, control]``.
    """
    result: list[ExperimentSpec] = []
    for spec in specs:
        result.append(spec)

        looming_entry = next(
            (entry for entry in spec.scene if isinstance(entry, Mapping) and entry.get("type") == "looming"),
            None,
        )
        if looming_entry is None:
            continue

        mean_lum = float(looming_entry.get("mean_lum", _LOOMING_DEFAULTS["mean_lum"]))
        contrast = float(looming_entry.get("contrast", _LOOMING_DEFAULTS["contrast"]))
        polarity = str(looming_entry.get("polarity", _LOOMING_DEFAULTS["polarity"]))

        flash_lum = _disc_luminance(mean_lum, contrast, polarity)

        # Match the dimming transient's timing to the loom's collision when known,
        # else fall back to the DarkFlash defaults (which still render fine).
        onset_s = float(looming_entry.get("t_collision_s", 0.5))

        control = ExperimentSpec(
            name=f"{spec.name}__dimming",
            seed=spec.seed,
            geometry=copy.deepcopy(spec.geometry),
            render=copy.deepcopy(spec.render),
            scene=[
                {
                    "type": "dark_flash",
                    "baseline_lum": mean_lum,
                    "flash_lum": flash_lum,
                    "onset_s": onset_s,
                    "duration_s": 0.1,
                }
            ],
        )
        result.append(control)

    return result
