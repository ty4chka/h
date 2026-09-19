# meta: name=info version=2.0.0 author=hydra-team framework=hydra
"""Hydra new-shape module: info with form and buttons."""

from hydra_kernel.api import ModuleBase, command


class Info(ModuleBase):
    name = "info"
    version = "2.0.0"

    @command("info", desc="информация о ядре")
    async def cmd_info(self, event):
        await self._form(event.chat_id)

    def _text(self) -> str:
        return (
            f"<b>{self.t('title')}</b>\n"
            f"{self.t('version', version=self.ctx.runtime.version)}\n"
            f"{self.t('modules', count=len(self.kernel.registry))}"
        )

    async def _form(self, chat_id):
        await self.form(
            chat_id,
            self._text(),
            buttons=[[
                {"text": self.strings("buttons")("refresh"), "callback": self.cb_refresh},
                {"text": self.strings("buttons")("close"), "callback": self.cb_close},
            ]],
        )

    async def cb_refresh(self, call):
        await call.edit(self._text())

    async def cb_close(self, call):
        await call.delete()
