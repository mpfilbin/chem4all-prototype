from __future__ import annotations
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QCheckBox, QDoubleSpinBox,
    QSpinBox, QRadioButton, QButtonGroup, QDialogButtonBox,
    QWidget, QHBoxLayout, QVBoxLayout,
)
from config import Config, save_config


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.config = Config(**config.__dict__)  # working copy

        form = QFormLayout()

        self._auto_filter = QCheckBox()
        self._auto_filter.setChecked(config.auto_filter)
        form.addRow("Auto-filter mode:", self._auto_filter)

        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(0.0, 1.0)
        self._threshold.setSingleStep(0.05)
        self._threshold.setValue(config.confidence_threshold)
        self._threshold.setEnabled(config.auto_filter)
        self._auto_filter.toggled.connect(self._threshold.setEnabled)
        form.addRow("Confidence threshold:", self._threshold)

        self._thumb_size = QSpinBox()
        self._thumb_size.setRange(64, 1024)
        self._thumb_size.setValue(config.thumbnail_max_size)
        form.addRow("Thumbnail max size (px):", self._thumb_size)

        self._recog_size = QSpinBox()
        self._recog_size.setRange(256, 4096)
        self._recog_size.setValue(config.recognition_max_size)
        form.addRow("Recognition max size (px):", self._recog_size)

        self._new_file_radio = QRadioButton("New file")
        self._in_place_radio = QRadioButton("In-place (overwrite original)")
        output_group = QButtonGroup(self)
        output_group.addButton(self._new_file_radio)
        output_group.addButton(self._in_place_radio)
        if config.output_mode == "in_place":
            self._in_place_radio.setChecked(True)
        else:
            self._new_file_radio.setChecked(True)
        output_row = QHBoxLayout()
        output_row.addWidget(self._new_file_radio)
        output_row.addWidget(self._in_place_radio)
        output_widget = QWidget()
        output_widget.setLayout(output_row)
        form.addRow("Output mode:", output_widget)

        self._page_size = QSpinBox()
        self._page_size.setRange(5, 10)
        self._page_size.setValue(config.page_size)
        form.addRow("Review page size:", self._page_size)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _save(self) -> None:
        self.config.auto_filter = self._auto_filter.isChecked()
        self.config.confidence_threshold = self._threshold.value()
        self.config.thumbnail_max_size = self._thumb_size.value()
        self.config.recognition_max_size = self._recog_size.value()
        self.config.output_mode = "in_place" if self._in_place_radio.isChecked() else "new_file"
        self.config.page_size = self._page_size.value()
        save_config(self.config)
        self.accept()
