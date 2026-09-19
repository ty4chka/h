"""L3 — GoLoader: Go-модули как граждане первого сорта.

Go-модуль — бинарник на SDK `gocore/hydra`: ядро держит с ним процесс и
общается JSON-строками по stdio (op = meta / command / callback). Модуль
имеет всё то же, что Python-модули: команды, инлайн-формы, callable-кнопки
(через .cb-мост), edit/delete/answer, lang.

    loader = GoLoader(hydra)
    names = await loader.load_dir("gocore/bin")
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hydra_kernel.go")


class GoModuleHandle:
    """Один запущенный Go-модуль (процесс + JSON-RPC по stdio)."""

    def __init__(self, hydra: Any, path: Path):
        self.h = hydra
        self.path = Path(path)
        self.name = self.path.name
        self.version = "0"
        self.commands: List[str] = []
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._id = 0
        self._lock: Optional[asyncio.Lock] = None
        self._tokens: Dict[str, Any] = {}

    async def start(self) -> Dict[str, Any]:
        try:
            self.proc = await asyncio.create_subprocess_exec(
                str(self.path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            )
        except PermissionError:
            # после unzip/снепшота мог слететь +x — чиним и повторяем
            import os

            os.chmod(self.path, 0o755)
            self.proc = await asyncio.create_subprocess_exec(
                str(self.path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            )
        self._lock = asyncio.Lock()
        meta = await self.call("meta")
        result = meta.get("result") or {}
        self.name = result.get("name") or self.path.name
        self.version = result.get("version", "0")
        self.commands = [c["name"] for c in result.get("commands", [])]
        return result

    async def call(self, op: str, **params: Any) -> Dict[str, Any]:
        assert self.proc is not None and self._lock is not None
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


class GoLoader:
    def __init__(self, hydra: Any):
        self.h = hydra
        self.modules: Dict[str, GoModuleHandle] = {}

    async def load_dir(self, dirpath: Any) -> List[str]:
        d = Path(dirpath)
        if not d.is_dir():
            return []
        names = []
        for f in sorted(d.iterdir()):
            if f.is_file() and not f.name.startswith(".") and not f.suffix:
                names.append(await self.load_binary(f))
        return names

    async def load_binary(self, path: Any) -> str:
        mod = GoModuleHandle(self.h, Path(path))
        await mod.start()
        self.modules[mod.name] = mod
        prefix = self.h.prefix
        import re

        for cmd in mod.commands:
            pattern = rf"(?i)^{re.escape(prefix)}{re.escape(cmd)}(?:\s|$)"
            self.h.transport.subscribe(
                self._make_command_handler(mod, cmd),
                pattern=pattern,
                outgoing=True,
                incoming=True,
            )
            self.h.command_handlers[cmd] = f"go:{mod.name}"
        logger.info("go-модуль %s v%s: команды %s", mod.name, mod.version, mod.commands)
        return mod.name

    # -------------------------------------------------------------- хендлеры

    def _make_command_handler(self, mod: GoModuleHandle, cmd: str):
        h = self.h

        async def handler(event: Any) -> None:
            if not h.permissions.check(event.sender_id, 1):
                return
            args = event.text.split(maxsplit=1)[1] if " " in event.text else ""
            try:
                resp = await mod.call(
                    "command",
                    cmd=cmd,
                    chat_id=event.chat_id,
                    message_id=event.message_id,
                    sender_id=event.sender_id,
                    args=args,
                    lang=h.config.get("language", "ru"),
                )
                await self._respond(mod, event, resp, edit=False)
            except Exception as e:  # noqa: BLE001
                logger.error("go %s.%s: %s", mod.name, cmd, e)
                await event.reply(f"<b>Error:</b> <code>{str(e)[:100]}</code>")

        return handler

    def _callback_token(self, mod: GoModuleHandle, cb: str, args: List[str]) -> str:
        key = (cb, tuple(args))
        if key in mod._tokens:
            return mod._tokens[key]
        token = f"go_{mod.name}_{cb}_{len(mod._tokens)}:"

        async def wrapper(call: Any) -> None:
            resp = await mod.call(
                "callback",
                name=cb,
                cb_args=args,
                chat_id=call.chat_id,
                message_id=call.message_id,
                lang=self.h.config.get("language", "ru"),
            )
            await self._respond(mod, call, resp, edit=True)

        self.h.register_callback(token, wrapper)
        mod._tokens[key] = token
        return token

    async def _respond(self, mod: GoModuleHandle, event: Any, resp: Dict[str, Any], edit: bool) -> None:
        if not resp.get("ok", True):
            await event.reply(f"<b>Error:</b> <code>{resp.get('error', '?')}</code>")
            return
        res = resp.get("result") or {}
        rows: List[Any] = []
        for row in res.get("buttons") or []:
            new_row = []
            for btn in row:
                if btn.get("callback"):
                    token = self._callback_token(mod, btn["callback"], btn.get("args") or [])
                    new_row.append({"text": btn.get("text", "?"), "data": token})
                elif btn.get("url"):
                    new_row.append({"text": btn.get("text", "?"), "url": btn["url"]})
            if new_row:
                rows.append(new_row)

        if res.get("delete"):
            await event.delete()
            return
        if res.get("answer"):
            if hasattr(event, "answer"):
                await event.answer(res["answer"])
            else:
                await event.reply(res["answer"])
        text = res.get("edit") if edit else res.get("text")
        if edit and res.get("edit"):
            await event.edit(res["edit"], buttons=rows or None)
        elif text:
            await event.reply(text, buttons=rows or None)
