# Design: Diagnostic Log Files

## Context

chem4all already uses the standard `logging` module with per-module loggers (`gui/worker.py`, `pipeline/recognizer.py`, `pipeline/extractor.py`, `pipeline/writer.py`), but `main.py` only wires up console output via `logging.basicConfig(level=logging.INFO, ...)`. There is no way to capture what happened during a run for troubleshooting a user's bug report.

This feature adds an off-by-default diagnostic file logging option, configurable from the Settings dialog, that writes one timestamped log file per app session to a user-chosen directory (default `~/Desktop/chem4all-logs/`). It applies to both the GUI and CLI entry points, since both load the same `Config`. The purpose is specifically **bug-report troubleshooting**: when enabled, the file captures DEBUG-level detail and uncaught exceptions, even though the console output stays at today's INFO level.

## Config Changes (`config.py`)

Two new fields on `Config` (requires adding `field` to the existing `from dataclasses import dataclass, asdict` import):

```python
diagnostic_logging_enabled: bool = False
diagnostic_log_dir: str = field(default_factory=lambda: str(Path.home() / "Desktop" / "chem4all-logs"))
```

`load_config`/`save_config` need no changes — both already round-trip arbitrary dataclass fields via `asdict`/`Config(**defaults)`.

A small helper, also in `config.py`, exposes the same computation for reuse by the Settings dialog:

```python
def default_log_dir() -> str:
    return str(Path.home() / "Desktop" / "chem4all-logs")
```

(the dataclass field's `default_factory` calls this helper too, rather than duplicating the expression).

## `logging_setup.py` (new file, project root)

Centralizes handler management so both the CLI and GUI entry points, and the Settings dialog's immediate-apply behavior, share one code path.

```python
from __future__ import annotations
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from config import Config

_CONSOLE_HANDLER_NAME = "chem4all-console"
_FILE_HANDLER_NAME = "chem4all-diagnostic-file"

_active_log_dir: str | None = None
_excepthook_installed = False


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
        root.setLevel(logging.INFO)
        return LoggingStatus(False, None, None)

    if existing is not None and _active_log_dir == config.diagnostic_log_dir:
        root.setLevel(logging.DEBUG)
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
        root.setLevel(logging.DEBUG)
        _active_log_dir = config.diagnostic_log_dir
        return LoggingStatus(True, log_path, None)
    except OSError as exc:
        root.setLevel(logging.INFO)
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
    if root.level == logging.NOTSET:
        root.setLevel(logging.INFO)


def _ensure_excepthook() -> None:
    global _excepthook_installed
    if _excepthook_installed:
        return
    previous = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        logging.getLogger("chem4all").critical(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_tb)
        )
        previous(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
    _excepthook_installed = True


def _find_handler(root: logging.Logger, name: str) -> logging.Handler | None:
    for handler in root.handlers:
        if handler.get_name() == name:
            return handler
    return None
```

Behavior summary:
- Console handler (INFO, today's format) is installed once and left alone regardless of diagnostic logging state.
- `sys.excepthook` is installed once, logs uncaught exceptions at CRITICAL with full traceback, then chains to the previous hook so existing crash behavior (stderr dump) is unchanged.
- Enabling creates a new `chem4all-YYYY-MM-DD_HH-MM-SS.log` file handler at DEBUG and raises the root logger level to DEBUG (console stays at INFO because its handler has its own level).
- Disabling removes and closes the file handler, drops the root logger level back to INFO.
- Changing `diagnostic_log_dir` while already enabled swaps to a new file in the new directory.
- Re-calling with unchanged enabled state and unchanged directory is a no-op (keeps writing to the same session file) — this matters because Settings can be opened/saved multiple times per session without fragmenting the log.
- Directory/file creation failures (bad permissions, missing drive) are caught and returned as `LoggingStatus.error` instead of raised, so a bad path can't crash the app.

## `main.py` Changes

Remove the module-level:
```python
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
```

Add, immediately after `config = load_config(args.config)` inside `main()`:
```python
from logging_setup import configure_logging
configure_logging(config)
```

This covers both the CLI path (file processing) and the GUI path (`_launch_gui`), since both branches read `config` after this point. The `--download-model` early-return happens before config is loaded and keeps using default `print()` output, unchanged.

## Settings Dialog (`gui/settings_dialog.py`)

New `QGroupBox` "Diagnostic Logging", added to the layout alongside the existing OpenRouter and Model Files sections:

- `QCheckBox` — "Write diagnostic log files (for troubleshooting)", bound to `config.diagnostic_logging_enabled`.
- Path row: editable `QLineEdit` pre-filled with `config.diagnostic_log_dir`, a "Browse…" `QPushButton` opening `QFileDialog.getExistingDirectory`, and an "Open Log Folder" `QPushButton` (enabled only if the directory currently exists) that calls `QDesktopServices.openUrl`.
- All three controls are disabled when the checkbox is unchecked, re-enabled when checked (wire via `checkbox.toggled`).

On `_save()`:
```python
self.config.diagnostic_logging_enabled = self._diag_checkbox.isChecked()
self.config.diagnostic_log_dir = self._diag_path_field.text().strip() or default_log_dir()
save_config(self.config, self._config_path)
status = configure_logging(self.config)
if status.error:
    QMessageBox.warning(
        self, "Diagnostic Logging",
        f"Could not enable diagnostic logging: {status.error}",
    )
self.accept()
```

`configure_logging` is called immediately so enabling takes effect without restarting the app — the primary use case is "hit a bug, turn this on, reproduce it right now." A failed enable (e.g. unwritable path) surfaces as a warning dialog rather than failing silently, since a diagnostic feature that silently doesn't work defeats its purpose.

`default_log_dir()` (see Config Changes above) lets the Settings dialog fall back to the default path if the user clears the text field. The dialog also needs `QFileDialog` and `QMessageBox` added to its existing `PyQt6.QtWidgets` import line.

## Testing

- `tests/test_config.py` — add roundtrip assertions for `diagnostic_logging_enabled` and `diagnostic_log_dir` (default value and persisted custom value), following the existing pattern in that file.
- `tests/test_logging_setup.py` (new) —
  - enabling with a `tmp_path` directory creates exactly one `chem4all-*.log` file and returns `file_logging_active=True`
  - disabling removes the file handler (status `file_logging_active=False`) without deleting the file already written
  - calling `configure_logging` twice with the same enabled config and directory does not create a second file
  - changing `diagnostic_log_dir` while enabled creates a new file in the new directory and stops writing to the old one
  - an unwritable/invalid directory (e.g. a path under a file, not a directory) returns `LoggingStatus.error` set and does not raise
  - uncaught-exception hook logs to the active file handler (simulate via calling the installed `sys.excepthook` directly, or triggering `_ensure_excepthook` and invoking it)

No changes needed to existing pipeline/worker tests — none of them assert on logging configuration.

```bash
python -m pytest tests/ -v
```
