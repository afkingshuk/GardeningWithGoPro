from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(root_dir: Path) -> Dict[str, Any]:
    base_path = root_dir / "config" / "config.yaml"
    local_path = Path(os.getenv("APP_CONFIG_PATH", root_dir / "config" / "config.local.yaml"))

    with base_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if local_path.exists():
        with local_path.open("r", encoding="utf-8") as f:
            config = _deep_merge(config, yaml.safe_load(f) or {})

    return config
