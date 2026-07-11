from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QCheckBox, QFrame, QSizePolicy, QStyle,
)
from config import Config
from models.image_record import ImageRecord
from gui.widgets import ThumbnailLabel, HoverHighlightMixin


class SelectionWindow(QWidget):
    def __init__(self, records: list[ImageRecord], config: Config, source_path: Path) -> None:
        super().__init__()
        self._records = records
        self._config = config
        self._source_path = source_path
        self._rows: list[_SelectionRow] = []

        self.setWindowTitle(f"Select Images — {source_path.name}")
        # Must exceed _SelectionRow.minimumSizeHint().width() (~902px, driven by the wide
        # checkbox columns matched to the "Toggle All X" header button text) so the row
        # never overflows its QScrollArea viewport. Below that floor the row's checkboxes
        # freeze at their minimum layout regardless of window width, decoupling them from
        # the header buttons above (which keep tracking window width via addStretch()) and
        # breaking the header/checkbox alignment fixed in prior tasks. Empirically confirmed
        # that alignment becomes stable once viewport width >= ~950px; 980 gives a little
        # headroom above that floor.
        self.setMinimumWidth(980)
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
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(4)

        for record in records:
            row = _SelectionRow(record)
            row.connect_changed(self._update_identify_btn)
            self._rows.append(row)
            container_layout.addWidget(row)

        container_layout.addStretch()
        scroll.setWidget(container)

        layout.addLayout(self._build_toggle_row())
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

    _TOGGLE_BUTTONS = [
        ("decorative", "Toggle All Decorative", "Decorative"),
        ("smiles", "Toggle All SMILES", "SMILES"),
        ("iupac", "Toggle All IUPAC", "IUPAC Name"),
        ("trivial", "Toggle All Common", "Common Name"),
        ("description", "Toggle All Describe", "Describe Image"),
    ]
    _DIVIDER_GAP = 11  # tuned in Task 5: matches the row's measured divider width (3px) + spacing (8px)
    # Fine-tune added to PM_ScrollBarExtent for the trailing spacer below: covers the
    # residual gap between the style's generic scrollbar-width hint and the scrollbar
    # instance's actual rendered width (plus the scroll frame border), measured empirically.
    _TRAILING_SPACER_ADJUST = 3

    def _build_toggle_row(self) -> QHBoxLayout:
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(8, 0, 8, 0)

        include_spacer = QWidget()
        include_spacer.setFixedWidth(QCheckBox().sizeHint().width())
        toggle_row.addWidget(include_spacer)

        thumb_spacer = QWidget()
        thumb_spacer.setFixedWidth(72)
        toggle_row.addWidget(thumb_spacer)

        toggle_row.addStretch()

        widths: dict[str, int] = {}
        buttons: list[tuple[str, QPushButton]] = []
        for pred_type, button_text, checkbox_label in self._TOGGLE_BUTTONS:
            button = QPushButton(button_text)
            width = max(
                QCheckBox(checkbox_label).sizeHint().width(),
                button.sizeHint().width(),
            )
            button.setFixedWidth(width)
            widths[pred_type] = width
            buttons.append((pred_type, button))

        _, decorative_button = buttons[0]
        toggle_row.addWidget(decorative_button)
        toggle_row.addSpacing(self._DIVIDER_GAP)
        for pred_type, button in buttons[1:]:
            toggle_row.addWidget(button)

        # The row's checkboxes live inside a QScrollArea whose vertical scrollbar
        # is forced always-on (see SelectionWindow.__init__), which narrows each
        # row's available width relative to this header row (not scrolled). Add a
        # trailing spacer matching the scrollbar's rendered width so the header's
        # fixed-width content is deducted by the same amount, keeping the header
        # buttons aligned with the checkbox columns below them.
        scrollbar_extent = QApplication.style().pixelMetric(
            QStyle.PixelMetric.PM_ScrollBarExtent
        )
        toggle_row.addSpacing(scrollbar_extent + self._TRAILING_SPACER_ADJUST)

        for pred_type, button in buttons:
            button.clicked.connect(lambda _checked, t=pred_type: self._toggle_all_type(t))

        for row in self._rows:
            row.apply_column_widths(widths)

        return toggle_row

    def _set_all(self, checked: bool) -> None:
        for row in self._rows:
            row.checkbox.setChecked(checked)

    def _toggle_all_type(self, pred_type: str) -> None:
        if not self._rows:
            return
        all_checked = all(row.is_type_checked(pred_type) for row in self._rows)
        target = not all_checked
        for row in self._rows:
            row.set_type_checked(pred_type, target)

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


class _SelectionRow(HoverHighlightMixin, QFrame):
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
        self._other_checks = [
            self._smiles_check, self._iupac_check, self._trivial_check, self._describe_check,
        ]
        for box in self._other_checks:
            layout.addWidget(box)

        self._decorative_check.setChecked(True)
        self._on_decorative_toggled()
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

    _TYPE_ATTR = {
        "decorative": "_decorative_check",
        "smiles": "_smiles_check",
        "iupac": "_iupac_check",
        "trivial": "_trivial_check",
        "description": "_describe_check",
    }

    def is_type_checked(self, pred_type: str) -> bool:
        return getattr(self, self._TYPE_ATTR[pred_type]).isChecked()

    def set_type_checked(self, pred_type: str, checked: bool) -> None:
        if pred_type == "decorative":
            self._decorative_check.setChecked(checked)
            return
        if checked and self._decorative_check.isChecked():
            self._decorative_check.setChecked(False)
        getattr(self, self._TYPE_ATTR[pred_type]).setChecked(checked)

    def apply_column_widths(self, widths: dict[str, int]) -> None:
        for pred_type, width in widths.items():
            getattr(self, self._TYPE_ATTR[pred_type]).setFixedWidth(width)

    def connect_changed(self, slot) -> None:
        self.checkbox.stateChanged.connect(slot)
        self._decorative_check.stateChanged.connect(slot)
        self._smiles_check.stateChanged.connect(slot)
        self._iupac_check.stateChanged.connect(slot)
        self._trivial_check.stateChanged.connect(slot)
        self._describe_check.stateChanged.connect(slot)
