"""L3 — registry: реестр загруженных модулей."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .manifest import Manifest


@dataclass
class Record:
    name: str
    module: Any
    manifest: Manifest
    framework: str
    lifecycle: Any = None


class Registry:
    def __init__(self) -> None:
        self._records: Dict[str, Record] = {}

    def register(self, record: Record) -> None:
        self._records[record.name] = record

    def unregister(self, name: str) -> Optional[Record]:
        return self._records.pop(name, None)

    def get(self, name: str) -> Optional[Record]:
        return self._records.get(name)

    def names(self) -> List[str]:
        return sorted(self._records)

    def __len__(self) -> int:
        return len(self._records)
