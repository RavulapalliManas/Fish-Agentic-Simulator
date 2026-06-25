"""Session / protocol builder — schedule clips into a timed presentation order.

A *session* is one subject's run: a flat list of tasks/specs, each repeated some
number of times, laid out end to end on a single clock. Where :mod:`sweep`
content-addresses a *factorial design* and emits one counterbalanced order, this
module is the experimenter-facing layer that turns a hand-authored *playlist*
(``[{"task": "omr"}, looming_spec, ...]``) into trials with onsets, durations,
and inter-trial intervals.

A session is scheduling metadata only — no frames are rendered here. Each item is
first normalised to an :class:`ExperimentSpec` (a ``{"task": ...}`` dict via
:func:`build_task`, an already-built spec passed through), then content-addressed
exactly the way :mod:`events` does it (``config_hash`` over the authored spec,
``duration`` from the spec's render ``duration_s``). That keeps a trial row
traceable back to its exact config and consistent with the BIDS events export.

Two clocks / two kinds of order, deliberately separated:

* the **expansion** order is the deterministic playlist order — item-major, with
  repeats varying fastest (item 0's repeats, then item 1's, ...). Each trial's
  ``index`` is its stable id in this expansion. It never depends on a seed.
* the **presentation** order is drawn from a SEPARATE
  ``np.random.default_rng(seed)`` (independent of item content/order), so the
  sequence a subject sees is reproducible per seed yet unbiased toward the
  identity. ``onset`` accumulates ``duration + iti_s`` *along this order*, so the
  returned ``trials`` list is already in temporal order: ``position`` is the
  0-based temporal slot and ``onset`` is strictly increasing.

:func:`per_subject_orders` reseeds the same machinery to hand each subject a
distinct, reproducible presentation order (rejection-sampled for distinctness
when the trial count allows it). :func:`session_to_events` flattens a built
session straight into rows for :func:`stimulus_lib.write_events_tsv`.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from .spec import ExperimentSpec, config_hash
from .tasks import build_task


def _normalize_item(item: Any) -> ExperimentSpec:
    """Coerce one playlist *item* to an :class:`ExperimentSpec`.

    A mapping with a ``"task"`` key is built via :func:`build_task` (which
    validates the remaining keys as task parameters); an existing
    :class:`ExperimentSpec` is passed through unchanged. ``build_task`` owns all
    parameter validation, so nothing is re-checked here.
    """
    if isinstance(item, ExperimentSpec):
        return item
    if isinstance(item, Mapping):
        params = dict(item)
        if "task" not in params:
            raise ValueError(
                f"session item dict must have a 'task' key; got keys {sorted(params)}"
            )
        name = params.pop("task")
        return build_task(str(name), **params)
    raise TypeError(
        f"session item must be an ExperimentSpec or a {{'task': ...}} dict, got {type(item)!r}"
    )


def _trial_meta(specs: Sequence[ExperimentSpec]) -> list[dict]:
    """Per-trial static metadata in expansion order (no timing yet).

    Each entry mirrors what :mod:`events` records for a clip: the condition name
    (``spec.name``), a ``spec_ref`` of ``name`` + ``config_hash`` (the authored
    content hash), and the clip ``duration`` read from the spec's render
    settings. ``index`` is the stable expansion id.
    """
    meta: list[dict] = []
    for index, spec in enumerate(specs):
        duration = float(spec.render_settings()["duration_s"])
        meta.append(
            {
                "index": index,
                "condition_name": spec.name,
                "spec_ref": {"name": spec.name, "config_hash": config_hash(spec)},
                "duration": duration,
            }
        )
    return meta


def _block_order(n_trials: int, blocks: int, rng: np.random.Generator) -> list[int]:
    """Presentation order that shuffles *within* contiguous blocks, block order fixed.

    The ``range(n_trials)`` expansion ids are split into *blocks* contiguous,
    near-equal segments; each segment is permuted independently with *rng* while
    the blocks themselves stay in ascending order. This keeps coarse structure
    (e.g. early vs. late phases) intact while randomising local order.
    """
    if blocks < 1:
        raise ValueError(f"blocks must be a positive integer, got {blocks!r}")
    edges = np.linspace(0, n_trials, blocks + 1).astype(int)
    order: list[int] = []
    for start, stop in zip(edges[:-1], edges[1:]):
        segment = list(range(int(start), int(stop)))
        if segment:
            order.extend(int(i) for i in rng.permutation(segment))
    return order


def build_session(
    items: Sequence[Any],
    iti_s: float = 1.0,
    repeats: int = 1,
    randomize: bool = True,
    seed: int = 0,
    blocks: int | None = None,
) -> dict:
    """Build a timed session from a playlist of tasks/specs.

    Parameters
    ----------
    items:
        Playlist entries, each either a ``{"task": <name>, **params}`` mapping
        (built + validated via :func:`build_task`) or an
        :class:`ExperimentSpec` (passed through).
    iti_s:
        Inter-trial interval (seconds) inserted after every clip when
        accumulating onsets.
    repeats:
        How many times each item is presented. Expansion is item-major: item 0's
        ``repeats`` trials, then item 1's, ... so the deterministic expansion of
        ``[A, B]`` with ``repeats=2`` is ``[A, A, B, B]``.
    randomize:
        When True (default), the presentation order is drawn from
        ``np.random.default_rng(seed)`` — independent of item order. When False,
        the presentation order is the expansion order (identity).
    seed:
        Seed for the presentation-order rng; recorded as ``order_seed``.
    blocks:
        When set (and ``randomize`` is True), partition the expansion ids into
        this many contiguous blocks and shuffle only *within* each block, keeping
        block order fixed. Ignored when ``randomize`` is False or ``None``.

    Returns
    -------
    dict with keys ``trials`` (in presentation/temporal order; each trial has
    ``index``, ``position``, ``condition_name``, ``spec_ref``, ``onset``,
    ``duration``, ``iti_s``), ``n_trials``, ``total_duration_s`` (last onset +
    last duration, no trailing ITI), ``order_seed``, and ``randomized``.
    """
    specs = [_normalize_item(item) for item in items]

    # Item-major expansion: item outer, repeat inner -> [A, A, B, B].
    expanded: list[ExperimentSpec] = []
    for spec in specs:
        for _ in range(int(repeats)):
            expanded.append(spec)

    meta = _trial_meta(expanded)
    n_trials = len(meta)

    # Presentation order: a SEPARATE rng, independent of item order, so the
    # sequence is reproducible per seed yet not biased toward the identity.
    if randomize and n_trials:
        rng = np.random.default_rng(seed)
        if blocks is not None:
            order = _block_order(n_trials, int(blocks), rng)
        else:
            order = [int(i) for i in rng.permutation(n_trials)]
    else:
        order = list(range(n_trials))

    trials: list[dict] = []
    onset = 0.0
    for position, index in enumerate(order):
        entry = meta[index]
        duration = entry["duration"]
        trials.append(
            {
                "index": entry["index"],
                "position": position,
                "condition_name": entry["condition_name"],
                "spec_ref": entry["spec_ref"],
                "onset": onset,
                "duration": duration,
                "iti_s": float(iti_s),
            }
        )
        onset += duration + float(iti_s)

    total_duration_s = (
        trials[-1]["onset"] + trials[-1]["duration"] if trials else 0.0
    )

    return {
        "trials": trials,
        "n_trials": n_trials,
        "total_duration_s": total_duration_s,
        "order_seed": seed,
        "randomized": bool(randomize),
    }


def per_subject_orders(session: Mapping, n_subjects: int, seed: int) -> list[list[int]]:
    """Distinct, reproducible presentation orders — one per subject.

    Each order is a permutation of the session's trial ``index`` values
    (``range(n_trials)``). Orders are drawn from a single
    ``np.random.default_rng(seed)``, so the whole set is reproducible for a fixed
    *seed*. Permutations are rejection-sampled to be pairwise distinct when the
    trial count makes that possible (``n_trials! >= n_subjects``); when there are
    too few distinct permutations to fill the request, duplicates are allowed
    rather than looping forever.

    The drawing matches :func:`build_session`'s presentation-order rng (a fresh
    ``permutation(n_trials)``), so per-subject orders index trials the same way a
    single randomized session does.
    """
    n_trials = int(session["n_trials"])
    n_subjects = int(n_subjects)
    rng = np.random.default_rng(seed)

    # Max distinct permutations of n_trials items (capped so we never demand more
    # distinctness than exists; the cap avoids overflow for large n_trials).
    max_distinct = 1
    for k in range(1, n_trials + 1):
        max_distinct *= k
        if max_distinct >= n_subjects:
            break
    enforce_distinct = max_distinct >= n_subjects

    orders: list[list[int]] = []
    seen: set[tuple[int, ...]] = set()
    while len(orders) < n_subjects:
        order = [int(i) for i in rng.permutation(n_trials)]
        key = tuple(order)
        if enforce_distinct and key in seen:
            continue
        seen.add(key)
        orders.append(order)
    return orders


def session_to_events(session: Mapping) -> list[dict]:
    """Flatten a built *session* into BIDS events rows.

    One row per trial, in the session's presentation (temporal) order, with the
    columns :data:`stimulus_lib.events.EVENT_COLUMNS` expects: ``onset`` and
    ``duration`` reused from the trial (never recomputed), ``trial_type`` from
    ``condition_name``, ``stim_file`` left empty (a session schedules but does
    not render), and ``config_hash`` from the trial's ``spec_ref``. The result is
    directly consumable by :func:`stimulus_lib.write_events_tsv`.
    """
    rows: list[dict] = []
    for trial in session["trials"]:
        rows.append(
            {
                "onset": trial["onset"],
                "duration": trial["duration"],
                "trial_type": trial["condition_name"],
                "stim_file": "",
                "config_hash": trial["spec_ref"]["config_hash"],
            }
        )
    return rows
