"""L0 — DB: асинхронное key-value хранилище с пространствами имён."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryDB:
    """Хранилище в памяти. Потокобезопасно через asyncio.Lock."""

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, ns: str, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._data.get(ns, {}).get(key, default)

    async def set(self, ns: str, key: str, value: Any) -> None:
        async with self._lock:
            self._data.setdefault(ns, {})[key] = value
            await self._flush_locked()

    async def delete(self, ns: str, key: str) -> None:
        async with self._lock:
            self._data.get(ns, {}).pop(key, None)
            await self._flush_locked()

    async def keys(self, ns: str) -> List[str]:
        async with self._lock:
            return list(self._data.get(ns, {}).keys())

    # синхронный фасад (нужен Heroku-модулям: self._db.set(...) без await)
    def get_sync(self, ns: str, key: str, default: Any = None) -> Any:
        return self._data.get(ns, {}).get(key, default)

    def set_sync(self, ns: str, key: str, value: Any) -> None:
        self._data.setdefault(ns, {})[key] = value

    async def _flush_locked(self) -> None:
        """Хук персистенции (JsonDB переопределяет)."""


class JsonDB(MemoryDB):
    """MemoryDB с сохранением в JSON-файл."""

    def __init__(self, path: str | Path):
        super().__init__()
        self.path = Path(path)
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self._data = {}

    async def _flush_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
