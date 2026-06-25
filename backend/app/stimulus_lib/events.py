"""BIDS-style events export for merging stimuli with behavior/imaging.

A single rendered clip, or a whole counterbalanced sweep, is flattened into the
BIDS ``_events.tsv`` table — the lingua franca for aligning a stimulus timeline
with neural/behavioral recordings. Each presented clip becomes one row with its
``onset`` (seconds from the start of the run), ``duration`` (seconds), a
human-readable ``trial_type``, an optional ``stim_file``, and the spec
``config_hash`` so every row is content-addressed back to the exact authored
config.

The two entry points mirror the two stimulus sources:

* :func:`spec_events` turns one :class:`ExperimentSpec` into a single-row table
  (one clip = one trial).
* :func:`sweep_events` walks a design's ``presentation_order`` (from
  :func:`stimulus_lib.expand_sweep`) and lays the presented conditions end to
  end, accumulating onsets across each clip's duration plus an inter-trial
  interval.

Onsets are kept as raw floats in the row dicts so the strictly-increasing
invariant is checked at full precision; the millisecond-resolution string
formatting happens only at :func:`write_events_tsv` time. ``config_hash`` is
imported only for :func:`spec_events`; :func:`sweep_events` reuses the hashes
already stored on each condition (it never recomputes them).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .spec import ExperimentSpec, config_hash

# BIDS events table columns, in fixed order (the TSV header and the JSON sidecar
# are both generated from this).
EVENT_COLUMNS = ("onset", "duration", "trial_type", "stim_file", "config_hash")

# JSON sidecar descriptions for each column (BIDS-style column documentation).
COLUMN_DESCRIPTIONS = {
    "onset": {
        "Description": "Start of the stimulus clip, in seconds from the start of the run.",
        "Units": "s",
    },
    "duration": {
        "Description": "Duration of the stimulus clip, in seconds.",
        "Units": "s",
    },
    "trial_type": {
        "Description": "Human-readable condition name (the spec or sweep-condition name).",
    },
    "stim_file": {
        "Description": "Path to the rendered stimulus file for this trial (empty if not provided).",
    },
    "config_hash": {
        "Description": "SHA-256 content hash of the authored spec for this trial.",
    },
}


def spec_events(spec: ExperimentSpec) -> list[dict]:
    """One-row events table for a single rendered clip.

    The clip starts at ``onset == 0.0`` and lasts the spec's render
    ``duration_s``; ``trial_type`` is ``spec.name``, ``stim_file`` is left empty,
    and ``config_hash`` is computed from the spec.
    """
    duration = float(spec.render_settings()["duration_s"])
    return [
        {
            "onset": 0.0,
            "duration": duration,
            "trial_type": spec.name,
            "stim_file": "",
            "config_hash": config_hash(spec),
        }
    ]


def sweep_events(
    design: Mapping,
    iti_s: float = 0.0,
    stim_files: Mapping[int, str] | None = None,
) -> list[dict]:
    """Flatten a sweep *design* into a BIDS events table in presentation order.

    Walks ``design["presentation_order"]`` (from
    :func:`stimulus_lib.expand_sweep`); each entry is a condition index into the
    aligned ``design["specs"]`` and ``design["conditions"]`` lists. For each
    presented clip the duration is read from its spec's render ``duration_s``, the
    onset accumulates (previous onset + previous duration + ``iti_s``), the
    ``trial_type`` is the condition name, the ``config_hash`` is the one already
    stored on the condition (never recomputed), and ``stim_file`` is looked up in
    *stim_files* by condition index (``""`` when absent).

    Onsets are strictly increasing for any positive clip duration (the default
    render duration is 2.0 s), so no defensive guard is needed.
    """
    files = stim_files or {}
    specs = design["specs"]
    conditions = design["conditions"]

    rows: list[dict] = []
    onset = 0.0
    for index in design["presentation_order"]:
        spec = specs[index]
        condition = conditions[index]
        duration = float(spec.render_settings()["duration_s"])

        rows.append(
            {
                "onset": onset,
                "duration": duration,
                "trial_type": condition["name"],
                "stim_file": files.get(index, ""),
                "config_hash": condition["config_hash"],
            }
        )

        onset += duration + float(iti_s)

    return rows


def _format_seconds(value: float) -> str:
    """Format a time in seconds at millisecond resolution (3 decimal places)."""
    return f"{float(value):.3f}"


def write_events_tsv(rows: list[dict], path: str | Path) -> str:
    """Write *rows* as a BIDS ``_events.tsv`` plus a ``<path>.json`` sidecar.

    The TSV is tab-separated with a fixed header
    (``onset\\tduration\\ttrial_type\\tstim_file\\tconfig_hash``) and one data line
    per row; ``onset``/``duration`` are formatted to millisecond resolution. A
    sibling sidecar at ``str(path) + ".json"`` documents the columns. Returns the
    string path of the TSV that was written.
    """
    file_path = Path(path)

    header = "\t".join(EVENT_COLUMNS)
    lines = [header]
    for row in rows:
        cells = [
            _format_seconds(row["onset"]),
            _format_seconds(row["duration"]),
            str(row["trial_type"]),
            str(row["stim_file"]),
            str(row["config_hash"]),
        ]
        lines.append("\t".join(cells))

    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sidecar_path = Path(str(file_path) + ".json")
    sidecar = {column: COLUMN_DESCRIPTIONS[column] for column in EVENT_COLUMNS}
    sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")

    return str(file_path)
