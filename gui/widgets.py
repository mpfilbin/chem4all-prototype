from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette, QPixmap
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
    """Tints a widget's background while the mouse hovers over it.

    Rows otherwise set no colors of their own and render entirely from the
    system palette, so a hardcoded light tint would wash out light,
    palette-driven text under a dark system theme. Below the lightness
    threshold, the tint is instead computed by lightening the widget's own
    palette background, keeping it close to whatever the current theme's
    background already is. The lighten step is additive rather than
    QColor.lighter()'s multiplicative scaling, which is a near no-op on
    near-black backgrounds (scaling an already-tiny value by 150% stays
    tiny) — additive guarantees the same visible delta everywhere in the
    typical dark-theme window-background range (roughly 20-60 lightness).
    """

    HOVER_STYLESHEET = "background-color: #eef3fb;"
    _DARK_LIGHTNESS_THRESHOLD = 128
    _DARK_MODE_LIGHTEN_DELTA = 30

    def enterEvent(self, event) -> None:
        self.setStyleSheet(self._hover_stylesheet())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setStyleSheet("")
        super().leaveEvent(event)

    def _hover_stylesheet(self) -> str:
        window_color = self.palette().color(QPalette.ColorRole.Window)
        if window_color.lightness() < self._DARK_LIGHTNESS_THRESHOLD:
            delta = self._DARK_MODE_LIGHTEN_DELTA
            r, g, b, _ = window_color.getRgb()
            tint = QColor(min(255, r + delta), min(255, g + delta), min(255, b + delta))
            return f"background-color: {tint.name()};"
        return self.HOVER_STYLESHEET
