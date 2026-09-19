# meta: name=text version=1.0.0 author=hydra-team framework=hydra
"""Текстовые инструменты: регистр, mock, reverse, счётчики.

.text <оп> <текст>  — преобразование + форма с кнопками
.text               — форма с вводом через .it
"""

from hydra_kernel.api import ModuleBase, command


def _mock(s: str) -> str:
    return "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(s))


OPS = {
    "upper": str.upper,
    "lower": str.lower,
    "title": str.title,
    "capitalize": str.capitalize,
    "reverse": lambda s: s[::-1],
    "mock": _mock,
}


class Text(ModuleBase):
    name = "text"
    version = "1.0.0"

    strings = {
        "ru": {
            "usage": "📝 Использование: <code>.text upper|lower|title|mock|reverse текст</code>",
            "result": "📝 Результат",
            "count": "🔢 слов: {words} · символов: {chars}",
        },
        "en": {
            "usage": "📝 Usage: <code>.text upper|lower|title|mock|reverse text</code>",
            "result": "📝 Result",
            "count": "🔢 words: {words} · chars: {chars}",
        },
    }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._last = {}  # chat -> (op, text)

    @command("text", desc="upper|lower|title|mock|reverse <текст>, форма с кнопками")
    async def cmd_text(self, event):
        args = event.text.split(maxsplit=1)
        args = args[1] if len(args) > 1 else ""
        parts = args.split(maxsplit=1)
        op = parts[0].lower() if parts else ""
        payload = parts[1] if len(parts) > 1 else ""
        if op in OPS and payload:
            self._last[event.chat_id] = (op, payload)
        elif args:
            self._last[event.chat_id] = ("", args)
        else:
            self._last.setdefault(event.chat_id, ("", ""))
        await self._form(event.chat_id)

    def _body(self, chat_id) -> str:
        op, text = self._last.get(chat_id, ("", ""))
        if not text:
            return self.t("usage")
        shown = OPS[op](text) if op in OPS else text
        words = len(text.split())
        head = f"{op}: " if op else ""
        return (
            f"{self.t('result')}: {head}<code>{shown}</code>\n"
            f"{self.t('count', words=words, chars=len(text))}"
        )

    async def _form(self, chat_id):
        await self.form(
            chat_id,
            self._body(chat_id),
            buttons=[
                [
                    {"text": "⬆️ upper", "callback": self.cb_op, "args": ("upper",)},
                    {"text": "⬇️ lower", "callback": self.cb_op, "args": ("lower",)},
                    {"text": "🔤 title", "callback": self.cb_op, "args": ("title",)},
                ],
                [
                    {"text": "🎭 mock", "callback": self.cb_op, "args": ("mock",)},
                    {"text": "🔄 reverse", "callback": self.cb_op, "args": ("reverse",)},
                ],
                [{"text": "✏️ Новый текст", "input": self.cb_set}],
            ],
        )

    async def cb_op(self, call, op):
        chat = call.chat_id
        _, text = self._last.get(chat, ("", ""))
        if not text:
            text = "пример текста"
        self._last[chat] = (op, text)
        await call.edit(self._body(chat))

    async def cb_set(self, call, text):
        chat = call.chat_id
        op, _ = self._last.get(chat, ("", ""))
        self._last[chat] = (op, text)
        await call.edit(self._body(chat))
