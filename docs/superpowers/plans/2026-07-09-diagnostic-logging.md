# Diagnostic Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an off-by-default, Settings-configurable diagnostic file logging feature that writes one timestamped log file per session to a user-chosen directory (default `~/Desktop/chem4all-logs/`), for both the GUI and CLI entry points.

**Architecture:** A new `logging_setup.py` module owns all `logging` handler/level state via one function, `configure_logging(config)`, called at startup (`main.py`) and again from the Settings dialog's Save handler so toggling applies immediately. `Config` gains two new persisted fields. The Settings dialog gets a new "Diagnostic Logging" section.

**Tech Stack:** Python stdlib `logging`, PyQt6, pytest (existing project stack — no new dependencies).

## Global Constraints

- Console output must keep its exact current format and INFO level — `%(levelname)s: %(message)s` (from `main.py`'s current `logging.basicConfig` call).
- Diagnostic logging is off by default (`diagnostic_logging_enabled: bool = False`).
- Default log directory is `~/Desktop/chem4all-logs/` (a subfolder, not loose files on the Desktop).
- One new log file per session: `chem4all-YYYY-MM-DD_HH-MM-SS.log`.
- No automatic pruning/rotation of old log files — user manages the folder.
- Feature applies to both CLI and GUI invocations of chem4all (same shared `Config`).
- Directory/file creation failures must be caught and surfaced, never raised/crash the app.
- Enabling/disabling from the Settings dialog takes effect immediately on Save, without restarting the app.

Reference spec: `docs/superpowers/specs/2026-07-09-diagnostic-logging-design.md`

---

### Task 1: Config fields for diagnostic logging

**Files:**
- Modify: `config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config.diagnostic_logging_enabled: bool` (default `False`), `Config.diagnostic_log_dir: str` (default from `default_log_dir()`), and a module-level function `default_log_dir() -> str` in `config.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_load_config_diagnostic_logging_defaults(tmp_path):
    config = load_config(tmp_path / "config.json")
    assert config.diagnostic_logging_enabled is False
    assert config.diagnostic_log_dir == default_log_dir()


def test_save_config_diagnostic_logging_roundtrip(tmp_path):
    cfg_path = tmp_path / "config.json"
    original = Config(diagnostic_logging_enabled=True, diagnostic_log_dir="/custom/log/dir")
    save_config(original, cfg_path)
    restored = load_config(cfg_path)
    assert restored.diagnostic_logging_enabled is True
    assert restored.diagnostic_log_dir == "/custom/log/dir"


def test_default_log_dir_is_desktop_subfolder():
    assert default_log_dir() == str(Path.home() / "Desktop" / "chem4all-logs")
```

Update the import line at the top of `tests/test_config.py`:

```python
from config import Config, load_config, save_config, default_log_dir
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'default_log_dir' from 'config'`

- [ ] **Step 3: Implement the Config changes**

In `config.py`, change the dataclasses import and add the two fields plus the helper function:

```python
from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

_DEFAULT_PATH = Path.home() / ".chem4all" / "config.json"


def default_log_dir() -> str:
    return str(Path.home() / "Desktop" / "chem4all-logs")


@dataclass
class Config:
    openrouter_api_key: str = ""
    thumbnail_max_size: int = 256
    recognition_max_size: int = 1024
    output_mode: str = "new_file"
    page_size: int = 5
    preload_model: bool = False
    diagnostic_logging_enabled: bool = False
    diagnostic_log_dir: str = field(default_factory=default_log_dir)
```

(`load_config` and `save_config` are unchanged — they already round-trip arbitrary fields via `asdict`/`Config(**defaults)`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (all tests in the file, including the three new ones)

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add diagnostic logging fields to Config"
```

---

### Task 2: `logging_setup.py` module

**Files:**
- Create: `logging_setup.py`
- Test: `tests/test_logging_setup.py`

**Interfaces:**
- Consumes: `Config.diagnostic_logging_enabled`, `Config.diagnostic_log_dir` (Task 1)
- Produces: `configure_logging(config: Config) -> LoggingStatus`, `LoggingStatus(file_logging_active: bool, log_file_path: Path | None, error: str | None)`, both importable from `logging_setup`. Also `logging_setup._FILE_HANDLER_NAME`, `logging_setup._find_handler`, `logging_setup._active_log_dir`, `logging_setup._excepthook_installed` (used by tests).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_logging_setup.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_logging_setup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'logging_setup'`

- [ ] **Step 3: Implement `logging_setup.py`**

Create `logging_setup.py`:

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_logging_setup.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add logging_setup.py tests/test_logging_setup.py
git commit -m "feat: add logging_setup module for diagnostic file logging"
```

---

### Task 3: Wire `logging_setup` into `main.py`

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `logging_setup.configure_logging` (Task 2)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_main.py`:

```python
def test_main_calls_configure_logging_with_loaded_config(monkeypatch, tmp_path):
    cfg_path = tmp_path / "custom-config.json"
    seen: dict[str, object] = {}

    def fake_load_config(path):
        return Config(page_size=9)

    def fake_configure_logging(config):
        seen["configured_config"] = config
        return object()

    def fake_launch_gui(config, config_path):
        pass

    monkeypatch.setattr("config.load_config", fake_load_config)
    monkeypatch.setattr("logging_setup.configure_logging", fake_configure_logging)
    monkeypatch.setattr(main, "_launch_gui", fake_launch_gui)
    monkeypatch.setattr(sys, "argv", ["chem4all", "--config", str(cfg_path)])

    main.main()

    assert seen["configured_config"].page_size == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_main.py::test_main_calls_configure_logging_with_loaded_config -v`
Expected: FAIL — `KeyError: 'configured_config'` (nothing calls `configure_logging` yet)

- [ ] **Step 3: Wire it up in `main.py`**

Remove these two lines near the top of `main.py` (the `import logging` line and the `basicConfig` call — nothing else in this file references the `logging` module):

```python
import logging
```

```python
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
```

In `main()`, right after `config = load_config(args.config)`, add:

```python
    from config import load_config
    config = load_config(args.config)
    from logging_setup import configure_logging
    configure_logging(config)
    if args.in_place:
        config.output_mode = "in_place"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_main.py -v`
Expected: PASS (all tests in the file, including the new one)

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: configure diagnostic logging at startup"
```

---

### Task 4: Settings dialog UI

**Files:**
- Modify: `gui/settings_dialog.py`

**Interfaces:**
- Consumes: `Config.diagnostic_logging_enabled`, `Config.diagnostic_log_dir`, `default_log_dir()` (Task 1); `logging_setup.configure_logging`, `logging_setup.LoggingStatus` (Task 2)

This repo has no existing automated tests for PyQt widgets (no test file targets `gui/settings_dialog.py`, `gui/review_window.py`, etc. today), so this task is verified manually per the steps below rather than with pytest.

- [ ] **Step 1: Update imports**

In `gui/settings_dialog.py`, change:

```python
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QCheckBox,
    QSpinBox, QRadioButton, QButtonGroup, QDialogButtonBox,
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
)
from config import Config, save_config
```

to:

```python
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QCheckBox,
    QSpinBox, QRadioButton, QButtonGroup, QDialogButtonBox,
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox,
)
from config import Config, save_config, default_log_dir
from logging_setup import configure_logging
```

- [ ] **Step 2: Add the Diagnostic Logging section builder**

Add this new method to `SettingsDialog`, near `_build_openrouter_section`/`_build_model_info`:

```python
    def _build_diagnostic_logging_section(self) -> QGroupBox:
        box = QGroupBox("Diagnostic Logging")
        vbox = QVBoxLayout(box)
        vbox.setSpacing(6)

        self._diag_checkbox = QCheckBox("Write diagnostic log files (for troubleshooting)")
        self._diag_checkbox.setChecked(self.config.diagnostic_logging_enabled)
        vbox.addWidget(self._diag_checkbox)

        path_row = QHBoxLayout()
        self._diag_path_field = QLineEdit(self.config.diagnostic_log_dir)
        path_row.addWidget(self._diag_path_field)
        self._diag_browse_btn = QPushButton("Browse…")
        self._diag_browse_btn.clicked.connect(self._browse_diagnostic_log_dir)
        path_row.addWidget(self._diag_browse_btn)
        self._diag_open_btn = QPushButton("Open Log Folder")
        self._diag_open_btn.clicked.connect(self._open_diagnostic_log_dir)
        path_row.addWidget(self._diag_open_btn)
        vbox.addLayout(path_row)

        self._diag_checkbox.toggled.connect(self._update_diagnostic_controls_enabled)
        self._update_diagnostic_controls_enabled(self._diag_checkbox.isChecked())

        return box

    def _update_diagnostic_controls_enabled(self, checked: bool) -> None:
        self._diag_path_field.setEnabled(checked)
        self._diag_browse_btn.setEnabled(checked)
        self._diag_open_btn.setEnabled(checked and Path(self._diag_path_field.text()).exists())

    def _browse_diagnostic_log_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Choose Diagnostic Log Folder", self._diag_path_field.text()
        )
        if directory:
            self._diag_path_field.setText(directory)
            self._update_diagnostic_controls_enabled(self._diag_checkbox.isChecked())

    def _open_diagnostic_log_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._diag_path_field.text()))
```

- [ ] **Step 3: Add the section to the dialog layout**

In `__init__`, change:

```python
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self._build_openrouter_section())
        layout.addWidget(self._build_model_info())
        layout.addWidget(buttons)
        self.setLayout(layout)
```

to:

```python
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self._build_openrouter_section())
        layout.addWidget(self._build_model_info())
        layout.addWidget(self._build_diagnostic_logging_section())
        layout.addWidget(buttons)
        self.setLayout(layout)
```

- [ ] **Step 4: Wire up `_save`**

Change `_save` from:

```python
    def _save(self) -> None:
        self.config.openrouter_api_key = self._api_key_field.text().strip()
        self.config.thumbnail_max_size = self._thumb_size.value()
        self.config.recognition_max_size = self._recog_size.value()
        self.config.output_mode = "in_place" if self._in_place_radio.isChecked() else "new_file"
        self.config.page_size = self._page_size.value()
        self.config.preload_model = self._preload_model.isChecked()
        save_config(self.config, self._config_path)
        self.accept()
```

to:

```python
    def _save(self) -> None:
        self.config.openrouter_api_key = self._api_key_field.text().strip()
        self.config.thumbnail_max_size = self._thumb_size.value()
        self.config.recognition_max_size = self._recog_size.value()
        self.config.output_mode = "in_place" if self._in_place_radio.isChecked() else "new_file"
        self.config.page_size = self._page_size.value()
        self.config.preload_model = self._preload_model.isChecked()
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

- [ ] **Step 5: Manual verification**

Run: `python main.py`

1. In the file picker window, click "Settings". Confirm a new "Diagnostic Logging" group box appears below "Model Files", with an unchecked checkbox, a path field pre-filled with `~/Desktop/chem4all-logs`, a "Browse…" button, and an "Open Log Folder" button. Confirm the path field, Browse, and Open Log Folder are all greyed out (checkbox unchecked = disabled).
2. Check the checkbox. Confirm the path field and both buttons become enabled.
3. Click "Browse…", pick a folder (e.g. your Desktop), confirm the path field updates to the chosen folder.
4. Click "Save". Confirm the dialog closes with no warning dialog, and that a new file named like `chem4all-2026-07-09_14-32-01.log` now exists in the chosen folder.
5. Reopen Settings, click "Open Log Folder". Confirm it opens the folder in Finder.
6. Uncheck the checkbox, click "Save". Confirm no new log file is created afterward but the existing one remains.
7. Re-check the checkbox with the same folder, click "Save". Confirm a *new* timestamped log file is created (a fresh session file, not resuming the old name).

- [ ] **Step 6: Commit**

```bash
git add gui/settings_dialog.py
git commit -m "feat: add diagnostic logging controls to Settings dialog"
```

---

### Task 5: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full automated test suite**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests, including everything added in Tasks 1-3)

- [ ] **Step 2: CLI smoke test**

Run (from repo root, with any sample `.pptx`/`.docx` you have, or reuse a fixture file):

```bash
python main.py --review path/to/sample.pptx
```

Expected: console output at INFO level looks the same as before this feature (no format change), and no log file is created since `diagnostic_logging_enabled` defaults to `False` in a fresh `~/.chem4all/config.json`.

- [ ] **Step 3: Enable via config file directly and re-run CLI**

```bash
python -c "
from config import load_config, save_config
c = load_config()
c.diagnostic_logging_enabled = True
save_config(c)
"
python main.py --review path/to/sample.pptx
```

Expected: a new `chem4all-*.log` file appears in `~/Desktop/chem4all-logs/`, containing DEBUG-level lines from `pipeline.extractor`, `pipeline.recognizer`, etc.

- [ ] **Step 4: Reset local config back to disabled**

```bash
python -c "
from config import load_config, save_config
c = load_config()
c.diagnostic_logging_enabled = False
save_config(c)
"
```

This avoids leaving diagnostic logging on in your local `~/.chem4all/config.json` after testing.
