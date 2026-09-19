"""L1 — inline: кнопки, результаты, события inline-запросов и callback'ов.

Семантика совместима с MCUB-реализацией (core/lib/telethon_mcub.py):
- inline роутится по первому слову запроса (имени хэндлера);
- InlineQueryEvent даёт .builder.article(...) и .answer(results);
- answer() пытается нативно ответить через транспорт, при невозможности —
  фолбэк: результаты уходят сообщением, как в MCUB.
- callback роутится по самому длинному префиксу data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

# ------------------------------------------------------------------ кнопки


@dataclass
class InlineButton:
    text: str
    data: Optional[str] = None
    url: Optional[str] = None

    def __post_init__(self) -> None:
        if self.data is None and self.url is None:
            raise ValueError("InlineButton требует data или url")


@dataclass
class InlineResult:
    """Готовая inline-форма: текст + ряды кнопок."""

    title: str
    description: str = ""
    body: str = ""
    buttons: List[List[InlineButton]] = field(default_factory=list)

    def row(self, *buttons: InlineButton) -> "InlineResult":
        self.buttons.append(list(buttons))
        return self


# ------------------------------------------------------------------ результаты


@dataclass
class InlineArticleResult:
    title: str
    description: str = ""
    text: str = ""
    parse_mode: str = "html"

    @property
    def id(self) -> str:
        return f"article_{hash(self.title) & 0x7FFFFFFF}"


@dataclass
class InlinePhotoResult:
    url: str
    title: str = ""
    description: str = ""

    @property
    def id(self) -> str:
        return f"photo_{hash(self.url) & 0x7FFFFFFF}"


class InlineResultBuilder:
    """Builder как в MCUB: article/photo."""

    def article(
        self, title: str, description: str = "", text: str = "", parse_mode: str = "html", **kw: Any
    ) -> InlineArticleResult:
        return InlineArticleResult(title, description, text, parse_mode)

    def photo(self, url: str, title: str = "", description: str = "", **kw: Any) -> InlinePhotoResult:
        return InlinePhotoResult(url, title, description)


# ------------------------------------------------------------------ события


class InlineQueryEvent:
    """Событие inline-запроса. name — имя хэндлера (первое слово query)."""

    def __init__(
        self,
        name: str,
        query: str,
        sender_id: int,
        transport: Any = None,
        raw: Any = None,
    ):
        self.name = name
        self.query = query
        self.text = query
        self.sender_id = sender_id
        self.raw = raw
        self._t = transport
        self.builder = InlineResultBuilder()

    @property
    def args(self) -> str:
        """Всё после имени хэндлера."""
        parts = self.query.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else ""

    async def answer(self, results: List[Any], **kw: Any) -> Any:
        if not results:
            return None
        if self._t is not None and hasattr(self._t, "answer_inline"):
            return await self._t.answer_inline(self, results, **kw)
        # фолбэк в стиле MCUB: результаты сообщением
        out = "<b>Results (inline):</b>\n\n"
        for art in results[:5]:
            out += f"<b>{getattr(art, 'title', '')}</b>\n"
            desc = getattr(art, "description", "")
            if desc:
                out += f"<i>{desc}</i>\n"
            out += f"{getattr(art, 'text', '')}\n\n"
        if self._t is not None:
            return await self._t.send(self.sender_id, out)
        return out


class CallbackQueryEvent:
    """Событие нажатия инлайн-кнопки. Роутинг по префиксу data — на ядре."""

    def __init__(
        self,
        data: str,
        sender_id: int,
        chat_id: int = 0,
        message_id: int = 0,
        transport: Any = None,
        raw: Any = None,
    ):
        self.data = data
        self.query = data
        self.sender_id = sender_id
        self.chat_id = chat_id
        self.message_id = message_id
        self.raw = raw
        self._t = transport

    async def answer(self, text: Optional[str] = None, alert: bool = False, **kw: Any) -> Any:
        if self._t is not None and hasattr(self._t, "answer_callback"):
            return await self._t.answer_callback(self, text, alert, **kw)
        if text and self._t is not None:
            return await self._t.send(self.sender_id, text)
        return None

    async def edit(self, text: str, **kw: Any) -> Any:
        if self._t is not None:
            return await self._t.edit(self.chat_id, self.message_id, text, **kw)
        return None

    async def delete(self) -> Any:
        if self._t is not None and hasattr(self._t, "delete"):
            return await self._t.delete(self.chat_id, self.message_id)
        return None
