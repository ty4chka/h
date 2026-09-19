"""Шим utils.* API Hikka — самые часто используемые модулями хелперы."""


async def answer(message, response, **kwargs):
    """Редактирует своё сообщение, либо отвечает на чужое — как в Hikka."""
    is_out = getattr(message, "out", True)
    if is_out:
        try:
            return await message.edit(response, **kwargs)
        except Exception:
            pass
    return await message.reply(response, **kwargs)


def get_args_raw(message) -> str:
    text = getattr(message, "raw_text", None) or getattr(message, "text", "") or ""
    parts = text.split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


def get_args(message) -> list:
    return get_args_raw(message).split()


def get_chat_id(message) -> int:
    return getattr(message, "chat_id", None)


async def get_message_media(message):
    reply = await message.get_reply_message()
    return getattr(reply, "media", None) if reply else None


def escape_html(text: str) -> str:
    import html as _html
    return _html.escape(str(text))
