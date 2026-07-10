from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QDialog
from models.image_record import ImageRecord


class ThumbnailLabel(QLabel):
    """Clickable thumbnail that opens a full-size view on click."""

    def __init__(self, record: ImageRecord, size: int = 128, parent=None) -> None:
        super().__init__(parent)
        self._record = record
        self._size = size
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to enlarge")
        self._refresh()

    def _refresh(self) -> None:
        if self._record.thumbnail_bytes:
            pix = QPixmap()
            pix.loadFromData(self._record.thumbnail_bytes)
            self.setPixmap(
                pix.scaled(self._size, self._size,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self.setText("(loading…)")

    def mousePressEvent(self, _event) -> None:
        if not self._record.thumbnail_bytes:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(self._record.source_ref)
        layout = QVBoxLayout(dlg)
        pix = QPixmap()
        pix.loadFromData(self._record.thumbnail_bytes)
        lbl = QLabel()
        lbl.setPixmap(pix)
        layout.addWidget(lbl)
        dlg.exec()

    def update_record(self, record: ImageRecord) -> None:
        self._record = record
        self._refresh()


class HoverHighlightMixin:
    """Tints a widget's background while the mouse hovers over it."""

    HOVER_STYLESHEET = "background-color: #eef3fb;"

    def enterEvent(self, event) -> None:
        self.setStyleSheet(self.HOVER_STYLESHEET)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setStyleSheet("")
        super().leaveEvent(event)
