# mcub_engine/bridge.py
"""
ButtonBridge — превращает инлайн-кнопки MCUB в команды.

Юзербот не может получать CallbackQuery (они приходят только ботам),
поэтому каждая кнопка рендерится строкой меню с командой:

    .cb 1 — ▶️ Play
    .cb 2 — ⏭ Next

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
    # РЕНДЕР МЕНЮ
    # ========================================================

    def render_menu(self, buttons, prefix=".") -> tuple[str, list]:
        """Возвращает (html-блок меню, entries)."""
        entries = []
        rows = self._flatten(buttons)
        for row in rows:
            for btn in row:
                entries.append(self._classify(btn))

        if not entries:
            return "", []

        cb_index = 0
        lines = ["", "<b>⚡ Кнопки → команды:</b>"]
        for entry in entries:
            label = html.escape(entry.label)
            if entry.kind == "cb":
                cb_index += 1
                entry.menu_index = cb_index
                lines.append(f"<code>{prefix}cb {cb_index}</code> — {label}")
            elif entry.kind == "url":
                url = html.escape(str(entry.payload), quote=True)
                lines.append(f"🔗 <a href='{url}'>{label}</a>")
            elif entry.kind == "switch":
                q = html.escape(str(entry.payload))
                lines.append(f"🔍 {label} → <code>{prefix}iq {q}</code>")
            elif entry.kind == "input":
                uuid, placeholder = entry.payload
                short = str(uuid)[:8]
                hint = f" {html.escape(placeholder)}" if placeholder else " &lt;текст&gt;"
                lines.append(f"✏️ {label} → <code>{prefix}it {short}{hint}</code>")
            else:
                lines.append(f"⌨️ {label} <i>(текстовая кнопка)</i>")
        return "\n".join(lines), entries

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

        full = self._merge(text or "", menu_html)
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
        full = self._merge(text or "", menu_html)
        try:
            if hasattr(message, "edit"):
                msg = await message.edit(full, parse_mode=parse_mode, **kwargs)
            else:
                msg = await self.kernel._real_client.edit_message(
                    chat_id, message, full, parse_mode=parse_mode, **kwargs
                )
        except Exception as e:
            if "not modified" in str(e).lower():
                msg = message
            else:
                logger.debug(f"edit_rendered fallback: {e}")
                try:
                    msg = await self.kernel._real_client.send_message(
                        chat_id, self._strip_html(full), **kwargs
                    )
                except Exception:
                    msg = message
        if entries:
            chat = chat_id if chat_id is not None else getattr(msg, "chat_id", None)
            self._register_menu(chat, getattr(msg, "id", None), entries)
        return msg

    async def edit_rendered_event(self, event, text, buttons=None,
                                  parse_mode="html", **kwargs):
        """edit() для EventProxy: редактирует исходное сообщение."""
        menu_html, entries = self.render_menu(buttons, self.kernel.custom_prefix)
        full = self._merge(text or "", menu_html)
        try:
            msg = await event.edit(full, parse_mode=parse_mode, **kwargs)
        except Exception as e:
            if "not modified" in str(e).lower():
                msg = getattr(event, "message", event)
            else:
                # сообщение нельзя редактировать (например, чужое) — шлём новое
                try:
                    msg = await event.reply(full, parse_mode=parse_mode, **kwargs)
                except Exception:
                    msg = await self.kernel._real_client.send_message(
                        event.chat_id, self._strip_html(full), **kwargs
                    )
        if entries:
            self._register_menu(event.chat_id, getattr(msg, "id", event.id), entries)
        return msg

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
            await self.kernel.handle_error(e, source=f"callback '{entry.label}'")
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
                await self.kernel.handle_error(e, source="inline_temp")
        except Exception as e:
            await self.kernel.handle_error(e, source="inline_temp")
        return True

    async def handle_iq(self, event, query: str) -> bool:
        """.iq <запрос> — локальный инлайн-поиск."""
        ok, err = await self.kernel.inline_query_and_click(event.chat_id, query)
        if not ok and err:
            await event.reply(f"❌ {html.escape(err)}", parse_mode="html")
        return True

    async def show_menu(self, event):
        """.cb без номера — показать текущее меню ещё раз."""
        rec = self._find_menu(event.chat_id)
        if rec is None:
            await event.reply("❌ <b>Нет активного меню кнопок</b>", parse_mode="html")
            return True
        prefix = self.kernel.custom_prefix
        lines = [f"<b>⚡ Активное меню</b> (сообщение #{rec.message_id}):"]
        n = 0
        for entry in rec.entries:
            label = html.escape(entry.label)
            if entry.kind == "cb":
                n += 1
                lines.append(f"<code>{prefix}cb {n}</code> — {label}")
            elif entry.kind == "url":
                lines.append(f"🔗 <a href='{html.escape(str(entry.payload), quote=True)}'>{label}</a>")
            elif entry.kind == "switch":
                lines.append(f"🔍 {label} → <code>{prefix}iq {html.escape(str(entry.payload))}</code>")
            elif entry.kind == "input":
                uuid, placeholder = entry.payload
                lines.append(f"✏️ {label} → <code>{prefix}it {str(uuid)[:8]} &lt;текст&gt;</code>")
        await event.reply("\n".join(lines), parse_mode="html")
        return True

    # ========================================================
    # УТИЛИТЫ ТЕКСТА
    # ========================================================

    @staticmethod
    def _merge(text, menu_html):
        if not menu_html:
            return text
        combined = (text or "") + menu_html
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
