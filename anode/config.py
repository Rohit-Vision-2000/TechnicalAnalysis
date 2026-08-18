"""Configuration loading.

Configuration lives in ``config/config.json`` at the repository root. All
paths inside the config file are interpreted relative to the repository root
so the CLI works regardless of the current working directory.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.json"


@dataclass
class Config:
    raw: Dict[str, Any] = field(default_factory=dict)
    config_path: Path = DEFAULT_CONFIG_PATH

    @property
    def db_path(self) -> Path:
        return self._resolve(self.raw.get("database", {}).get("path", "data/anode.db"))

    @property
    def log_file(self) -> Optional[Path]:
        f = self.raw.get("logging", {}).get("file")
        return self._resolve(f) if f else None

    @property
    def log_level(self) -> str:
        return self.raw.get("logging", {}).get("level", "INFO")

    @property
    def market(self) -> Dict[str, Any]:
        return self.raw.get("market", {})

    @property
    def costs(self) -> Dict[str, Any]:
        return self.raw.get("costs", {})

    @property
    def paper_trading(self) -> Dict[str, Any]:
        return self.raw.get("paper_trading", {})

    def _resolve(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else REPO_ROOT / path


def load_config(path: Optional[Path] = None) -> Config:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    else:
        raw = {}
    return Config(raw=raw, config_path=config_path)
