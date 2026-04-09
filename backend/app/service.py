"""FastAPI service that wraps deterministic stimulus generation."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api_models import (
    OptimizeResponse,
    PreviewAgent,
    PreviewPoint,
    PreviewRequest,
    PreviewResponse,
    SimulateRequest,
    SimulateResponse,
    StatusResponse,
)
from job_manager import JobManager
from simulation import sample_preview_state
from utils.config import StimulusConfig
from utils.device import detect_device_profile, recommend_export_settings, recommend_parallel_jobs


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="Fish Stimulus Backend", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    manager = JobManager()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/optimize", response_model=OptimizeResponse)
    def optimize(
        screen_width: int | None = Query(default=None),
        screen_height: int | None = Query(default=None),
    ) -> OptimizeResponse:
        profile = detect_device_profile(screen_width=screen_width, screen_height=screen_height)
        recommendation = recommend_export_settings(profile)
        return OptimizeResponse(
            cpu_cores=profile.cpu_cores,
            ram_gb=round(profile.ram_gb, 1),
            recommended_parallel_jobs=recommend_parallel_jobs(profile),
            **recommendation,
        )

    @app.post("/simulate", response_model=SimulateResponse)
    def simulate(payload: SimulateRequest) -> SimulateResponse:
        config = _validated_config(payload.config)
        output_path = _resolve_output_path(payload.output_path)
        record = manager.submit(config, output_path)
        return SimulateResponse(
            job_id=record.job_id,
            status=record.status,
            output_path=record.output_path,
            status_url=f"/status?job_id={record.job_id}",
            video_url=f"/jobs/{record.job_id}/video",
        )

    @app.post("/preview", response_model=PreviewResponse)
    def preview(payload: PreviewRequest) -> PreviewResponse:
        config = _validated_config(payload.config)
        frame_state = sample_preview_state(config, payload.phase)
        return PreviewResponse(
            phase=frame_state.phase,
            width=config.output_width,
            height=config.output_height,
            attractors={
                name: PreviewPoint(x=float(value[0]), y=float(value[1]))
                for name, value in frame_state.attractors.items()
            },
            agents=[
                PreviewAgent(
                    x=float(agent.position[0]),
                    y=float(agent.position[1]),
                    heading=float(agent.heading),
                    group=agent.group,
                )
                for agent in frame_state.agents
            ],
            metrics=frame_state.metrics,
        )

    @app.get("/status", response_model=StatusResponse)
    def status(job_id: str = Query(...)) -> StatusResponse:
        record = manager.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Unknown job id: {job_id}")
        return StatusResponse(**record.snapshot())

    @app.get("/jobs/{job_id}/video")
    def video(job_id: str):
        record = manager.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Unknown job id: {job_id}")
        snapshot = record.snapshot()
        if snapshot["status"] != "completed":
            raise HTTPException(status_code=409, detail="Video is not ready yet")
        video_path = Path(snapshot["output_path"])
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file was not found")
        return FileResponse(video_path, media_type="video/mp4", filename=video_path.name)

    return app


def _make_config(raw: dict) -> StimulusConfig:
    config = StimulusConfig()
    for key, value in raw.items():
        if hasattr(config, key):
            setattr(config, key, value)
    return config.validate()


def _validated_config(raw: dict) -> StimulusConfig:
    try:
        return _make_config(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _resolve_output_path(output_path: str | None) -> str:
    if output_path:
        resolved = Path(output_path).expanduser()
        if resolved.suffix.lower() != ".mp4":
            resolved = resolved.with_suffix(".mp4")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return str(resolved.resolve())

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    default_dir = Path.cwd() / "output"
    default_dir.mkdir(parents=True, exist_ok=True)
    return str((default_dir / f"stimulus_{timestamp}.mp4").resolve())
