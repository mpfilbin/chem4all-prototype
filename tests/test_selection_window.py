from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtWidgets import QApplication

from config import Config
from models.image_record import ImageRecord
from gui.selection_window import SelectionWindow
from gui.widgets import HoverHighlightMixin

_app = QApplication.instance() or QApplication(sys.argv)


def _make_record(id="r1"):
    return ImageRecord(
        id=id,
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
    )


def test_selection_row_defaults_to_decorative_only():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    assert row.prediction_types == ["decorative"]
    assert row._decorative_check.isChecked() is True
    assert row._smiles_check.isChecked() is False
    assert row._smiles_check.isEnabled() is False


def test_unchecking_default_decorative_leaves_all_types_unchecked():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]

    row._decorative_check.setChecked(False)

    assert row._smiles_check.isChecked() is False
    assert row._iupac_check.isChecked() is False
    assert row._trivial_check.isChecked() is False
    assert row._describe_check.isChecked() is False
    assert row.prediction_types == []


def test_selection_row_reports_multiple_checked_types():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._decorative_check.setChecked(False)
    row._smiles_check.setChecked(True)
    row._iupac_check.setChecked(True)
    row._describe_check.setChecked(True)
    assert row.prediction_types == ["smiles", "iupac", "description"]


def test_identify_button_disabled_when_included_row_has_no_types():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    window.show()
    row = window._rows[0]
    row._decorative_check.setChecked(False)
    assert window._identify_btn.isEnabled() is False
    assert window._error_banner.isVisible() is True


def test_identify_button_enabled_with_only_decorative_checked():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    window.show()
    row = window._rows[0]
    row._decorative_check.setChecked(False)
    assert window._identify_btn.isEnabled() is False  # sanity check: no types yet

    row._decorative_check.setChecked(True)

    assert window._identify_btn.isEnabled() is True
    assert window._error_banner.isVisible() is False


def test_identify_button_enabled_when_all_included_rows_have_types():
    window = SelectionWindow(
        [_make_record("r1"), _make_record("r2")], Config(), Path("dummy.pptx")
    )
    window.show()
    assert window._identify_btn.isEnabled() is True
    assert window._error_banner.isVisible() is False


def test_error_banner_ignores_excluded_rows_with_no_types():
    window = SelectionWindow(
        [_make_record("r1"), _make_record("r2")], Config(), Path("dummy.pptx")
    )
    window.show()
    row2 = window._rows[1]
    row2.checkbox.setChecked(False)
    row2._decorative_check.setChecked(False)
    assert window._identify_btn.isEnabled() is True
    assert window._error_banner.isVisible() is False


def _enter_event() -> QEnterEvent:
    return QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))


def test_selection_row_applies_hover_stylesheet_on_enter():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    assert row.styleSheet() == ""

    row.enterEvent(_enter_event())

    assert row.styleSheet() == HoverHighlightMixin.HOVER_STYLESHEET


def test_selection_row_clears_hover_stylesheet_on_leave():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row.enterEvent(_enter_event())

    row.leaveEvent(QEvent(QEvent.Type.Leave))

    assert row.styleSheet() == ""


def test_start_identification_sets_prediction_types_on_selected_records(monkeypatch):
    class MockSignal:
        def connect(self, slot):
            pass

    class MockReviewWindow:
        def __init__(self, *args, **kwargs):
            pass
        def show(self):
            pass
        def raise_(self):
            pass
        def activateWindow(self):
            pass
        def on_record_ready(self, record):
            pass
        def on_recognition_status(self, msg):
            pass
        def on_recognition_finished(self):
            pass
        def on_recognition_error(self, error_msg):
            pass

    class MockRecognizerWorker:
        def __init__(self, *args, **kwargs):
            self.record_ready = MockSignal()
            self.status = MockSignal()
            self.finished = MockSignal()
            self.error = MockSignal()
        def start(self):
            pass

    monkeypatch.setattr("gui.review_window.ReviewWindow", MockReviewWindow)
    monkeypatch.setattr("gui.worker.RecognizerWorker", MockRecognizerWorker)

    record = _make_record()
    window = SelectionWindow([record], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._decorative_check.setChecked(False)
    row._smiles_check.setChecked(True)
    row._iupac_check.setChecked(True)

    window._start_identification()

    assert record.prediction_types == ["smiles", "iupac"]


def test_decorative_checkbox_disables_other_prediction_checks():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._decorative_check.setChecked(False)
    row._smiles_check.setChecked(True)

    row._decorative_check.setChecked(True)

    assert row._smiles_check.isChecked() is False
    assert row._smiles_check.isEnabled() is False
    assert row._iupac_check.isEnabled() is False
    assert row._trivial_check.isEnabled() is False
    assert row._describe_check.isEnabled() is False
    assert row.prediction_types == ["decorative"]


def test_unchecking_decorative_restores_prior_checkbox_state():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._decorative_check.setChecked(False)
    row._smiles_check.setChecked(True)
    row._iupac_check.setChecked(True)

    row._decorative_check.setChecked(True)
    row._decorative_check.setChecked(False)

    assert row._smiles_check.isChecked() is True
    assert row._smiles_check.isEnabled() is True
    assert row._iupac_check.isChecked() is True
    assert row._trivial_check.isChecked() is False
    assert row._describe_check.isChecked() is False
    assert row.prediction_types == ["smiles", "iupac"]


def test_set_type_checked_decorative_sets_decorative_checkbox():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._decorative_check.setChecked(False)

    row.set_type_checked("decorative", True)

    assert row._decorative_check.isChecked() is True
    assert row.is_type_checked("decorative") is True


def test_set_type_checked_non_decorative_clears_decorative_first():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    assert row._decorative_check.isChecked() is True  # default state

    row.set_type_checked("smiles", True)

    assert row._decorative_check.isChecked() is False
    assert row._smiles_check.isChecked() is True
    assert row.is_type_checked("smiles") is True


def test_set_type_checked_false_unchecks_without_touching_decorative():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._decorative_check.setChecked(False)
    row._smiles_check.setChecked(True)

    row.set_type_checked("smiles", False)

    assert row._smiles_check.isChecked() is False
    assert row._decorative_check.isChecked() is False
    assert row.is_type_checked("smiles") is False
