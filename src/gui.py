"""PyQt5 application for the fish swarm simulator."""

from __future__ import annotations

import sys

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config import AGENT_SHAPES, DEFAULT_CONFIG, MODEL_OPTIONS
from controller import SimulationController
from renderer import SimulationCanvas

SOFT_BLUE = "#4a88f0"
WINDOW_BG = "#f3f5f8"

SLIDER_DEFS = [
    ("cohesion", "Cohesion", 0.0, 2.5, 0.01, "{:.2f}"),
    ("alignment", "Alignment", 0.0, 2.5, 0.01, "{:.2f}"),
    ("separation", "Separation", 0.0, 3.0, 0.01, "{:.2f}"),
    ("noise", "Noise", 0.0, 1.0, 0.01, "{:.2f}"),
    ("speed", "Speed", 0.6, 4.5, 0.01, "{:.2f}"),
    ("split_ratio", "Split Ratio", 0.05, 0.95, 0.01, "{:.0%}"),
    ("attractor_strength", "Attractor Strength", 0.0, 1.5, 0.01, "{:.2f}"),
    ("rotation_strength", "Rotation Strength", 0.0, 1.2, 0.01, "{:.2f}"),
    ("agent_size", "Agent Size", 3.0, 16.0, 1.0, "{:.0f}"),
]

SHAPE_LABELS = {shape.title(): shape for shape in AGENT_SHAPES}


class LabeledSlider(QWidget):
    """Slider with a title and live numeric readout."""

    value_changed = pyqtSignal(float)

    def __init__(self, label: str, minimum: float, maximum: float, step: float, value: float, formatter: str):
        super().__init__()
        self.minimum = float(minimum)
        self.step = float(step)
        self.formatter = formatter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(label)
        self.value_label = QLabel(self._format(value))
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self.label)
        header.addStretch(1)
        header.addWidget(self.value_label)
        layout.addLayout(header)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, int(round((maximum - minimum) / step)))
        self.slider.setValue(self._to_slider(value))
        self.slider.valueChanged.connect(self._emit_value)
        layout.addWidget(self.slider)

    def _format(self, value: float) -> str:
        return self.formatter.format(float(value))

    def _to_slider(self, value: float) -> int:
        return int(round((float(value) - self.minimum) / self.step))

    def _from_slider(self, value: int) -> float:
        return self.minimum + float(value) * self.step

    def _emit_value(self, raw_value: int) -> None:
        numeric = self._from_slider(raw_value)
        self.value_label.setText(self._format(numeric))
        self.value_changed.emit(numeric)

    def set_numeric_value(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(self._to_slider(value))
        self.slider.blockSignals(False)
        self.value_label.setText(self._format(value))


class FishSimulatorWindow(QMainWindow):
    """Minimal PyQt5 UI with a left control panel and right simulation canvas."""

    def __init__(self):
        super().__init__()
        self.config_data = DEFAULT_CONFIG.copy()
        self.controller = SimulationController(self.config_data)

        self.setWindowTitle("Fish Swarm Simulator")
        self.resize(1400, 860)
        self.setMinimumSize(1260, 760)
        self.setStyleSheet(self._build_stylesheet())

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(self.controller.frame_delay_ms)
        self.timer.timeout.connect(self._tick)

        self.slider_widgets: dict[str, LabeledSlider] = {}
        self.metric_labels: dict[str, QLabel] = {}

        self._build_ui()
        self._refresh_view()

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("Root")
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(18)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        controls_scroll.setFrameShape(QFrame.NoFrame)
        controls_scroll.setFixedWidth(380)

        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(16)
        controls_scroll.setWidget(controls_widget)
        root_layout.addWidget(controls_scroll, 0)

        title_card = self._make_card()
        title_layout = QVBoxLayout(title_card)
        title_layout.setSpacing(8)
        title = QLabel("Fish Swarm Simulator")
        title.setObjectName("TitleLabel")
        subtitle = QLabel("Gather, orbit, then split. Built to stay simple and intuitive.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("SubtitleLabel")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        controls_layout.addWidget(title_card)

        controls_layout.addWidget(self._build_button_card())
        controls_layout.addWidget(self._build_selection_card())
        controls_layout.addWidget(self._build_slider_card())
        controls_layout.addWidget(self._build_timing_card())
        controls_layout.addWidget(self._build_metric_card())
        controls_layout.addStretch(1)

        stage_card = self._make_card()
        stage_layout = QVBoxLayout(stage_card)
        stage_layout.setContentsMargins(16, 16, 16, 16)
        stage_layout.setSpacing(12)
        root_layout.addWidget(stage_card, 1)

        stage_header = QHBoxLayout()
        stage_title = QLabel("Simulation")
        stage_title.setObjectName("SectionTitle")
        self.status_badge = QLabel("Stopped")
        self.status_badge.setObjectName("StatusBadge")
        stage_header.addWidget(stage_title)
        stage_header.addStretch(1)
        stage_header.addWidget(self.status_badge)
        stage_layout.addLayout(stage_header)

        self.canvas = SimulationCanvas(self.controller)
        stage_layout.addWidget(self.canvas, 1)

    def _build_button_card(self) -> QFrame:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        heading = QLabel("Simulation Control")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start_simulation)
        self.start_button.setObjectName("PrimaryButton")
        row.addWidget(self.start_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self._pause_simulation)
        row.addWidget(self.pause_button)

        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self._reset_simulation)
        row.addWidget(self.reset_button)

        layout.addLayout(row)
        return card

    def _build_selection_card(self) -> QFrame:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        heading = QLabel("Model and Appearance")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        self.model_combo = self._add_labeled_combo(
            layout,
            "Motion Model",
            list(MODEL_OPTIONS),
            self.config_data.model_name,
            self._on_model_changed,
        )

        shape_items = list(SHAPE_LABELS.keys())
        current_shape = self.config_data.agent_shape.title()
        self.shape_combo = self._add_labeled_combo(
            layout,
            "Agent Shape",
            shape_items,
            current_shape,
            self._on_shape_changed,
        )

        self.trail_combo = self._add_labeled_combo(
            layout,
            "Trails",
            ["On", "Off"],
            "On" if self.config_data.show_trails else "Off",
            lambda text: self._set_boolean("show_trails", text == "On"),
        )

        self.com_combo = self._add_labeled_combo(
            layout,
            "Center of Mass",
            ["On", "Off"],
            "On" if self.config_data.show_center_of_mass else "Off",
            lambda text: self._set_boolean("show_center_of_mass", text == "On"),
        )

        return card

    def _build_slider_card(self) -> QFrame:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        heading = QLabel("Behavior")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        for name, label, minimum, maximum, step, formatter in SLIDER_DEFS:
            slider = LabeledSlider(label, minimum, maximum, step, getattr(self.config_data, name), formatter)
            slider.value_changed.connect(lambda value, attr=name: self._set_numeric(attr, value))
            layout.addWidget(slider)
            self.slider_widgets[name] = slider

        return card

    def _build_timing_card(self) -> QFrame:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        heading = QLabel("Timing")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        self.center_spin = self._add_labeled_spin(
            layout,
            "Time in Center",
            self.config_data.time_in_center,
            0.0,
            60.0,
            self._on_center_time_changed,
        )
        self.split_spin = self._add_labeled_spin(
            layout,
            "Time to Split",
            self.config_data.time_to_split,
            self.config_data.time_in_center + 0.1,
            120.0,
            self._on_split_time_changed,
        )

        return card

    def _build_metric_card(self) -> QFrame:
        card = self._make_card()
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        heading = QLabel("Metrics")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        for label, key in [
            ("State", "simulation_state"),
            ("Phase", "phase"),
            ("Elapsed", "elapsed_time"),
            ("Groups", "groups"),
            ("Average Speed", "avg_speed"),
            ("Alignment", "polarization"),
            ("Spread", "spread"),
        ]:
            row = QHBoxLayout()
            left = QLabel(label)
            left.setObjectName("MetricLabel")
            right = QLabel("--")
            right.setObjectName("MetricValue")
            row.addWidget(left)
            row.addStretch(1)
            row.addWidget(right)
            layout.addLayout(row)
            self.metric_labels[key] = right

        return card

    def _add_labeled_combo(self, layout: QVBoxLayout, label: str, items: list[str], current: str, handler) -> QComboBox:
        label_widget = QLabel(label)
        label_widget.setObjectName("FieldLabel")
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentText(current)
        combo.currentTextChanged.connect(handler)
        layout.addWidget(label_widget)
        layout.addWidget(combo)
        return combo

    def _add_labeled_spin(
        self,
        layout: QVBoxLayout,
        label: str,
        value: float,
        minimum: float,
        maximum: float,
        handler,
    ) -> QDoubleSpinBox:
        label_widget = QLabel(label)
        label_widget.setObjectName("FieldLabel")
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setSuffix(" s")
        spin.setValue(value)
        spin.valueChanged.connect(handler)
        layout.addWidget(label_widget)
        layout.addWidget(spin)
        return spin

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(Qt.lightGray)
        card.setGraphicsEffect(shadow)
        return card

    def _start_simulation(self) -> None:
        self.controller.start()
        self.timer.start(self.controller.frame_delay_ms)
        self._refresh_view()

    def _pause_simulation(self) -> None:
        self.controller.pause()
        self.timer.stop()
        self._refresh_view()

    def _reset_simulation(self) -> None:
        self.timer.stop()
        self.controller.reset()
        self._refresh_view()

    def _tick(self) -> None:
        if self.controller.step():
            self._refresh_view()

    def _on_model_changed(self, model_name: str) -> None:
        self.controller.set_model(model_name)
        self._refresh_view()

    def _on_shape_changed(self, label: str) -> None:
        self.config_data.agent_shape = SHAPE_LABELS[label]
        self.controller.sync_live_config()
        self._refresh_view()

    def _on_center_time_changed(self, value: float) -> None:
        self.config_data.time_in_center = float(value)
        self.split_spin.blockSignals(True)
        self.split_spin.setMinimum(self.config_data.time_in_center + 0.1)
        if self.config_data.time_to_split < self.config_data.time_in_center + 0.1:
            self.config_data.time_to_split = self.config_data.time_in_center + 0.1
            self.split_spin.setValue(self.config_data.time_to_split)
        self.split_spin.blockSignals(False)
        self.controller.sync_live_config()
        self._refresh_view()

    def _on_split_time_changed(self, value: float) -> None:
        self.config_data.time_to_split = max(float(value), self.config_data.time_in_center + 0.1)
        if abs(self.split_spin.value() - self.config_data.time_to_split) > 1e-6:
            self.split_spin.blockSignals(True)
            self.split_spin.setValue(self.config_data.time_to_split)
            self.split_spin.blockSignals(False)
        self.controller.sync_live_config()
        self._refresh_view()

    def _set_numeric(self, name: str, value: float) -> None:
        previous = getattr(self.config_data, name)
        setattr(self.config_data, name, value)
        if name == "speed":
            self.controller.rescale_agent_speed(value, previous)
        self.controller.sync_live_config()
        self._refresh_view()

    def _set_boolean(self, name: str, value: bool) -> None:
        setattr(self.config_data, name, value)
        self._refresh_view()

    def _refresh_view(self) -> None:
        metrics = self.controller.metrics
        self.metric_labels["simulation_state"].setText(str(metrics["simulation_state"]).title())
        self.metric_labels["phase"].setText(str(metrics["phase"]).title())
        self.metric_labels["elapsed_time"].setText(f"{float(metrics['elapsed_time']):.1f} s")
        self.metric_labels["groups"].setText(
            f"school {metrics['school_count']} | left {metrics['left_count']} | right {metrics['right_count']}"
        )
        self.metric_labels["avg_speed"].setText(f"{float(metrics['avg_speed']):.2f} px/frame")
        self.metric_labels["polarization"].setText(f"{float(metrics['polarization']):.2f}")
        self.metric_labels["spread"].setText(f"{float(metrics['spread']):.1f} px")
        self.status_badge.setText(str(metrics["simulation_state"]).title())
        self.canvas.update()

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.controller.pause()
        super().closeEvent(event)

    def _build_stylesheet(self) -> str:
        font = QFont("Helvetica Neue", 11)
        QApplication.instance().setFont(font)
        return f"""
            QWidget#Root {{
                background: {WINDOW_BG};
                color: #25313d;
            }}
            QFrame#Card {{
                background: rgba(255, 255, 255, 0.94);
                border: 1px solid rgba(219, 227, 236, 0.95);
                border-radius: 24px;
            }}
            QLabel {{
                color: #2b3947;
            }}
            QLabel#TitleLabel {{
                font-size: 28px;
                font-weight: 700;
                color: #1d2733;
            }}
            QLabel#SubtitleLabel {{
                color: #61707f;
                font-size: 13px;
            }}
            QLabel#SectionTitle {{
                font-size: 15px;
                font-weight: 600;
                color: #23303d;
            }}
            QLabel#FieldLabel {{
                margin-top: 4px;
                color: #627181;
                font-size: 12px;
            }}
            QLabel#MetricLabel {{
                color: #627181;
                font-size: 12px;
            }}
            QLabel#MetricValue {{
                color: #243241;
                font-weight: 600;
            }}
            QLabel#StatusBadge {{
                background: rgba(74, 136, 240, 0.12);
                color: {SOFT_BLUE};
                padding: 8px 14px;
                border-radius: 16px;
                font-weight: 600;
            }}
            QPushButton {{
                background: #eef2f7;
                border: none;
                border-radius: 18px;
                padding: 12px 18px;
                color: #2b3947;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #e6ecf5;
            }}
            QPushButton#PrimaryButton {{
                background: {SOFT_BLUE};
                color: white;
            }}
            QPushButton#PrimaryButton:hover {{
                background: #5a96f4;
            }}
            QComboBox, QDoubleSpinBox {{
                background: #f7f9fc;
                border: 1px solid #dbe3ec;
                border-radius: 16px;
                padding: 10px 12px;
                min-height: 22px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 26px;
            }}
            QSlider::groove:horizontal {{
                background: #dfe6ef;
                height: 8px;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: white;
                border: 2px solid {SOFT_BLUE};
                width: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }}
            QScrollArea {{
                background: transparent;
            }}
        """


def main() -> None:
    app = QApplication(sys.argv)
    window = FishSimulatorWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
