from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from unittest.mock import MagicMock

from PyQt6.QtCore import QPoint, QPointF, Qt, QMimeData, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PyQt6.QtWidgets import QApplication

from config import Config
from gui.file_picker import FilePickerWindow

_app = QApplication.instance() or QApplication(sys.argv)

# QDragEnterEvent/QDropEvent hold a raw pointer to QMimeData but don't increment Python's
# refcount. Without this module-level list, local mime objects are garbage-collected after
# the event is constructed, causing segfaults when event.mimeData() is called.
_test_mimes = []


def _drag_enter_event(paths: list[str]) -> QDragEnterEvent:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    _test_mimes.append(mime)  # Keep reference
    return QDragEnterEvent(
        QPoint(0, 0), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )


def _drop_event(paths: list[str]) -> QDropEvent:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    _test_mimes.append(mime)  # Keep reference
    return QDropEvent(
        QPointF(0, 0), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )


def test_is_valid_drag_accepts_single_docx():
    window = FilePickerWindow(Config())
    assert window._is_valid_drag(_drag_enter_event(["/tmp/sample.docx"])) is True


def test_is_valid_drag_accepts_single_pptx():
    window = FilePickerWindow(Config())
    assert window._is_valid_drag(_drag_enter_event(["/tmp/sample.pptx"])) is True


def test_is_valid_drag_rejects_wrong_extension():
    window = FilePickerWindow(Config())
    assert window._is_valid_drag(_drag_enter_event(["/tmp/sample.pdf"])) is False


def test_is_valid_drag_rejects_multiple_files():
    window = FilePickerWindow(Config())
    event = _drag_enter_event(["/tmp/a.docx", "/tmp/b.docx"])
    assert window._is_valid_drag(event) is False


def test_is_valid_drag_rejects_when_open_button_disabled():
    window = FilePickerWindow(Config())
    window._open_btn.setEnabled(False)
    assert window._is_valid_drag(_drag_enter_event(["/tmp/sample.docx"])) is False


def test_drag_enter_event_highlights_window_for_valid_drag():
    window = FilePickerWindow(Config())
    assert window.styleSheet() == ""

    event = _drag_enter_event(["/tmp/sample.docx"])
    window.dragEnterEvent(event)

    assert window.styleSheet() == FilePickerWindow._DRAG_HIGHLIGHT_STYLESHEET
    assert event.isAccepted()


def test_drag_enter_event_ignores_invalid_drag():
    window = FilePickerWindow(Config())

    event = _drag_enter_event(["/tmp/sample.pdf"])
    window.dragEnterEvent(event)

    assert window.styleSheet() == ""
    assert not event.isAccepted()


def test_drag_leave_event_clears_highlight():
    window = FilePickerWindow(Config())
    window.dragEnterEvent(_drag_enter_event(["/tmp/sample.docx"]))

    window.dragLeaveEvent(QDragLeaveEvent())

    assert window.styleSheet() == ""


def test_drop_event_starts_extraction_with_dropped_path(tmp_path):
    window = FilePickerWindow(Config())
    window._start_extraction = MagicMock()
    docx_path = tmp_path / "dropped.docx"
    docx_path.write_bytes(b"")

    window.dropEvent(_drop_event([str(docx_path)]))

    window._start_extraction.assert_called_once_with(docx_path)
    assert window.styleSheet() == ""


def test_drop_event_ignores_invalid_drop():
    window = FilePickerWindow(Config())
    window._start_extraction = MagicMock()

    window.dropEvent(_drop_event(["/tmp/sample.pdf"]))

    window._start_extraction.assert_not_called()


def test_drag_hint_label_visible_with_expected_text():
    window = FilePickerWindow(Config())
    assert window._drag_hint_label.text() == "You can also drag and drop a file here to open it."
    assert window._drag_hint_label.isVisible()
