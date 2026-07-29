from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    hotkey: str = "ctrl+shift+space"
    microphone: int | None = None
    model_name: str = "gigaam-v3-e2e-rnnt"
    quantization: str | None = "int8"
    partial_interval_ms: int = 900
    auto_finish_silence_seconds: float = 2.2
    show_partial_text: bool = True
    start_minimized: bool = False
    filler_filter: str = "soft"
    overlay_x: int | None = None
    overlay_y: int | None = None
    performance_version: int = 2

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if int(raw.get("performance_version", 0)) < 2:
                raw["partial_interval_ms"] = 900
                raw["auto_finish_silence_seconds"] = 2.2
                raw["performance_version"] = 2
            allowed = cls.__dataclass_fields__.keys()
            return cls(**{key: value for key, value in raw.items() if key in allowed})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
