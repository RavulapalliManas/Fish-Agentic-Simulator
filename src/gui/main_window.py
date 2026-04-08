"""Main PyQt window for the research-grade fish stimulus generator."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QDoubleSpinBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.export_worker import ExportWorker
from gui.widgets import CardFrame, ColorButton
from renderer import PreviewCanvas
from simulation import StimulusEngine
from utils import MODEL_OPTIONS, SHAPE_OPTIONS, StimulusConfig, detect_device_profile, recommend_export_settings


class FishStimulusWindow(QMainWindow):
    """Control surface focused on reproducible fish-training video export."""

    def __init__(self):
        super().__init__()
        self.config = StimulusConfig()
        self.preview_engine = StimulusEngine(self.config)
        self.preview_timer = QTimer(self)
        self.preview_timer.setTimerType(Qt.PreciseTimer)
        self.preview_timer.timeout.connect(self._advance_preview)
        self.export_worker: ExportWorker | None = None
        self._loading_values = False
        self._last_resolution = self.config.resolution
        self.field_widgets: dict[str, object] = {}
        self.metric_labels: dict[str, QLabel] = {}

        self.setWindowTitle("Fish Stimulus Generator")
        self.resize(1520, 940)
        self.setMinimumSize(1320, 820)
        self._apply_base_style()
        self._build_ui()
        self._load_config_into_fields(self.config)
        self._refresh_preview()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)

        layout.addWidget(self._build_left_panel(), 0)
        layout.addWidget(self._build_right_panel(), 1)

    def _build_left_panel(self) -> QWidget:
        container = QWidget()
        container.setFixedWidth(470)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title_card = CardFrame()
        title_layout = QVBoxLayout(title_card)
        title_layout.setContentsMargins(20, 20, 20, 20)
        title_layout.setSpacing(8)

        title = QLabel("Research-Grade Fish Stimulus Generator")
        title.setObjectName("TitleLabel")
        subtitle = QLabel(
            "Deterministic T-maze splitting stimuli with fixed-timestep export, "
            "phase-controlled grouping, and reproducible video output."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("SubtitleLabel")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        layout.addWidget(title_card)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._wrap_scroll(self._build_simulation_tab()), "Simulation")
        self.tabs.addTab(self._wrap_scroll(self._build_paradigm_tab()), "Paradigm")
        self.tabs.addTab(self._wrap_scroll(self._build_rendering_tab()), "Rendering")
        self.tabs.addTab(self._wrap_scroll(self._build_appearance_tab()), "Appearance")
        self.tabs.addTab(self._wrap_scroll(self._build_output_tab()), "Output")
        layout.addWidget(self.tabs, 1)

        return container

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        preview_card = CardFrame()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(18, 18, 18, 18)
        preview_layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Stimulus Preview")
        title.setObjectName("SectionTitle")
        self.phase_badge = QLabel("CENTER")
        self.phase_badge.setObjectName("BadgeLabel")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.phase_badge)
        preview_layout.addLayout(header)

        self.preview_canvas = PreviewCanvas()
        preview_layout.addWidget(self.preview_canvas, 1)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.preview_play_button = QPushButton("Play Preview")
        self.preview_play_button.setObjectName("PrimaryButton")
        self.preview_play_button.clicked.connect(self._start_preview)
        self.preview_pause_button = QPushButton("Pause")
        self.preview_pause_button.clicked.connect(self._pause_preview)
        self.preview_reset_button = QPushButton("Reset")
        self.preview_reset_button.clicked.connect(self._reset_preview)
        controls.addWidget(self.preview_play_button)
        controls.addWidget(self.preview_pause_button)
        controls.addWidget(self.preview_reset_button)
        controls.addStretch(1)
        preview_layout.addLayout(controls)
        layout.addWidget(preview_card, 1)

        metrics_card = CardFrame()
        metrics_layout = QGridLayout(metrics_card)
        metrics_layout.setContentsMargins(18, 18, 18, 18)
        metrics_layout.setHorizontalSpacing(16)
        metrics_layout.setVerticalSpacing(10)

        metrics_title = QLabel("Current State")
        metrics_title.setObjectName("SectionTitle")
        metrics_layout.addWidget(metrics_title, 0, 0, 1, 2)

        rows = [
            ("Frame", "frame"),
            ("Time", "time"),
            ("Phase", "phase"),
            ("Average Speed", "avg_speed"),
            ("Polarization", "polarization"),
            ("Spread", "spread"),
            ("School / Left / Right", "groups"),
        ]
        for row_index, (label_text, key) in enumerate(rows, start=1):
            left = QLabel(label_text)
            left.setObjectName("MetricLabel")
            right = QLabel("--")
            right.setObjectName("MetricValue")
            metrics_layout.addWidget(left, row_index, 0)
            metrics_layout.addWidget(right, row_index, 1)
            self.metric_labels[key] = right

        layout.addWidget(metrics_card, 0)
        return panel

    def _build_simulation_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        card = CardFrame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(12)
        title = QLabel("School Dynamics")
        title.setObjectName("SectionTitle")
        card_layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        self._add_spin(form, "random_seed", "Random Seed", 0, 999999999, self.config.random_seed)
        self._add_spin(form, "number_of_agents", "Number of Agents", 2, 300, self.config.number_of_agents)
        self._add_combo(form, "model_type", "Model Type", list(MODEL_OPTIONS), self.config.model_type)
        self._add_double_spin(form, "noise", "Noise", 0.0, 2.0, self.config.noise, decimals=3, step=0.01)
        self._add_double_spin(form, "speed", "Speed (px/s)", 10.0, 500.0, self.config.speed, decimals=1, step=5.0)
        self._add_double_spin(form, "cohesion", "Cohesion", 0.0, 4.0, self.config.cohesion, decimals=2, step=0.05)
        self._add_double_spin(form, "alignment", "Alignment", 0.0, 4.0, self.config.alignment, decimals=2, step=0.05)
        self._add_double_spin(form, "separation", "Separation", 0.0, 4.0, self.config.separation, decimals=2, step=0.05)

        card_layout.addLayout(form)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_paradigm_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        timing_card = CardFrame()
        timing_layout = QVBoxLayout(timing_card)
        timing_layout.setContentsMargins(18, 18, 18, 18)
        timing_layout.setSpacing(12)
        timing_title = QLabel("Splitting Control")
        timing_title.setObjectName("SectionTitle")
        timing_layout.addWidget(timing_title)
        timing_form = QFormLayout()
        timing_form.setHorizontalSpacing(12)
        timing_form.setVerticalSpacing(12)

        self._add_double_spin(timing_form, "split_ratio", "Split Ratio", 0.0, 1.0, self.config.split_ratio, decimals=2, step=0.01)
        self._add_double_spin(timing_form, "time_in_center", "Time in Center (s)", 0.0, 60.0, self.config.time_in_center, decimals=2, step=0.1)
        self._add_double_spin(timing_form, "time_to_split", "Time to Split (s)", 0.1, 60.0, self.config.time_to_split, decimals=2, step=0.1)
        self._add_double_spin(
            timing_form,
            "attractor_strength",
            "Attractor Strength",
            0.0,
            400.0,
            self.config.attractor_strength,
            decimals=1,
            step=5.0,
        )
        self._add_double_spin(
            timing_form,
            "rotation_strength",
            "Rotation Strength",
            0.0,
            240.0,
            self.config.rotation_strength,
            decimals=1,
            step=2.0,
        )
        timing_layout.addLayout(timing_form)
        layout.addWidget(timing_card)

        attractor_card = CardFrame()
        attractor_layout = QVBoxLayout(attractor_card)
        attractor_layout.setContentsMargins(18, 18, 18, 18)
        attractor_layout.setSpacing(12)
        attractor_title = QLabel("Attractor Positions")
        attractor_title.setObjectName("SectionTitle")
        attractor_layout.addWidget(attractor_title)

        attractor_form = QFormLayout()
        attractor_form.setHorizontalSpacing(12)
        attractor_form.setVerticalSpacing(12)
        self._add_double_spin(attractor_form, "center_attractor_x", "Center X", 0.0, 4000.0, self.config.center_attractor_x, decimals=1, step=5.0)
        self._add_double_spin(attractor_form, "center_attractor_y", "Center Y", 0.0, 4000.0, self.config.center_attractor_y, decimals=1, step=5.0)
        self._add_double_spin(attractor_form, "left_attractor_x", "Left X", 0.0, 4000.0, self.config.left_attractor_x, decimals=1, step=5.0)
        self._add_double_spin(attractor_form, "left_attractor_y", "Left Y", 0.0, 4000.0, self.config.left_attractor_y, decimals=1, step=5.0)
        self._add_double_spin(attractor_form, "right_attractor_x", "Right X", 0.0, 4000.0, self.config.right_attractor_x, decimals=1, step=5.0)
        self._add_double_spin(attractor_form, "right_attractor_y", "Right Y", 0.0, 4000.0, self.config.right_attractor_y, decimals=1, step=5.0)
        attractor_layout.addLayout(attractor_form)

        reset_layout_button = QPushButton("Reset T-Maze Layout")
        reset_layout_button.clicked.connect(self._reset_layout_defaults)
        attractor_layout.addWidget(reset_layout_button)
        layout.addWidget(attractor_card)
        layout.addStretch(1)
        return page

    def _build_rendering_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        card = CardFrame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(12)
        title = QLabel("Video Rendering")
        title.setObjectName("SectionTitle")
        card_layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        self._add_double_spin(form, "video_duration", "Duration (s)", 0.1, 600.0, self.config.video_duration, decimals=2, step=0.5)
        self._add_spin(form, "fps", "Frames Per Second", 1, 240, self.config.fps)
        self._add_spin(form, "output_width", "Width", 160, 4096, self.config.output_width, handler=self._on_resolution_changed)
        self._add_spin(form, "output_height", "Height", 120, 4096, self.config.output_height, handler=self._on_resolution_changed)
        card_layout.addLayout(form)

        device_button_row = QHBoxLayout()
        self.auto_optimize_button = QPushButton("Auto Optimize")
        self.auto_optimize_button.setObjectName("PrimaryButton")
        self.auto_optimize_button.clicked.connect(self._auto_optimize)
        device_button_row.addWidget(self.auto_optimize_button)
        device_button_row.addStretch(1)
        card_layout.addLayout(device_button_row)

        self.device_summary_label = QLabel("")
        self.device_summary_label.setObjectName("HintLabel")
        self.device_summary_label.setWordWrap(True)
        card_layout.addWidget(self.device_summary_label)
        layout.addWidget(card)
        layout.addStretch(1)
        self._update_device_summary()
        return page

    def _build_appearance_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        appearance_card = CardFrame()
        appearance_layout = QVBoxLayout(appearance_card)
        appearance_layout.setContentsMargins(18, 18, 18, 18)
        appearance_layout.setSpacing(12)
        title = QLabel("Fish Appearance")
        title.setObjectName("SectionTitle")
        appearance_layout.addWidget(title)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        self._add_double_spin(form, "size", "Size", 2.0, 40.0, self.config.size, decimals=1, step=0.5)
        self._add_combo(form, "shape", "Shape", list(SHAPE_OPTIONS), self.config.shape)
        background_button = ColorButton(self.config.background_color)
        background_button.color_changed.connect(self._sync_config_from_fields)
        self.field_widgets["background_color"] = background_button
        form.addRow("Background Color", background_button)
        appearance_layout.addLayout(form)
        layout.addWidget(appearance_card)

        environment_card = CardFrame()
        environment_layout = QVBoxLayout(environment_card)
        environment_layout.setContentsMargins(18, 18, 18, 18)
        environment_layout.setSpacing(12)
        environment_title = QLabel("Spatial Cues")
        environment_title.setObjectName("SectionTitle")
        environment_layout.addWidget(environment_title)
        env_form = QFormLayout()
        env_form.setHorizontalSpacing(12)
        env_form.setVerticalSpacing(12)
        self._add_checkbox(env_form, "grid_enabled", "Show Grid", self.config.grid_enabled)
        self._add_checkbox(env_form, "landmark_enabled", "Show Landmarks", self.config.landmark_enabled)
        self._add_double_spin(env_form, "grid_spacing", "Grid Spacing", 12.0, 400.0, self.config.grid_spacing, decimals=1, step=4.0)
        self._add_double_spin(
            env_form,
            "landmark_radius",
            "Landmark Radius",
            2.0,
            100.0,
            self.config.landmark_radius,
            decimals=1,
            step=1.0,
        )
        self._add_double_spin(env_form, "landmark_left_x", "Left Landmark X", 0.0, 4000.0, self.config.landmark_left_x, decimals=1, step=5.0)
        self._add_double_spin(env_form, "landmark_left_y", "Left Landmark Y", 0.0, 4000.0, self.config.landmark_left_y, decimals=1, step=5.0)
        self._add_double_spin(env_form, "landmark_right_x", "Right Landmark X", 0.0, 4000.0, self.config.landmark_right_x, decimals=1, step=5.0)
        self._add_double_spin(env_form, "landmark_right_y", "Right Landmark Y", 0.0, 4000.0, self.config.landmark_right_y, decimals=1, step=5.0)
        environment_layout.addLayout(env_form)
        layout.addWidget(environment_card)
        layout.addStretch(1)
        return page

    def _build_output_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        export_card = CardFrame()
        export_layout = QVBoxLayout(export_card)
        export_layout.setContentsMargins(18, 18, 18, 18)
        export_layout.setSpacing(12)
        title = QLabel("Export")
        title.setObjectName("SectionTitle")
        export_layout.addWidget(title)

        path_row = QHBoxLayout()
        self.output_path_edit = QLineEdit(str((Path.cwd() / "output" / "stimulus.mp4").resolve()))
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._choose_output_path)
        path_row.addWidget(self.output_path_edit, 1)
        path_row.addWidget(browse_button)
        export_layout.addWidget(QLabel("Output MP4"))
        export_layout.addLayout(path_row)

        metadata_checkbox = QCheckBox("Save metadata JSON sidecar")
        metadata_checkbox.setChecked(self.config.save_metadata_json)
        metadata_checkbox.toggled.connect(self._sync_config_from_fields)
        self.field_widgets["save_metadata_json"] = metadata_checkbox
        export_layout.addWidget(metadata_checkbox)

        self.generate_button = QPushButton("Generate Video")
        self.generate_button.setObjectName("PrimaryButton")
        self.generate_button.clicked.connect(self._generate_video)
        export_layout.addWidget(self.generate_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        export_layout.addWidget(self.progress_bar)

        self.export_status_label = QLabel("Ready to export.")
        self.export_status_label.setObjectName("HintLabel")
        self.export_status_label.setWordWrap(True)
        export_layout.addWidget(self.export_status_label)

        layout.addWidget(export_card)
        layout.addStretch(1)
        return page

    def _wrap_scroll(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _add_spin(self, form: QFormLayout, key: str, label: str, minimum: int, maximum: int, value: int, handler=None) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(int(minimum), int(maximum))
        widget.setValue(int(value))
        widget.valueChanged.connect(handler or self._sync_config_from_fields)
        self.field_widgets[key] = widget
        form.addRow(label, widget)
        return widget

    def _add_double_spin(
        self,
        form: QFormLayout,
        key: str,
        label: str,
        minimum: float,
        maximum: float,
        value: float,
        decimals: int = 2,
        step: float = 0.1,
        handler=None,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(float(minimum), float(maximum))
        widget.setDecimals(int(decimals))
        widget.setSingleStep(float(step))
        widget.setValue(float(value))
        widget.valueChanged.connect(handler or self._sync_config_from_fields)
        self.field_widgets[key] = widget
        form.addRow(label, widget)
        return widget

    def _add_combo(self, form: QFormLayout, key: str, label: str, items: list[str], value: str) -> QComboBox:
        widget = QComboBox()
        widget.addItems(items)
        widget.setCurrentText(str(value))
        widget.currentTextChanged.connect(self._sync_config_from_fields)
        self.field_widgets[key] = widget
        form.addRow(label, widget)
        return widget

    def _add_checkbox(self, form: QFormLayout, key: str, label: str, checked: bool) -> QCheckBox:
        widget = QCheckBox(label)
        widget.setChecked(bool(checked))
        widget.toggled.connect(self._sync_config_from_fields)
        self.field_widgets[key] = widget
        form.addRow("", widget)
        return widget

    def _load_config_into_fields(self, config: StimulusConfig) -> None:
        self._loading_values = True
        try:
            for key, widget in self.field_widgets.items():
                value = getattr(config, key)
                if isinstance(widget, QSpinBox):
                    widget.setValue(int(value))
                elif isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(value))
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(str(value))
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, ColorButton):
                    widget.set_color(str(value))
        finally:
            self._loading_values = False

    def _collect_config(self) -> StimulusConfig:
        config = self.config.copy()
        for key, widget in self.field_widgets.items():
            if isinstance(widget, QSpinBox):
                setattr(config, key, int(widget.value()))
            elif isinstance(widget, QDoubleSpinBox):
                setattr(config, key, float(widget.value()))
            elif isinstance(widget, QComboBox):
                setattr(config, key, str(widget.currentText()))
            elif isinstance(widget, QCheckBox):
                setattr(config, key, bool(widget.isChecked()))
            elif isinstance(widget, ColorButton):
                setattr(config, key, str(widget.color_hex))
        return config.validate()

    def _sync_config_from_fields(self) -> None:
        if self._loading_values:
            return
        self.config = self._collect_config()
        self._load_config_into_fields(self.config)
        self._last_resolution = self.config.resolution
        self._rebuild_preview_engine()

    def _on_resolution_changed(self) -> None:
        if self._loading_values:
            return

        width_widget = self.field_widgets["output_width"]
        height_widget = self.field_widgets["output_height"]
        new_width = int(width_widget.value())
        new_height = int(height_widget.value())
        old_width, old_height = self._last_resolution

        if old_width > 0 and old_height > 0:
            scale_x = new_width / float(old_width)
            scale_y = new_height / float(old_height)
            for field_name in (
                "center_attractor_x",
                "left_attractor_x",
                "right_attractor_x",
                "landmark_left_x",
                "landmark_right_x",
            ):
                widget = self.field_widgets[field_name]
                widget.blockSignals(True)
                widget.setValue(float(widget.value()) * scale_x)
                widget.blockSignals(False)

            for field_name in (
                "center_attractor_y",
                "left_attractor_y",
                "right_attractor_y",
                "landmark_left_y",
                "landmark_right_y",
            ):
                widget = self.field_widgets[field_name]
                widget.blockSignals(True)
                widget.setValue(float(widget.value()) * scale_y)
                widget.blockSignals(False)

        self._last_resolution = (new_width, new_height)
        self._sync_config_from_fields()

    def _reset_layout_defaults(self) -> None:
        fresh = self._collect_config()
        fresh.apply_layout_defaults(force=True)
        self.config = fresh.validate()
        self._load_config_into_fields(self.config)
        self._last_resolution = self.config.resolution
        self._rebuild_preview_engine()

    def _update_device_summary(self) -> None:
        profile = detect_device_profile()
        recommendation = recommend_export_settings(profile)
        screen = (
            f"{profile.screen_width}x{profile.screen_height}"
            if profile.screen_width and profile.screen_height
            else "unavailable"
        )
        self.device_summary_label.setText(
            "Detected screen: "
            f"{screen} | CPU cores: {profile.cpu_cores} | RAM: {profile.ram_gb:.1f} GB. "
            "Recommended export: "
            f"{recommendation['output_width']}x{recommendation['output_height']} at {recommendation['fps']} FPS "
            f"with {recommendation['number_of_agents']} agents."
        )

    def _auto_optimize(self) -> None:
        recommendation = recommend_export_settings(detect_device_profile())
        self.field_widgets["fps"].setValue(recommendation["fps"])
        self.field_widgets["number_of_agents"].setValue(recommendation["number_of_agents"])
        self.field_widgets["output_width"].setValue(recommendation["output_width"])
        self.field_widgets["output_height"].setValue(recommendation["output_height"])
        self._reset_layout_defaults()
        self.export_status_label.setText("Applied auto-optimized rendering defaults for this machine.")

    def _rebuild_preview_engine(self) -> None:
        self.preview_timer.stop()
        self.preview_engine = StimulusEngine(self.config)
        self.preview_timer.setInterval(max(1, int(round(1000 / self.config.fps))))
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        frame = self.preview_engine.current_frame()
        self.preview_canvas.set_frame(frame, self.config)
        self.phase_badge.setText(frame.phase.upper())
        self.metric_labels["frame"].setText(str(frame.frame_index))
        self.metric_labels["time"].setText(f"{frame.time_seconds:.2f} s")
        self.metric_labels["phase"].setText(frame.phase.title())
        self.metric_labels["avg_speed"].setText(f"{float(frame.metrics['avg_speed']):.1f} px/s")
        self.metric_labels["polarization"].setText(f"{float(frame.metrics['polarization']):.2f}")
        self.metric_labels["spread"].setText(f"{float(frame.metrics['spread']):.1f} px")
        self.metric_labels["groups"].setText(
            f"{frame.metrics['school_count']} / {frame.metrics['left_count']} / {frame.metrics['right_count']}"
        )

    def _start_preview(self) -> None:
        self.preview_timer.setInterval(max(1, int(round(1000 / self.config.fps))))
        self.preview_timer.start()

    def _pause_preview(self) -> None:
        self.preview_timer.stop()

    def _reset_preview(self) -> None:
        self._rebuild_preview_engine()

    def _advance_preview(self) -> None:
        if self.preview_engine.frame_index + 1 >= self.preview_engine.config.total_frames:
            self.preview_timer.stop()
            return
        self.preview_engine.step()
        self._refresh_preview()

    def _choose_output_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Output Video",
            self.output_path_edit.text(),
            "MP4 Video (*.mp4)",
        )
        if path:
            self.output_path_edit.setText(path)

    def _generate_video(self) -> None:
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "Missing Output Path", "Choose an output `.mp4` file before exporting.")
            return
        if not output_path.lower().endswith(".mp4"):
            output_path += ".mp4"
            self.output_path_edit.setText(output_path)

        self.preview_timer.stop()
        self.config = self._collect_config()
        self.generate_button.setEnabled(False)
        self.auto_optimize_button.setEnabled(False)
        self.export_status_label.setText("Rendering deterministic video offscreen...")
        self.progress_bar.setValue(0)

        self.export_worker = ExportWorker(self.config, output_path, self)
        self.export_worker.progress_changed.connect(self._on_export_progress)
        self.export_worker.export_finished.connect(self._on_export_finished)
        self.export_worker.export_failed.connect(self._on_export_failed)
        self.export_worker.start()

    def _on_export_progress(self, completed: int, total: int, eta_seconds: float, phase: str) -> None:
        progress = int(round((completed / max(total, 1)) * 100))
        self.progress_bar.setValue(progress)
        self.export_status_label.setText(
            f"Rendered {completed}/{total} frames | phase: {phase} | ETA: {eta_seconds:.1f} s"
        )

    def _on_export_finished(self, video_path: str, metadata_path: str) -> None:
        self.generate_button.setEnabled(True)
        self.auto_optimize_button.setEnabled(True)
        self.progress_bar.setValue(100)
        if metadata_path:
            self.export_status_label.setText(
                f"Saved video to {video_path}\nSaved metadata to {metadata_path}"
            )
        else:
            self.export_status_label.setText(f"Saved video to {video_path}")
        QMessageBox.information(self, "Export Complete", self.export_status_label.text())

    def _on_export_failed(self, message: str) -> None:
        self.generate_button.setEnabled(True)
        self.auto_optimize_button.setEnabled(True)
        self.export_status_label.setText(f"Export failed: {message}")
        QMessageBox.critical(self, "Export Failed", message)

    def _apply_base_style(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setFont(QFont("Avenir Next", 11))
        self.setStyleSheet(
            """
            QWidget#Root {
                background: #F3F7FB;
                color: #20303F;
            }
            QFrame#Card {
                background: rgba(255, 255, 255, 0.96);
                border: 1px solid rgba(202, 214, 226, 0.95);
                border-radius: 24px;
            }
            QLabel#TitleLabel {
                font-size: 28px;
                font-weight: 700;
                color: #142130;
            }
            QLabel#SubtitleLabel {
                color: #667789;
                font-size: 13px;
            }
            QLabel#SectionTitle {
                font-size: 15px;
                font-weight: 700;
                color: #1B2A39;
            }
            QLabel#BadgeLabel {
                background: rgba(38, 118, 255, 0.12);
                color: #2676FF;
                padding: 8px 14px;
                border-radius: 16px;
                font-weight: 700;
            }
            QLabel#MetricLabel, QLabel#HintLabel {
                color: #667789;
            }
            QLabel#MetricValue {
                color: #183041;
                font-weight: 700;
            }
            QTabWidget::pane {
                border: none;
            }
            QTabBar::tab {
                background: rgba(232, 239, 247, 0.96);
                border: none;
                border-radius: 14px;
                padding: 10px 14px;
                margin-right: 8px;
                font-weight: 600;
                color: #485D72;
            }
            QTabBar::tab:selected {
                background: #FFFFFF;
                color: #17324A;
            }
            QPushButton {
                background: #EAF1F8;
                border: none;
                border-radius: 16px;
                padding: 11px 16px;
                font-weight: 700;
                color: #294156;
            }
            QPushButton:hover {
                background: #E1EAF5;
            }
            QPushButton#PrimaryButton {
                background: #2676FF;
                color: white;
            }
            QPushButton#PrimaryButton:hover {
                background: #3A84FF;
            }
            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
                background: #F7FAFD;
                border: 1px solid #D4DEE9;
                border-radius: 14px;
                padding: 8px 12px;
                min-height: 22px;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QProgressBar {
                background: #E8EFF6;
                border: none;
                border-radius: 10px;
                text-align: center;
                min-height: 18px;
            }
            QProgressBar::chunk {
                background: #2676FF;
                border-radius: 10px;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            """
        )


def main() -> None:
    app = QApplication.instance() or QApplication([])
    window = FishStimulusWindow()
    window.show()
    app.exec_()
