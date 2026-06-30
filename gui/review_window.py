from __future__ import annotations
import math
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QCheckBox,
    QMessageBox, QDialog,
)
from config import Config
from models.image_record import ImageRecord
from pipeline.writer import write


class _ThumbnailLabel(QLabel):
    def __init__(self, record: ImageRecord, parent=None):
        super().__init__(parent)
        self._record = record
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh()

    def _refresh(self):
        if self._record.thumbnail_bytes:
            pix = QPixmap()
            pix.loadFromData(self._record.thumbnail_bytes)
            self.setPixmap(pix.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.setText("(loading…)")

    def mousePressEvent(self, _event):
        if not self._record.thumbnail_bytes:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(self._record.source_ref)
        layout = QVBoxLayout()
        pix = QPixmap()
        pix.loadFromData(self._record.thumbnail_bytes)
        lbl = QLabel()
        lbl.setPixmap(pix)
        layout.addWidget(lbl)
        dlg.setLayout(layout)
        dlg.exec()

    def update_record(self, record: ImageRecord):
        self._record = record
        self._refresh()


class _RecordRow(QWidget):
    def __init__(self, record: ImageRecord, parent=None):
        super().__init__(parent)
        self._record = record
        layout = QHBoxLayout()

        self._thumb = _ThumbnailLabel(record)
        layout.addWidget(self._thumb)

        info = QVBoxLayout()
        info.addWidget(QLabel(record.source_ref))

        self._smiles_field = QLineEdit(record.predicted_smiles or "")
        self._smiles_field.setReadOnly(True)
        self._smiles_field.setPlaceholderText("Awaiting recognition…")
        info.addWidget(QLabel("Predicted SMILES:"))
        info.addWidget(self._smiles_field)

        self._override_field = QLineEdit()
        self._override_field.setPlaceholderText("Override (leave blank to use prediction)")
        info.addWidget(QLabel("Override:"))
        info.addWidget(self._override_field)

        self._not_chemical = QCheckBox("Not a chemical structure")
        self._not_chemical.toggled.connect(self._on_not_chemical_toggled)
        info.addWidget(self._not_chemical)

        layout.addLayout(info)
        self.setLayout(layout)

    def _on_not_chemical_toggled(self, checked: bool):
        self._override_field.setEnabled(not checked)

    def update_record(self, record: ImageRecord):
        self._record = record
        self._thumb.update_record(record)
        self._smiles_field.setText(record.predicted_smiles or "")

    def apply_to_record(self):
        if self._not_chemical.isChecked():
            self._record.is_chemical = False
            self._record.approved_value = None
        else:
            override = self._override_field.text().strip()
            self._record.approved_value = override if override else self._record.predicted_smiles
            if self._record.approved_value:
                self._record.is_chemical = True
            else:
                self._record.is_chemical = None


class ReviewWindow(QWidget):
    def __init__(self, records: list[ImageRecord], config: Config, source_path: Path) -> None:
        super().__init__()
        self._records = records
        self._config = config
        self._source_path = source_path
        self._page = 0
        self._rows: list[_RecordRow] = []

        self.setWindowTitle(f"Review — {source_path.name}")
        self._layout = QVBoxLayout()

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
            QMessageBox.information(self, "Done", f"Accessible file written to:\n{out}")
            self.close()
        except Exception as exc:
            QMessageBox.critical(self, "Write Error", str(exc))

    def on_record_ready(self, record: ImageRecord):
        for row in self._rows:
            if row._record.id == record.id:
                row.update_record(record)
                break
