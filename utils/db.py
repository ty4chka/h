# utils/db.py — простое key-value хранилище (поверхность utils.db из Dragon).
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class DB:
    def __init__(self, path: str = "data/dragon_db.json"):
        self._path = Path(path)
        self._data: dict = {}
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}

    def _flush(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass

    def get(self, ns: str, key: str, default: Any = None) -> Any:
        return self._data.get(f"{ns}:{key}", default)

    def set(self, ns: str, key: str, value: Any) -> None:
        self._data[f"{ns}:{key}"] = value
        self._flush()

    def delete(self, ns: str, key: str) -> None:
        self._data.pop(f"{ns}:{key}", None)
        self._flush()


db = DB()

__all__ = ["DB", "db"]
