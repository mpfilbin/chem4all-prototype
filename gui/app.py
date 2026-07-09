from __future__ import annotations
from pathlib import Path
from config import Config


def restart_app() -> None:
    """Re-exec the current process so a freshly downloaded model gets preloaded on startup."""
    import os
    import sys

    if getattr(sys, "frozen", False):
        args = [sys.executable, *sys.argv[1:]]
    else:
        args = [sys.executable, *sys.argv]
    os.execv(sys.executable, args)


def run_app(config: Config, config_path: Path | None = None) -> object:
    from PyQt6.QtCore import QTimer
    from gui.file_picker import FilePickerWindow
    from gui.splash import make_splash, splash_message
    from gui.model_manager import is_model_ready

    splash = make_splash()
    splash.show()

    window = FilePickerWindow(config, config_path)

    def _finish() -> None:
        splash.finish(window)
        window.show()
        window.raise_()
        window.activateWindow()

    if config.preload_model and is_model_ready():
        from gui.model_manager import ModelPreloadWorker
        splash_message(splash, "Loading DECIMER model…")
        worker = ModelPreloadWorker()
        worker.finished.connect(lambda elapsed: (window.set_model_load_time(elapsed), _finish()))
        worker.error.connect(lambda _msg: _finish())
        worker.start()
        window._preload_worker = worker  # keep reference alive during event loop
    else:
        QTimer.singleShot(2000, _finish)

    return window
