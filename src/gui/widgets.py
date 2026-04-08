"""Reusable PyQt widgets for the stimulus generator UI."""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QColorDialog, QFrame, QPushButton


class CardFrame(QFrame):
    """Rounded card used throughout the UI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")


class ColorButton(QPushButton):
    """Button that displays and edits a hex color."""

    color_changed = pyqtSignal(str)

    def __init__(self, color_hex: str, label: str = "Choose Color", parent=None):
        super().__init__(label, parent)
        self._color_hex = color_hex
        self.clicked.connect(self._pick_color)
        self._refresh_style()

    @property
    def color_hex(self) -> str:
        return self._color_hex

    def set_color(self, color_hex: str) -> None:
        self._color_hex = str(color_hex)
        self._refresh_style()

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color_hex), self.window(), "Select Background Color")
        if not color.isValid():
            return
        self._color_hex = color.name().upper()
        self._refresh_style()
        self.color_changed.emit(self._color_hex)

    def _refresh_style(self) -> None:
        self.setText(self._color_hex.upper())
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {self._color_hex};
                color: {"#0F1720" if QColor(self._color_hex).lightness() > 150 else "#FFFFFF"};
                border: 1px solid rgba(130, 150, 170, 0.30);
                border-radius: 14px;
                padding: 10px 14px;
                font-weight: 600;
            }}
            """
        )
