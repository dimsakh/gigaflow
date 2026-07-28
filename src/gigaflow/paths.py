from __future__ import annotations

import os
from pathlib import Path


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "GigaFlow"
    return Path.home() / ".gigaflow"


def ensure_app_dirs() -> dict[str, Path]:
    root = app_data_dir()
    paths = {
        "root": root,
        "models": root / "models",
        "logs": root / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths

