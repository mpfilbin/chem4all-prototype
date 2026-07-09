from __future__ import annotations

import sys
import types
from pathlib import Path

from config import Config
import main


def test_main_passes_custom_config_path_to_gui(monkeypatch, tmp_path):
    cfg_path = tmp_path / "custom-config.json"
    seen: dict[str, object] = {}

    def fake_load_config(path):
        seen["loaded_path"] = path
        return Config(page_size=9)

    def fake_launch_gui(config, config_path):
        seen["gui_config"] = config
        seen["gui_path"] = config_path

    monkeypatch.setattr("config.load_config", fake_load_config)
    monkeypatch.setattr(main, "_launch_gui", fake_launch_gui)
    monkeypatch.setattr(sys, "argv", ["chem4all", "--config", str(cfg_path)])

    main.main()

    assert seen["loaded_path"] == cfg_path
    assert seen["gui_path"] == cfg_path
    assert seen["gui_config"].page_size == 9


def test_launch_gui_passes_config_path_to_run_app(monkeypatch):
    config_path = Path("/tmp/custom-config.json")
    seen: dict[str, object] = {}

    class FakeApplication:
        def __init__(self, argv):
            seen["argv"] = argv

        def exec(self):
            return 0

    def fake_run_app(config, passed_path):
        seen["run_app_config"] = config
        seen["run_app_path"] = passed_path
        return object()

    monkeypatch.setitem(sys.modules, "PyQt6.QtWidgets", types.SimpleNamespace(QApplication=FakeApplication))
    monkeypatch.setitem(sys.modules, "gui.app", types.SimpleNamespace(run_app=fake_run_app))
    monkeypatch.setattr(main.sys, "exit", lambda code: seen.setdefault("exit_code", code))

    config = Config()
    main._launch_gui(config, config_path)

    assert seen["argv"] is main.sys.argv
    assert seen["run_app_config"] == config
    assert seen["run_app_path"] == config_path
    assert seen["exit_code"] == 0


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
