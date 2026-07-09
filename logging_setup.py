from __future__ import annotations
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from config import Config

_CONSOLE_HANDLER_NAME = "chem4all-console"
_FILE_HANDLER_NAME = "chem4all-diagnostic-file"
_DIAGNOSTIC_LOGGER_NAMES = ("pipeline", "gui")

_active_log_dir: str | None = None
_excepthook_installed = False


def _set_diagnostic_logger_levels(level: int) -> None:
    for name in _DIAGNOSTIC_LOGGER_NAMES:
        logging.getLogger(name).setLevel(level)


@dataclass
class LoggingStatus:
    file_logging_active: bool
    log_file_path: Path | None
    error: str | None


def configure_logging(config: Config) -> LoggingStatus:
    root = logging.getLogger()
    _ensure_console_handler(root)
    _ensure_excepthook()

    global _active_log_dir
    existing = _find_handler(root, _FILE_HANDLER_NAME)

    if not config.diagnostic_logging_enabled:
        if existing is not None:
            root.removeHandler(existing)
            existing.close()
        _active_log_dir = None
        _set_diagnostic_logger_levels(logging.NOTSET)
        return LoggingStatus(False, None, None)

    if existing is not None and _active_log_dir == config.diagnostic_log_dir:
        _set_diagnostic_logger_levels(logging.DEBUG)
        return LoggingStatus(True, Path(existing.baseFilename), None)

    if existing is not None:
        root.removeHandler(existing)
        existing.close()

    try:
        log_dir = Path(config.diagnostic_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = log_dir / f"chem4all-{timestamp}.log"
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.set_name(_FILE_HANDLER_NAME)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
        ))
        root.addHandler(handler)
        _set_diagnostic_logger_levels(logging.DEBUG)
        _active_log_dir = config.diagnostic_log_dir
        return LoggingStatus(True, log_path, None)
    except OSError as exc:
        _set_diagnostic_logger_levels(logging.NOTSET)
        _active_log_dir = None
        return LoggingStatus(False, None, str(exc))


def _ensure_console_handler(root: logging.Logger) -> None:
    if _find_handler(root, _CONSOLE_HANDLER_NAME) is not None:
        return
    handler = logging.StreamHandler()
    handler.set_name(_CONSOLE_HANDLER_NAME)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _ensure_excepthook() -> None:
    global _excepthook_installed
    if _excepthook_installed:
        return
    previous = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        root = logging.getLogger()
        file_handler = _find_handler(root, _FILE_HANDLER_NAME)
        if file_handler is not None:
            record = logging.LogRecord(
                name="chem4all",
                level=logging.CRITICAL,
                pathname="",
                lineno=0,
                msg="Uncaught exception",
                args=(),
                exc_info=(exc_type, exc_value, exc_tb),
            )
            file_handler.handle(record)
        previous(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
    _excepthook_installed = True


def _find_handler(root: logging.Logger, name: str) -> logging.Handler | None:
    for handler in root.handlers:
        if handler.get_name() == name:
            return handler
    return None
