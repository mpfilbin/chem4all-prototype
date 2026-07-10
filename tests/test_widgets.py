from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QEnterEvent
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
