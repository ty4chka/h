# meta: name=help version=2.0.0 author=hydra-team framework=hydra
"""Hydra new-shape module: help with per-module buttons."""

from hydra_kernel.api import ModuleBase, command


class Help(ModuleBase):
    name = "help"
    version = "2.0.0"

    @command("help", desc="список модулей с кнопками")
    async def cmd_help(self, event):
        names = self.kernel.registry.names()
        rows = [
            [{"text": self.t("module", name=n), "callback": self.cb_module, "args": (n,)}]
            for n in names
        ]
        await self.form(event.chat_id, f"<b>{self.t('title')}</b> — {len(names)}", buttons=rows)

    async def cb_module(self, call, name=None):
        if not name:
            return
        cmds = sorted(
            cn
            for cn, owner in getattr(self.kernel, "command_handlers", {}).items()
            if True
        )
        # команды принадлежат ядру глобально; показываем все + алиасы
        aliases = getattr(self.kernel, "aliases", {})
        lines = [f".{c}" for c in cmds] + [f".{a} → .{t_}" for a, t_ in sorted(aliases.items())]
        text = f"<b>{self.t('module', name=name)}</b>\n" + ("\n".join(lines) or self.t("no_commands"))
        await call.edit(text)
