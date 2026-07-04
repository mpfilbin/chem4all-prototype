import json
from pathlib import Path
import pytest
from config import Config, load_config, save_config


def test_load_config_creates_defaults(tmp_path):
    cfg_path = tmp_path / "config.json"
    config = load_config(cfg_path)
    assert config.thumbnail_max_size == 256
    assert config.recognition_max_size == 1024
    assert config.output_mode == "new_file"
    assert config.page_size == 5
    assert config.preload_model is False
    assert cfg_path.exists()


def test_load_config_reads_existing(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"page_size": 10}))
    config = load_config(cfg_path)
    assert config.page_size == 10
    assert config.thumbnail_max_size == 256  # default preserved


def test_save_config_roundtrip(tmp_path):
    cfg_path = tmp_path / "config.json"
    original = Config(page_size=8, output_mode="in_place")
    save_config(original, cfg_path)
    restored = load_config(cfg_path)
    assert restored.page_size == 8
    assert restored.output_mode == "in_place"


def test_load_config_preload_model_default(tmp_path):
    config = load_config(tmp_path / "config.json")
    assert config.preload_model is False


def test_load_config_ignores_unknown_keys(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text('{"page_size": 7, "deprecated_key": "value"}')
    config = load_config(cfg_path)
    assert config.page_size == 7
    # Should not raise even though "deprecated_key" is not a Config field
