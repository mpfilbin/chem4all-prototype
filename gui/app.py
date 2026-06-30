from __future__ import annotations
from PyQt6.QtWidgets import QApplication
from config import Config


def run_app(app: QApplication, config: Config) -> None:
    from gui.file_picker import FilePickerWindow
    window = FilePickerWindow(config)
    window.show()
