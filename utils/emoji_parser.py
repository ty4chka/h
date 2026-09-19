"""
Шим для utils.emoji_parser — реальный API MCUB-fork
(см. https://github.com/hairpin01/MCUB-fork/blob/main/doc/reference/emoji.md).

Родной формат MCUB: <emoji document_id=123>fallback</emoji>
Формат, который нативно понимает HTML-парсер стокового Telethon: <tg-emoji emoji-id="123">fallback</tg-emoji>

Мы не используем настоящий Telethon-MCUB форк (только сток Telethon), поэтому
здесь просто нормализуем родной формат в тот, что Telethon реально умеет
рендерить как premium-эмодзи.
"""

import re

_EMOJI_TAG_RE = re.compile(r'<emoji\s+document_id=["\']?(\d+)["\']?\s*>(.*?)</emoji>', re.DOTALL)
_TG_EMOJI_RE = re.compile(r'<tg-emoji\s+emoji-id=["\']?(\d+)["\']?\s*>(.*?)</tg-emoji>', re.DOTALL)


def add_emoji(text: str, emoji_id, fallback: str = "🔹") -> str:
    """Добавляет premium-эмодзи в конец текста.

    text = emoji_parser.add_emoji("Hello", emoji_id=5368324170671202286)
    """
    return f'{text}<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def is_emoji_tag(text) -> bool:
    """Есть ли в тексте тег premium-эмодзи (любого из двух форматов)."""
    if not isinstance(text, str):
        return False
    return bool(_EMOJI_TAG_RE.search(text) or _TG_EMOJI_RE.search(text))


def normalize(text: str) -> str:
    """Родной MCUB-формат <emoji document_id=X> -> формат Telethon <tg-emoji emoji-id="X">."""
    if not isinstance(text, str):
        return text
    return _EMOJI_TAG_RE.sub(r'<tg-emoji emoji-id="\1">\2</tg-emoji>', text)


def parse_to_entities(text: str):
    """Парсит текст с premium-эмодзи в (plain_text, entities) через
    нативный HTML-парсер Telethon — им и рендерятся настоящие custom emoji."""
    from telethon.extensions import html as _html
    normalized = normalize(text)
    plain, entities = _html.parse(normalized)
    return plain, entities

