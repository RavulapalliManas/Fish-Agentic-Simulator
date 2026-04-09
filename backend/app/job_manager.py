"""Background job management for deterministic video exports."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from renderer.video_exporter import VideoExporter
from utils.device import detect_device_profile, recommend_parallel_jobs


@dataclass
class JobRecord:
    """Mutable state for a single export job."""

    job_id: str
    output_path: str
    status: str = "queued"
    progress: float = 0.0
    eta_seconds: float | None = None
    phase: str | None = None
    metadata_path: str | None = None
    error: str | None = None
    video_url: str | None = None
    total_frames: int = 0
    completed_frames: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status,
                "progress": self.progress,
                "eta_seconds": self.eta_seconds,
                "phase": self.phase,
                "output_path": self.output_path,
                "metadata_path": self.metadata_path,
                "video_url": self.video_url,
                "error": self.error,
            }

    def update_progress(self, completed: int, total: int, eta_seconds: float, phase: str) -> None:
        with self._lock:
            self.completed_frames = int(completed)
            self.total_frames = int(total)
            self.progress = round((completed / max(total, 1)) * 100.0, 2)
            self.eta_seconds = max(0.0, float(eta_seconds))
            self.phase = str(phase)
            self.status = "running"

    def mark_running(self) -> None:
        with self._lock:
            self.status = "running"
            self.progress = 0.0

    def mark_complete(self, metadata_path: str | None) -> None:
        with self._lock:
            self.status = "completed"
            self.progress = 100.0
            self.eta_seconds = 0.0
            self.metadata_path = metadata_path
            self.video_url = f"/jobs/{self.job_id}/video"

    def mark_failed(self, error: str) -> None:
        with self._lock:
            self.status = "failed"
            self.error = error
            self.eta_seconds = None


class JobManager:
    """Manage headless export jobs while allowing safe local parallelism."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._jobs_lock = threading.Lock()
        profile = detect_device_profile()
        self._max_workers = recommend_parallel_jobs(profile)
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="stimulus-export")

    def submit(self, config, output_path: str) -> JobRecord:
        job_id = uuid.uuid4().hex
        record = JobRecord(job_id=job_id, output_path=str(Path(output_path).expanduser().resolve()))
        with self._jobs_lock:
            self._jobs[job_id] = record

        self._executor.submit(self._run_job, record, config.copy().validate())
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._jobs_lock:
            return self._jobs.get(job_id)

    def _run_job(self, record: JobRecord, config) -> None:
        record.mark_running()
        try:
            exporter = VideoExporter(config, progress_callback=record.update_progress)
            result = exporter.export(record.output_path)
            record.mark_complete(result.metadata_path)
        except Exception as exc:  # pragma: no cover - surfaced through API
            record.mark_failed(str(exc))
