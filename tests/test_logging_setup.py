from __future__ import annotations
import logging
import sys
import pytest
from config import Config
import logging_setup
from logging_setup import configure_logging


@pytest.fixture(autouse=True)
def _reset_logging_state():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    original_excepthook = sys.excepthook
    logging_setup._active_log_dir = None
    logging_setup._excepthook_installed = False
    yield
    for h in root.handlers[:]:
        root.removeHandler(h)
    for h in original_handlers:
        root.addHandler(h)
    root.setLevel(original_level)
    sys.excepthook = original_excepthook


def test_enabling_creates_one_log_file(tmp_path):
    config = Config(diagnostic_logging_enabled=True, diagnostic_log_dir=str(tmp_path))
    status = configure_logging(config)
    assert status.file_logging_active is True
    assert status.error is None
    log_files = list(tmp_path.glob("chem4all-*.log"))
    assert len(log_files) == 1
    assert status.log_file_path == log_files[0]


def test_disabling_removes_file_handler_but_keeps_file(tmp_path):
    config = Config(diagnostic_logging_enabled=True, diagnostic_log_dir=str(tmp_path))
    status = configure_logging(config)
    log_path = status.log_file_path

    config.diagnostic_logging_enabled = False
    status = configure_logging(config)

    assert status.file_logging_active is False
    assert status.log_file_path is None
    assert log_path.exists()
    root = logging.getLogger()
    assert logging_setup._find_handler(root, logging_setup._FILE_HANDLER_NAME) is None


def test_reconfiguring_unchanged_does_not_create_second_file(tmp_path):
    config = Config(diagnostic_logging_enabled=True, diagnostic_log_dir=str(tmp_path))
    first_status = configure_logging(config)
    second_status = configure_logging(config)

    assert first_status.log_file_path == second_status.log_file_path
    assert len(list(tmp_path.glob("chem4all-*.log"))) == 1


def test_changing_log_dir_swaps_to_new_file(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    config = Config(diagnostic_logging_enabled=True, diagnostic_log_dir=str(dir_a))
    status_a = configure_logging(config)

    config.diagnostic_log_dir = str(dir_b)
    status_b = configure_logging(config)

    assert status_a.log_file_path.parent == dir_a
    assert status_b.log_file_path.parent == dir_b
    root = logging.getLogger()
    handler = logging_setup._find_handler(root, logging_setup._FILE_HANDLER_NAME)
    assert handler.baseFilename == str(status_b.log_file_path)


def test_invalid_directory_returns_error_without_raising(tmp_path):
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("x")
    config = Config(
        diagnostic_logging_enabled=True,
        diagnostic_log_dir=str(blocking_file / "logs"),
    )
    status = configure_logging(config)
    assert status.file_logging_active is False
    assert status.error is not None


def test_uncaught_exception_is_logged_to_file(tmp_path):
    config = Config(diagnostic_logging_enabled=True, diagnostic_log_dir=str(tmp_path))
    configure_logging(config)

    try:
        raise ValueError("boom")
    except ValueError:
        exc_info = sys.exc_info()
    sys.excepthook(*exc_info)

    log_files = list(tmp_path.glob("chem4all-*.log"))
    contents = log_files[0].read_text()
    assert "Uncaught exception" in contents
    assert "ValueError: boom" in contents


def test_uncaught_exception_prints_to_console_exactly_once(capsys):
    config = Config()
    configure_logging(config)

    try:
        raise ValueError("boom")
    except ValueError:
        exc_info = sys.exc_info()
    sys.excepthook(*exc_info)

    captured = capsys.readouterr()
    assert captured.err.count("ValueError: boom") == 1
