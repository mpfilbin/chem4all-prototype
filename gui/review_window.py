from __future__ import annotations
import math
from pathlib import Path
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit,
    QMessageBox, QScrollArea,
)
from config import Config
from models.image_record import ImageRecord
from pipeline.writer import write
from gui.widgets import ThumbnailLabel, HoverHighlightMixin


class _RecordRow(HoverHighlightMixin, QWidget):
    def __init__(self, record: ImageRecord, done: bool, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._record = record
        self._done = done
        self._edited = False

        layout = QHBoxLayout()

        self._thumb = ThumbnailLabel(record)
        layout.addWidget(self._thumb)

        info = QVBoxLayout()
        info.addWidget(QLabel(record.source_ref))

        info.addWidget(QLabel("Prediction Results:"))
        self._value_field = QTextEdit()
        self._value_field.setPlaceholderText("Awaiting result…")
        self._value_field.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        metrics = self._value_field.fontMetrics()
        frame = self._value_field.frameWidth() * 2
        self._value_field.setFixedHeight(metrics.lineSpacing() * 4 + frame + 12)

        if done:
            composed = "\n\n".join(record.result_lines())
            initial_text = record.approved_value if record.approved_value is not None else composed
            self._value_field.setPlainText(initial_text)
            self._edited = initial_text != composed
        else:
            self._value_field.setReadOnly(True)

        self._value_field.textChanged.connect(self._on_text_changed)
        info.addWidget(self._value_field)

        self._restore_btn = QPushButton("↺ Restore predicted value")
        self._restore_btn.clicked.connect(self._restore_predicted)
        info.addWidget(self._restore_btn)
        self._update_restore_visibility()

        layout.addLayout(info)
        self.setLayout(layout)

    def _set_field_text(self, text: str) -> None:
        self._value_field.blockSignals(True)
        self._value_field.setPlainText(text)
        self._value_field.blockSignals(False)
        self._update_restore_visibility()

    def _on_text_changed(self) -> None:
        self._edited = True
        self._update_restore_visibility()

    def _update_restore_visibility(self) -> None:
        if not self._done:
            self._restore_btn.setVisible(False)
            return
        predicted = "\n\n".join(self._record.result_lines())
        self._restore_btn.setVisible(self._value_field.toPlainText().strip() != predicted)

    def _restore_predicted(self) -> None:
        self._set_field_text("\n\n".join(self._record.result_lines()))
        self._edited = False

    def update_record(self, record: ImageRecord) -> None:
        self._record = record
        self._thumb.update_record(record)
        was_done = self._done
        self._done = True
        if not was_done:
            self._value_field.setReadOnly(False)
        if not self._edited:
            self._set_field_text("\n\n".join(record.result_lines()))

    def apply_to_record(self) -> None:
        value = self._value_field.toPlainText().strip()
        self._record.approved_value = value
        self._record.is_chemical = True


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
        self._recognition_done = False
        self._done_ids: set[str] = set()

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

        self._hint_banner = QLabel(
            "Predicted values are editable — edit a field to override the "
            "prediction in the exported file. Clearing a field writes empty "
            "alt text for that image; use Restore to undo."
        )
        self._hint_banner.setWordWrap(True)
        self._hint_banner.setStyleSheet(
            "QLabel { background: #f0f0f0; color: #444; "
            "padding: 6px 10px; border-radius: 4px; }"
        )
        self._layout.addWidget(self._hint_banner)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._grid_widget = QWidget()
        self._grid = QVBoxLayout(self._grid_widget)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll_area.setWidget(self._grid_widget)
        self._layout.addWidget(self._scroll_area)

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
        self._set_navigation_enabled(False)

    def _page_size(self) -> int:
        return self._config.page_size

    def _total_pages(self) -> int:
        return max(1, math.ceil(len(self._records) / self._page_size()))

    def _set_navigation_enabled(self, enabled: bool) -> None:
        self._accept_btn.setEnabled(enabled)
        self._prev_btn.setEnabled(enabled and self._page > 0)
        is_last = self._page >= self._total_pages() - 1
        self._next_btn.setEnabled(enabled and not is_last)

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
            row = _RecordRow(record, done=record.id in self._done_ids)
            self._rows.append(row)
            self._grid.addWidget(row)
        self._page_label.setText(f"Page {self._page + 1} of {self._total_pages()}")
        self._prev_btn.setEnabled(self._recognition_done and self._page > 0)
        is_last = self._page >= self._total_pages() - 1
        self._next_btn.setEnabled(self._recognition_done and not is_last)
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
        self._done_ids.add(record.id)
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
        self._recognition_done = True
        self._set_navigation_enabled(True)

    def on_recognition_error(self, msg: str) -> None:
        self._error_count += 1
        self._status_bar.setStyleSheet(
            "QLabel { background: #fff3cd; color: #856404; "
            "padding: 6px 10px; border-radius: 4px; }"
        )
        self._status_bar.setText(f"Warning: {msg}")
