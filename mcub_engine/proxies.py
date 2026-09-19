# mcub_engine/proxies.py
"""
Прокси-объекты: перехватывают кнопки и направляют их в ButtonBridge,
чтобы каждая инлайн-кнопка превращалась в видимую команду.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

logger = logging.getLogger("mcub_engine.proxies")


# ============================================================
# CLIENT PROXY — kernel.client / module.client
# ============================================================

class ClientProxy:
    """Обёртка над Telethon client: send_message/edit_message без кнопок,
    кнопки рендерятся текстом через мост."""

    def __init__(self, real_client, kernel, module_name: str | None = None):
        object.__setattr__(self, "_real", real_client)
        object.__setattr__(self, "_kernel", kernel)
        object.__setattr__(self, "_module_name", module_name)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_real"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_real"), name, value)

    @property
    def real_client(self):
        return object.__getattribute__(self, "_real")

    async def send_message(self, entity, message="", **kwargs):
        kernel = object.__getattribute__(self, "_kernel")
        buttons = kwargs.pop("buttons", None)
        if buttons:
            return await kernel.bridge.send_rendered(
                entity, message, buttons=buttons, **kwargs
            )
        return await object.__getattribute__(self, "_real").send_message(
            entity, message, **kwargs
        )

    async def edit_message(self, entity, message=None, text=None, **kwargs):
        kernel = object.__getattribute__(self, "_kernel")
        buttons = kwargs.pop("buttons", None)
        real = object.__getattribute__(self, "_real")
        if buttons:
            return await kernel.bridge.edit_rendered(
                entity, message, text if text is not None else "",
                buttons=buttons, **kwargs
            )
        return await real.edit_message(entity, message, text, **kwargs)

    async def send_file(self, entity, file, **kwargs):
        buttons = kwargs.pop("buttons", None)
        if buttons:
            # Кнопки рядом с файлом — подписью-меню отдельным сообщением
            kernel = object.__getattribute__(self, "_kernel")
            msg = await object.__getattribute__(self, "_real").send_file(
                entity, file, **kwargs
            )
            await kernel.bridge.send_rendered(entity, "<b>⚡ Действия:</b>",
                                              buttons=buttons)
            return msg
        return await object.__getattribute__(self, "_real").send_file(
            entity, file, **kwargs
        )


# ============================================================
# EVENT PROXY — событие, которое получают команды модулей
# ============================================================

class EventProxy:
    """Обёртка Telethon event: edit/reply/respond с кнопками → текст+команды."""

    def __init__(self, event, kernel):
        object.__setattr__(self, "_event", event)
        object.__setattr__(self, "_kernel", kernel)

    def __getattr__(self, name):
        if name == "client":
            return object.__getattribute__(self, "_kernel").client
        return getattr(object.__getattribute__(self, "_event"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_event"), name, value)

    def no_owner(self):
        return False  # в юзерботе владелец — сам пользователь

    # ---- отправка с перехватом кнопок ----

    async def edit(self, text=None, **kwargs):
        kernel = object.__getattribute__(self, "_kernel")
        event = object.__getattribute__(self, "_event")
        buttons = kwargs.pop("buttons", None)
        if isinstance(text, str) and "<emoji" in text:
            from utils.emoji_parser import normalize as _norm_emoji
            text = _norm_emoji(text)
        if buttons:
            return await kernel.bridge.edit_rendered_event(
                event, text or "", buttons=buttons, **kwargs
            )
        try:
            return await event.edit(text, **kwargs)
        except Exception as e:
            if "not modified" in str(e).lower():
                return None
            raise

    async def reply(self, message="", **kwargs):
        kernel = object.__getattribute__(self, "_kernel")
        event = object.__getattribute__(self, "_event")
        buttons = kwargs.pop("buttons", None)
        if isinstance(message, str) and "<emoji" in message:
            from utils.emoji_parser import normalize as _norm_emoji
            message = _norm_emoji(message)
        if buttons:
            return await kernel.bridge.send_rendered(
                event.chat_id, message, buttons=buttons,
                reply_to=event.id, **kwargs
            )
        return await event.reply(message, **kwargs)

    async def respond(self, message="", **kwargs):
        kernel = object.__getattribute__(self, "_kernel")
        event = object.__getattribute__(self, "_event")
        buttons = kwargs.pop("buttons", None)
        if buttons:
            return await kernel.bridge.send_rendered(
                event.chat_id, message, buttons=buttons, **kwargs
            )
        return await event.respond(message, **kwargs)

    async def answer(self, text=None, **kwargs):
        event = object.__getattribute__(self, "_event")
        if hasattr(event, "answer"):
            try:
                return await event.answer(text, **kwargs)
            except Exception:
                pass
        if text:
            return await self.reply(text, **kwargs)
        return None


# ============================================================
# CALLBACK EVENT MOCK — событие «нажатия кнопки» из команды .cb N
# ============================================================

class CallbackEventMock:
    """Эмуляция CallbackQuery для обработчиков кнопок.
    .edit() редактирует исходное меню, .answer() шлёт уведомление в чат."""

    def __init__(self, kernel, menu_message, chat_id, data: bytes = b"", module_name=None):
        self._kernel = kernel
        self._menu_message = menu_message
        self.chat_id = chat_id
        self.data = data
        self.query = data.decode(errors="ignore") if isinstance(data, bytes) else str(data)
        self.message_id = getattr(menu_message, "id", None)
        self.id = self.message_id
        self.sender_id = kernel.ADMIN_ID
        self.from_user = None
        self.client = kernel.client
        self.input_chat = chat_id
        self.chat_instance = str(chat_id)
        self._answered = False

    @property
    def message(self):
        return self._menu_message

    async def answer(self, text=None, alert=False, **kwargs):
        self._answered = True
        if not text:
            return None
        try:
            return await self._kernel.bridge.send_notification(
                self.chat_id, str(text)
            )
        except Exception as e:
            logger.debug(f"callback answer failed: {e}")
            return None

    async def edit(self, text=None, buttons=None, **kwargs):
        if self._menu_message is None:
            return None
        return await self._kernel.bridge.edit_rendered(
            self.chat_id, self._menu_message, text or "",
            buttons=buttons, **kwargs
        )

    async def reply(self, text=None, **kwargs):
        buttons = kwargs.pop("buttons", None)
        if buttons:
            return await self._kernel.bridge.send_rendered(
                self.chat_id, text or "", buttons=buttons, **kwargs
            )
        return await self._kernel.client.send_message(self.chat_id, text or "", **kwargs)

    async def respond(self, text=None, **kwargs):
        return await self.reply(text, **kwargs)

    async def delete(self):
        try:
            if self._menu_message is not None:
                await self._kernel._real_client.delete_messages(
                    self.chat_id, [self._menu_message.id]
                )
        except Exception as e:
            logger.debug(f"callback delete failed: {e}")

    async def get_message(self):
        return self._menu_message


# ============================================================
# INLINE QUERY EVENT MOCK — .iq / inline_query_and_click
# ============================================================

class InlineArticleResult:
    def __init__(self, title, description="", text="", parse_mode="html", **kwargs):
        self.title = title
        self.description = description
        self.text = text
        self.parse_mode = parse_mode
        self.id = f"article_{abs(hash(title)) & 0x7FFFFFFF}"


class InlinePhotoResult:
    def __init__(self, url, title="", description="", **kwargs):
        self.url = url
        self.title = title
        self.description = description
        self.id = f"photo_{abs(hash(url)) & 0x7FFFFFFF}"


class InlineResultBuilderMock:
    def article(self, title, description="", text="", parse_mode="html", **kwargs):
        return InlineArticleResult(title, description, text, parse_mode, **kwargs)

    def photo(self, url, title="", description="", **kwargs):
        return InlinePhotoResult(url, title, description, **kwargs)


class InlineQueryEventMock:
    """Эмуляция инлайн-запроса: answer(articles) рендерится текстом в чат."""

    def __init__(self, kernel, chat_id, query_text, query_name="", sender_id=None):
        self._kernel = kernel
        self.chat_id = chat_id
        parts = str(query_text).split(maxsplit=1)
        if query_name and len(parts) > 1:
            self.text = f"{query_name} {parts[1]}"
            self.args = parts[1]
        else:
            self.text = str(query_text)
            self.args = parts[1] if len(parts) > 1 else ""
        self.query = self.text
        self.builder = InlineResultBuilderMock()
        self.client = kernel.client
        self.sender_id = sender_id or kernel.ADMIN_ID or 0
        self.from_user = None
        self.chat_instance = str(chat_id)

    async def answer(self, results=None, **kwargs):
        if not results:
            results = []
        if isinstance(results, str):
            results = [self.builder.article("Результат", text=results)]
        out = "🤖 <b>Инлайн-результаты:</b>\n\n"
        for art in results[:8]:
            title = getattr(art, "title", "") or ""
            desc = getattr(art, "description", "") or ""
            text = getattr(art, "text", "") or ""
            url = getattr(art, "url", None)
            if title:
                out += f"▪️ <b>{title}</b>\n"
            if desc:
                out += f"<i>{desc}</i>\n"
            if url:
                out += f"🖼 <a href='{url}'>медиа</a>\n"
            if text:
                clean = text.replace(chr(8288), " ")
                if len(clean) > 900:
                    clean = clean[:900] + "…"
                out += f"📄 {clean}\n"
            out += "\n"
        try:
            return await self._kernel._real_client.send_message(
                self.chat_id, out.strip(), parse_mode="html",
                link_preview=False,
            )
        except TypeError:
            # старые форки Telethon используют другое имя параметра
            try:
                return await self._kernel._real_client.send_message(
                    self.chat_id, out.strip(), parse_mode="html",
                    disable_web_page_preview=True,
                )
            except Exception:
                return await self._kernel._real_client.send_message(
                    self.chat_id, out.strip(),
                )


# ============================================================
# INLINE MESSAGE MOCK — возвращается из kernel.inline_form
# ============================================================

class InlineMessageMock:
    """Мок InlineMessage из core.lib.types: .edit/.delete/.form_id."""

    def __init__(self, kernel, message, form_id=None, unit_id=None):
        self._kernel = kernel
        self._message = message
        self.form_id = form_id or unit_id
        self.unit_id = self.form_id
        self.chat_id = getattr(message, "chat_id", None)
        self.id = getattr(message, "id", None)
        self.message_id = self.id

    @property
    def message(self):
        return self._message

    async def edit(self, text, buttons=None, **kwargs):
        if self._message is None:
            return None
        return await self._kernel.bridge.edit_rendered(
            self.chat_id, self._message, text, buttons=buttons, **kwargs
        )

    async def delete(self):
        try:
            if self._message is not None:
                await self._message.delete()
        except Exception:
            pass

    async def click(self, i=0, j=None, **kwargs):
        """Симулирует нажатие инлайн-кнопки — делегирует реальному
        Message.click() из Telethon (у него уже есть такая логика)."""
        if self._message is None:
            return None
        try:
            if j is not None:
                return await self._message.click(i, j, **kwargs)
            return await self._message.click(i, **kwargs)
        except Exception as e:
            try:
                self._kernel.logger.debug(f"InlineMessageMock.click failed: {e}")
            except Exception:
                pass
            return None


# ============================================================
# CONVERSATION MOCK
# ============================================================

class ConversationMock:
    """kernel.conversation(chat_id) — ожидание ответа из чата."""

    def __init__(self, client, chat_id):
        self._client = client
        self._chat_id = chat_id
        self._messages = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def send_message(self, text, **kwargs):
        msg = await self._client.send_message(self._chat_id, text, **kwargs)
        self._messages.append(msg)
        return msg

    async def get_response(self, timeout=30, **kwargs):
        from telethon import events as _events

        future = asyncio.get_event_loop().create_future()

        async def _handler(event):
            if not future.done():
                future.set_result(event)

        self._client.add_event_handler(
            _handler, _events.NewMessage(chats=self._chat_id, incoming=True)
        )
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            class _Resp:
                text = ""
                raw_text = ""
                message = None

            return _Resp()
        finally:
            try:
                self._client.remove_event_handler(_handler)
            except Exception:
                pass


# ============================================================
# MODULE KERNEL PROXY — ядро, привязанное к модулю
# ============================================================

class ModuleKernelProxy:
    """Фасад ядра для конкретного модуля.
    type(...).__name__ == 'ModuleKernelProxy' — это проверяется кодом MCUB."""

    def __init__(self, kernel, module_name: str, is_system: bool = False):
        object.__setattr__(self, "_kernel", kernel)
        object.__setattr__(self, "_module_name", module_name)
        object.__setattr__(self, "_is_system", is_system)
        object.__setattr__(self, "_client_proxy",
                           ClientProxy(kernel._real_client, kernel, module_name))

    @property
    def client(self):
        return object.__getattribute__(self, "_client_proxy")

    @property
    def current_loading_module(self):
        return object.__getattribute__(self, "_module_name")

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_kernel"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_kernel"), name, value)

    # storage API, который ModuleBase вызывает через proxy
    def store_inline_callback(self, token, callback_data):
        object.__getattribute__(self, "_kernel").store_inline_callback(token, callback_data)

    def remove_inline_callback_tokens(self, tokens):
        object.__getattribute__(self, "_kernel").remove_inline_callback_tokens(tokens)

    def allow_inline_callback_user(self, user_id, token, allow_ttl=100):
        object.__getattribute__(self, "_kernel").allow_inline_callback_user(
            user_id, token, allow_ttl
        )


def get_module_kernel(kernel, module_name, is_system=False):
    return ModuleKernelProxy(kernel, module_name, is_system)


def get_module_client(kernel, module_name, is_system=False):
    return ClientProxy(kernel._real_client, kernel, module_name)


def get_module_register(kernel, module_name, is_system=False):
    """Register, привязанный к имени модуля (владение командами)."""
    from .runtime import Register

    reg = Register(kernel)
    proxy_kernel = ModuleKernelProxy(kernel, module_name, is_system)
    reg.kernel = proxy_kernel
    return reg


def get_module_db(kernel, module_name, is_system=False):
    return kernel.db_manager


def wrap_event_for_module(event, module_name, kernel):
    """Оборачивает Telethon-событие в EventProxy."""
    if isinstance(event, EventProxy):
        return event
    return EventProxy(event, kernel)

