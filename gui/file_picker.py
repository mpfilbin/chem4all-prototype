from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QMessageBox,
)
from config import Config


class FilePickerWindow(QWidget):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self.setWindowTitle("chem4all")
        self.setMinimumWidth(400)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Open a PPTX or DOCX file to begin."))

        btn_row = QHBoxLayout()
        open_btn = QPushButton("Open File…")
        open_btn.clicked.connect(self._open_file)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._open_settings)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(settings_btn)
        layout.addLayout(btn_row)
        self.setLayout(layout)

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Document", "",
            "Chemistry Documents (*.pptx *.docx);;All Files (*)",
        )
        if path:
            self._start_pipeline(Path(path))

    def _open_settings(self) -> None:
        from gui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self._config, self)
        if dlg.exec():
            self._config = dlg.config

    def _start_pipeline(self, file_path: Path) -> None:
        from gui.review_window import ReviewWindow
        from gui.worker import RecognizerWorker
        from pipeline.extractor import extract

        try:
            records = extract(file_path, self._config)
        except Exception as exc:
            QMessageBox.critical(self, "Extraction Error", str(exc))
            return

        self._review_window = ReviewWindow(records, self._config, file_path)
        self._worker = RecognizerWorker(records, self._config)
        self._worker.record_ready.connect(self._review_window.on_record_ready)
        self._worker.error.connect(lambda msg: QMessageBox.warning(self, "Recognition Error", msg))
        self._worker.start()
        self.hide()
        self._review_window.show()
