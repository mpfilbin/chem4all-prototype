import json
from pathlib import Path
import pytest
from config import Config, load_config, save_config


def test_load_config_creates_defaults(tmp_path):
    cfg_path = tmp_path / "config.json"
    config = load_config(cfg_path)
    assert config.auto_filter is False
    assert config.confidence_threshold == 0.7
    assert config.thumbnail_max_size == 256
    assert config.recognition_max_size == 1024
    assert config.output_mode == "new_file"
    assert config.page_size == 5
    assert cfg_path.exists()


def test_load_config_reads_existing(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"auto_filter": True, "page_size": 10}))
    config = load_config(cfg_path)
    assert config.auto_filter is True
    assert config.page_size == 10
    assert config.confidence_threshold == 0.7  # default preserved


def test_save_config_roundtrip(tmp_path):
    cfg_path = tmp_path / "config.json"
    original = Config(auto_filter=True, page_size=8, output_mode="in_place")
    save_config(original, cfg_path)
    restored = load_config(cfg_path)
    assert restored.auto_filter is True
    assert restored.page_size == 8
    assert restored.output_mode == "in_place"
