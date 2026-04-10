"""Deterministic MP4 export pipeline for the headless backend."""

from __future__ import annotations

import importlib
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

from renderer.frame_renderer import FrameRenderer
from simulation import StimulusEngine


@dataclass
class ExportResult:
    """Summary of an export run."""

    status: str
    video_path: str
    metadata_path: str | None
    total_frames: int
    frames_rendered: int
    duration_seconds: float
    writer_backend: str


class ExportControl:
    """Thread-safe controls for graceful stop and hard cancel requests."""

    def __init__(self) -> None:
        self._stop_requested = threading.Event()
        self._cancel_requested = threading.Event()

    def request_stop(self) -> None:
        if not self._cancel_requested.is_set():
            self._stop_requested.set()

    def request_cancel(self) -> None:
        self._cancel_requested.set()
        self._stop_requested.clear()

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested.is_set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested.is_set()


class VideoExporter:
    """Run a fixed-timestep simulation entirely offscreen and save an MP4."""

    def __init__(self, config, progress_callback=None, control: ExportControl | None = None):
        self.config = config.copy().validate()
        self.progress_callback = progress_callback
        self.control = control or ExportControl()
        self.renderer = FrameRenderer()

    def export(self, output_path: str) -> ExportResult:
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        writer, writer_backend = self._create_writer(output)

        engine = StimulusEngine(self.config)
        total_frames = self.config.total_frames
        start_time = time.perf_counter()
        frames_rendered = 0
        export_status = "completed"

        try:
            for frame_number in range(total_frames):
                if self.control.cancel_requested:
                    export_status = "cancelled"
                    break

                frame_state = engine.current_frame()
                writer.write(self.renderer.render_to_bgr(frame_state, self.config))

                elapsed = max(time.perf_counter() - start_time, 1e-6)
                completed = frame_number + 1
                frames_rendered = completed
                eta_seconds = (elapsed / completed) * (total_frames - completed)
                if self.progress_callback is not None:
                    self.progress_callback(completed, total_frames, eta_seconds, frame_state.phase)

                if self.control.cancel_requested:
                    export_status = "cancelled"
                    break
                if self.control.stop_requested and completed < total_frames:
                    export_status = "stopped"
                    break
                if completed < total_frames:
                    engine.step()
        finally:
            writer.close()

        if export_status == "cancelled":
            if output.exists():
                output.unlink()
            return ExportResult(
                status=export_status,
                video_path=str(output),
                metadata_path=None,
                total_frames=total_frames,
                frames_rendered=frames_rendered,
                duration_seconds=frames_rendered / float(self.config.fps),
                writer_backend=writer_backend,
            )

        metadata_path = self._write_metadata(output, frames_rendered, export_status, writer_backend)
        return ExportResult(
            status=export_status,
            video_path=str(output),
            metadata_path=metadata_path,
            total_frames=total_frames,
            frames_rendered=frames_rendered,
            duration_seconds=frames_rendered / float(self.config.fps),
            writer_backend=writer_backend,
        )

    def _write_metadata(
        self,
        output_path: Path,
        frames_rendered: int,
        export_status: str,
        writer_backend: str,
    ) -> str | None:
        if not self.config.save_metadata_json:
            return None

        metadata_path = output_path.with_suffix(".json")
        payload = {
            "generator": "fish-stimulus-desktop-backend",
            "status": export_status,
            "writer_backend": writer_backend,
            "video_path": str(output_path),
            "duration_seconds": frames_rendered / float(self.config.fps),
            "total_frames": self.config.total_frames,
            "frames_rendered": frames_rendered,
            "config": self.config.to_dict(),
        }
        metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(metadata_path)

    def _create_writer(self, output_path: Path):
        errors: list[str] = []

        try:
            return _FfmpegVideoWriter(output_path, self.config), "ffmpeg"
        except Exception as exc:  # pragma: no cover - exercised when dependency/runtime is absent
            errors.append(f"ffmpeg writer unavailable: {exc}")

        try:
            return _OpenCvVideoWriter(output_path, self.config), "opencv"
        except Exception as exc:
            errors.append(f"opencv writer unavailable: {exc}")

        joined = "; ".join(errors) if errors else "no writer backends were attempted"
        raise RuntimeError(f"Unable to initialize an MP4 writer for {output_path}: {joined}")


class _OpenCvVideoWriter:
    """Fallback MP4 writer using OpenCV codecs when ffmpeg packaging is unavailable."""

    def __init__(self, output_path: Path, config) -> None:
        self._writer = None
        self._output_path = output_path
        for codec in ("mp4v", "avc1", "H264"):
            writer = cv2.VideoWriter(
                str(output_path),
                cv2.VideoWriter_fourcc(*codec),
                float(config.fps),
                config.resolution,
            )
            if writer.isOpened():
                self._writer = writer
                return
            writer.release()

        raise RuntimeError("OpenCV could not open any MP4 codecs (tried mp4v, avc1, H264)")

    def write(self, frame_bgr) -> None:
        self._writer.write(frame_bgr)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()


class _FfmpegVideoWriter:
    """Primary MP4 writer backed by the packaged imageio-ffmpeg binary."""

    def __init__(self, output_path: Path, config) -> None:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        self._writer = imageio_ffmpeg.write_frames(
            str(output_path),
            size=config.resolution,
            fps=float(config.fps),
            codec="libx264",
            pix_fmt_in="bgr24",
            pix_fmt_out="yuv420p",
            macro_block_size=1,
            output_params=["-movflags", "+faststart"],
        )
        self._writer.send(None)

    def write(self, frame_bgr) -> None:
        self._writer.send(frame_bgr.tobytes())

    def close(self) -> None:
        self._writer.close()
