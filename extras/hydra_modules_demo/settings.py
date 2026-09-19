# meta: name=settings version=2.0.0 author=hydra-team framework=hydra
"""Hydra new-shape module: kernel settings toggles with buttons."""

from hydra_kernel.api import ModuleBase, command

FLAGS = ["power_save", "silent_errors", "show_prefix"]


class Settings(ModuleBase):
    name = "settings"
    version = "2.0.0"

    @command("settings", desc="настройки ядра с кнопками")
    async def cmd_settings(self, event):
        await self._form(event.chat_id)

    def _text(self) -> str:
        lines = [f"<b>{self.t('title')}</b>"]
        for flag in FLAGS:
            state = self.t("on") if self.kernel.config.get(flag) else self.t("off")
            lines.append(f"{state} {flag}")
        return "\n".join(lines)

    async def _form(self, chat_id):
        rows = [
            [{"text": flag, "callback": self.cb_toggle, "args": (flag,)}] for flag in FLAGS
        ]
        await self.form(chat_id, self._text(), buttons=rows)

    async def cb_toggle(self, call, flag=None):
        if not flag:
            return
        self.kernel.config[flag] = not self.kernel.config.get(flag, False)
        self.kernel.save_config()
        await call.edit(self._text())
