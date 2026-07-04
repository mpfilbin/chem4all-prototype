from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path

_DEFAULT_PATH = Path.home() / ".chem4all" / "config.json"


@dataclass
class Config:
    openrouter_api_key: str = ""
    thumbnail_max_size: int = 256
    recognition_max_size: int = 1024
    output_mode: str = "new_file"
    page_size: int = 5
    preload_model: bool = False


def load_config(path: Path | None = None) -> Config:
    p = Path(path) if path else _DEFAULT_PATH
    if not p.exists():
        config = Config()
        save_config(config, p)
        return config
    data = json.loads(p.read_text())
    defaults = asdict(Config())
    defaults.update({k: v for k, v in data.items() if k in defaults})
    return Config(**defaults)


def save_config(config: Config, path: Path | None = None) -> None:
    p = Path(path) if path else _DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(config), indent=2))
