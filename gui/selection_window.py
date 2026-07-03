from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QCheckBox, QFrame, QSizePolicy,
    QRadioButton, QButtonGroup,
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
            row.checkbox.stateChanged.connect(self._update_identify_btn)
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
        self._identify_btn.setText(f"Identify Selected ({n})  →")
        self._identify_btn.setEnabled(n > 0)

    def _start_identification(self) -> None:
        from gui.review_window import ReviewWindow
        from gui.worker import RecognizerWorker

        selected = []
        for row in self._rows:
            if row.checkbox.isChecked():
                row.record.prediction_type = row.prediction_type
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

        thumb = ThumbnailLabel(record, size=64)
        thumb.setFixedSize(72, 72)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(thumb)

        ref = QLabel(record.source_ref)
        ref.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(ref)

        self._smiles_radio = QRadioButton("SMILES")
        self._iupac_radio = QRadioButton("IUPAC Name")
        self._trivial_radio = QRadioButton("Common Name")
        self._type_group = QButtonGroup(self)
        for btn in (self._smiles_radio, self._iupac_radio, self._trivial_radio):
            self._type_group.addButton(btn)
            layout.addWidget(btn)
        self._smiles_radio.setChecked(True)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.setToolTip("Include in identification")
        layout.addWidget(self.checkbox)

    @property
    def prediction_type(self) -> str:
        if self._iupac_radio.isChecked():
            return "iupac"
        if self._trivial_radio.isChecked():
            return "trivial"
        return "smiles"
