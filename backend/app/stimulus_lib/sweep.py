"""Batch-sweep / counterbalancing layer.

This is the reproducible-experiment companion to a single :class:`ExperimentSpec`:
given a *base* spec and a list of factor *axes*, it expands the full-factorial
Cartesian product of those axes into one ``ExperimentSpec`` per cell, content-
addresses each with :func:`config_hash`, and emits a counterbalanced
*presentation order*.

DIFFERENT CONTRACT from the renderable stimuli: nothing here is a ``Stimulus`` or
a ``Layer``. ``expand_sweep`` consumes specs and returns a plain dict describing
the design (axes, per-condition overrides + hashes, the rebuilt specs, and the
randomised presentation order).

The two sources of randomness are deliberately kept separate:

* the **generation** order is the deterministic, lexicographic order of the
  Cartesian product (``itertools.product``), with the *last* axis varying
  fastest. It never depends on a seed.
* the **presentation** order is drawn from its own
  ``np.random.default_rng(presentation_seed)`` and is therefore reproducible for
  a fixed ``presentation_seed`` yet statistically independent of the generation
  order (it is not biased toward the identity permutation).

This separation is what makes the layer usable for counterbalancing: condition
*content* is fixed and auditable by config hash, while the *sequence* a subject
sees is randomised and reseedable without touching the stimuli.
"""

from __future__ import annotations

import copy
import itertools
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .spec import ExperimentSpec, config_hash


def _parse_segment(node: Any, segment: str) -> Any:
    """Coerce a dotted-path *segment* to the key/index appropriate for *node*.

    Lists are indexed by ``int`` (e.g. ``scene.0`` -> ``scene[0]``); mappings are
    keyed by the raw string. The distinction is driven by the container type so
    that integer-looking dict keys are never silently turned into list indices.
    """
    if isinstance(node, (list, tuple)):
        try:
            return int(segment)
        except (TypeError, ValueError):
            raise KeyError(
                f"path segment {segment!r} is not a valid list index for a sequence"
            ) from None
    return segment


def set_path(canonical_dict: Any, dotted_path: str, value: Any) -> Any:
    """Set ``canonical_dict[a][b]...[z] = value`` for ``dotted_path == "a.b...z"``.

    Walks dict keys and ``int`` list indices in place, mutating *canonical_dict*,
    and returns it for convenience. The walk descends through every segment but
    the last, then assigns ``value`` at the final segment.

    Examples (paths into ``ExperimentSpec.to_canonical_dict()``)::

        set_path(d, "scene.0.contrast", 0.8)        # d["scene"][0]["contrast"]
        set_path(d, "render.fps", 30)               # d["render"]["fps"]
        set_path(d, "scene.1.temporal_freq_hz", 2)  # d["scene"][1]["temporal_freq_hz"]
    """
    if not dotted_path:
        raise ValueError("dotted_path must be a non-empty string")

    segments = dotted_path.split(".")
    node = canonical_dict
    for segment in segments[:-1]:
        key = _parse_segment(node, segment)
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            raise KeyError(
                f"cannot resolve path segment {segment!r} of {dotted_path!r}"
            ) from None

    last = _parse_segment(node, segments[-1])
    try:
        node[last] = value
    except (IndexError, TypeError):
        raise KeyError(
            f"cannot set final path segment {segments[-1]!r} of {dotted_path!r}"
        ) from None
    return canonical_dict


def _spec_from_canonical(data: Mapping[str, Any], name: str) -> ExperimentSpec:
    """Rebuild an :class:`ExperimentSpec` from a canonical dict, overriding name.

    Mirrors the keys produced by :meth:`ExperimentSpec.to_canonical_dict`; the
    explicit ``name`` argument wins over any ``name`` in *data*.
    """
    return ExperimentSpec(
        name=name,
        seed=int(data.get("seed", 0)),
        geometry=dict(data.get("geometry") or {}),
        render=dict(data.get("render") or {}),
        scene=list(data.get("scene") or []),
    )


def expand_sweep(
    base: ExperimentSpec,
    axes: Sequence[Mapping[str, Any]],
    presentation_seed: int = 0,
) -> dict:
    """Expand a full-factorial sweep over *axes* applied to a *base* spec.

    Parameters
    ----------
    base:
        The template :class:`ExperimentSpec`. Its canonical dict is deep-copied
        once per condition and never mutated.
    axes:
        Ordered list of ``{"path": <dotted path>, "values": [...]}`` factors.
        ``path`` is a dotted path into ``base.to_canonical_dict()`` (e.g.
        ``"scene.0.contrast"``, ``"render.fps"``). The Cartesian product is taken
        with the last axis varying fastest.
    presentation_seed:
        Seed for an independent ``np.random.default_rng`` used solely to draw the
        randomised presentation order.

    Returns
    -------
    dict with keys ``axes``, ``n_conditions``, ``conditions`` (one record per
    cell with ``index``, ``name``, ``overrides``, ``config_hash``), ``specs``
    (the rebuilt ``ExperimentSpec`` objects, in generation order),
    ``presentation_order`` (a permutation of ``range(n_conditions)``), and
    ``presentation_seed``.
    """
    axes_list = [
        {"path": str(axis["path"]), "values": list(axis["values"])}
        for axis in axes
    ]

    paths = [axis["path"] for axis in axes_list]
    value_lists: list[list[Any]] = [axis["values"] for axis in axes_list]

    # Full-factorial Cartesian product. itertools.product over zero axes yields a
    # single empty tuple, i.e. exactly one condition that equals the base spec.
    combinations: Iterable[tuple] = itertools.product(*value_lists)

    base_canonical = base.to_canonical_dict()

    conditions: list[dict] = []
    specs: list[ExperimentSpec] = []

    for index, combo in enumerate(combinations):
        overrides = {path: value for path, value in zip(paths, combo)}

        canonical = copy.deepcopy(base_canonical)
        for path, value in overrides.items():
            set_path(canonical, path, value)

        name = f"{base.name}__cond{index:03d}"
        spec = _spec_from_canonical(canonical, name)
        specs.append(spec)

        conditions.append(
            {
                "index": index,
                "name": name,
                "overrides": overrides,
                "config_hash": config_hash(spec),
            }
        )

    n_conditions = len(specs)

    # Presentation order: a SEPARATE rng, independent of generation order, so the
    # sequence is reproducible per seed yet not biased toward the identity.
    rng = np.random.default_rng(presentation_seed)
    presentation_order = [int(i) for i in rng.permutation(n_conditions)]

    return {
        "axes": axes_list,
        "n_conditions": n_conditions,
        "conditions": conditions,
        "specs": specs,
        "presentation_order": presentation_order,
        "presentation_seed": presentation_seed,
    }
