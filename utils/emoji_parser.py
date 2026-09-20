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


# ---------------------------------------------------------------------------
# Поверхность EmojiParser из MCUB-fork (utils/emoji_parser.py).
# Объединена с нашими tg-emoji-хелперами: родной формат <emoji document_id=N>
# прозрачно нормализуется в <tg-emoji emoji-id="N">, который умеет сток Telethon.
# ---------------------------------------------------------------------------

import html as _html_module


class EmojiParser:
    """Emoji parser for MCUB with improved handling (порт MCUB-fork)."""

    _EMOJI_TAG_PATTERN = re.compile(r"<emoji\s+document_id=(\d+)>(.*?)</emoji>")
    _EMOJI_ID_PATTERN = re.compile(r"<emoji\s+document_id=(\d+)>")
    _ALL_EMOJI_TAGS_PATTERN = re.compile(r"<emoji\s+[^>]*>.*?</emoji>")

    @staticmethod
    def parse_to_entities(text):
        return parse_to_entities(text)

    @staticmethod
    def entities_to_html(text, entities):
        """Преобразует сущности сообщения в HTML-подобный формат MCUB."""
        if not entities:
            return _html_module.escape(text)

        from telethon.tl.types import MessageEntityCustomEmoji

        sorted_entities = sorted(
            entities,
            key=lambda e: e.offset if hasattr(e, "offset") else 0,
            reverse=True,
        )
        utf16_text = text.encode("utf-16-le")
        for entity in sorted_entities:
            if isinstance(entity, MessageEntityCustomEmoji):
                try:
                    byte_start = entity.offset * 2
                    byte_end = (entity.offset + entity.length) * 2
                    emoji_bytes = utf16_text[byte_start:byte_end]
                    emoji_text = emoji_bytes.decode("utf-16-le")
                    before = text[: entity.offset]
                    after = text[entity.offset + entity.length :]
                    text = f"{before}<emoji document_id={entity.document_id}>{emoji_text}</emoji>{after}"
                except (IndexError, UnicodeDecodeError):
                    continue

        return _html_module.escape(text)

    @staticmethod
    def is_emoji_tag(text):
        return is_emoji_tag(text)

    @staticmethod
    def extract_emoji_ids(text):
        ids = []
        for match in EmojiParser._EMOJI_ID_PATTERN.findall(text):
            try:
                ids.append(int(match))
            except (ValueError, TypeError):
                continue
        for match in _TG_EMOJI_RE.finditer(text):
            try:
                ids.append(int(match.group(1)))
            except (ValueError, TypeError):
                continue
        return ids

    @staticmethod
    def remove_emoji_tags(text):
        """Удаляет теги эмодзи, оставляя только текст-заполнитель."""
        text = EmojiParser._ALL_EMOJI_TAGS_PATTERN.sub(
            lambda m: (
                m.group(0).split(">", 1)[1].rsplit("<", 1)[0]
                if ">" in m.group(0) and "<" in m.group(0)
                else ""
            ),
            text,
        )
        return _TG_EMOJI_RE.sub(r"\2", text)

    @staticmethod
    def extract_custom_emoji_entities(message):
        """Извлекает кастомные эмодзи из полученного сообщения."""
        if not message or not message.entities:
            return []

        from telethon.tl.types import MessageEntityCustomEmoji

        return [
            entity
            for entity in message.entities
            if isinstance(entity, MessageEntityCustomEmoji)
        ]

    @staticmethod
    def validate_emoji_content(emoji_text):
        """Telegram требует, чтобы внутри тега был ровно один обычный эмодзи."""
        if not emoji_text:
            return False
        emoji_pattern = re.compile(
            r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+",
            flags=re.UNICODE,
        )
        return bool(emoji_pattern.fullmatch(emoji_text))

    @staticmethod
    def create_emoji_tag(document_id, placeholder="🔴"):
        """Создаёт HTML-тег для кастомного эмодзи."""
        return f"<emoji document_id={document_id}>{placeholder}</emoji>"

    @staticmethod
    def normalize(text):
        """Хидра-дополнение: <emoji document_id=N> -> <tg-emoji emoji-id="N">."""
        return normalize(text)


# Global instance for backward compatibility (как в MCUB-fork)
emoji_parser = EmojiParser()

