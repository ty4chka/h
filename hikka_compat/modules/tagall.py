# meta developer: @hdjsfzbxm
# meta name: TagAll
# meta version: 2.5.2

import asyncio
import contextlib
import logging
import random
import time
import re

from hikkatl.tl.functions.channels import InviteToChannelRequest
from hikkatl.tl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)


class StopEvent:
    """
    Event class to signal stopping the TagAll process.
    Stores the chat_id to ensure the trigger message comes from the correct chat.
    """

    def __init__(self, chat_id: int):
        self.state = True
        self.chat_id = chat_id
        self.last_timeout: float | None = None

    def stop(self):
        self.state = False


@loader.tds
class TagAllMod(loader.Module):
    """Отмечает всех участников чата через команды или триггеры в тексте.
    Включает/выключает работу триггеров командой .autotagall."""

    strings = {
        "name": "TagAll",
        "bot_error": "🚫 <b>Не получилось пригласить бота в чат.</b>",
        "_cfg_doc_delete": "Удалять сообщения после тега",
        "_cfg_doc_use_bot": "Использовать бота для тегов",
        "_cfg_doc_timeout": "Время между сообщениями (число, список или диапазон 0.1-1.0)",
        "_cfg_doc_silent": "Не отправлять сообщение с кнопкой отмены",
        "_cfg_doc_cycle_tagging": "Цикличный тег (пока не остановите)",
        "_cfg_doc_cycle_delay": "Задержка между циклами (сек)",
        "_cfg_doc_chunk_size": "Сколько пользователей в одном сообщении",
        "_cfg_doc_duration": "Длительность работы (0 = бесконечно)",
        "_cfg_doc_exclude_user_ids": "ID пользователей-исключений",
        "_cfg_doc_allowed_chat_ids": "ID разрешенных чатов для выполнения команд",
        "_cfg_start_trigger": "Триггер(ы) для запуска (если есть в тексте сообщения). Разделяйте запятыми.",
        "_cfg_stop_trigger": "Триггер(ы) для остановки (если есть в тексте сообщения). Разделяйте запятыми.",
        "_cfg_doc_allowed_trigger_user_ids": (
            "ID пользователей, которые могут использовать триггеры (через текст сообщения). "
            "Разделяйте запятыми. Если пусто, любой может использовать триггеры."
        ),
        "_cfg_doc_enable_watcher": "Включить/выключить работу триггеров (команда .autotagall)",
        "tagall_not_running": "🚫 <b>TagAll не запущен в чате {chat_id}.</b>",
        "tagall_already_running": "🚫 <b>TagAll уже запущен в чате {chat_id}.</b>",
        "no_eligible_participants": "🚫 <b>Нет подходящих участников.</b>",
        "cmd_redirected": "➡️ <b>Команда перенаправлена в чат</b> <code>{target_chat_id}</code>, так как он единственный разрешенный.",
        "cmd_not_allowed_multiple": "🚫 <b>Чат не в белом списке. Разрешенные:</b> {allowed_chats}.",
        "trigger_not_allowed": "🚫 <b>Вам не разрешено использовать триггеры для TagAll.</b>",
        "autotagall_enabled": "✅ <b>Работа триггеров TagAll включена.</b>",
        "autotagall_disabled": "❌ <b>Работа триггеров TagAll выключена.</b>",
        "_cmd_tagall_doc": "[<номер чата>] [текст] - Отметить всех участников чата. [текст] будет отправлен вместе с тегами. Если текст не указан, будут отправлены только теги.",
        "_cmd_stoptagall_doc": "[<номер чата>] - Остановить запущенный процесс TagAll в <b>указанном или текущем чате</b>.",
        "_cmd_autotagall_doc": "Включить/выключить работу триггеров TagAll (установленных в .cfg)",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("delete", False, lambda: self.strings("_cfg_doc_delete"), validator=loader.validators.Boolean()),
            loader.ConfigValue("use_bot", False, lambda: self.strings("_cfg_doc_use_bot"), validator=loader.validators.Boolean()),
            loader.ConfigValue("timeout", "0.1", lambda: self.strings("_cfg_doc_timeout"), validator=loader.validators.String()),
            loader.ConfigValue("silent", False, lambda: self.strings("_cfg_doc_silent"), validator=loader.validators.Boolean()),
            loader.ConfigValue("cycle_tagging", False, lambda: self.strings("_cfg_doc_cycle_tagging"), validator=loader.validators.Boolean()),
            loader.ConfigValue("cycle_delay", 0, lambda: self.strings("_cfg_doc_cycle_delay"), validator=loader.validators.Integer(minimum=0)),
            loader.ConfigValue("chunk_size", 3, lambda: self.strings("_cfg_doc_chunk_size"), validator=loader.validators.Integer(minimum=1)),
            loader.ConfigValue("duration", 0, lambda: self.strings("_cfg_doc_duration"), validator=loader.validators.Integer(minimum=0)),
            loader.ConfigValue("exclude_user_ids", "", lambda: self.strings("_cfg_doc_exclude_user_ids"), validator=loader.validators.String()),
            loader.ConfigValue("allowed_chat_ids", "", lambda: self.strings("_cfg_doc_allowed_chat_ids"), validator=loader.validators.String()),
            loader.ConfigValue("start_trigger", "тагалл", lambda: self.strings("_cfg_start_trigger"), validator=loader.validators.String()),
            loader.ConfigValue("stop_trigger", "стоп таг", lambda: self.strings("_cfg_stop_trigger"), validator=loader.validators.String()),
            loader.ConfigValue(
                "allowed_trigger_user_ids",
                "",
                lambda: self.strings("_cfg_doc_allowed_trigger_user_ids"),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "enable_watcher",
                True,
                lambda: self.strings("_cfg_doc_enable_watcher"),
                validator=loader.validators.Boolean(),
            ),
        )
        self._tagall_events: dict[int, StopEvent] = {}

    async def client_ready(self, client, db):
        self._client = client
        self._db = db

    async def on_unload(self):
        for event in list(self._tagall_events.values()):
            event.stop()
        self._tagall_events.clear()

    @loader.watcher()
    async def watcher(self, message: Message):
        if not self.config["enable_watcher"]: # Проверка нового параметра
            return

        if not isinstance(message, Message) or not message.text:
            return

        # Проверяем, разрешено ли отправителю использовать триггеры
        allowed_trigger_ids_raw = self.config["allowed_trigger_user_ids"]
        allowed_trigger_ids = {int(x.strip()) for x in allowed_trigger_ids_raw.split(",") if x.strip().isdigit()}

        if allowed_trigger_ids and message.sender_id not in allowed_trigger_ids:
            # Если allowed_trigger_user_ids настроен и отправитель не в списке, игнорируем триггер
            return

        message_text_lower = message.text.lower()
        
        # Разбираем множественные стоп-триггеры
        stop_triggers_raw = self.config["stop_trigger"]
        stop_triggers = [t.strip().lower() for t in stop_triggers_raw.split(',') if t.strip()]

        # Разбираем множественные старт-триггеры
        start_triggers_raw = self.config["start_trigger"]
        start_triggers = [t.strip().lower() for t in start_triggers_raw.split(',') if t.strip()]

        # Сначала проверяем стоп-триггер
        for trigger in stop_triggers:
            if trigger and trigger in message_text_lower:
                await self._stop_logic(message, "")
                return

        # Затем старт-триггер
        for trigger in start_triggers:
            if trigger and trigger in message_text_lower:
                # Если триггер для запуска найден, весь остальной текст игнорируется.
                # Поэтому prefix устанавливается в пустую строку.
                prefix = "" 
                await self._start_logic(message, prefix)
                return # Выходим после первого сработавшего старт-триггера

    def _get_allowed_chat_ids_map(self) -> dict[int, int]:
        allowed_ids_raw = self.config["allowed_chat_ids"]
        allowed_chats_map = {}
        cleaned = re.sub(r"[^0-9,]", "", allowed_ids_raw)
        if not cleaned: return {}
        for i, chat_id_str in enumerate(cleaned.split(',')):
            if chat_id_str:
                with contextlib.suppress(ValueError):
                    allowed_chats_map[i + 1] = int(chat_id_str)
        return allowed_chats_map

    def _format_allowed_chats_list(self, allowed_chats_map: dict[int, int]) -> str:
        """Форматирует список разрешенных чатов для вывода."""
        if not allowed_chats_map:
            return "<i>нет</i>"
        return ", ".join([f"<code>{idx}</code>: <code>{chat_id}</code>" for idx, chat_id in sorted(allowed_chats_map.items())])


    async def _resolve_target_chat(self, message: Message, raw_args: str) -> tuple[int | None, str | None]:
        original_chat_id = message.chat_id
        remaining_args = raw_args.strip()
        allowed_chats_map = self._get_allowed_chat_ids_map()
        allowed_chat_ids_set = set(allowed_chats_map.values())

        chat_index_match = re.match(r"^\s*(\d+)\s*(.*)$", remaining_args)
        if chat_index_match:
            try:
                index = int(chat_index_match.group(1))
                if index in allowed_chats_map:
                    target_id = allowed_chats_map[index]
                    # Убрано сообщение о перенаправлении по индексу
                    return target_id, chat_index_match.group(2).strip()
                else:
                    await utils.answer(message, self.strings("invalid_chat_index").format(index=index, allowed_chats=self._format_allowed_chats_list(allowed_chats_map)))
                    return None, None
            except ValueError:
                pass # Невалидный индекс, продолжаем с обычным парсингом

        if not allowed_chat_ids_set or original_chat_id in allowed_chat_ids_set:
            return original_chat_id, remaining_args
        
        if len(allowed_chat_ids_set) == 1:
            target_id = next(iter(allowed_chat_ids_set))
            # Убрано сообщение о перенаправлении, если только один чат
            return target_id, remaining_args

        await utils.answer(message, self.strings("cmd_not_allowed_multiple").format(
            allowed_chats=self._format_allowed_chats_list(allowed_chats_map)
        ))
        return None, None

    async def _start_logic(self, message: Message, prefix: str):
        target_chat_id, message_prefix = await self._resolve_target_chat(message, prefix)
        if target_chat_id is None:
            return

        if target_chat_id in self._tagall_events and self._tagall_events[target_chat_id].state:
            return # Уже запущен

        # Удаляем исходное сообщение, если это исходящая команда или триггер
        if message.out:
            with contextlib.suppress(Exception): await message.delete()

        event = StopEvent(target_chat_id)
        self._tagall_events[target_chat_id] = event
        self._client.loop.create_task(self._run_tagall_process(target_chat_id, message_prefix, event))

    async def _stop_logic(self, message: Message, args: str):
        target_chat_id, _ = await self._resolve_target_chat(message, args)
        if target_chat_id is None: return
        
        event = self._tagall_events.get(target_chat_id)
        if event and event.state:
            event.stop()
            if message.out: # Удаляем исходящее сообщение-триггер/команду
                with contextlib.suppress(Exception): await message.delete()
        else:
            await utils.answer(message, self.strings("tagall_not_running").format(chat_id=target_chat_id))

    @loader.command(
        groups=True,
        ru_doc=lambda self: self.strings("_cmd_tagall_doc"),
        # de_doc=lambda self: self.strings("_cmd_tagall_doc"), # Добавить, если нужно
        # tr_doc=lambda self: self.strings("_cmd_tagall_doc"), # Добавить, если нужно
        # uz_doc=lambda self: self.strings("_cmd_tagall_doc"), # Добавить, если нужно
    )
    async def tagall(self, message: Message):
        """[<номер чата>] [текст] - Отметить всех участников чата. [текст] будет отправлен вместе с тегами. Если текст не указан, будут отправлены только теги."""
        await self._start_logic(message, utils.get_args_raw(message))

    @loader.command(
        ru_doc=lambda self: self.strings("_cmd_stoptagall_doc"),
        # de_doc=lambda self: self.strings("_cmd_stoptagall_doc"), # Добавить, если нужно
        # tr_doc=lambda self: self.strings("_cmd_stoptagall_doc"), # Добавить, если нужно
        # uz_doc=lambda self: self.strings("_cmd_stoptagall_doc"), # Добавить, если нужно
    )
    async def stoptagall(self, message: Message):
        """[<номер чата>] - Остановить запущенный процесс TagAll в <b>указанном или текущем чате</b>."""
        await self._stop_logic(message, utils.get_args_raw(message))

    @loader.command(
        ru_doc=lambda self: self.strings("_cmd_autotagall_doc"),
    )
    async def autotagall(self, message: Message):
        """Включить/выключить работу триггеров TagAll (установленных в .cfg)"""
        self.config["enable_watcher"] = not self.config["enable_watcher"]
        if self.config["enable_watcher"]:
            await utils.answer(message, self.strings("autotagall_enabled"))
        else:
            await utils.answer(message, self.strings("autotagall_disabled"))
        if message.out:
            with contextlib.suppress(Exception): await message.delete()


    def _get_random_timeout(self, event: StopEvent) -> float:
        timeout_str = str(self.config["timeout"])
        try:
            cleaned = re.sub(r"[^0-9.,-]", "", timeout_str)
            if "-" in cleaned:
                parts = cleaned.split("-")
                min_val = max(0.0, float(parts[0]))
                max_val = max(0.0, float(parts[1]))
                if min_val > max_val: min_val, max_val = max_val, min_val
                return random.uniform(min_val, max_val)
            if "," in cleaned:
                vals = [float(x) for x in cleaned.split(",") if x and float(x) >= 0.0]
                # Избегаем повторения того же таймаута, если есть несколько значений
                if len(vals) > 1 and event.last_timeout is not None and event.last_timeout in vals:
                    available_values = [v for v in vals if v != event.last_timeout]
                    if available_values:
                        new_timeout = random.choice(available_values)
                    else: # Если все значения совпадают с last_timeout, повтор допустим
                        new_timeout = random.choice(vals)
                else:
                    new_timeout = random.choice(vals)
                event.last_timeout = new_timeout
                return new_timeout
            single_val = float(cleaned)
            event.last_timeout = max(0.0, single_val)
            return event.last_timeout
        except (ValueError, TypeError):
            logger.warning(f"Не удалось разобрать таймаут '{timeout_str}'. Используется значение по умолчанию 0.1.")
            event.last_timeout = 0.1
            return 0.1

    async def _run_tagall_process(self, chat_id: int, message_prefix: str, event: StopEvent):
        """Внутренняя функция для обработки основной логики TagAll."""
        deleted_message_ids_hikkatl = []
        deleted_message_ids_bot_client = []

        is_bot_sender = self.config["use_bot"]

        try:
            chat_entity = await self._client.get_input_entity(chat_id)
        except Exception as e:
            logger.error(f"Не удалось получить сущность чата для ID {chat_id}: {e}")
            await self._client.send_message(chat_id, f"🚫 <b>Не удалось найти чат с ID:</b> <code>{chat_id}</code>")
            event.stop()
            if chat_id in self._tagall_events:
                del self._tagall_events[chat_id]
            return

        excluded_user_ids = set()
        exclude_ids_raw = self.config["exclude_user_ids"]
        for uid_str in exclude_ids_raw.split(','):
            uid_str = uid_str.strip()
            if uid_str:
                try:
                    excluded_user_ids.add(int(uid_str))
                except ValueError:
                    logger.warning(f"Неверный ID пользователя в конфигурации 'exclude_user_ids': '{uid_str}'. Должен быть целым числом.")

        if is_bot_sender:
            try:
                # Добавлена проверка на наличие self.inline.bot_client
                if not hasattr(self, 'inline') or not hasattr(self.inline, 'bot_client') or not getattr(self.inline, 'bot_client', None):
                    raise RuntimeError("Инлайн-бот не настроен или недоступен.")

                bot_entity = await self._client.get_input_entity(self.inline.bot_username)
                with contextlib.suppress(Exception):  # Подавляем ошибки, если бот уже в чате или не может быть приглашен
                    await self._client(InviteToChannelRequest(chat_entity, [bot_entity]))
            except Exception as e:
                logger.error(f"Не удалось получить сущность бота или пригласить бота: {e}")
                await self._client.send_message(chat_id, self.strings("bot_error"))
                event.stop()
                if chat_id in self._tagall_events:
                    del self._tagall_events[chat_id]
                return

        participants = []
        owner_id = self._client.tg_id
        async for user in self._client.iter_participants(chat_id):
            if not user.bot and not user.deleted and user.id != owner_id and user.id not in excluded_user_ids:
                participants.append(user)

        if not participants:
            logger.warning(f"В чате {chat_id} не найдено подходящих участников для TagAll, останавливаем.")
            await self._client.send_message(chat_id, self.strings("no_eligible_participants"))
            event.stop()
            if chat_id in self._tagall_events:
                del self._tagall_events[chat_id]
            return

        random.shuffle(participants)

        start_time = time.time()

        try:
            first_pass = True
            while self.config["cycle_tagging"] or first_pass:
                if not event.state:
                    break

                if self.config["duration"] > 0 and (time.time() - start_time) > self.config["duration"]:
                    event.stop()
                    break

                current_cycle_participants = []
                if self.config["cycle_tagging"] and not first_pass: # Re-fetch participants if cycling
                    logger.debug(f"Повторный запрос участников для цикла в чате {chat_id}.")
                    async for user in self._client.iter_participants(chat_id):
                        if not user.bot and not user.deleted and user.id != owner_id and user.id not in excluded_user_ids:
                            current_cycle_participants.append(user)
                    random.shuffle(current_cycle_participants)
                    participants = current_cycle_participants
                    if not participants:
                        logger.warning(f"В чате {chat_id} не найдено участников для TagAll для следующего цикла, останавливаем.")
                        break

                for chunk in utils.chunks(participants, self.config["chunk_size"]):
                    if not event.state:
                        break

                    if self.config["duration"] > 0 and (time.time() - start_time) > self.config["duration"]:
                        event.stop()
                        break

                    tags = []
                    for user in chunk:
                        if user.username:
                            user_display_name = f"@{user.username}"
                        else:
                            display_name_parts = []
                            if user.first_name:
                                display_name_parts.append(user.first_name)
                            if user.last_name:
                                display_name_parts.append(user.last_name)

                            display_name = " ".join(display_name_parts)
                            user_display_name = utils.escape_html(display_name or "Пользователь")

                        tags.append(f'<a href="tg://user?id={user.id}">{user_display_name}</a>')

                    # message_prefix уже пустой, если сработал триггер, так что здесь все ок
                    if message_prefix:
                        full_message_text = f"{message_prefix}\n{' '.join(tags)}"
                    else:
                        full_message_text = " ".join(tags)

                    if is_bot_sender:
                        if hasattr(self, 'inline') and hasattr(self.inline, 'bot_client') and self.inline.bot_client:
                            m = await self.inline.bot_client.send_message(
                                chat_id,
                                full_message_text,
                                parse_mode="HTML",
                            )
                            if self.config["delete"]:
                                deleted_message_ids_bot_client.append(m.id)
                        else:
                            logger.error("Клиент инлайн-бота недоступен или не настроен, переключаемся на юзербота для отправки сообщений.")
                            m = await self._client.send_message(
                                chat_entity,
                                full_message_text,
                                parse_mode="HTML",
                            )
                            if self.config["delete"]:
                                deleted_message_ids_hikkatl.append(m.id)
                    else:
                        m = await self._client.send_message(
                            chat_entity,
                            full_message_text,
                            parse_mode="HTML",
                        )
                        if self.config["delete"]:
                            deleted_message_ids_hikkatl.append(m.id)

                    await asyncio.sleep(self._get_random_timeout(event))

                first_pass = False
                if self.config["cycle_tagging"] and event.state:
                    await asyncio.sleep(self.config["cycle_delay"])
                elif not self.config["cycle_tagging"]:
                    break

        finally:
            if self.config["delete"]:
                with contextlib.suppress(Exception):
                    if deleted_message_ids_hikkatl:
                        for chunk_ids in utils.chunks(deleted_message_ids_hikkatl, 100):
                            await self._client.delete_messages(chat_entity, chunk_ids)

                    if deleted_message_ids_bot_client:
                        if hasattr(self, 'inline') and hasattr(self.inline, 'bot_client') and self.inline.bot_client:
                            for chunk_ids in utils.chunks(deleted_message_ids_bot_client, 100):
                                await self.inline.bot_client.delete_messages(chat_entity, chunk_ids)
                        else:
                            logger.warning("Клиент инлайн-бота недоступен для удаления своих сообщений.")

            if event.state:
                logger.info(f"Процесс TagAll завершен естественным образом в чате {chat_id}.")

            if chat_id in self._tagall_events:
                del self._tagall_events[chat_id]
