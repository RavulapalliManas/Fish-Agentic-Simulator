"""PyQt5 renderer for the fish simulator."""

from __future__ import annotations

from typing import Dict, Tuple

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import QSizePolicy, QWidget

NEUTRAL_COLOR = QColor("#526577")
LEFT_COLOR = QColor("#4a88f0")
RIGHT_COLOR = QColor("#f05f67")
CENTER_COLOR = QColor("#93a0ad")


class ShapeCache:
    """Cache simple local polygons so each paint pass stays lightweight."""

    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, int], QPolygonF] = {}

    def polygon(self, shape: str, size: int) -> QPolygonF:
        key = (shape, size)
        if key not in self._cache:
            self._cache[key] = self._create_polygon(shape, float(size))
        return self._cache[key]

    def _create_polygon(self, shape: str, size: float) -> QPolygonF:
        if shape == "triangle":
            return QPolygonF(
                [
                    QPointF(size * 1.45, 0.0),
                    QPointF(-size * 0.95, -size * 0.78),
                    QPointF(-size * 0.45, 0.0),
                    QPointF(-size * 0.95, size * 0.78),
                ]
            )
        if shape == "square":
            return QPolygonF(
                [
                    QPointF(size, size),
                    QPointF(size, -size),
                    QPointF(-size, -size),
                    QPointF(-size, size),
                ]
            )
        if shape == "arrow":
            return QPolygonF(
                [
                    QPointF(size * 1.55, 0.0),
                    QPointF(size * 0.25, -size * 0.82),
                    QPointF(size * 0.18, -size * 0.34),
                    QPointF(-size * 1.15, -size * 0.34),
                    QPointF(-size * 1.15, size * 0.34),
                    QPointF(size * 0.18, size * 0.34),
                    QPointF(size * 0.25, size * 0.82),
                ]
            )
        return QPolygonF()


class SimulationCanvas(QWidget):
    """High-performance QWidget canvas for drawing the swarm."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.shape_cache = ShapeCache()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(760, 560)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#f6f8fb"))

        arena_width, arena_height = self.controller.config.arena_size
        scale = min(self.width() / arena_width, self.height() / arena_height)
        x_offset = (self.width() - arena_width * scale) / 2.0
        y_offset = (self.height() - arena_height * scale) / 2.0

        painter.save()
        painter.translate(x_offset, y_offset)
        painter.scale(scale, scale)
        self._draw_stage(painter, arena_width, arena_height)
        self._draw_attractors(painter)
        if self.controller.config.show_trails:
            self._draw_trails(painter)
        if self.controller.config.show_center_of_mass:
            self._draw_center_of_mass(painter)
        self._draw_agents(painter)
        painter.restore()

    def _draw_stage(self, painter: QPainter, width: int, height: int) -> None:
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#fbfcfe"))
        painter.drawRoundedRect(QRectF(0.0, 0.0, width, height), 24.0, 24.0)
        painter.setPen(QPen(QColor("#dde5ee"), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(0.5, 0.5, width - 1.0, height - 1.0), 24.0, 24.0)
        painter.restore()

    def _draw_attractors(self, painter: QPainter) -> None:
        phase = self.controller.phase
        radius = 9.0
        center_pen = QPen(CENTER_COLOR, 2.0)
        if phase != "split":
            center_pen.setStyle(Qt.DashLine)
        painter.setPen(center_pen)
        painter.setBrush(Qt.NoBrush if phase == "center" else QColor(147, 160, 173, 35))
        center = self.controller.attractors["center"]
        painter.drawEllipse(QPointF(center[0], center[1]), radius, radius)

        painter.setPen(QPen(LEFT_COLOR, 2.0))
        painter.setBrush(QColor(74, 136, 240, 55) if phase == "split" else Qt.NoBrush)
        left = self.controller.attractors["left"]
        painter.drawEllipse(QPointF(left[0], left[1]), radius, radius)

        painter.setPen(QPen(RIGHT_COLOR, 2.0))
        painter.setBrush(QColor(240, 95, 103, 55) if phase == "split" else Qt.NoBrush)
        right = self.controller.attractors["right"]
        painter.drawEllipse(QPointF(right[0], right[1]), radius, radius)

    def _draw_trails(self, painter: QPainter) -> None:
        for agent in self.controller.agents:
            trail = list(agent.trail)
            if len(trail) < 2:
                continue
            path = QPainterPath(QPointF(trail[0][0], trail[0][1]))
            for point in trail[1:]:
                path.lineTo(QPointF(point[0], point[1]))
            trail_pen = QPen(self._trail_color(agent.group), 2.0)
            painter.setPen(trail_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

    def _draw_center_of_mass(self, painter: QPainter) -> None:
        center_of_mass = self.controller.metrics["center_of_mass"]
        painter.save()
        painter.setPen(QPen(QColor("#d2a128"), 2.0))
        painter.setBrush(QColor(210, 161, 40, 45))
        painter.drawEllipse(QPointF(center_of_mass[0], center_of_mass[1]), 7.0, 7.0)
        painter.restore()

    def _draw_agents(self, painter: QPainter) -> None:
        for agent in self.controller.agents:
            color = self._agent_color(agent.group)
            painter.save()
            painter.translate(agent.pos[0], agent.pos[1])
            painter.rotate(agent.heading * 180.0 / 3.141592653589793)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            self._draw_agent_shape(painter, agent.shape, agent.size)
            painter.restore()

    def _draw_agent_shape(self, painter: QPainter, shape: str, size: int) -> None:
        if shape == "circle":
            painter.drawEllipse(QPointF(0.0, 0.0), float(size), float(size))
            return

        polygon = self.shape_cache.polygon(shape, size)
        if not polygon.isEmpty():
            painter.drawPolygon(polygon)

    def _agent_color(self, group: str) -> QColor:
        if self.controller.phase != "split":
            return NEUTRAL_COLOR
        if group == "left":
            return LEFT_COLOR
        if group == "right":
            return RIGHT_COLOR
        return NEUTRAL_COLOR

    def _trail_color(self, group: str) -> QColor:
        if self.controller.phase != "split":
            return QColor(82, 101, 119, 95)
        if group == "left":
            return QColor(74, 136, 240, 90)
        if group == "right":
            return QColor(240, 95, 103, 90)
        return QColor(82, 101, 119, 95)
