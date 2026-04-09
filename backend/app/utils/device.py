"""Device detection and export recommendations for the headless backend."""

from __future__ import annotations

import os
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class DeviceProfile:
    """Simple summary of the local machine for performance suggestions."""

    screen_width: int | None
    screen_height: int | None
    cpu_cores: int
    ram_gb: float


def detect_device_profile(
    screen_width: int | None = None,
    screen_height: int | None = None,
) -> DeviceProfile:
    """Return display hints, CPU count, and RAM information."""
    return DeviceProfile(
        screen_width=screen_width,
        screen_height=screen_height,
        cpu_cores=max(1, int(os.cpu_count() or 1)),
        ram_gb=float(psutil.virtual_memory().total) / (1024.0 ** 3),
    )


def recommend_export_settings(profile: DeviceProfile) -> dict[str, int]:
    """Recommend stable defaults for the current machine."""
    if profile.cpu_cores >= 10 and profile.ram_gb >= 24.0:
        width, height, fps, agents = 1920, 1080, 60, 96
    elif profile.cpu_cores >= 8 and profile.ram_gb >= 16.0:
        width, height, fps, agents = 1600, 900, 60, 72
    elif profile.cpu_cores >= 4 and profile.ram_gb >= 8.0:
        width, height, fps, agents = 1280, 720, 60, 56
    else:
        width, height, fps, agents = 960, 540, 30, 40

    if profile.screen_width:
        width = min(width, int(profile.screen_width))
    if profile.screen_height:
        height = min(height, int(profile.screen_height))

    return {"output_width": width, "output_height": height, "fps": fps, "number_of_agents": agents}


def recommend_parallel_jobs(profile: DeviceProfile) -> int:
    """Suggest a safe amount of parallelism for batch sweeps on this device."""
    cpu_limited = max(1, profile.cpu_cores // 2)
    ram_limited = max(1, int(profile.ram_gb // 6.0))
    return max(1, min(4, cpu_limited, ram_limited))
