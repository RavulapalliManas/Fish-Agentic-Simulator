"""Reproducible visual-stimulus platform.

A degrees-of-visual-angle, config-as-code stimulus generator that renders
deterministic, lossless frame sequences with a provenance manifest, a baked
per-frame sync marker, and stimulus-level Nyquist validation.

See docs/stimulus-platform-roadmap.md for the design. This package is the P0
foundation plus the core P1 primitives (grating, looming, RDK, dark flash,
moving bar). The shoaling engine in the rest of ``app`` is untouched.
"""

from .geometry import DisplayGeometry
from .scene import Scene
from .spec import ExperimentSpec, config_hash, load_spec
from .render import render_experiment

__all__ = [
    "DisplayGeometry",
    "ExperimentSpec",
    "Scene",
    "config_hash",
    "load_spec",
    "render_experiment",
]
