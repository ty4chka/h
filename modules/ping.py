# meta: name=ping version=1.0.0 author=hydra-team framework=hydra
"""Fast built-in health command for the unified runtime.

The old project advertised ``.ping`` in its config/help data, but only a demo
module defined it.  This production module deliberately uses one edit and no
artificial delay so it is also a quick way to distinguish Telegram delivery
latency from a slow module command.
"""

from __future__ import annotations

import time

from hydra_kernel.api import ModuleBase, OWNER, command


def _format_uptime(seconds: float) -> str:
    total = max(0, int(seconds))
    days, rest = divmod(total, 86_400)
    hours, rest = divmod(rest, 3_600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class Ping(ModuleBase):
    """A minimal, owner-only response-time and runtime-health command."""

    name = "ping"
    version = "1.0.0"

    @command("ping", desc="быстрый статус ядра", required_level=OWNER)
    async def cmd_ping(self, event) -> None:
        started = time.perf_counter()
        modules = len(self.kernel.registry) if self.kernel is not None else 0
        elapsed_ms = (time.perf_counter() - started) * 1000
        uptime = _format_uptime(self.ctx.runtime.uptime)
        await event.edit(
            "<b>🏓 Pong!</b>\n"
            f"<blockquote>⚡ Ядро: <code>{elapsed_ms:.2f} ms</code>\n"
            f"⏳ Аптайм: <code>{uptime}</code>\n"
            f"📦 Модулей: <code>{modules}</code></blockquote>"
        )
