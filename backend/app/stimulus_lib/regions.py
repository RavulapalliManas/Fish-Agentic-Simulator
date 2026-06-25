"""Region / masking system.

A region confines any primitive to a sub-region of the visual field. This single
abstraction is what makes "split" fall out for free: a split-field stimulus is just
two layers, one masked to the left hemifield and one to the right — there is no
dedicated split renderer. Monocular = one side full, the other absent. Phototaxis
gradients, annular surrounds, and quadrant maps all reuse the same masks.

Regions are authored in degrees of visual angle (origin = screen centre, +x right,
+y down) and rasterised to a soft-edged alpha mask (H, W) in [0, 1].
"""

from __future__ import annotations

import numpy as np

from .geometry import DisplayGeometry

FEATHER_PX = 1.5  # edge softening (px) to avoid aliasing at region boundaries

_GRID_CACHE: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}


def _centered_grid(geometry: DisplayGeometry) -> tuple[np.ndarray, np.ndarray]:
    key = (geometry.screen_w_px, geometry.screen_h_px)
    if key not in _GRID_CACHE:
        width, height = key
        xs = np.arange(width, dtype=np.float32) - width / 2.0
        ys = np.arange(height, dtype=np.float32) - height / 2.0
        _GRID_CACHE[key] = np.meshgrid(xs, ys)
    return _GRID_CACHE[key]


def _soft_nonneg(value: np.ndarray) -> np.ndarray:
    """Alpha for the predicate ``value >= 0`` with a feathered boundary."""
    return np.clip(value / FEATHER_PX + 0.5, 0.0, 1.0)


def build_region_mask(region, geometry: DisplayGeometry) -> np.ndarray:
    """Rasterise a region spec to an (H, W) float32 alpha mask in [0, 1]."""
    if region is None:
        region = {"kind": "full"}
    if isinstance(region, str):
        region = {"kind": region}

    kind = region.get("kind", "full")
    height, width = geometry.screen_h_px, geometry.screen_w_px
    grid_x, grid_y = _centered_grid(geometry)
    to_px = geometry.deg_to_px

    def center() -> tuple[float, float]:
        cx, cy = region.get("center_deg", [0.0, 0.0])
        return to_px(cx), to_px(cy)

    if kind == "full":
        mask = np.ones((height, width), dtype=np.float32)
    elif kind in ("left", "right", "top", "bottom"):
        boundary = to_px(region.get("boundary_deg", 0.0))
        if kind == "left":
            mask = _soft_nonneg(boundary - grid_x)
        elif kind == "right":
            mask = _soft_nonneg(grid_x - boundary)
        elif kind == "top":
            mask = _soft_nonneg(boundary - grid_y)
        else:
            mask = _soft_nonneg(grid_y - boundary)
    elif kind == "circle":
        cx, cy = center()
        radius = to_px(region.get("radius_deg", 5.0))
        dist = np.sqrt((grid_x - cx) ** 2 + (grid_y - cy) ** 2)
        mask = _soft_nonneg(radius - dist)
    elif kind == "annulus":
        cx, cy = center()
        inner = to_px(region.get("inner_deg", 2.0))
        outer = to_px(region.get("outer_deg", 6.0))
        dist = np.sqrt((grid_x - cx) ** 2 + (grid_y - cy) ** 2)
        mask = _soft_nonneg(outer - dist) * _soft_nonneg(dist - inner)
    elif kind == "rect":
        cx, cy = center()
        half_w = to_px(region.get("width_deg", 10.0)) / 2.0
        half_h = to_px(region.get("height_deg", 10.0)) / 2.0
        mask = _soft_nonneg(half_w - np.abs(grid_x - cx)) * _soft_nonneg(half_h - np.abs(grid_y - cy))
    elif kind == "quadrant":
        which = str(region.get("which", "tl"))
        horizontal = _soft_nonneg(-grid_x) if "l" in which else _soft_nonneg(grid_x)
        vertical = _soft_nonneg(-grid_y) if "t" in which else _soft_nonneg(grid_y)
        mask = horizontal * vertical
    else:
        raise ValueError(f"unknown region kind {kind!r}")

    if region.get("invert", False):
        mask = 1.0 - mask
    return mask.astype(np.float32)
