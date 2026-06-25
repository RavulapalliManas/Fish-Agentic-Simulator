"""Config-as-code experiment specs + content-addressed hashing.

A spec is authored in JSON or YAML, validated, and hashed so a paper figure maps
to an exact commit + config hash.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .geometry import DisplayGeometry
from .scene import Scene
from .stimuli import STIMULUS_REGISTRY

DEFAULT_RENDER = {
    "fps": 60,
    "duration_s": 2.0,
    "bit_depth": 8,
    # "encode_into_file": store display-ready (gamma-encoded for the named display).
    # "linear_record_only": store linear values; the rig applies gamma at playback.
    "gamma_policy": "encode_into_file",
    "sync_marker": True,
    "codec": "png_sequence",  # or "ffv1"
    "mean_lum": 0.5,
}


@dataclass
class ExperimentSpec:
    name: str = "experiment"
    seed: int = 0
    geometry: dict = field(default_factory=dict)
    render: dict = field(default_factory=dict)
    scene: list = field(default_factory=list)

    def display_geometry(self) -> DisplayGeometry:
        return DisplayGeometry(**self.geometry)

    def render_settings(self) -> dict:
        return {**DEFAULT_RENDER, **self.render}

    def build_scene(self) -> Scene:
        layers = []
        for entry in self.scene:
            params = dict(entry)
            stimulus_type = params.pop("type", None)
            cls = STIMULUS_REGISTRY.get(stimulus_type)
            if cls is None:
                raise ValueError(
                    f"unknown stimulus type {stimulus_type!r}; known types: {sorted(STIMULUS_REGISTRY)}"
                )
            layers.append(cls(**params))
        return Scene(layers, mean_lum=float(self.render_settings()["mean_lum"]))

    def to_canonical_dict(self) -> dict:
        return {
            "name": self.name,
            "seed": self.seed,
            "geometry": self.geometry,
            "render": self.render,
            "scene": self.scene,
        }


def config_hash(spec: ExperimentSpec) -> str:
    """SHA-256 over the canonical spec — the authored content, not the rendered bytes."""
    blob = json.dumps(spec.to_canonical_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_spec(path: str | Path) -> ExperimentSpec:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if file_path.suffix.lower() in (".yaml", ".yml"):
        import yaml  # optional dependency; only needed for YAML specs

        data = yaml.safe_load(text)
    else:
        data = json.loads(text)

    return ExperimentSpec(
        name=str(data.get("name", "experiment")),
        seed=int(data.get("seed", 0)),
        geometry=dict(data.get("geometry") or {}),
        render=dict(data.get("render") or {}),
        scene=list(data.get("scene") or []),
    )
