from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QCheckBox,
    QSpinBox, QRadioButton, QButtonGroup, QDialogButtonBox,
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox,
)
from config import Config, save_config, default_log_dir
from logging_setup import configure_logging


def _dir_size_human(path: Path) -> str:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    for unit in ("KB", "MB", "GB"):
        total /= 1024
        if total < 1024:
            return f"{total:.1f} {unit}"
    return f"{total:.1f} GB"


class SettingsDialog(QDialog):
    def __init__(
        self,
        config: Config,
        config_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.config = Config(**config.__dict__)  # working copy
        self._config_path = config_path

        form = QFormLayout()

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

        self._preload_model = QCheckBox()
        self._preload_model.setChecked(config.preload_model)
        self._preload_model.setToolTip(
            "Load the DECIMER model in the background when the app opens,\n"
            "so the first identification is faster."
        )
        form.addRow("Preload model on startup:", self._preload_model)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self._build_openrouter_section())
        layout.addWidget(self._build_model_info())
        layout.addWidget(self._build_diagnostic_logging_section())
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _build_openrouter_section(self) -> QGroupBox:
        box = QGroupBox("OpenRouter")
        vbox = QVBoxLayout(box)
        vbox.setSpacing(6)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API Key:"))
        self._api_key_field = QLineEdit(self.config.openrouter_api_key)
        self._api_key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_field.setPlaceholderText("sk-or-…")
        key_row.addWidget(self._api_key_field)
        vbox.addLayout(key_row)

        note = QLabel("The OPENROUTER_API_KEY environment variable takes precedence if set.")
        note.setStyleSheet("color: #6c757d; font-size: 11px;")
        note.setWordWrap(True)
        vbox.addWidget(note)

        return box

    def _build_model_info(self) -> QGroupBox:
        from gui.model_manager import MODEL_URLS, _decimer_home
        box = QGroupBox("Model Files")
        vbox = QVBoxLayout(box)
        vbox.setSpacing(6)

        home = _decimer_home()
        path_str = str(home) if home else "pystow not installed"

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Location:"))
        path_edit = QLineEdit(path_str)
        path_edit.setReadOnly(True)
        path_edit.setToolTip("Directory where DECIMER model files are stored")
        path_row.addWidget(path_edit)
        open_btn = QPushButton("Show in Finder")
        open_btn.setEnabled(home is not None and home.exists())
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path_str)))
        path_row.addWidget(open_btn)
        vbox.addLayout(path_row)

        model_form = QFormLayout()
        model_form.setContentsMargins(0, 4, 0, 0)
        for name in MODEL_URLS:
            if home is not None:
                model_dir = home / f"{name}_model"
                present = (model_dir / "saved_model.pb").exists()
                if present:
                    size_str = _dir_size_human(model_dir)
                    status_text = f"✓  Downloaded  ({size_str})"
                    status_color = "#155724"
                else:
                    status_text = "✗  Not downloaded"
                    status_color = "#721c24"
            else:
                status_text = "—  Unknown (pystow missing)"
                status_color = "#6c757d"

            label = QLabel(status_text)
            label.setStyleSheet(f"color: {status_color}; font-weight: bold;")
            model_form.addRow(f"{name}:", label)

        vbox.addLayout(model_form)
        return box

    def _build_diagnostic_logging_section(self) -> QGroupBox:
        box = QGroupBox("Diagnostic Logging")
        vbox = QVBoxLayout(box)
        vbox.setSpacing(6)

        self._diag_checkbox = QCheckBox("Write diagnostic log files (for troubleshooting)")
        self._diag_checkbox.setChecked(self.config.diagnostic_logging_enabled)
        vbox.addWidget(self._diag_checkbox)

        path_row = QHBoxLayout()
        self._diag_path_field = QLineEdit(self.config.diagnostic_log_dir)
        path_row.addWidget(self._diag_path_field)
        self._diag_browse_btn = QPushButton("Browse…")
        self._diag_browse_btn.clicked.connect(self._browse_diagnostic_log_dir)
        path_row.addWidget(self._diag_browse_btn)
        self._diag_open_btn = QPushButton("Open Log Folder")
        self._diag_open_btn.clicked.connect(self._open_diagnostic_log_dir)
        path_row.addWidget(self._diag_open_btn)
        vbox.addLayout(path_row)

        self._diag_checkbox.toggled.connect(self._update_diagnostic_controls_enabled)
        self._update_diagnostic_controls_enabled(self._diag_checkbox.isChecked())

        return box

    def _update_diagnostic_controls_enabled(self, checked: bool) -> None:
        self._diag_path_field.setEnabled(checked)
        self._diag_browse_btn.setEnabled(checked)
        self._diag_open_btn.setEnabled(checked and Path(self._diag_path_field.text()).exists())

    def _browse_diagnostic_log_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Choose Diagnostic Log Folder", self._diag_path_field.text()
        )
        if directory:
            self._diag_path_field.setText(directory)
            self._update_diagnostic_controls_enabled(self._diag_checkbox.isChecked())

    def _open_diagnostic_log_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._diag_path_field.text()))

    def _save(self) -> None:
        self.config.openrouter_api_key = self._api_key_field.text().strip()
        self.config.thumbnail_max_size = self._thumb_size.value()
        self.config.recognition_max_size = self._recog_size.value()
        self.config.output_mode = "in_place" if self._in_place_radio.isChecked() else "new_file"
        self.config.page_size = self._page_size.value()
        self.config.preload_model = self._preload_model.isChecked()
        self.config.diagnostic_logging_enabled = self._diag_checkbox.isChecked()
        self.config.diagnostic_log_dir = self._diag_path_field.text().strip() or default_log_dir()
        save_config(self.config, self._config_path)
        status = configure_logging(self.config)
        if status.error:
            QMessageBox.warning(
                self, "Diagnostic Logging",
                f"Could not enable diagnostic logging: {status.error}",
            )
        self.accept()
