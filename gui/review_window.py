from __future__ import annotations
import math
from pathlib import Path
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit,
    QMessageBox,
)
from config import Config
from models.image_record import ImageRecord
from pipeline.writer import write
from gui.widgets import ThumbnailLabel

_TYPE_LABELS = {
    "iupac": "IUPAC Name:",
    "trivial": "Common Name:",
}


class _RecordRow(QWidget):
    def __init__(self, record: ImageRecord, parent=None):
        super().__init__(parent)
        self._record = record

        layout = QHBoxLayout()

        self._thumb = ThumbnailLabel(record)
        layout.addWidget(self._thumb)

        info = QVBoxLayout()
        info.addWidget(QLabel(record.source_ref))

        info.addWidget(QLabel(_TYPE_LABELS.get(record.prediction_type, "Predicted SMILES:")))
        self._result_field = QTextEdit(record.result_value() or "")
        self._result_field.setReadOnly(True)
        self._result_field.setPlaceholderText("Awaiting result…")
        self._result_field.setFixedHeight(64)
        self._result_field.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        info.addWidget(self._result_field)

        info.addWidget(QLabel("Custom override:"))
        self._override_field = QLineEdit()
        self._override_field.setPlaceholderText("Leave blank to use the predicted value")
        info.addWidget(self._override_field)

        layout.addLayout(info)
        self.setLayout(layout)

    def update_record(self, record: ImageRecord) -> None:
        self._record = record
        self._thumb.update_record(record)
        self._result_field.setPlainText(record.result_value() or "")

    def apply_to_record(self) -> None:
        override = self._override_field.text().strip()
        self._record.approved_value = override if override else self._record.result_value()
        self._record.is_chemical = bool(self._record.approved_value)


class ReviewWindow(QWidget):
    def __init__(self, records: list[ImageRecord], config: Config, source_path: Path) -> None:
        super().__init__()
        self._records = records
        self._config = config
        self._source_path = source_path
        self._page = 0
        self._rows: list[_RecordRow] = []
        self._recognized = 0
        self._error_count = 0

        self.setWindowTitle(f"Review — {source_path.name}")
        self.setMinimumWidth(700)
        self._layout = QVBoxLayout()

        self._status_bar = QLabel(f"Identifying images…  (0 of {len(records)} done)")
        self._status_bar.setStyleSheet(
            "QLabel { background: #cce5ff; color: #004085; "
            "padding: 6px 10px; border-radius: 4px; }"
        )
        self._status_bar.setWordWrap(True)
        self._layout.addWidget(self._status_bar)

        self._grid = QVBoxLayout()
        self._layout.addLayout(self._grid)

        nav = QHBoxLayout()
        self._prev_btn = QPushButton("← Previous")
        self._prev_btn.clicked.connect(self._prev_page)
        self._page_label = QLabel()
        self._next_btn = QPushButton("Next →")
        self._next_btn.clicked.connect(self._next_page)
        nav.addWidget(self._prev_btn)
        nav.addWidget(self._page_label, alignment=Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self._next_btn)
        self._layout.addLayout(nav)

        bottom = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        self._accept_btn = QPushButton("Accept")
        self._accept_btn.clicked.connect(self._accept)
        bottom.addWidget(cancel_btn)
        bottom.addWidget(self._accept_btn)
        self._layout.addLayout(bottom)

        self.setLayout(self._layout)
        self._render_page()

    def _page_size(self) -> int:
        return self._config.page_size

    def _total_pages(self) -> int:
        return max(1, math.ceil(len(self._records) / self._page_size()))

    def _page_records(self) -> list[ImageRecord]:
        start = self._page * self._page_size()
        return self._records[start: start + self._page_size()]

    def _render_page(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows = []
        for record in self._page_records():
            row = _RecordRow(record)
            self._rows.append(row)
            self._grid.addWidget(row)
        self._page_label.setText(f"Page {self._page + 1} of {self._total_pages()}")
        self._prev_btn.setEnabled(self._page > 0)
        is_last = self._page >= self._total_pages() - 1
        self._next_btn.setEnabled(not is_last)
        self._accept_btn.setText("Accept & Finish" if is_last else "Accept & Next →")

    def _prev_page(self):
        self._apply_current_page()
        self._page -= 1
        self._render_page()

    def _next_page(self):
        self._apply_current_page()
        self._page += 1
        self._render_page()

    def _apply_current_page(self):
        for row in self._rows:
            row.apply_to_record()

    def _accept(self):
        self._apply_current_page()
        is_last = self._page >= self._total_pages() - 1
        if not is_last:
            self._page += 1
            self._render_page()
            return
        try:
            out = write(self._records, self._source_path, self._config)
            msg = QMessageBox(self)
            msg.setWindowTitle("Done")
            msg.setText(f"Accessible file written to:\n{out}")
            msg.setIcon(QMessageBox.Icon.Information)
            open_btn = msg.addButton("Open File", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() is open_btn:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))
            self.close()
        except Exception as exc:
            QMessageBox.critical(self, "Write Error", str(exc))

    def on_record_ready(self, record: ImageRecord) -> None:
        self._recognized += 1
        for row in self._rows:
            if row._record.id == record.id:
                row.update_record(record)
                break

    def on_recognition_status(self, msg: str) -> None:
        self._status_bar.setText(msg)

    def on_recognition_finished(self) -> None:
        total = len(self._records)
        if self._error_count:
            self._status_bar.setStyleSheet(
                "QLabel { background: #fff3cd; color: #856404; "
                "padding: 6px 10px; border-radius: 4px; }"
            )
            self._status_bar.setText(
                f"Identification complete — {total - self._error_count} of {total} succeeded. "
                f"{self._error_count} image(s) could not be identified. Review results below."
            )
        else:
            self._status_bar.setStyleSheet(
                "QLabel { background: #d4edda; color: #155724; "
                "padding: 6px 10px; border-radius: 4px; }"
            )
            self._status_bar.setText(
                f"Identification complete — {total} image(s) processed. Review results below."
            )

    def on_recognition_error(self, msg: str) -> None:
        self._error_count += 1
        self._status_bar.setStyleSheet(
            "QLabel { background: #fff3cd; color: #856404; "
            "padding: 6px 10px; border-radius: 4px; }"
        )
        self._status_bar.setText(f"Warning: {msg}")
