"""Display geometry: the single source of truth for degrees <-> pixels.

Everything spatial in a stimulus spec is authored in degrees of visual angle and
converted to pixels here, against a measured display. This is the coordinate spine
the roadmap calls out as retrofit-expensive, so it is deliberately explicit.

NOTE: this is a planar, fronto-parallel, screen-centre approximation. Degrees of
visual angle are not well defined on a curved dish or below-projection without the
projection topology; ``projection`` must stay "planar" until a warp model is added.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DisplayGeometry:
    """Measured display parameters. Defaults describe a generic small rig screen."""

    viewing_distance_mm: float = 30.0
    screen_w_mm: float = 68.0
    screen_h_mm: float = 38.0
    screen_w_px: int = 1280
    screen_h_px: int = 720
    refresh_hz: float = 60.0
    gamma: float = 2.2
    projection: str = "planar"
    display_id: str = "unspecified-display"

    def __post_init__(self) -> None:
        if self.projection != "planar":
            raise ValueError(
                f"projection={self.projection!r} is not supported yet; only 'planar' is implemented "
                "(curved-dish / below-projection perspective correction is a tracked gap)."
            )

    @property
    def px_per_mm_x(self) -> float:
        return self.screen_w_px / self.screen_w_mm

    @property
    def px_per_mm_y(self) -> float:
        return self.screen_h_px / self.screen_h_mm

    @property
    def px_per_deg(self) -> float:
        """Pixels per degree at screen centre (planar small-angle approximation).

        One degree subtends ``viewing_distance * tan(1 deg)`` mm on a flat screen.
        Assumes roughly square pixels; uses the horizontal scale.
        """
        mm_per_deg = self.viewing_distance_mm * math.tan(math.radians(1.0))
        return mm_per_deg * self.px_per_mm_x

    @property
    def max_cpd(self) -> float:
        """Highest spatial frequency (cycles/deg) the display can show before aliasing."""
        return 0.5 * self.px_per_deg

    def deg_to_px(self, degrees: float) -> float:
        return float(degrees) * self.px_per_deg

    def px_to_deg(self, pixels: float) -> float:
        return float(pixels) / self.px_per_deg

    def cpd_to_cyc_per_px(self, cycles_per_degree: float) -> float:
        return float(cycles_per_degree) / self.px_per_deg

    def to_dict(self) -> dict:
        data = asdict(self)
        data["px_per_deg"] = round(self.px_per_deg, 4)
        data["max_cpd"] = round(self.max_cpd, 4)
        return data
