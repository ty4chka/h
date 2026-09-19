"""Модель редактора: файлы, чтение, сохранение с валидацией и бэкапом.

Отделена от curses-рендера, чтобы тестироваться headless.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path
from typing import List, Tuple

from ..pkg.scanner import scan_source


class EditorModel:
    def __init__(self, directory: str | Path, backups: str | Path = "data/backups"):
        self.dir = Path(directory)
        self.backups = Path(backups)

    def files(self) -> List[str]:
        if not self.dir.exists():
            return []
        return sorted(p.name for p in self.dir.glob("*.py") if p.name != "__init__.py")

    def read(self, name: str) -> str:
        return (self.dir / name).read_text(encoding="utf-8")

    def validate(self, code: str) -> str:
        """Возвращает причину отказа или пустую строку."""
        critical = [f for f in scan_source(code) if f.severity == "critical"]
        if critical:
            return "scanner: " + ", ".join(sorted({f.rule for f in critical}))
        try:
            ast.parse(code)
        except SyntaxError as e:
            return f"синтаксис @{e.lineno}: {e.msg}"
        return ""

    def save(self, name: str, code: str) -> Tuple[bool, str]:
        reason = self.validate(code)
        if reason:
            return False, reason
        path = self.dir / name
        self.backups.mkdir(parents=True, exist_ok=True)
        bak = self.backups / f"{name}.bak"
        if path.exists():
            shutil.copy2(path, bak)
        path.write_text(code, encoding="utf-8")
        return True, str(bak)
