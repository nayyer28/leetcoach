from __future__ import annotations

import os
from pathlib import Path


_LOADED = False


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    return key, value


def load_environment() -> None:
    global _LOADED
    if _LOADED:
        return
    env_path = Path(".env")
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_env_line(raw)
            if parsed is None:
                continue
            key, value = parsed
            os.environ.setdefault(key, value)
    _LOADED = True
