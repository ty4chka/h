# mcub_engine/bridge.py
"""
ButtonBridge — превращает инлайн-кнопки MCUB в команды.

Юзербот не может получать CallbackQuery (они приходят только ботам),
поэтому каждая кнопка рендерится строкой меню с командой:

    🔘 Play → .cb 1
    ⏭  Next → .cb 2

Пользователь отправляет `.cb 1` — мост вызывает оригинальный
обработчик кнопки с CallbackEventMock, который умеет редактировать
меню (пагинация/переключатели работают как в MCUB).
"""

from __future__ import annotations

import html
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("mcub_engine.bridge")

try:
    from utils import emoji_parser as _emoji_parser
except Exception:
    try:
        import emoji_parser as _emoji_parser
    except Exception:
        _emoji_parser = None


def _normalize_emoji(text: str) -> str:
    """Прогоняет текст через emoji_parser.normalize(), если модуль доступен."""
    if _emoji_parser is None or not text:
        return text
    try:
        return _emoji_parser.normalize(text)
    except Exception:
        return text

MAX_TEXT = 4000  # лимит сообщения Telegram с запасом


@dataclass
class ButtonEntry:
    kind: str          # cb | url | switch | input | text
    label: str
    payload: Any = None  # token / url / query / uuid


@dataclass
class MenuRecord:
    chat_id: Any
    message_id: int
    entries: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class ButtonBridge:
    def __init__(self, kernel):
        self.kernel = kernel
        # chat_id -> последнее меню
        self._menus: dict[Any, MenuRecord] = {}
        self._last_chat = None
        self._max_menus = 200

    # ========================================================
    # РАЗБОР КНОПОК
    # ========================================================

    def _flatten(self, buttons):
        """Приводит buttons к списку рядов списка кнопок."""
        if buttons is None:
            return []
        if not isinstance(buttons, (list, tuple)):
            buttons = [buttons]
        rows = []
        for row in buttons:
            if isinstance(row, (list, tuple)):
                rows.append(list(row))
            else:
                rows.append([row])
        return rows

    def _button_text(self, btn) -> str:
        text = getattr(btn, "text", None)
        if text is None and isinstance(btn, dict):
            text = btn.get("text")
        if text is None:
            inner = getattr(btn, "button", None)
            text = getattr(inner, "text", None)
        return str(text) if text is not None else "❔"

    def _classify(self, btn) -> ButtonEntry:
        """Определяет тип кнопки и извлекает payload."""
        # dict-кнопка Button.input из нашего ButtonFactory
        if isinstance(btn, dict):
            if btn.get("_mcub_input"):
                return ButtonEntry("input", self._button_text(btn),
                                   (btn.get("uuid"), btn.get("placeholder", "")))
            return ButtonEntry("text", self._button_text(btn))

        # Telethon types
        type_name = type(btn).__name__
        inner = getattr(btn, "button", btn)
        inner_type = type(inner).__name__

        if inner_type == "KeyboardButtonUrl" or type_name == "KeyboardButtonUrl":
            return ButtonEntry("url", self._button_text(btn), getattr(inner, "url", ""))

        if inner_type == "KeyboardButtonSwitchInline" or "switch" in type_name.lower():
            query = getattr(inner, "query", "") or ""
            return ButtonEntry("switch", self._button_text(btn), query)

        if inner_type == "KeyboardButtonCallback" or type_name in ("Button", "KeyboardButtonCallback"):
            data = getattr(inner, "data", None)
            if data is None:
                data = getattr(btn, "data", None)
            if data is not None:
                if isinstance(data, str):
                    data = data.encode()
                return ButtonEntry("cb", self._button_text(btn), data)
            return ButtonEntry("text", self._button_text(btn))

        if inner_type in ("KeyboardButton", "InputKeyboardButtonUserProfile"):
            return ButtonEntry("text", self._button_text(btn))

        # объекты вида make_cb_button (text + data)
        data = getattr(btn, "data", None)
        if data is not None:
            if isinstance(data, str):
                data = data.encode()
            return ButtonEntry("cb", self._button_text(btn), data)

        return ButtonEntry("text", self._button_text(btn))

    # ========================================================
    # РЕНДЕР МЕНЮ (компактный формат)
    # ========================================================

    def render_menu(self, buttons, prefix=".") -> tuple[str, list]:
        """Возвращает компактное HTML-меню, кнопки идут по 2 в ряд —
        так же, как расположены инлайн-кнопки в оригинальном MCUB."""
        entries = []
        rows = self._flatten(buttons)
        for row in rows:
            for btn in row:
                entries.append(self._classify(btn))

        if not entries:
            return "", []

        cb_entries = [e for e in entries if e.kind == "cb"]
        url_entries = [e for e in entries if e.kind == "url"]
        switch_entries = [e for e in entries if e.kind == "switch"]
        input_entries = [e for e in entries if e.kind == "input"]
        text_entries = [e for e in entries if e.kind == "text"]

        for i, entry in enumerate(cb_entries, 1):
            entry.menu_index = i

        lines = []

        # Callback-кнопки — по 2 в ряд, сохраняя исходную раскладку рядов
        # (row-структуру buttons), как в оригинальном инлайн-меню.
        if cb_entries:
            lines.append("<b>⚙️ Меню:</b>")
            idx = 1
            for row in rows:
                row_cb = [self._classify(b) for b in row if self._classify(b).kind == "cb"]
                if not row_cb:
                    continue
                row_items = []
                for _ in row_cb:
                    entry = cb_entries[idx - 1]
                    label = html.escape(entry.label)
                    row_items.append(f"<code>{prefix}cb {idx}</code> {label}")
                    idx += 1
                lines.append(" ┃ ".join(row_items))

        if url_entries:
            lines.append("<b>🔗 Ссылки:</b>")
            for entry in url_entries:
                label = html.escape(entry.label)
                url = html.escape(str(entry.payload), quote=True)
                lines.append(f"<a href='{url}'>↗ {label}</a>")

        if switch_entries:
            lines.append("<b>🔎 Поиск:</b>")
            for entry in switch_entries:
                label = html.escape(entry.label)
                q = html.escape(str(entry.payload))
                lines.append(f"<code>{prefix}iq {q}</code> — {label}")

        if input_entries:
            lines.append("<b>✏️ Ввод:</b>")
            for entry in input_entries:
                uuid, placeholder = entry.payload
                short = str(uuid)[:6]
                hint = html.escape(placeholder) if placeholder else "текст"
                label = html.escape(entry.label)
                lines.append(f"<code>{prefix}it {short}</code> {label} ({hint})")

        if text_entries:
            for entry in text_entries:
                lines.append(html.escape(entry.label))

        menu_html = "\n".join(lines) if lines else ""
        return _normalize_emoji(menu_html), entries

    def _register_menu(self, chat_id, message_id, entries):
        rec = MenuRecord(chat_id=chat_id, message_id=message_id, entries=entries)
        self._menus[chat_id] = rec
        self._last_chat = chat_id
        if len(self._menus) > self._max_menus:
            oldest = sorted(self._menus.items(), key=lambda kv: kv[1].created_at)
            for k, _ in oldest[: len(self._menus) - self._max_menus]:
                self._menus.pop(k, None)
        return rec

    # ========================================================
    # ОТПРАВКА / РЕДАКТИРОВАНИЕ С КНОПКАМИ
    # ========================================================

    async def send_rendered(self, chat_id, text, buttons=None, prefix=None,
                            parse_mode="html", reply_to=None, **kwargs):
        """Отправить сообщение, отрендерив кнопки как команды."""
        prefix = prefix or self.kernel.custom_prefix
        real = self.kernel._real_client
        menu_html, entries = self.render_menu(buttons, prefix)
        text = _normalize_emoji(text or "")

        full = self._merge(text, menu_html)
        try:
            msg = await real.send_message(
                chat_id, full, parse_mode=parse_mode,
                reply_to=reply_to, **kwargs
            )
        except Exception:
            # fallback без parse_mode (если в тексте битый HTML)
            plain = self._strip_html(full)
            msg = await real.send_message(chat_id, plain, reply_to=reply_to, **kwargs)
        if entries:
            self._register_menu(chat_id, msg.id, entries)
        return msg

    async def edit_rendered(self, chat_id, message, text, buttons=None,
                            prefix=None, parse_mode="html", **kwargs):
        """Отредактировать сообщение, отрендерив кнопки как команды."""
        prefix = prefix or self.kernel.custom_prefix
        menu_html, entries = self.render_menu(buttons, prefix)
        text = _normalize_emoji(text or "")
        full = self._merge(text, menu_html)
        try:
            if hasattr(message, "edit"):
                await message.edit(full, parse_mode=parse_mode, **kwargs)
            else:
                # try to guess if it's Telethon Message or Event
                if hasattr(message, "message"):
                    # It's likely an Event
                    await message.message.edit(full, parse_mode=parse_mode, **kwargs)
        except Exception:
            if hasattr(message, "edit_text"):
                await message.edit_text(full, parse_mode=parse_mode, **kwargs)
            else:
                # сообщение нельзя редактировать (например, чужое) — шлём новое
                try:
                    msg = await message.reply(full, parse_mode=parse_mode, **kwargs)
                except Exception:
                    msg = await self.kernel._real_client.send_message(
                        chat_id, self._strip_html(full), **kwargs
                    )
        if entries:
            mid = message.id if hasattr(message, "id") else (message.message.id if hasattr(message, "message") else message.id)
            self._register_menu(chat_id, mid, entries)
        return message

    async def send_notification(self, chat_id, text):
        """Короткое уведомление от callback.answer()."""
        try:
            return await self.kernel._real_client.send_message(
                chat_id, f"🔔 {text}", parse_mode="html"
            )
        except Exception:
            return await self.kernel._real_client.send_message(chat_id, f"🔔 {text}")

    # ========================================================
    # ОБРАБОТКА КОМАНД МОСТА
    # ========================================================

    def _find_menu(self, chat_id):
        rec = self._menus.get(chat_id)
        if rec is None and self._last_chat is not None:
            rec = self._menus.get(self._last_chat)
        return rec

    async def handle_cb(self, event, index: int) -> bool:
        """.cb N — «нажать» кнопку N из последнего меню."""
        rec = self._find_menu(event.chat_id)
        if rec is None:
            await event.reply("❌ <b>Нет активного меню кнопок</b>", parse_mode="html")
            return True

        cb_entries = [e for e in rec.entries if e.kind == "cb"]
        if not (1 <= index <= len(cb_entries)):
            await event.reply(
                f"❌ <b>Кнопка #{index} не найдена</b> (всего {len(cb_entries)})",
                parse_mode="html",
            )
            return True

        entry = cb_entries[index - 1]
        token = entry.payload
        token_key = token.decode(errors="ignore") if isinstance(token, bytes) else str(token)
        data = self.kernel.inline_callback_map.get(token_key)
        if data is None:
            data = self.kernel.inline_callback_map.get(token)  # на случай bytes-ключей

        # prefix-based callback handlers (register_callback_handler)
        if data is None:
            decoded = token_key
            for prefix, func in list(self.kernel._callback_handlers.items()):
                if decoded.startswith(prefix):
                    data = {"handler": func, "args": [decoded], "kwargs": {}}
                    break

        if data is None:
            await event.reply(
                f"⏰ <b>Кнопка «{html.escape(entry.label)}» устарела</b>\n"
                f"<i>Вызови команду модуля заново</i>",
                parse_mode="html",
            )
            return True

        exp = data.get("expires_at")
        if exp and exp < time.time():
            self.kernel.inline_callback_map.pop(token_key, None)
            self.kernel.inline_callback_map.pop(token, None)
            await event.reply("⏰ <b>Кнопка устарела (TTL)</b>", parse_mode="html")
            return True

        # исходное сообщение меню — цель для .edit() колбэка
        menu_msg = None
        try:
            msgs = await self.kernel._real_client.get_messages(
                rec.chat_id, ids=rec.message_id
            )
            menu_msg = msgs
        except Exception:
            pass

        from .proxies import CallbackEventMock
        mock = CallbackEventMock(
            self.kernel, menu_msg, rec.chat_id,
            data=token if isinstance(token, bytes) else str(token).encode(),
        )

        handler = data["handler"]
        args = list(data.get("args", []))
        kwargs = dict(data.get("kwargs", {}))
        # как в MCUB: пользовательский data кнопки идёт в handler как data=...
        if "data" not in kwargs and data.get("data") is not None:
            kwargs["data"] = data.get("data")
        try:
            await handler(mock, *args, **kwargs)
        except Exception as e:
            logger.error(f"callback handler error: {e}", exc_info=True)
            await self.kernel.handle_error(e, source=f"callback '{entry.label}'", event=event)
        return True

    async def handle_it(self, event, short_uuid: str, args_text: str) -> bool:
        """.it <uuid8> <текст> — ввод для input-кнопки / inline_temp."""
        form_id = None
        for fid in self.kernel._inline_temps:
            if fid.startswith(short_uuid):
                form_id = fid
                break
        if form_id is None:
            await event.reply("❌ <b>Обработчик ввода не найден или устарел</b>",
                              parse_mode="html")
            return True

        rec = self.kernel._inline_temps[form_id]
        if rec.get("expires_at") and rec["expires_at"] < time.time():
            self.kernel._inline_temps.pop(form_id, None)
            await event.reply("⏰ <b>Обработчик ввода устарел</b>", parse_mode="html")
            return True

        from .proxies import InlineQueryEventMock
        mock = InlineQueryEventMock(self.kernel, event.chat_id,
                                    f"{short_uuid} {args_text}",
                                    sender_id=getattr(event, "sender_id", None))
        try:
            func = rec["func"]
            bound = getattr(func, "__bound_instance__", None)
            raw = getattr(func, "__original__", func)
            if bound is not None:
                await raw(bound, mock, args_text, rec.get("data"))
            else:
                await func(mock, args_text, rec.get("data"))
        except TypeError:
            try:
                await rec["func"](mock, args_text)
            except Exception as e:
                await self.kernel.handle_error(e, source="inline_temp", event=event)
        except Exception as e:
            await self.kernel.handle_error(e, source="inline_temp", event=event)
        return True

    async def handle_iq(self, event, query: str) -> bool:
        """.iq <запрос> — локальный инлайн-поиск."""
        ok, err = await self.kernel.inline_query_and_click(event.chat_id, query)
        if not ok and err:
            await event.reply(f"❌ {html.escape(err)}", parse_mode="html")
        elif ok:
            try:
                await event.delete()
            except Exception:
                pass
        return True

    async def show_menu(self, event):
        """.cb без номера — показать текущее меню ещё раз."""
        rec = self._find_menu(event.chat_id)
        if rec is None:
            await event.reply("❌ <b>Нет активного меню кнопок</b>", parse_mode="html")
            return True
        prefix = self.kernel.custom_prefix
        menu_html, _ = self.render_menu([e for e in rec.entries], prefix)
        await event.reply(menu_html or "❌ <b>Меню пусто</b>", parse_mode="html")
        return True

    # ========================================================
    # УТИЛИТЫ ТЕКСТА
    # ========================================================

    @staticmethod
    def _merge(text, menu_html):
        if not menu_html:
            return text
        combined = (text or "") + "\n" + menu_html
        if len(combined) > MAX_TEXT:
            combined = combined[: MAX_TEXT - len(menu_html) - 10] + "…" + menu_html
        return combined

    @staticmethod
    def _strip_html(text):
        import re
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"</p>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(text)

