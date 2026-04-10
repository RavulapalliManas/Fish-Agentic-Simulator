"""Pure OpenCV frame renderer for headless stimulus export."""

from __future__ import annotations

import math

import cv2
import numpy as np


class FrameRenderer:
    """Render fish trajectories into BGR frames without GUI dependencies."""

    SCHOOL_COLOR = "#4B6275"
    LEFT_COLOR = "#2676FF"
    RIGHT_COLOR = "#FF6B5B"
    GRID_COLOR = "#C7D6E4"
    LANDMARK_COLOR = "#77A9DE"

    def render_to_bgr(self, frame_state, config) -> np.ndarray:
        frame = np.full(
            (int(config.output_height), int(config.output_width), 3),
            self._hex_to_bgr(config.background_color),
            dtype=np.uint8,
        )
        if config.grid_enabled:
            self._draw_grid(frame, config)
        if config.landmark_enabled:
            self._draw_landmarks(frame, config)
        for agent in frame_state.agents:
            color = self._group_color(agent.group, frame_state.phase)
            self._draw_shape(frame, agent.position, agent.heading, config.shape, float(config.size), color)
        return frame

    def _draw_grid(self, frame: np.ndarray, config) -> None:
        color = self._hex_to_bgr(self.GRID_COLOR)
        for x in np.arange(config.grid_spacing, config.output_width, config.grid_spacing):
            cv2.line(frame, (int(x), 0), (int(x), int(config.output_height)), color, 1, cv2.LINE_AA)
        for y in np.arange(config.grid_spacing, config.output_height, config.grid_spacing):
            cv2.line(frame, (0, int(y)), (int(config.output_width), int(y)), color, 1, cv2.LINE_AA)

    def _draw_landmarks(self, frame: np.ndarray, config) -> None:
        color = self._hex_to_bgr(self.LANDMARK_COLOR)
        radius = int(round(config.landmark_radius))
        cv2.circle(frame, (int(config.landmark_left_x), int(config.landmark_left_y)), radius, color, 2, cv2.LINE_AA)
        cv2.circle(frame, (int(config.landmark_right_x), int(config.landmark_right_y)), radius, color, 2, cv2.LINE_AA)

    def _draw_shape(
        self,
        frame: np.ndarray,
        position: np.ndarray,
        heading: float,
        shape: str,
        size: float,
        color: tuple[int, int, int],
    ) -> None:
        center = (int(round(position[0])), int(round(position[1])))
        if shape == "circle":
            radius = int(round(size))
            cv2.circle(frame, center, radius, color, -1, cv2.LINE_AA)
            cv2.circle(frame, center, radius, (255, 255, 255), 1, cv2.LINE_AA)
            return

        polygon = self._rotated_polygon(shape, size, heading, position)
        cv2.fillPoly(frame, [polygon.astype(np.int32)], color, lineType=cv2.LINE_AA)

    def _rotated_polygon(self, shape: str, size: float, heading: float, position: np.ndarray) -> np.ndarray:
        if shape == "square":
            points = np.array(
                [
                    [size, size],
                    [size, -size],
                    [-size, -size],
                    [-size, size],
                ],
                dtype=float,
            )
        elif shape == "arrow":
            points = np.array(
                [
                    [size * 1.45, 0.0],
                    [size * 0.15, -size * 0.80],
                    [size * 0.08, -size * 0.34],
                    [-size * 1.00, -size * 0.34],
                    [-size * 1.00, size * 0.34],
                    [size * 0.08, size * 0.34],
                    [size * 0.15, size * 0.80],
                ],
                dtype=float,
            )
        else:
            points = np.array(
                [
                    [size * 1.45, 0.0],
                    [-size * 0.95, -size * 0.76],
                    [-size * 0.35, 0.0],
                    [-size * 0.95, size * 0.76],
                ],
                dtype=float,
            )

        rotation = np.array(
            [
                [math.cos(heading), -math.sin(heading)],
                [math.sin(heading), math.cos(heading)],
            ],
            dtype=float,
        )
        return points @ rotation.T + np.asarray(position, dtype=float)

    def _group_color(self, group: str, phase: str) -> tuple[int, int, int]:
        if phase != "split":
            return self._hex_to_bgr(self.SCHOOL_COLOR)
        if group == "left":
            return self._hex_to_bgr(self.LEFT_COLOR)
        if group == "right":
            return self._hex_to_bgr(self.RIGHT_COLOR)
        return self._hex_to_bgr(self.SCHOOL_COLOR)

    def _hex_to_bgr(self, hex_color: str) -> tuple[int, int, int]:
        value = str(hex_color).lstrip("#")
        if len(value) != 6:
            return 0, 0, 0
        return int(value[4:6], 16), int(value[2:4], 16), int(value[0:2], 16)
