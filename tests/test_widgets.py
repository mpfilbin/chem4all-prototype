from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QColor, QEnterEvent, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

from gui.widgets import HoverHighlightMixin

_app = QApplication.instance() or QApplication(sys.argv)


class _HoverWidget(HoverHighlightMixin, QWidget):
    pass


def _enter_event() -> QEnterEvent:
    return QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))


def test_enter_event_applies_hover_stylesheet():
    widget = _HoverWidget()
    assert widget.styleSheet() == ""

    widget.enterEvent(_enter_event())

    assert widget.styleSheet() == HoverHighlightMixin.HOVER_STYLESHEET


def test_leave_event_clears_hover_stylesheet():
    widget = _HoverWidget()
    widget.enterEvent(_enter_event())

    widget.leaveEvent(QEvent(QEvent.Type.Leave))

    assert widget.styleSheet() == ""


def test_enter_event_uses_lightened_tint_for_dark_palette():
    widget = _HoverWidget()
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    widget.setPalette(palette)

    widget.enterEvent(_enter_event())

    assert widget.styleSheet() == "background-color: #2d2d2d;"
