from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QMessageBox, QFrame, QProgressBar,
)
from PyQt6.QtCore import Qt
from config import Config


class FilePickerWindow(QWidget):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self.setWindowTitle("chem4all")
        self.setMinimumWidth(440)

        layout = QVBoxLayout()
        layout.setSpacing(12)

        self._model_banner = self._build_model_banner()
        layout.addWidget(self._model_banner)

        self._model_load_label = QLabel()
        self._model_load_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._model_load_label.setStyleSheet("QLabel { color: #6c757d; font-size: 11px; }")
        self._model_load_label.hide()
        layout.addWidget(self._model_load_label)

        layout.addWidget(QLabel("Open a PPTX or DOCX file to begin."))

        btn_row = QHBoxLayout()
        self._open_btn = QPushButton("Open File…")
        self._open_btn.clicked.connect(self._open_file)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._open_settings)
        btn_row.addWidget(self._open_btn)
        btn_row.addWidget(settings_btn)
        layout.addLayout(btn_row)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("QLabel { color: #555; padding: 2px 0; }")
        self._status_label.setWordWrap(True)
        self._status_label.hide()
        layout.addWidget(self._status_label)

        self._extract_progress_bar = QProgressBar()
        self._extract_progress_bar.setRange(0, 0)
        self._extract_progress_bar.setTextVisible(False)
        self._extract_progress_bar.hide()
        layout.addWidget(self._extract_progress_bar)

        self._extract_count_label = QLabel()
        self._extract_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._extract_count_label.setStyleSheet("QLabel { color: #555; }")
        self._extract_count_label.hide()
        layout.addWidget(self._extract_count_label)

        self.setLayout(layout)

        from gui.model_manager import is_model_ready
        if is_model_ready():
            self._model_banner.hide()

    def set_model_load_time(self, elapsed: float) -> None:
        self._model_load_label.setText(f"DECIMER model loaded in {elapsed:.1f} s")
        self._model_load_label.show()

    def _build_model_banner(self) -> QFrame:
        banner = QFrame()
        banner.setFrameShape(QFrame.Shape.StyledPanel)
        banner.setStyleSheet(
            "QFrame { background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; }"
        )

        vbox = QVBoxLayout(banner)
        vbox.setContentsMargins(12, 10, 12, 10)
        vbox.setSpacing(6)

        self._model_status_label = QLabel(
            "⚠  DECIMER model not downloaded. "
            "Chemical structure recognition will not work until the model is installed. "
            "Click the button below to download it."
        )
        self._model_status_label.setWordWrap(True)
        self._model_status_label.setStyleSheet("QLabel { color: #664d03; }")
        vbox.addWidget(self._model_status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.hide()
        vbox.addWidget(self._progress_bar)

        self._bytes_label = QLabel()
        self._bytes_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._bytes_label.setStyleSheet("QLabel { color: #664d03; }")
        self._bytes_label.hide()
        vbox.addWidget(self._bytes_label)

        self._download_btn = QPushButton("Download Model  (~600 MB)")
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_btn.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffce3a, stop:1 #ffc107);"
            "  color: #212529; border: 1px solid #d39e00; border-bottom: 2px solid #b38600;"
            "  border-radius: 6px; padding: 8px 16px; font-weight: 600;"
            "}"
            "QPushButton:hover {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffd65c, stop:1 #ffcd39);"
            "}"
            "QPushButton:pressed {"
            "  background: #e0a800; border: 1px solid #b38600; border-bottom: 1px solid #b38600;"
            "  padding-top: 9px; padding-bottom: 7px;"
            "}"
            "QPushButton:disabled { background: #ffe69c; color: #8a6d1f; border: 1px solid #ffe69c; }"
        )
        self._download_btn.clicked.connect(self._start_download)
        vbox.addWidget(self._download_btn)

        return banner

    def _start_download(self) -> None:
        from gui.model_manager import ModelDownloadWorker
        self._download_btn.setEnabled(False)
        self._download_btn.setText("Downloading…")
        self._progress_bar.show()
        self._bytes_label.show()
        self._open_btn.setEnabled(False)

        self._download_worker = ModelDownloadWorker()
        self._download_worker.status.connect(self._model_status_label.setText)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    def _on_download_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(int(done * 100 / total))
            done_mb = done / 1_048_576
            total_mb = total / 1_048_576
            self._bytes_label.setText(f"{done_mb:.1f} / {total_mb:.1f} MB")
        else:
            self._progress_bar.setRange(0, 0)
            self._bytes_label.clear()

    def _on_download_finished(self) -> None:
        self._model_banner.hide()
        self._open_btn.setEnabled(True)

    def _on_download_error(self, msg: str) -> None:
        self._model_status_label.setText(f"⚠  Download failed: {msg}")
        self._progress_bar.hide()
        self._bytes_label.hide()
        self._download_btn.setText("Retry Download")
        self._download_btn.setEnabled(True)
        self._open_btn.setEnabled(True)

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Document", "",
            "Chemistry Documents (*.pptx *.docx);;All Files (*)",
        )
        if path:
            self._start_extraction(Path(path))

    def _open_settings(self) -> None:
        from gui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self._config, self)
        if dlg.exec():
            self._config = dlg.config

    def _start_extraction(self, file_path: Path) -> None:
        from gui.extractor_worker import ExtractorWorker

        self._open_btn.setEnabled(False)
        self._status_label.setText(f"Extracting images from {file_path.name}…")
        self._status_label.show()
        self._extract_progress_bar.setRange(0, 0)
        self._extract_progress_bar.show()
        self._extract_count_label.setText("Counting images…")
        self._extract_count_label.show()

        self._extractor = ExtractorWorker(file_path, self._config)
        self._extractor.finished.connect(
            lambda records: self._on_extraction_done(records, file_path)
        )
        self._extractor.progress.connect(self._on_extraction_progress)
        self._extractor.error.connect(self._on_extraction_error)
        self._extractor.start()

    def _on_extraction_progress(self, extracted: int, total: int) -> None:
        self._extract_progress_bar.setRange(0, total)
        self._extract_progress_bar.setValue(extracted)
        self._extract_count_label.setText(f"{extracted} of {total} images extracted")

    def _on_extraction_done(self, records: list, file_path: Path) -> None:
        self._open_btn.setEnabled(True)
        self._status_label.hide()
        self._extract_progress_bar.hide()
        self._extract_count_label.hide()

        if not records:
            QMessageBox.information(
                self, "No Images Found",
                f"No images were found in {file_path.name}."
            )
            return

        from gui.selection_window import SelectionWindow
        self._selection_window = SelectionWindow(records, self._config, file_path)
        self._selection_window.show()
        self._selection_window.raise_()
        self._selection_window.activateWindow()

    def _on_extraction_error(self, msg: str) -> None:
        self._open_btn.setEnabled(True)
        self._status_label.hide()
        self._extract_progress_bar.hide()
        self._extract_count_label.hide()
        QMessageBox.critical(self, "Extraction Error", msg)
