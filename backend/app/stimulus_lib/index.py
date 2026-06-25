"""Catalog / query a rendered set and export tables + presentation playlists.

A render directory is content-addressed by its manifest (see :mod:`.render`): one
``<name>.manifest.json`` per clip, carrying the authored canonical ``spec``, the
``config_hash`` over that spec, resolved ``geometry``/``render``/``scene`` and the
QA record. This module is the read side of that contract — it walks a directory
tree of such manifests and turns the *set* into something a human or a downstream
presenter can act on:

* :func:`build_index` — one flat entry per manifest (name, paths, ``config_hash``,
  timing, geometry summary, the stimulus types present, and the *flattened* key
  parameters keyed by dotted path, e.g. ``scene.0.contrast`` / ``render.fps``).
* :func:`query` — filter the index by exact value or by an operator suffix
  (``__eq`` / ``__ge`` / ``__le`` / ``__gt`` / ``__lt``) on any flattened key.
* :func:`condition_table` — a tidy condition x parameter table (CSV or Markdown),
  one row per indexed clip with the union of key parameters as columns.
* :func:`export_playlist` — a presentation playlist (CSV, or JSON for PsychoPy /
  Bonsai / Stytra) of ``{stim_file, name, duration_s, config_hash, key params}``
  in a chosen order.
* :func:`auto_name` — a stable, informative slug derived from a params dict, with
  collision-safe numeric suffixing.

Flattening convention
---------------------
Parameters are flattened from the manifest's authored canonical ``spec`` so the
dotted keys line up exactly with the sweep override paths (:func:`stimulus_lib.set_path`
sets ``scene.0.contrast`` into the same canonical dict). The ``scene`` list flattens
to ``scene.<layer_index>.<param>``; ``render`` flattens to ``render.<param>``; nested
dicts (e.g. a dict ``region``) flatten with further dotted segments. Geometry is kept
both as a structured summary (the ``geometry`` field) and flattened under
``geometry.<param>`` so it is queryable too.

stdlib + json only — no numpy, no third-party deps — so the read/query/export side
stays importable in a thin analysis or CLI environment.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Iterable

# Operator suffixes understood by :func:`query` on a flattened key, mapped to a
# two-argument comparison. ``__eq`` is also the implicit operator when a filter
# key carries no suffix.
_OPERATORS = {
    "eq": lambda a, b: a == b,
    "ge": lambda a, b: a >= b,
    "le": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
}

# Geometry fields surfaced in the structured ``geometry`` summary on each entry.
_GEOMETRY_FIELDS = (
    "display_id",
    "screen_w_px",
    "screen_h_px",
    "px_per_deg",
    "max_cpd",
    "refresh_hz",
    "viewing_distance_mm",
    "gamma",
    "projection",
)


# --------------------------------------------------------------------------- #
# Flattening
# --------------------------------------------------------------------------- #

def _flatten(value: Any, prefix: str, out: dict[str, Any]) -> None:
    """Flatten nested dicts/lists into ``out`` keyed by dotted path.

    Lists are indexed numerically (``scene.0.contrast``), matching the dotted-path
    convention used by :func:`stimulus_lib.set_path` for sweep overrides; dict keys
    extend the path verbatim. Leaf scalars (and ``None``) are stored as-is.
    """
    if isinstance(value, dict):
        for key, sub in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            _flatten(sub, child, out)
    elif isinstance(value, (list, tuple)):
        for index, sub in enumerate(value):
            child = f"{prefix}.{index}" if prefix else str(index)
            _flatten(sub, child, out)
    else:
        out[prefix] = value


def _flatten_params(spec: dict) -> dict[str, Any]:
    """Flatten the authored canonical *spec*'s scene + render + geometry params.

    Returns dotted-key params: ``scene.<i>.<param>``, ``render.<param>`` and
    ``geometry.<param>``. ``name``/``seed`` are surfaced too so they can be queried,
    but the heavy scene/render structure is what the dotted convention targets.
    """
    params: dict[str, Any] = {}
    _flatten(spec.get("scene") or [], "scene", params)
    _flatten(spec.get("render") or {}, "render", params)
    _flatten(spec.get("geometry") or {}, "geometry", params)
    if "name" in spec:
        params["name"] = spec["name"]
    if "seed" in spec:
        params["seed"] = spec["seed"]
    return params


def _stimulus_types(spec: dict) -> list[str]:
    """Ordered, de-duplicated stimulus ``type`` values across the authored scene."""
    types: list[str] = []
    for layer in spec.get("scene") or []:
        if isinstance(layer, dict):
            stim_type = layer.get("type")
            if stim_type is not None and stim_type not in types:
                types.append(str(stim_type))
    return types


def _geometry_summary(manifest: dict, spec: dict) -> dict[str, Any]:
    """A compact geometry summary, preferring the enriched manifest geometry.

    The top-level ``manifest["geometry"]`` carries derived ``px_per_deg`` / ``max_cpd``
    (added by :meth:`DisplayGeometry.to_dict`); the authored ``spec["geometry"]`` is the
    fallback when an entry is built from a bare spec dict.
    """
    geo = manifest.get("geometry") or spec.get("geometry") or {}
    return {field: geo.get(field) for field in _GEOMETRY_FIELDS if field in geo}


# --------------------------------------------------------------------------- #
# build_index
# --------------------------------------------------------------------------- #

def build_index(out_root: str | Path) -> list[dict]:
    """Walk *out_root* for ``*.manifest.json`` and catalog one entry per manifest.

    Each entry is a flat dict::

        {
          "name", "manifest_path", "config_hash",
          "fps", "n_frames", "duration_s",
          "geometry": {display_id, screen_w_px, ..., px_per_deg, max_cpd, ...},
          "stimulus_types": [...],
          "params": {"scene.0.contrast": 0.8, "render.fps": 60, ...},
        }

    The authored canonical ``manifest["spec"]`` is the source for the flattened
    ``params`` and ``stimulus_types`` (so dotted keys match sweep override paths);
    timing fields come from the manifest top level. Entries are returned sorted by
    ``manifest_path`` for a stable, filesystem-independent order. Malformed JSON or
    a manifest missing ``config_hash`` is skipped rather than aborting the walk.
    """
    root = Path(out_root)
    entries: list[dict] = []

    for manifest_path in sorted(root.rglob("*.manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(manifest, dict) or "config_hash" not in manifest:
            continue

        # The authored canonical spec is the dotted-path source of truth; fall back
        # to the enriched top-level copies if an older manifest lacks "spec".
        spec = manifest.get("spec")
        if not isinstance(spec, dict):
            spec = {
                "name": manifest.get("name"),
                "seed": manifest.get("seed"),
                "geometry": manifest.get("geometry") or {},
                "render": manifest.get("render") or {},
                "scene": [
                    layer.get("stimulus", layer) if isinstance(layer, dict) else layer
                    for layer in (manifest.get("scene") or [])
                ],
            }

        entries.append(
            {
                "name": manifest.get("name") or spec.get("name") or manifest_path.stem.replace(".manifest", ""),
                "manifest_path": str(manifest_path.resolve()),
                "config_hash": manifest["config_hash"],
                "fps": manifest.get("fps"),
                "n_frames": manifest.get("n_frames"),
                "duration_s": manifest.get("duration_s"),
                "geometry": _geometry_summary(manifest, spec),
                "stimulus_types": _stimulus_types(spec),
                "params": _flatten_params(spec),
            }
        )

    return entries


# --------------------------------------------------------------------------- #
# query
# --------------------------------------------------------------------------- #

def _split_operator(filter_key: str) -> tuple[str, str]:
    """Split a filter key into ``(flattened_key, operator)``.

    A trailing ``__eq`` / ``__ge`` / ``__le`` / ``__gt`` / ``__lt`` selects the
    operator; with no recognised suffix the operator defaults to ``eq`` and the
    whole key is the flattened key (so ``"scene.0.contrast"`` means equality).
    """
    for op in _OPERATORS:
        suffix = "__" + op
        if filter_key.endswith(suffix):
            return filter_key[: -len(suffix)], op
    return filter_key, "eq"


def _entry_value(entry: dict, key: str) -> tuple[bool, Any]:
    """Resolve *key* against an entry's params and top-level fields.

    Looks in ``entry["params"]`` first (the flattened dotted params), then falls
    back to flat top-level fields (``name``, ``config_hash``, ``fps``,
    ``n_frames``, ``duration_s``) and the ``geometry.<field>`` summary. Returns
    ``(found, value)`` so a missing key excludes the entry rather than matching.
    """
    params = entry.get("params") or {}
    if key in params:
        return True, params[key]
    if key in ("name", "config_hash", "fps", "n_frames", "duration_s"):
        return True, entry.get(key)
    if key.startswith("geometry."):
        geo = entry.get("geometry") or {}
        field = key.split(".", 1)[1]
        if field in geo:
            return True, geo[field]
    return False, None


def query(index: Iterable[dict], **filters: Any) -> list[dict]:
    """Filter *index* entries by exact value or operator-suffixed comparison.

    Each keyword is ``"<flattened_key>[__op]" = value``. Supported operator
    suffixes are ``__eq`` (default when omitted), ``__ge``, ``__le``, ``__gt`` and
    ``__lt``. Because Python identifiers can't contain dots, dotted keys are passed
    via ``**{...}`` — e.g. ``query(idx, **{"scene.0.contrast__ge": 0.7})``.

    An entry matches only if it has the key *and* the comparison holds; all filters
    are AND-combined. A comparison that raises ``TypeError`` (e.g. number vs string
    on an ordering operator) is treated as non-matching rather than fatal, so a
    heterogeneous index never crashes a query.
    """
    matches: list[dict] = []
    parsed = [(*_split_operator(raw_key), value) for raw_key, value in filters.items()]

    for entry in index:
        keep = True
        for key, op, target in parsed:
            found, value = _entry_value(entry, key)
            if not found:
                keep = False
                break
            try:
                if not _OPERATORS[op](value, target):
                    keep = False
                    break
            except TypeError:
                keep = False
                break
        if keep:
            matches.append(entry)

    return matches


# --------------------------------------------------------------------------- #
# condition_table
# --------------------------------------------------------------------------- #

def _ordered_param_columns(index: list[dict]) -> list[str]:
    """Union of flattened param keys across *index*, in first-seen order.

    First-seen order (rather than sorted) keeps related params from the same scene
    grouped as the user authored them; columns absent from a given row render as an
    empty cell.
    """
    columns: list[str] = []
    for entry in index:
        for key in (entry.get("params") or {}):
            if key not in columns:
                columns.append(key)
    return columns


def _cell(value: Any) -> str:
    """Render a param value as a flat table cell (compact JSON for containers)."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def condition_table(index: list[dict], fmt: str = "csv") -> str:
    """Render a condition x key-parameter table as CSV or Markdown text.

    One row per indexed clip. Fixed leading columns are ``name``, ``config_hash``,
    ``duration_s``, ``fps`` and ``stimulus_types``; the remaining columns are the
    union of flattened param keys (e.g. ``scene.0.contrast``) in first-seen order.

    ``fmt="csv"`` emits RFC-4180 CSV (a header line + one line per row).
    ``fmt="md"`` emits a GitHub-flavoured Markdown table (header + separator + rows).
    Both always include the header, so the output is non-empty even for an empty
    index.
    """
    index = list(index)
    fixed = ["name", "config_hash", "duration_s", "fps", "stimulus_types"]
    # Drop any flattened param that collides with a fixed leading column (notably
    # "name", which _flatten_params surfaces for queryability) so the table never
    # emits a duplicate header column that would collapse under a dict-based reader.
    param_cols = [col for col in _ordered_param_columns(index) if col not in fixed]
    header = fixed + param_cols

    def row_cells(entry: dict) -> list[str]:
        params = entry.get("params") or {}
        cells = [
            _cell(entry.get("name")),
            _cell(entry.get("config_hash")),
            _cell(entry.get("duration_s")),
            _cell(entry.get("fps")),
            ",".join(entry.get("stimulus_types") or []),
        ]
        cells.extend(_cell(params.get(col)) for col in param_cols)
        return cells

    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(header)
        for entry in index:
            writer.writerow(row_cells(entry))
        return buffer.getvalue()

    if fmt == "md":
        def md_escape(text: str) -> str:
            return text.replace("|", "\\|").replace("\n", " ")

        lines = ["| " + " | ".join(md_escape(h) for h in header) + " |"]
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for entry in index:
            cells = [md_escape(c) for c in row_cells(entry)]
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines) + "\n"

    raise ValueError(f"unknown condition_table fmt {fmt!r}; use 'csv' or 'md'")


# --------------------------------------------------------------------------- #
# export_playlist
# --------------------------------------------------------------------------- #

# Scene-level "key params" promoted into a playlist record. These are the levers a
# presenter most often varies across a sweep; the full param set still travels in
# the ``params`` field of the JSON formats.
_PLAYLIST_KEY_PARAMS = (
    "contrast",
    "spatial_freq_cpd",
    "temporal_freq_hz",
    "direction_deg",
    "coherence",
    "speed_dps",
    "l_over_v_s",
    "polarity",
    "waveform",
)


def _stim_file(entry: dict) -> str:
    """Best-guess rendered stimulus path beside the manifest.

    The render writes either ``frames/`` (png_sequence) or ``<name>.mkv`` (ffv1)
    next to ``<name>.manifest.json``. We point at the per-clip directory (the
    manifest's parent) since that is the unit a presenter loads, falling back to the
    manifest path itself if the parent is unavailable.
    """
    manifest_path = entry.get("manifest_path")
    if not manifest_path:
        return entry.get("name", "")
    return str(Path(manifest_path).parent)


def _key_params(entry: dict) -> dict[str, Any]:
    """Pull the promoted scene-level key params from an entry's flattened params.

    A flattened key like ``scene.0.contrast`` contributes ``contrast``; the first
    scene layer to define a given param wins (lower layer index), so a single
    representative value surfaces per playlist record.
    """
    params = entry.get("params") or {}
    out: dict[str, Any] = {}
    for key in sorted(params):  # sorted -> scene.0 before scene.1, deterministic
        if not key.startswith("scene."):
            continue
        leaf = key.rsplit(".", 1)[-1]
        if leaf in _PLAYLIST_KEY_PARAMS and leaf not in out:
            value = params[key]
            if value is not None:
                out[leaf] = value
    return out


def _ordered_for_playlist(index: list[dict], order: list[int] | None) -> list[dict]:
    """Reorder *index* by an explicit permutation of indices, or keep index order."""
    if order is None:
        return list(index)
    return [index[i] for i in order]


def export_playlist(
    index: list[dict],
    fmt: str = "csv",
    order: list[int] | None = None,
) -> str:
    """Export a presentation playlist of the indexed clips in a chosen *order*.

    Each playlist record carries ``stim_file`` (the rendered clip directory beside
    the manifest), ``name``, ``duration_s``, ``config_hash`` and the promoted
    scene-level key params (contrast, spatial/temporal frequency, direction, ...).

    *order* is an optional list of indices into *index* (e.g. a sweep's
    ``presentation_order``); ``None`` keeps index order.

    Formats:

    * ``"csv"`` — RFC-4180 CSV with fixed columns ``name, stim_file, duration_s,
      config_hash`` followed by the union of key-param columns.
    * ``"psychopy"`` — JSON ``{"playlist": [...]}`` of trial dicts, the shape a
      PsychoPy ``TrialHandler``/loop ingests; each trial has ``stim_file``,
      ``name``, ``duration_s``, ``config_hash`` and a nested ``params`` dict.
    * ``"bonsai"`` — JSON ``{"trials": [...]}`` with ``StimulusFile`` / ``Duration``
      / ``ConfigHash`` keys (Bonsai's PascalCase property convention).
    * ``"stytra"`` — JSON ``{"stimuli": [...]}`` with ``duration`` (s) and a
      ``"name"``/``"config_hash"`` plus flattened params, the dict-of-stimuli shape
      a Stytra protocol consumes.

    Returns the playlist as text (CSV or ``json.dumps`` output).
    """
    ordered = _ordered_for_playlist(list(index), order)
    records = [
        {
            "name": entry.get("name"),
            "stim_file": _stim_file(entry),
            "duration_s": entry.get("duration_s"),
            "config_hash": entry.get("config_hash"),
            "params": _key_params(entry),
        }
        for entry in ordered
    ]

    if fmt == "csv":
        key_cols: list[str] = []
        for rec in records:
            for key in rec["params"]:
                if key not in key_cols:
                    key_cols.append(key)
        header = ["name", "stim_file", "duration_s", "config_hash"] + key_cols
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(header)
        for rec in records:
            row = [
                _cell(rec["name"]),
                _cell(rec["stim_file"]),
                _cell(rec["duration_s"]),
                _cell(rec["config_hash"]),
            ]
            row.extend(_cell(rec["params"].get(col)) for col in key_cols)
            writer.writerow(row)
        return buffer.getvalue()

    if fmt == "psychopy":
        trials = [
            {
                "stim_file": rec["stim_file"],
                "name": rec["name"],
                "duration_s": rec["duration_s"],
                "config_hash": rec["config_hash"],
                "params": rec["params"],
            }
            for rec in records
        ]
        return json.dumps({"playlist": trials}, indent=2)

    if fmt == "bonsai":
        trials = [
            {
                "Name": rec["name"],
                "StimulusFile": rec["stim_file"],
                "Duration": rec["duration_s"],
                "ConfigHash": rec["config_hash"],
                "Parameters": rec["params"],
            }
            for rec in records
        ]
        return json.dumps({"trials": trials}, indent=2)

    if fmt == "stytra":
        stimuli = [
            {
                "name": rec["name"],
                "duration": rec["duration_s"],
                "config_hash": rec["config_hash"],
                "stim_file": rec["stim_file"],
                **rec["params"],
            }
            for rec in records
        ]
        return json.dumps({"stimuli": stimuli}, indent=2)

    raise ValueError(
        f"unknown export_playlist fmt {fmt!r}; use 'csv', 'psychopy', 'bonsai' or 'stytra'"
    )


# --------------------------------------------------------------------------- #
# auto_name
# --------------------------------------------------------------------------- #

# Abbreviations for common verbose param keys, so a slug stays informative but
# short. Keys are matched against the leaf of a flattened param name.
_PARAM_ABBREV = {
    "spatial_freq_cpd": "sf",
    "temporal_freq_hz": "tf",
    "direction_deg": "dir",
    "orientation_deg": "ori",
    "contrast": "c",
    "coherence": "coh",
    "speed_dps": "spd",
    "velocity_dps": "vel",
    "l_over_v_s": "lv",
    "max_radius_deg": "rad",
    "polarity": "pol",
    "waveform": "wf",
    "n_dots": "ndots",
    "check_size_deg": "chk",
    "reversal_hz": "rev",
    "size_deg": "sz",
    "width_deg": "w",
    "condition": "cond",
}

# Params that read as identity/structure rather than informative levers; excluded
# from the slug so it stays focused on what varies across a set.
_SLUG_SKIP_LEAVES = {"type", "mean_lum", "phase_deg", "name"}

_SLUG_SANITISE = re.compile(r"[^a-z0-9]+")

# Module-level registry of slugs already handed out, so repeated calls with
# colliding params get distinct ``-2`` / ``-3`` suffixes within a process.
_SEEN_SLUGS: dict[str, int] = {}


def _slug_token(value: Any) -> str:
    """Compact, filename-safe token for a single param value."""
    if isinstance(value, bool):
        return "t" if value else "f"
    if isinstance(value, float):
        # Trim trailing zeros; turn the decimal point into 'p' so the slug has no dots.
        text = f"{value:.4g}"
        text = text.replace("-", "n").replace(".", "p")
        return text
    if isinstance(value, int):
        text = str(value)
        return text.replace("-", "n")
    text = str(value).strip().lower()
    text = _SLUG_SANITISE.sub("-", text).strip("-")
    return text or "x"


def _flatten_for_slug(params: dict) -> list[tuple[str, Any]]:
    """Flatten *params* to ``(leaf_key, value)`` pairs for slug construction.

    Accepts either an already-flattened dotted-key dict (an index entry's
    ``params``) or a raw nested params dict (a scene-entry dict / spec). Container
    values are flattened; only scalar leaves contribute, and identity/structure
    leaves are skipped.
    """
    flat: dict[str, Any] = {}
    _flatten(params, "", flat)

    pairs: list[tuple[str, Any]] = []
    for dotted_key, value in flat.items():
        leaf = dotted_key.rsplit(".", 1)[-1]
        if leaf in _SLUG_SKIP_LEAVES:
            continue
        if isinstance(value, (dict, list, tuple)) or value is None:
            continue
        pairs.append((leaf, value))
    return pairs


def auto_name(params: dict) -> str:
    """Build a stable, informative slug from a params dict, collision-safe.

    *params* may be a raw stimulus/scene params dict (``{"type": "grating",
    "contrast": 0.8, ...}``), a whole authored spec, or an index entry's already-
    flattened ``params``. A leading stimulus ``type`` (when present anywhere in the
    params) becomes the slug stem; the remaining scalar params are appended as
    abbreviated ``key<value>`` tokens in sorted-by-key order, so the same params
    always yield the same slug (determinism) regardless of dict insertion order.

    Collision safety: the first time a given slug is produced it is returned as-is;
    a later call that would produce the *same* slug gets a ``-2`` / ``-3`` ... suffix.
    Distinct params therefore never share a name within a process. Resetting is a
    matter of clearing :data:`_SEEN_SLUGS` (exposed for tests via
    :func:`reset_auto_name`).
    """
    flat: dict[str, Any] = {}
    _flatten(params, "", flat)

    # Stem from any stimulus "type" leaf (first scene layer wins on sorted key).
    stem = None
    for dotted_key in sorted(flat):
        if dotted_key == "type" or dotted_key.rsplit(".", 1)[-1] == "type":
            candidate = flat[dotted_key]
            if isinstance(candidate, str) and candidate:
                stem = _slug_token(candidate)
                break

    pairs = _flatten_for_slug(params)
    # Stable order: sort by abbreviated/leaf key then by the raw value's token, so a
    # given params dict is order-independent and reproducible.
    tokens: list[str] = []
    for leaf, value in sorted(pairs, key=lambda kv: (kv[0], str(kv[1]))):
        abbrev = _PARAM_ABBREV.get(leaf, leaf)
        tokens.append(f"{abbrev}{_slug_token(value)}")

    parts = [p for p in ([stem] if stem else []) + tokens if p]
    base = "_".join(parts) if parts else "stim"

    count = _SEEN_SLUGS.get(base, 0)
    _SEEN_SLUGS[base] = count + 1
    if count == 0:
        return base
    return f"{base}-{count + 1}"


def reset_auto_name() -> None:
    """Clear the process-level slug registry used by :func:`auto_name`.

    Exposed so a caller (or a test) can get fresh, suffix-free slugs again; without
    it the collision counter persists for the lifetime of the process.
    """
    _SEEN_SLUGS.clear()
