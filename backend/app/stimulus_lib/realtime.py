"""Closed-loop real-time presenter core (offline-testable, no hardware).

DIRECTION 4. The rest of the platform is an *open-loop* generator: a spec is
authored, content-addressed, and rendered to a fixed clip ahead of time. A
behaving fish, though, moves the goalposts mid-trial — an escape assay wants the
looming disc to fire *when the fish reaches a position*, not at a pre-baked
wall-clock time. That is a feedback loop: read tracker -> decide -> update the
live stimulus parameters -> repeat, every frame.

This module is that loop, deliberately split from any hardware or display I/O so
it is reproducible and unit-testable on a laptop:

* :class:`Tracker` is the read side — a protocol returning the tracked fish state
  at a query time. :class:`SimulatedTracker` plays back a *scripted* trajectory
  so a closed-loop session is deterministic and replayable (the offline analogue
  of a real camera/tracker).
* :class:`ClosedLoopController` is the decide side. It owns the immutable *base*
  spec and a ``policy(state, t) -> overrides`` callback. Each step it re-applies
  the policy's overrides onto a fresh deep copy of the base spec's canonical dict
  (via :func:`stimulus_lib.set_path`), yielding the *live* stimulus parameters
  for that frame. The base spec is never mutated, so the loop is replay-safe.
* :func:`run_closed_loop` drives the loop for ``n_steps`` and returns an audit
  log: the per-step overrides (``param_log``), the per-step wall-clock latency in
  milliseconds (``latency_log_ms``, via :func:`time.perf_counter`), how many
  steps blew the ``dt`` budget (``dropped``), and the step indices where the
  policy fired (``triggered``). Behaviour-relevant outputs (``param_log`` and
  ``triggered``) depend only on the scripted trajectory and the policy, so they
  are bit-for-bit reproducible; only ``latency_log_ms``/``dropped`` carry the
  non-deterministic wall-clock measurement, which is what a real-time budget
  check is *for*.

:func:`looming_on_approach` is the canonical example policy: fire a looming disc
once the tracked fish comes within ``threshold_deg`` of screen centre.

The separation mirrors the rest of the library: the controller produces *spec
overrides*, not pixels. Rendering stays the renderer's job — pass a ``render_fn``
(e.g. a per-frame preview) to materialise the live params into a frame.
"""

from __future__ import annotations

import copy
import math
import time
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, Union, runtime_checkable

from .spec import ExperimentSpec
from .sweep import set_path

# A tracker state: the tracked fish position in degrees of visual angle relative
# to screen centre, its heading in degrees, and the query time in seconds.
TrackerState = dict
# A policy maps (state, t) to a dict of dotted-path -> value overrides into the
# base spec's canonical dict, or None/{} when it does not fire this step.
Policy = Callable[[TrackerState, float], Optional[Mapping[str, Any]]]
# A render hook receives the live (base + overrides) canonical spec dict.
RenderFn = Callable[[Mapping[str, Any]], Any]


@runtime_checkable
class Tracker(Protocol):
    """Read side of the loop: the tracked fish state at a query time.

    ``read(t)`` returns a mapping with at least ``x_deg``, ``y_deg``,
    ``heading_deg`` (all degrees, position relative to screen centre) and ``t``
    (the query time echoed back, in seconds). A real implementation would wrap a
    camera/tracker; :class:`SimulatedTracker` plays back a scripted trajectory.
    """

    def read(self, t: float) -> TrackerState:  # pragma: no cover - protocol
        ...


def _coerce_state(raw: Any, step: int, t: float) -> TrackerState:
    """Normalise a scripted position into a full tracker-state dict.

    Accepts either a mapping (``x_deg``/``y_deg``/``heading_deg`` keys, any
    missing one defaulting to 0.0) or a 2-/3-tuple ``(x_deg, y_deg[, heading_deg])``.
    The query time ``t`` is always written into the returned ``t`` field so a
    state is self-describing regardless of what the script supplied.
    """
    if isinstance(raw, Mapping):
        state = {
            "x_deg": float(raw.get("x_deg", 0.0)),
            "y_deg": float(raw.get("y_deg", 0.0)),
            "heading_deg": float(raw.get("heading_deg", 0.0)),
        }
    elif isinstance(raw, (tuple, list)) and len(raw) in (2, 3):
        state = {
            "x_deg": float(raw[0]),
            "y_deg": float(raw[1]),
            "heading_deg": float(raw[2]) if len(raw) == 3 else 0.0,
        }
    else:
        raise TypeError(
            f"trajectory entry {step} = {raw!r} is not a mapping or a 2/3-tuple "
            "of (x_deg, y_deg[, heading_deg])"
        )
    state["t"] = float(t)
    return state


class SimulatedTracker:
    """Replay a scripted trajectory as a :class:`Tracker` (deterministic).

    ``trajectory`` is either

    * a sequence of positions (one per step), each a mapping with
      ``x_deg``/``y_deg``/``heading_deg`` keys or a ``(x_deg, y_deg[, heading_deg])``
      tuple, or
    * a callable ``fn(step, t) -> position`` returning a position in the same form.

    The tracker is *step-indexed*: :meth:`read` is called once per loop step with
    a monotonically increasing internal step counter, so playback is fully
    deterministic and independent of wall-clock timing. A sequence shorter than
    the number of steps clamps to its last entry (the fish "holds position").
    """

    def __init__(self, trajectory: Union[Sequence[Any], Callable[[int, float], Any]]) -> None:
        if callable(trajectory):
            self._fn: Optional[Callable[[int, float], Any]] = trajectory
            self._positions: Optional[list] = None
        else:
            self._fn = None
            self._positions = list(trajectory)
            if not self._positions:
                raise ValueError("trajectory sequence must be non-empty")
        self._step = 0

    def reset(self) -> None:
        """Rewind to the first scripted step (for a replay of the same script)."""
        self._step = 0

    def read(self, t: float) -> TrackerState:
        step = self._step
        if self._fn is not None:
            raw = self._fn(step, float(t))
        else:
            assert self._positions is not None
            index = min(step, len(self._positions) - 1)
            raw = self._positions[index]
        self._step += 1
        return _coerce_state(raw, step, t)


class ClosedLoopController:
    """Decide side: turn a tracker state into live stimulus parameters.

    Holds an immutable *base* :class:`ExperimentSpec` (captured once as a
    canonical dict) and a ``policy(state, t) -> overrides`` callback. :meth:`step`
    asks the policy for overrides and, if it fired, deep-copies the base canonical
    dict and applies each ``dotted_path -> value`` override with
    :func:`stimulus_lib.set_path`. The base is never mutated, so repeated runs
    over the same script produce identical results.
    """

    def __init__(self, base_spec: ExperimentSpec, policy: Policy) -> None:
        self.base_spec = base_spec
        self.policy = policy
        # Capture the authored spec once; every step copies from this snapshot.
        self._base_canonical = base_spec.to_canonical_dict()

    def live_params(self, overrides: Optional[Mapping[str, Any]]) -> dict:
        """The base canonical dict with *overrides* applied to a fresh deep copy.

        Returns the unmodified base copy when *overrides* is falsy, so a non-firing
        step still yields a complete, renderable live spec.
        """
        canonical = copy.deepcopy(self._base_canonical)
        if overrides:
            for dotted_path, value in overrides.items():
                set_path(canonical, dotted_path, value)
        return canonical

    def step(self, state: TrackerState, t: float) -> tuple[dict, dict, bool]:
        """Evaluate the policy for one step.

        Returns ``(overrides, live_params, fired)`` where ``overrides`` is the
        normalised (possibly empty) dict the policy returned, ``live_params`` is
        the base spec with those overrides applied, and ``fired`` is True iff the
        policy returned a non-empty override set.
        """
        raw_overrides = self.policy(state, t)
        overrides = dict(raw_overrides) if raw_overrides else {}
        fired = bool(overrides)
        live = self.live_params(overrides)
        return overrides, live, fired


def run_closed_loop(
    controller: ClosedLoopController,
    tracker: Tracker,
    n_steps: int,
    dt: float,
    render_fn: Optional[RenderFn] = None,
) -> dict:
    """Drive the closed loop for *n_steps* and return an audit log.

    Each step: read the tracker at ``t = step * dt``, evaluate the controller's
    policy to get override params + the live spec, optionally call ``render_fn``
    with the live params, and record the wall-clock time the whole step took.

    Timing uses :func:`time.perf_counter`; a step whose measured latency exceeds
    the per-step budget ``dt`` (i.e. it could not keep up with the requested frame
    period) increments ``dropped``. A step "fires" — and lands in ``triggered`` —
    when the policy returns a non-empty override set.

    Returns a dict with:

    * ``param_log``  — list of length ``n_steps``; the override dict per step
      (``{}`` when the policy did not fire).
    * ``latency_log_ms`` — list of length ``n_steps``; per-step wall time in ms.
    * ``dropped`` — count of steps with ``latency_ms > dt * 1000``.
    * ``triggered`` — sorted list of step indices where the policy fired.
    * ``n_steps``, ``dt`` — echoed back for provenance.

    ``param_log`` and ``triggered`` depend only on the scripted trajectory and the
    policy, so they are deterministic across runs; ``latency_log_ms`` and
    ``dropped`` reflect real wall-clock measurement and are expected to vary.
    """
    if n_steps < 0:
        raise ValueError("n_steps must be non-negative")
    if dt <= 0:
        raise ValueError("dt must be positive")

    budget_ms = float(dt) * 1000.0

    param_log: list[dict] = []
    latency_log_ms: list[float] = []
    triggered: list[int] = []
    dropped = 0

    for step in range(n_steps):
        t = step * float(dt)
        start = time.perf_counter()

        state = tracker.read(t)
        overrides, live, fired = controller.step(state, t)
        if render_fn is not None:
            render_fn(live)

        elapsed_ms = (time.perf_counter() - start) * 1000.0

        param_log.append(overrides)
        latency_log_ms.append(elapsed_ms)
        if fired:
            triggered.append(step)
        if elapsed_ms > budget_ms:
            dropped += 1

    return {
        "param_log": param_log,
        "latency_log_ms": latency_log_ms,
        "dropped": dropped,
        "triggered": triggered,
        "n_steps": n_steps,
        "dt": float(dt),
    }


def looming_on_approach(
    threshold_deg: float,
    l_over_v_s: float,
    center_deg: tuple[float, float] = (0.0, 0.0),
    scene_index: int = 0,
    t_collision_s: Optional[float] = None,
) -> Policy:
    """Policy: fire a looming disc when the fish nears screen centre.

    Returns a ``policy(state, t)`` that computes the fish's distance from
    *center_deg* (Euclidean, in degrees of visual angle) and, when that distance
    is ``<= threshold_deg``, returns an override that turns ``scene[scene_index]``
    into a :class:`stimulus_lib.stimuli.looming.LoomingDisc` with the given
    ``l_over_v_s``. Outside the threshold it returns ``None`` (the loop logs no
    trigger and keeps the base stimulus).

    The override replaces the *whole* canonical scene entry (path ``scene.<i>``)
    in one shot rather than patching individual leaf keys, so the triggered slot
    is a complete, valid looming spec regardless of what stimulus the base put
    there (a leaf-by-leaf patch would leave the previous stimulus's parameters
    behind and fail to build). The collision time defaults to the trigger time
    ``t`` plus ``l_over_v_s`` (the disc starts expanding from the moment of the
    approach), keeping the policy self-contained and the run deterministic for a
    scripted trajectory.
    """
    cx, cy = float(center_deg[0]), float(center_deg[1])
    threshold = float(threshold_deg)
    lv = float(l_over_v_s)

    def policy(state: TrackerState, t: float) -> Optional[dict]:
        dx = float(state.get("x_deg", 0.0)) - cx
        dy = float(state.get("y_deg", 0.0)) - cy
        distance = math.hypot(dx, dy)
        if distance > threshold:
            return None
        collision = float(t_collision_s) if t_collision_s is not None else float(t) + lv
        return {
            f"scene.{int(scene_index)}": {
                "type": "looming",
                "l_over_v_s": lv,
                "t_collision_s": collision,
                "center_deg": [cx, cy],
            }
        }

    return policy
