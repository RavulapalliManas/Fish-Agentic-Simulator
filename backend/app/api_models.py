"""API request and response models for the FastAPI backend."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SimulateRequest(BaseModel):
    """Request body for creating a simulation job."""

    config: dict[str, Any] = Field(default_factory=dict)
    output_path: str | None = None


class SimulateResponse(BaseModel):
    """Response returned when a simulation job is queued."""

    job_id: str
    status: str
    output_path: str
    status_url: str
    video_url: str


class StatusResponse(BaseModel):
    """Current state of a simulation job."""

    job_id: str
    status: str
    progress: float
    eta_seconds: float | None = None
    phase: str | None = None
    output_path: str | None = None
    metadata_path: str | None = None
    video_url: str | None = None
    error: str | None = None


class OptimizeResponse(BaseModel):
    """Recommended simulation/rendering settings for the current device."""

    number_of_agents: int
    fps: int
    output_width: int
    output_height: int
    cpu_cores: int
    ram_gb: float
