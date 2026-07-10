from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QCheckBox, QFrame, QSizePolicy,
)
from config import Config
from models.image_record import ImageRecord
from gui.widgets import ThumbnailLabel


class SelectionWindow(QWidget):
    def __init__(self, records: list[ImageRecord], config: Config, source_path: Path) -> None:
        super().__init__()
        self._records = records
        self._config = config
        self._source_path = source_path
        self._rows: list[_SelectionRow] = []

        self.setWindowTitle(f"Select Images — {source_path.name}")
        self.setMinimumWidth(520)
        self.setMinimumHeight(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        header = QLabel(
            f"<b>{len(records)} image(s) found.</b> "
            "Select which to send for chemical structure identification."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        self._error_banner = QLabel()
        self._error_banner.setWordWrap(True)
        self._error_banner.setStyleSheet(
            "QLabel { background: #f8d7da; color: #721c24; "
            "padding: 6px 10px; border-radius: 4px; }"
        )
        self._error_banner.setVisible(False)
        layout.addWidget(self._error_banner)

        sel_row = QHBoxLayout()
        all_btn = QPushButton("Select All")
        none_btn = QPushButton("Select None")
        all_btn.clicked.connect(lambda: self._set_all(True))
        none_btn.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(all_btn)
        sel_row.addWidget(none_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(4)

        for record in records:
            row = _SelectionRow(record)
            row.connect_changed(self._update_identify_btn)
            self._rows.append(row)
            container_layout.addWidget(row)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        footer = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        self._identify_btn = QPushButton()
        self._identify_btn.clicked.connect(self._start_identification)
        footer.addWidget(cancel_btn)
        footer.addStretch()
        footer.addWidget(self._identify_btn)
        layout.addLayout(footer)

        self._update_identify_btn()

    def _set_all(self, checked: bool) -> None:
        for row in self._rows:
            row.checkbox.setChecked(checked)

    def _update_identify_btn(self) -> None:
        n = sum(1 for row in self._rows if row.checkbox.isChecked())
        has_invalid_row = any(
            row.checkbox.isChecked() and not row.prediction_types
            for row in self._rows
        )
        if has_invalid_row:
            self._error_banner.setText(
                "Each selected image needs at least one prediction type checked."
            )
            self._error_banner.setVisible(True)
            self._identify_btn.setEnabled(False)
        else:
            self._error_banner.setVisible(False)
            self._identify_btn.setEnabled(n > 0)
        self._identify_btn.setText(f"Identify Selected ({n})  →")

    def _start_identification(self) -> None:
        from gui.review_window import ReviewWindow
        from gui.worker import RecognizerWorker

        selected = []
        for row in self._rows:
            if row.checkbox.isChecked():
                row.record.prediction_types = row.prediction_types
                selected.append(row.record)

        self._review_window = ReviewWindow(selected, self._config, self._source_path)
        self._worker = RecognizerWorker(selected, self._config)
        self._worker.record_ready.connect(self._review_window.on_record_ready)
        self._worker.status.connect(self._review_window.on_recognition_status)
        self._worker.finished.connect(self._review_window.on_recognition_finished)
        self._worker.error.connect(self._review_window.on_recognition_error)
        self._worker.start()

        self.hide()
        self._review_window.show()
        self._review_window.raise_()
        self._review_window.activateWindow()


class _SelectionRow(QFrame):
    def __init__(self, record: ImageRecord) -> None:
        super().__init__()
        self.record = record
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.setToolTip("Include in identification")
        layout.addWidget(self.checkbox)

        thumb = ThumbnailLabel(record, size=64)
        thumb.setFixedSize(72, 72)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(thumb)

        ref = QLabel(record.source_ref)
        ref.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(ref)

        self._decorative_check = QCheckBox("Decorative")
        layout.addWidget(self._decorative_check)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider)
        layout.addSpacing(8)

        self._smiles_check = QCheckBox("SMILES")
        self._iupac_check = QCheckBox("IUPAC Name")
        self._trivial_check = QCheckBox("Common Name")
        self._describe_check = QCheckBox("Describe Image")
        self._smiles_check.setChecked(True)
        self._other_checks = [
            self._smiles_check, self._iupac_check, self._trivial_check, self._describe_check,
        ]
        for box in self._other_checks:
            layout.addWidget(box)

        self._saved_other_states = [box.isChecked() for box in self._other_checks]
        self._decorative_check.stateChanged.connect(self._on_decorative_toggled)

    def _on_decorative_toggled(self) -> None:
        if self._decorative_check.isChecked():
            self._saved_other_states = [box.isChecked() for box in self._other_checks]
            for box in self._other_checks:
                box.setChecked(False)
                box.setEnabled(False)
        else:
            for box, was_checked in zip(self._other_checks, self._saved_other_states):
                box.setEnabled(True)
                box.setChecked(was_checked)

    @property
    def prediction_types(self) -> list[str]:
        if self._decorative_check.isChecked():
            return ["decorative"]
        types = []
        if self._smiles_check.isChecked():
            types.append("smiles")
        if self._iupac_check.isChecked():
            types.append("iupac")
        if self._trivial_check.isChecked():
            types.append("trivial")
        if self._describe_check.isChecked():
            types.append("description")
        return types

    def connect_changed(self, slot) -> None:
        self.checkbox.stateChanged.connect(slot)
        self._decorative_check.stateChanged.connect(slot)
        self._smiles_check.stateChanged.connect(slot)
        self._iupac_check.stateChanged.connect(slot)
        self._trivial_check.stateChanged.connect(slot)
        self._describe_check.stateChanged.connect(slot)
