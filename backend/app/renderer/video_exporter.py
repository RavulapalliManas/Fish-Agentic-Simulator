"""Deterministic MP4 export pipeline for the headless backend."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

from renderer.frame_renderer import FrameRenderer
from simulation import StimulusEngine


@dataclass
class ExportResult:
    """Summary of an export run."""

    video_path: str
    metadata_path: str | None
    total_frames: int
    duration_seconds: float


class VideoExporter:
    """Run a fixed-timestep simulation entirely offscreen and save an MP4."""

    def __init__(self, config, progress_callback=None):
        self.config = config.copy().validate()
        self.progress_callback = progress_callback
        self.renderer = FrameRenderer()

    def export(self, output_path: str) -> ExportResult:
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output), fourcc, float(self.config.fps), self.config.resolution)
        if not writer.isOpened():
            raise RuntimeError(f"Unable to open video writer for {output}")

        engine = StimulusEngine(self.config)
        total_frames = self.config.total_frames
        start_time = time.perf_counter()

        try:
            for frame_number in range(total_frames):
                frame_state = engine.current_frame()
                writer.write(self.renderer.render_to_bgr(frame_state, self.config))

                elapsed = max(time.perf_counter() - start_time, 1e-6)
                completed = frame_number + 1
                eta_seconds = (elapsed / completed) * (total_frames - completed)
                if self.progress_callback is not None:
                    self.progress_callback(completed, total_frames, eta_seconds, frame_state.phase)

                if completed < total_frames:
                    engine.step()
        finally:
            writer.release()

        metadata_path = self._write_metadata(output)
        return ExportResult(
            video_path=str(output),
            metadata_path=metadata_path,
            total_frames=total_frames,
            duration_seconds=total_frames / float(self.config.fps),
        )

    def _write_metadata(self, output_path: Path) -> str | None:
        if not self.config.save_metadata_json:
            return None

        metadata_path = output_path.with_suffix(".json")
        payload = {
            "generator": "fish-stimulus-desktop-backend",
            "video_path": str(output_path),
            "duration_seconds": self.config.total_frames / float(self.config.fps),
            "total_frames": self.config.total_frames,
            "config": self.config.to_dict(),
        }
        metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(metadata_path)
