"""Threaded export worker so the UI stays responsive during rendering."""

from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from renderer import VideoExporter


class ExportWorker(QThread):
    """Run deterministic video export in a background thread."""

    progress_changed = pyqtSignal(int, int, float, str)
    export_finished = pyqtSignal(str, str)
    export_failed = pyqtSignal(str)

    def __init__(self, config, output_path: str, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.output_path = str(output_path)

    def run(self) -> None:
        try:
            exporter = VideoExporter(self.config, progress_callback=self._emit_progress)
            result = exporter.export(self.output_path)
            self.export_finished.emit(result.video_path, result.metadata_path or "")
        except Exception as exc:  # pragma: no cover - surfaced to the UI
            self.export_failed.emit(str(exc))

    def _emit_progress(self, completed: int, total: int, eta_seconds: float, phase: str) -> None:
        self.progress_changed.emit(int(completed), int(total), float(eta_seconds), str(phase))
