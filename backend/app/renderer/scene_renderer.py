"""Offscreen and preview renderer built on QPainter."""

from __future__ import annotations

import cv2
import numpy as np
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPolygonF


class SceneRenderer:
    """Render the fish stimulus either into a widget or a video frame."""

    SCHOOL_COLOR = QColor("#4B6275")
    LEFT_COLOR = QColor("#2676FF")
    RIGHT_COLOR = QColor("#FF6B5B")
    GRID_COLOR = QColor(177, 198, 215, 60)
    LANDMARK_FILL = QColor(96, 152, 214, 34)
    LANDMARK_STROKE = QColor(96, 152, 214, 90)

    def paint_scene(self, painter: QPainter, frame_state, config, target_rect: QRectF) -> None:
        painter.save()
        painter.fillRect(target_rect, QColor(config.background_color))
        scale = min(target_rect.width() / config.output_width, target_rect.height() / config.output_height)
        x_offset = target_rect.x() + (target_rect.width() - config.output_width * scale) / 2.0
        y_offset = target_rect.y() + (target_rect.height() - config.output_height * scale) / 2.0
        painter.translate(x_offset, y_offset)
        painter.scale(scale, scale)
        self._draw_background(painter, config)
        self._draw_agents(painter, frame_state, config)
        painter.restore()

    def render_to_bgr(self, frame_state, config) -> np.ndarray:
        """Render a frame directly into a NumPy BGR image for OpenCV."""
        image = QImage(config.output_width, config.output_height, QImage.Format_RGBA8888)
        image.fill(QColor(config.background_color))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self.paint_scene(
            painter,
            frame_state,
            config,
            QRectF(0.0, 0.0, float(config.output_width), float(config.output_height)),
        )
        painter.end()

        pointer = image.bits()
        pointer.setsize(image.byteCount())
        array = np.frombuffer(pointer, dtype=np.uint8).reshape(
            image.height(),
            image.bytesPerLine() // 4,
            4,
        )[:, : image.width(), :]
        return cv2.cvtColor(array, cv2.COLOR_RGBA2BGR)

    def _draw_background(self, painter: QPainter, config) -> None:
        if config.grid_enabled:
            self._draw_grid(painter, config)
        if config.landmark_enabled:
            self._draw_landmarks(painter, config)

    def _draw_grid(self, painter: QPainter, config) -> None:
        painter.save()
        painter.setPen(QPen(self.GRID_COLOR, 1.0))
        spacing = float(config.grid_spacing)
        for x in np.arange(spacing, config.output_width, spacing):
            painter.drawLine(QPointF(float(x), 0.0), QPointF(float(x), float(config.output_height)))
        for y in np.arange(spacing, config.output_height, spacing):
            painter.drawLine(QPointF(0.0, float(y)), QPointF(float(config.output_width), float(y)))
        painter.restore()

    def _draw_landmarks(self, painter: QPainter, config) -> None:
        painter.save()
        painter.setPen(QPen(self.LANDMARK_STROKE, 2.0))
        painter.setBrush(self.LANDMARK_FILL)
        radius = float(config.landmark_radius)
        painter.drawEllipse(QPointF(config.landmark_left_x, config.landmark_left_y), radius, radius)
        painter.drawEllipse(QPointF(config.landmark_right_x, config.landmark_right_y), radius, radius)
        painter.restore()

    def _draw_agents(self, painter: QPainter, frame_state, config) -> None:
        for agent in frame_state.agents:
            painter.save()
            painter.translate(float(agent.position[0]), float(agent.position[1]))
            painter.rotate(np.degrees(agent.heading))
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._group_color(agent.group, frame_state.phase))
            self._draw_shape(painter, config.shape, float(config.size))
            painter.restore()

    def _draw_shape(self, painter: QPainter, shape: str, size: float) -> None:
        if shape == "circle":
            painter.drawEllipse(QPointF(0.0, 0.0), size, size)
            return

        if shape == "square":
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(size, size),
                        QPointF(size, -size),
                        QPointF(-size, -size),
                        QPointF(-size, size),
                    ]
                )
            )
            return

        if shape == "arrow":
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(size * 1.45, 0.0),
                        QPointF(size * 0.15, -size * 0.80),
                        QPointF(size * 0.08, -size * 0.34),
                        QPointF(-size * 1.00, -size * 0.34),
                        QPointF(-size * 1.00, size * 0.34),
                        QPointF(size * 0.08, size * 0.34),
                        QPointF(size * 0.15, size * 0.80),
                    ]
                )
            )
            return

        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(size * 1.45, 0.0),
                    QPointF(-size * 0.95, -size * 0.76),
                    QPointF(-size * 0.35, 0.0),
                    QPointF(-size * 0.95, size * 0.76),
                ]
            )
        )

    def _group_color(self, group: str, phase: str) -> QColor:
        if phase != "split":
            return self.SCHOOL_COLOR
        if group == "left":
            return self.LEFT_COLOR
        if group == "right":
            return self.RIGHT_COLOR
        return self.SCHOOL_COLOR
