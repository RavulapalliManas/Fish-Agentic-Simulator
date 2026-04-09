"""Preview widget backed by the shared scene renderer."""

from __future__ import annotations

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget

from renderer.scene_renderer import SceneRenderer


class PreviewCanvas(QWidget):
    """Live preview surface for the current configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = SceneRenderer()
        self.frame_state = None
        self.config = None
        self.setMinimumSize(700, 520)

    def set_frame(self, frame_state, config) -> None:
        self.frame_state = frame_state
        self.config = config
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#EEF4FA"))
        if self.frame_state is None or self.config is None:
            return
        self.renderer.paint_scene(painter, self.frame_state, self.config, QRectF(self.rect()))
