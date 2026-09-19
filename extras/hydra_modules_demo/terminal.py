# meta: name=terminal version=2.0.0 author=hydra-team framework=hydra
"""Hydra new-shape module: terminal with streamed output and buttons."""

import asyncio
import html
import re

from hydra_kernel.api import ModuleBase, command

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mABCDEFGHJKSTfhilmnprsu]")
TIMEOUT = 10
MAX_OUT = 3000


class Terminal(ModuleBase):
    name = "terminal"
    version = "2.0.0"

    @command("term", aliases=("t",), desc="выполнить команду (owner only)")
    async def cmd_term(self, event):
        cmd = self.args_raw(event).strip()
        if not cmd:
            await self.reply(event, self.t("no_command"))
            return
        await self.run(event.chat_id, cmd)

    async def run(self, chat_id: int, cmd: str):
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
            code = proc.returncode
        except asyncio.TimeoutError:
            proc.kill()
            out_b, code = b"", -1
            await self.send(chat_id, self.t("timeout", sec=TIMEOUT))
            return

        out = ANSI_RE.sub("", out_b.decode("utf-8", "ignore"))[:MAX_OUT]
        text = self.t("result", cmd=html.escape(cmd), code=code, out=html.escape(out) or "-")
        await self.form(
            chat_id,
            text,
            buttons=[[
                {"text": self.strings("buttons")("refresh"), "callback": self.cb_rerun, "args": (cmd,)},
                {"text": self.strings("buttons")("close"), "callback": self.cb_close},
            ]],
        )

    async def cb_rerun(self, call, cmd=None):
        if not cmd:
            return
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        try:
            out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
            code = proc.returncode
        except asyncio.TimeoutError:
            proc.kill()
            out_b, code = b"", -1
        out = ANSI_RE.sub("", out_b.decode("utf-8", "ignore"))[:MAX_OUT]
        await call.edit(
            self.t("result", cmd=html.escape(cmd), code=code, out=html.escape(out) or "-")
        )

    async def cb_close(self, call):
        await call.delete()
