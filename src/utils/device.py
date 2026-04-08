"""Device detection and export recommendations."""

from __future__ import annotations

import os
from dataclasses import dataclass

import psutil
from PyQt5.QtWidgets import QApplication


@dataclass(frozen=True)
class DeviceProfile:
    """Simple summary of the local machine for performance suggestions."""

    screen_width: int | None
    screen_height: int | None
    cpu_cores: int
    ram_gb: float


def detect_device_profile() -> DeviceProfile:
    """Return display, CPU, and RAM information for the current machine."""
    app = QApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    geometry = screen.availableGeometry() if screen is not None else None

    return DeviceProfile(
        screen_width=geometry.width() if geometry is not None else None,
        screen_height=geometry.height() if geometry is not None else None,
        cpu_cores=max(1, int(os.cpu_count() or 1)),
        ram_gb=float(psutil.virtual_memory().total) / (1024.0 ** 3),
    )


def recommend_export_settings(profile: DeviceProfile) -> dict[str, int]:
    """Recommend stable rendering defaults for the detected machine."""
    if profile.cpu_cores >= 10 and profile.ram_gb >= 24.0:
        width, height, fps, agents = 1920, 1080, 60, 96
    elif profile.cpu_cores >= 6 and profile.ram_gb >= 16.0:
        width, height, fps, agents = 1600, 900, 60, 72
    elif profile.cpu_cores >= 4 and profile.ram_gb >= 8.0:
        width, height, fps, agents = 1280, 720, 60, 56
    else:
        width, height, fps, agents = 960, 540, 30, 40

    if profile.screen_width and profile.screen_height:
        width = min(width, profile.screen_width)
        height = min(height, profile.screen_height)

    return {
        "output_width": width,
        "output_height": height,
        "fps": fps,
        "number_of_agents": agents,
    }
