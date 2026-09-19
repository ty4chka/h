"""L0 — GoBridge: мост Python-ядра к Go-части (gocore/hydracore).

Go-ядро берёт на себя быстрые операции (ANSI-strip, sha256, файловый IO,
запуск Go-модулей). Без бинарника bridge просто не стартует — ядро
работает в чисто питоновом режиме.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional


class GoBridge:
    def __init__(self, binary: str = "gocore/hydracore"):
        self.binary = Path(binary)
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._id = 0
        self._lock: Optional[asyncio.Lock] = None

    async def start(self) -> bool:
        if not self.binary.exists():
            return False
        self.proc = await asyncio.create_subprocess_exec(
            str(self.binary),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        self._lock = asyncio.Lock()
        return True

    async def call(self, op: str, **params: Any) -> Dict[str, Any]:
        if self.proc is None or self._lock is None:
            raise RuntimeError("GoBridge не запущен")
        async with self._lock:
            self._id += 1
            req = {"id": self._id, "op": op, **params}
            self.proc.stdin.write((json.dumps(req) + "\n").encode())
            await self.proc.stdin.drain()
            line = await asyncio.wait_for(self.proc.stdout.readline(), 5)
            return json.loads(line)

    async def stop(self) -> None:
        if self.proc is not None:
            self.proc.kill()
            self.proc = None
