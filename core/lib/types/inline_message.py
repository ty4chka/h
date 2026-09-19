# core/lib/types/inline_message.py
# Совместимый InlineMessage: делегирует в InlineMessageMock движка.
from __future__ import annotations


class InlineMessage:
    """Обёртка над отправленным сообщением «инлайн-формы»."""

    def __init__(self, message, unit_id=None, kernel=None, form_id=None):
        self._message = message
        self._kernel = kernel
        self.form_id = form_id or unit_id
        self.unit_id = self.form_id
        self.chat_id = getattr(message, "chat_id", None)
        self.id = getattr(message, "id", None)
        self.message_id = self.id

    @property
    def message(self):
        return self._message

    async def edit(self, text, buttons=None, **kwargs):
        if self._kernel is not None and self._message is not None:
            return await self._kernel.bridge.edit_rendered(
                self.chat_id, self._message, text, buttons=buttons, **kwargs
            )
        if self._message is not None:
            return await self._message.edit(text, **kwargs)

    async def delete(self):
        try:
            if self._message is not None:
                await self._message.delete()
        except Exception:
            pass
