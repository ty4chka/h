# meta: name=ping version=2.0.0 author=hydra-team framework=hydra
"""Hydra new-shape module: ping with inline form and buttons."""

from hydra_kernel.api import ModuleBase, command


class Ping(ModuleBase):
    name = "ping"
    version = "2.0.0"

    strings = {
        "ru": {"title": "🏓 Понг!", "uptime": "⏱ Аптайм: {uptime} с"},
        "en": {"title": "🏓 Pong!", "uptime": "⏱ Uptime: {uptime} s"},
    }

    @command("ping", desc="пинг с инлайн-формой")
    async def cmd_ping(self, event):
        await self._form(event.chat_id, first=True)

    def _text(self, first: bool) -> str:
        title = self.t("title")
        if not first:
            title += " ♻️"
        return f"{title}\n{self.t('uptime', uptime=int(self.ctx.runtime.uptime))}"

    async def _form(self, chat_id, first=True):
        await self.form(
            chat_id,
            self._text(first),
            buttons=[
                [
                    {"text": self.strings("buttons")("refresh"), "callback": self.cb_refresh},
                    {"text": self.strings("buttons")("close"), "callback": self.cb_close},
                ],
                [{"text": "✏️ Подпись", "input": self.cb_caption}],
            ],
        )

    async def cb_refresh(self, call):
        await call.edit(self._text(first=False))

    async def cb_caption(self, call, text):
        """Кнопка ввода (.it 1 текст): подписывает форму своим текстом."""
        await call.edit(f"🏓 {text}")

    async def cb_close(self, call):
        await call.delete()
