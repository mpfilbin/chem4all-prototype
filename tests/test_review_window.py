from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtWidgets import QApplication, QLabel

from config import Config
from models.image_record import ImageRecord
from gui.review_window import ReviewWindow, _RecordRow, _make_pill, _PILL_COLORS, _PILL_LABELS
from gui.widgets import HoverHighlightMixin

_app = QApplication.instance() or QApplication(sys.argv)


def _make_record(id="r1", **kwargs):
    return ImageRecord(
        id=id,
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        **kwargs,
    )


def test_record_row_locked_while_not_done():
    record = _make_record()
    row = _RecordRow(record, done=False)
    row.show()
    assert row._value_field.isReadOnly() is True
    assert row._value_field.toPlainText() == ""
    assert row._restore_btn.isVisible() is False


def test_record_row_editable_and_populated_when_done():
    record = _make_record(
        predicted_smiles="CCO",
        iupac_name="ethanol",
        prediction_types=["smiles", "iupac"],
    )
    row = _RecordRow(record, done=True)
    assert row._value_field.isReadOnly() is False
    assert row._value_field.toPlainText() == "CCO\n\nethanol"


def test_record_row_shows_decorative_placeholder_when_done():
    record = _make_record(prediction_types=["decorative"])
    row = _RecordRow(record, done=True)
    assert row._value_field.isReadOnly() is False
    assert row._value_field.toPlainText() == "Decorative Image"


def test_restore_predicted_value_resets_decorative_text():
    record = _make_record(prediction_types=["decorative"])
    row = _RecordRow(record, done=True)
    row._value_field.setPlainText("edited alt text")

    row._restore_predicted()

    assert row._value_field.toPlainText() == "Decorative Image"


def test_update_record_unlocks_row_and_fills_composed_text():
    record = _make_record(prediction_types=["smiles", "description"])
    row = _RecordRow(record, done=False)

    record.predicted_smiles = "CCO"
    record.description = "A clear liquid in a flask."
    row.update_record(record)

    assert row._value_field.isReadOnly() is False
    assert row._value_field.toPlainText() == "CCO\n\nA clear liquid in a flask."


def test_apply_to_record_writes_empty_alt_text_instead_of_excluding(tmp_path):
    record = _make_record(predicted_smiles="CCO", prediction_types=["smiles"])
    row = _RecordRow(record, done=True)
    row._value_field.setPlainText("")

    row.apply_to_record()

    assert record.approved_value == ""
    assert record.is_chemical is True


def test_apply_to_record_sets_is_chemical_true_with_a_value():
    record = _make_record(predicted_smiles="CCO", prediction_types=["smiles"])
    row = _RecordRow(record, done=True)

    row.apply_to_record()

    assert record.approved_value == "CCO"
    assert record.is_chemical is True


def test_review_window_on_record_ready_unlocks_visible_row(tmp_path):
    record = _make_record(prediction_types=["smiles"])
    window = ReviewWindow([record], Config(), tmp_path / "sample.pptx")
    row = window._rows[0]
    assert row._value_field.isReadOnly() is True

    record.predicted_smiles = "CCO"
    window.on_record_ready(record)

    assert record.id in window._done_ids
    assert row._value_field.isReadOnly() is False
    assert row._value_field.toPlainText() == "CCO"


def _enter_event() -> QEnterEvent:
    return QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))


def test_record_row_applies_hover_stylesheet_on_enter():
    row = _RecordRow(_make_record(), done=False)
    assert row.styleSheet() == ""

    row.enterEvent(_enter_event())

    assert row.styleSheet() == HoverHighlightMixin.HOVER_STYLESHEET


def test_record_row_clears_hover_stylesheet_on_leave():
    row = _RecordRow(_make_record(), done=False)
    row.enterEvent(_enter_event())

    row.leaveEvent(QEvent(QEvent.Type.Leave))

    assert row.styleSheet() == ""


def test_make_pill_sets_label_text():
    pill = _make_pill("smiles")
    assert pill.text() == "SMILES"


def test_make_pill_sets_background_color():
    pill = _make_pill("iupac")
    assert _PILL_COLORS["iupac"] in pill.styleSheet()


def test_make_pill_labels_cover_all_prediction_types():
    for pred_type in ["decorative", "smiles", "iupac", "trivial", "description"]:
        pill = _make_pill(pred_type)
        assert pill.text() == _PILL_LABELS[pred_type]


def _header_pill_texts(row: _RecordRow) -> list[str]:
    info = row.layout().itemAt(1).layout()  # info QVBoxLayout is item 1 of the row's QHBoxLayout
    header_row = info.itemAt(1).layout()  # header_row QHBoxLayout is item 1 of info (item 0 is source_ref label)
    texts = []
    for i in range(header_row.count()):
        item = header_row.itemAt(i)
        widget = item.widget()
        if isinstance(widget, QLabel) and widget.text() != "Prediction Results:":
            texts.append(widget.text())
    return texts


def test_record_row_shows_pills_in_fixed_order():
    record = _make_record(prediction_types=["description", "smiles"])
    row = _RecordRow(record, done=False)
    assert _header_pill_texts(row) == ["SMILES", "Description"]


def test_record_row_shows_single_decorative_pill():
    record = _make_record(prediction_types=["decorative"])
    row = _RecordRow(record, done=False)
    assert _header_pill_texts(row) == ["Decorative"]


def test_record_row_shows_all_four_non_decorative_pills():
    record = _make_record(prediction_types=["trivial", "iupac", "description", "smiles"])
    row = _RecordRow(record, done=False)
    assert _header_pill_texts(row) == ["SMILES", "IUPAC", "Trivial", "Description"]


def test_last_page_row_does_not_stretch_taller_than_full_page(tmp_path):
    cfg = Config()
    records = [
        _make_record(id=f"r{i}", prediction_types=["smiles", "iupac"])
        for i in range(cfg.page_size + 1)
    ]
    window = ReviewWindow(records, cfg, tmp_path / "sample.pptx")
    window.resize(1200, 900)
    window.show()
    QApplication.processEvents()

    window._page = 0
    window._render_page()
    QApplication.processEvents()
    full_page_row_height = window._rows[0].height()

    window._page = 1  # last page: only 1 record, well short of a full page
    window._render_page()
    QApplication.processEvents()
    partial_page_row_height = window._rows[0].height()

    assert partial_page_row_height == full_page_row_height
