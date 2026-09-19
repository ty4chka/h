# meta developer: @CoderHoly
# version: 1.7.1
# description: Модуль для чтения и анализа файлов Python
import os
import json
import httpx
import re
import base64
import zlib
import logging
import hashlib
import tempfile
import html
from telethon import Button

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
__version__ = (1, 7, 1)

def register(kernel):
    client = kernel.client

    chunks = []
    file_info = {}
    file_content = ""
    file_path = ""
    desc_cache = {}
    analyzed_count = 0
    current_message_id = None
    current_chat_id = None

    async_cmd_re = re.compile(r'async\s+def\s+(\w+cmd)\s*\(')
    sync_cmd_re = re.compile(r'def\s+(\w+cmd)\s*\(')

    loader_cmd_re = re.compile(
        r'@loader\.command\s*\((?:[^)]*?ru_doc\s*=\s*["\']([^"\']+)["\'])?[^)]*?\)\s*async\s+def\s+(\w+)\s*\(',
        re.DOTALL | re.IGNORECASE
    )

    class_name_re = re.compile(
        r'class\s+(\w+)\s*\(\s*(?:loader\.)?Module\s*\)', re.IGNORECASE
    )

    strings_name_re = re.compile(
        r'strings\s*=\s*\{.*?["\']name["\']\s*:\s*["\']([^"\']+)["\']',
        re.DOTALL | re.IGNORECASE
    )

    b64_zlib_re = re.compile(r"b'([A-Za-z0-9+/=]+)'")

    raw_patterns = [
        (r"DeleteAccountRequest", "Попытка удаления аккаунта", "critical"),
        (r"ResetAuthorizationRequest", "Сброс всех сеансов авторизации", "critical"),
        (r"export_session_string", "Экспорт сессии (угон аккаунта)", "critical"),
        (r"edit_2fa|edit_cloud_password", "Смена пароля 2FA", "critical"),
        (r"terminate_all_sessions", "Завершение всех сеансов", "critical"),
        (r"\.session", "Работа с .session файлом", "critical"),
        (r"os\.environ", "Чтение переменных окружения", "warning"),
        (r"config\.env", "Чтение config.env", "warning"),
        (r"os\.system", "Выполнение системных команд", "critical"),
        (r"subprocess\.Popen|subprocess\.call", "Запуск внешних процессов", "critical"),
        (r"socket\.socket", "Создание сокетов", "critical"),
        (r"shutil\.rmtree", "Рекурсивное удаление файлов", "warning"),
        (r"(requests|httpx|aiohttp)\.post", "Отправка данных POST-запросами", "warning"),
        (r"GetHistoryRequest|GetMessagesRequest", "Массовое чтение переписок", "warning"),
        (r"ctypes\.CDLL", "Загрузка нативных библиотек", "critical"),
    ]
    patterns = [
        (re.compile(p, re.IGNORECASE), msg, sev) for p, msg, sev in raw_patterns
    ]

    ignored_cmds = {"myname", "cmd", "func", "wrapper", "main"}

    http_client = None

    cache_dir = os.path.join(tempfile.gettempdir(), "readfilemod_cache")
    os.makedirs(cache_dir, exist_ok=True)

    module_config = {
        'provider': 'OpenRouter',
        'model': 'kwaipilot/kat-coder-pro:free',
        'api_key': None
    }

    async def load_config():
        nonlocal module_config
        saved_config = await kernel.get_module_config(__name__, module_config)
        module_config.update(saved_config)

    def content_hash(content: str) -> str:
        h = hashlib.sha256()
        h.update(content.encode("utf-8"))
        return h.hexdigest()

    def cache_path_for_hash(h: str) -> str:
        return os.path.join(cache_dir, f"{h}.json")

    def load_ai_cache(h: str) -> str | None:
        path = cache_path_for_hash(h)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("ai_raw_json")
            except Exception:
                return None
        return None

    def save_ai_cache(h: str, ai_raw_json: str):
        path = cache_path_for_hash(h)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"ai_raw_json": ai_raw_json}, f, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"Не удалось сохранить кеш: {e}")

    async def get_http_client():
        nonlocal http_client
        if http_client is None:
            http_client = httpx.AsyncClient(timeout=60)
        return http_client

    def decode_base64_zlib(encoded_string: str) -> str:
        try:
            decoded_bytes = base64.b64decode(encoded_string)
            decompressed_bytes = zlib.decompress(decoded_bytes)
            return decompressed_bytes.decode("utf-8")
        except Exception as e:
            logger.debug(f"Ошибка при декодировании base64+zlib: {e}")
            raise ValueError("Incorrect padding")

    def try_decode(code: str) -> tuple[str, bool]:
        if "__import__('zlib')" in code and "__import__('base64')" in code:
            match = b64_zlib_re.search(code)
            if match:
                try:
                    encoded_string = match.group(1)
                    decoded_code = decode_base64_zlib(encoded_string)
                    logger.info("Код успешно декодирован.")
                    return decoded_code, True
                except Exception:
                    logger.debug("Не удалось декодировать код — пропускаем.")
                    return code, False
        return code, False

    def recursive_decode(content: str, depth: int = 0) -> str:
        if depth > 5:
            return content
        try:
            m = b64_zlib_re.search(content)
            if m:
                encoded_string = m.group(1)
                try:
                    decoded_bytes = base64.b64decode(encoded_string)
                    try:
                        res = zlib.decompress(decoded_bytes).decode("utf-8")
                    except zlib.error:
                        res = decoded_bytes.decode("utf-8", errors="ignore")
                    return recursive_decode(res, depth + 1)
                except Exception:
                    return content
            if len(content) > 100 and " " not in content[:50]:
                try:
                    res = base64.b64decode(content).decode("utf-8")
                    return recursive_decode(res, depth + 1)
                except Exception:
                    pass
        except Exception:
            pass
        return content

    async def generate_description(content: str, json_mode: bool = True) -> str:
        model = module_config['model']
        api_key = module_config['api_key']

        if not api_key:
            return "❌ Ошибка: Не указан API ключ OpenRouter. Пожалуйста, настройте его для полноценного AI-анализа."

        if json_mode:
            system_prompt = (
                "Ты — эксперт по кибербезопасности и анализу Python-кода для Telegram-юзерботов "
                "(Hikka, Heroku, Telethon). "
                "Твоя задача — проанализировать код модуля и оценить его с точки зрения безопасности. "
                "Верни ТОЛЬКО JSON строго в формате:\n"
                "{\n"
                '  \"статус\": \"Безопасный модуль ✅\" ИЛИ \"Установка на ваш риск 👀\" ИЛИ \"Опасный модуль 📛\",\n'
                '  \"назначение\": \"Краткое описание назначения модуля\",\n'
                '  \"возможности\": [\"Функция 1\", \"Функция 2\"],\n'
                '  \"опасности\": [\"Опасное действие 1\", \"Опасное действие 2\"]\n'
                "}\n"
                "Интерпретация статусов:\n"
                "• \"Опасный модуль 📛\" — только если модуль явно направлен на кражу аккаунта, кражу сессии, удаление аккаунта, "
                "массовую утечку данных, скрытый контроль владельца, выполнение произвольного кода или похожие критические действия.\n"
                "• \"Установка на ваш риск 👀\" — если модуль сам по себе не крадёт аккаунт и не наносит прямой вред владельцу, "
                "но может привести к блокировке, нарушает правила сервисов, агрессивно спамит, автоматизирует войны/рейды/игровые боты "
                "или может использоваться во вред другим пользователям.\n"
                "• \"Безопасный модуль ✅\" — если модуль выполняет полезные или нейтральные функции и не содержит опасных действий.\n"
                "Поле \"опасности\" обязательно (может быть пустым массивом []). Там перечисляй конкретные риски и возможные "
                "последствия для владельца аккаунта и других пользователей. Не добавляй никакого текста вокруг JSON."
            )
        else:
            system_prompt = (
                "Ты — помощник по описанию команд в Python-коде. "
                "Отвечай очень кратко, по-русски, без лишнего текста."
            )

        safe_content = content[:40000]
        user_content = f"Код для анализа:\n\n```python\n{safe_content}\n```"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }

        try:
            client = await get_http_client()
            response = await client.post(
                OPENROUTER_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.debug(f"API error: {e}")
            return f"❌ Ошибка API: {e}"

    async def describe_command(cmd: str, code: str) -> str:
        if cmd in desc_cache:
            return desc_cache[cmd]

        prompt = (
            f"Кратко и по-русски опиши, что делает команда «{cmd}» в этом коде. "
            f"Не более 10 слов. Только суть."
        )
        try:
            response = await generate_description(prompt + "\n\n" + code, json_mode=False)
            if not response.startswith("❌"):
                res = response.strip('." \n`')
                desc_cache[cmd] = res
                return res
        except Exception:
            pass
        return "выполняет команду"

    def analyze_file_for_safety(content: str) -> tuple:
        decoded_content, is_decoded = try_decode(content)
        if not is_decoded:
            decoded_content = recursive_decode(content)
            is_decoded = decoded_content != content

        critical = []
        warnings = []
        suspicious = []

        if is_decoded:
            suspicious.append("Код был деобфусцирован (распакован) для анализа")

        for cre, msg, sev in patterns:
            if cre.search(decoded_content):
                if sev == "critical":
                    critical.append(msg)
                else:
                    warnings.append(msg)

        if "eval(" in decoded_content or "exec(" in decoded_content:
            suspicious.append("Использование eval/exec (динамическое исполнение кода)")

        if "meta developer:" not in decoded_content:
            suspicious.append("Отсутствует meta developer (автор модуля не указан)")

        if "api_id" in decoded_content and "api_hash" in decoded_content:
            suspicious.append("Обнаружены api_id/api_hash в коде")

        return critical, warnings, suspicious, decoded_content

    def format_size(size: int) -> str:
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} мб"
        elif size >= 1024:
            return f"{int(size / 1024)} кб"
        else:
            return f"{size} байт"

    def get_cache_stats() -> tuple[int, int]:
        total_bytes = 0
        total_files = 0

        if os.path.isdir(cache_dir):
            for root, dirs, files in os.walk(cache_dir):
                for f in files:
                    path = os.path.join(root, f)
                    try:
                        total_bytes += os.path.getsize(path)
                        total_files += 1
                    except OSError:
                        pass

        if file_path and os.path.exists(file_path):
            try:
                total_bytes += os.path.getsize(file_path)
                total_files += 1
            except OSError:
                pass

        return total_bytes, total_files

    def split_text(text, size):
        return [text[i: i + size] for i in range(0, len(text), size)]

    async def show_page(call, index):
        nonlocal chunks, current_message_id, current_chat_id

        if not chunks:
            await call.edit(
                "❌ Файл пуст.",
                buttons=[[Button.inline("↩️ Закрыть", b"rf_close")]]
            )
            return

        total = len(chunks)
        index = max(0, min(index, total - 1))

        text = (
            f"📒 Страница {index + 1}/{total}\n"
            f"<pre>{html.escape(chunks[index])}</pre>"
        )

        buttons = [
            [
                Button.inline("⬅️", f"rf_page_{max(0, index - 1)}".encode()),
                Button.inline("➡️", f"rf_page_{min(total - 1, index + 1)}".encode())
            ],
            [Button.inline("🕵️ Анализ", f"rf_info_{index}".encode())]
        ]

        await call.edit(text, buttons=buttons, parse_mode='html')

    async def send_open_form(event, file_name, file_size):
        nonlocal current_message_id, current_chat_id

        size_str = format_size(file_size)

        text = (
            f"📁 <b>Файл загружен</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Имя:</b> {html.escape(file_name)}\n"
            f"<b>Размер:</b> {size_str}\n"
        )

        buttons = [
            {"text": "📖 Открыть файл", "type": "callback", "data": "rf_open_file"}
            ]

        success, message = await kernel.inline_form(
            event.chat_id,
            text,
            buttons=buttons
        )

        if success:
            current_message_id = message.id
            current_chat_id = message.peer_id
            await event.delete()

        return success

    @kernel.register.command('rf')
    async def rf_handler(event):
        nonlocal chunks, file_info, file_content, file_path, analyzed_count, current_message_id, current_chat_id

        reply = await event.get_reply_message()
        if not reply or not reply.file:
            await event.edit("❌ Ответьте на файл.")
            return

        await event.edit("⏳ Чтение файла...")

        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        file_path = await reply.download_media()
        chunks = []
        file_content = ""
        file_info = {}

        try:
            if os.path.getsize(file_path) > 10 * 1024 * 1024:
                await event.edit("❌ Файл слишком большой.")
                return

            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
        except Exception as e:
            await event.edit(f"❌ Ошибка чтения: {e}")
            return

        chunks = split_text(file_content, 1500)
        file_info = {
            "Имя": os.path.basename(file_path),
            "Размер": os.path.getsize(file_path),
            "Страниц": len(chunks),
            "Путь": file_path,
        }
        analyzed_count += 1

        success = await send_open_form(event, file_info["Имя"], file_info["Размер"])
        if not success:
            await event.edit("❌ Ошибка создания формы")
            return

    @kernel.register.command('rfcache')
    async def rfcache_handler(event):
        total_bytes, total_files = get_cache_stats()
        size_str = format_size(total_bytes)

        text = (
            "📊 <b>Статистика кеша ReadFileMod</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Занятое место временной папки:</b> {size_str}\n"
            f"<b>Файлов во временной папке:</b> {total_files}\n"
            f"<b>Проанализированных модулей:</b> {analyzed_count}\n"
        )

        success, message = await kernel.inline_form(
            event.chat_id,
            text,
            buttons=[[{"text": "Очистить 🚮", "type": "callback", "data": "rf_clear_cache"}]]
        )
        if success:
            await event.delete()

    @kernel.register.command('rfconfig')
    async def rfconfig_handler(event):
        args = event.text.split(maxsplit=2)

        if len(args) < 2:
            current_model = module_config.get('model', 'Не указана')
            has_api_key = bool(module_config.get('api_key'))
            api_status = "✅ Установлен" if has_api_key else "❌ Не установлен"

            text = (
                "⚙️ <b>Конфигурация ReadFileMod</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Модель AI:</b> {current_model}\n"
                f"<b>API ключ:</b> {api_status}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "<b>Использование:</b>\n"
                ".rfconfig key ваш_api_ключ\n"
                ".rfconfig model имя_модели\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "<b>Пример моделей:</b>\n"
                "• kwaipilot/kat-coder-pro:free\n"
                "• openai/gpt-4o\n"
                "• google/gemini-pro\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "<a href='https://openrouter.ai/settings/keys'>Получить API ключ</a>"
            )

            await event.edit(text, parse_mode='html')
            return

        config_type = args[1].lower()

        if config_type == 'key':
            if len(args) < 3:
                await event.edit("❌ Укажите API ключ")
                return

            module_config['api_key'] = args[2]
            await kernel.save_module_config(__name__, module_config)
            await event.edit("✅ API ключ сохранен")

        elif config_type == 'model':
            if len(args) < 3:
                await event.edit("❌ Укажите название модели")
                return

            module_config['model'] = args[2]
            await kernel.save_module_config(__name__, module_config)
            await event.edit(f"✅ Модель изменена на: {args[2]}")

        else:
            await event.edit("❌ Неизвестный тип конфигурации. Используйте 'key' или 'model'")

    async def handle_callback(event):
        data = event.data.decode('utf-8') if isinstance(event.data, bytes) else str(event.data)

        if data == "rf_close":
            await event.delete()
            return

        elif data == "rf_open_file":
            await event.answer("⏳ Открываем файл...", alert=False)
            await show_page(event, 0)
            return

        elif data == "rf_clear_cache":
            await event.answer("⏳ Очистка кеша...", alert=False)

            removed_files = 0
            removed_cache = 0

            nonlocal file_path, chunks, desc_cache, analyzed_count

            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    removed_files += 1
                except Exception:
                    pass

            file_path = ""
            chunks = []

            if os.path.isdir(cache_dir):
                for filename in os.listdir(cache_dir):
                    path = os.path.join(cache_dir, filename)
                    try:
                        os.remove(path)
                        removed_cache += 1
                    except Exception:
                        pass

            desc_cache.clear()
            analyzed_count = 0

            await event.edit(
                "🧹 <b>Кеш и временные файлы очищены!</b>\n"
                f"• Удалено временных файлов: {removed_files}\n"
                f"• Удалено файлов кеша: {removed_cache}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Можно продолжать анализ новых модулей 🙂",
                parse_mode='html'
            )
            return

        elif data.startswith("rf_page_"):
            try:
                page_num = int(data.split("_")[2])
                await show_page(event, page_num)
            except (IndexError, ValueError):
                await event.answer("❌ Ошибка номера страницы", alert=True)
            return

        elif data.startswith("rf_info_"):
            try:
                return_index = int(data.split("_")[2])
                await show_info(event, return_index)
            except (IndexError, ValueError):
                await event.answer("❌ Ошибка", alert=True)
            return

        await event.answer("❌ Неизвестное действие", alert=True)

    async def show_info(event, return_index):
        nonlocal file_content, file_info

        await event.answer("⏳ Углубленный анализ...", show_alert=False)

        display_name = "N/A"
        filename = file_info.get("Имя", "N/A")

        class_match = class_name_re.search(file_content)
        if class_match:
            display_name = class_match.group(1)
        else:
            strings_match = strings_name_re.search(file_content)
            if strings_match:
                display_name = strings_match.group(1)
            else:
                clean_name = re.sub(r"\s*\(\d+\)", "", filename)
                display_name = clean_name
                if display_name.endswith(".py"):
                    display_name = display_name[:-3]

        fsize = int(file_info.get("Размер", 0))
        pages = file_info.get("Страниц", 0)
        size_str = format_size(fsize)

        crit_list, warn_list, susp_list, working_content = analyze_file_for_safety(file_content)

        content_hash_value = content_hash(working_content)
        ai_raw_json = load_ai_cache(content_hash_value)
        if ai_raw_json is None:
            ai_raw_json = await generate_description(working_content, json_mode=True)
            if not ai_raw_json.startswith("❌"):
                try:
                    cleaned = re.sub(r"```json\n|```json|```|\n", "", ai_raw_json).strip()
                    json.loads(cleaned)
                    save_ai_cache(content_hash_value, ai_raw_json)
                except Exception:
                    pass

        ai_data = {
            "статус": "Установка на ваш риск 👀",
            "назначение": "Не удалось проанализировать",
            "возможности": [],
            "опасности": [],
        }
        if ai_raw_json and not ai_raw_json.startswith("❌"):
            try:
                cleaned = re.sub(r"```json\n|```json|```|\n", "", ai_raw_json).strip()
                loaded = json.loads(cleaned)
                ai_data.update(loaded)
            except Exception:
                pass

        status = html.escape(ai_data.get("статус", "Установка на ваш риск 👀"))
        purpose = html.escape(ai_data.get("назначение", "Нет описания"))
        general_caps = ai_data.get("возможности", []) or []
        ai_risks = ai_data.get("опасности", []) or []

        command_lines = []
        found_cmd_names = set()

        loader_matches = loader_cmd_re.findall(working_content)
        has_loader_cmds = bool(loader_matches)

        for doc_text, cmd_name in loader_matches:
            if cmd_name in ignored_cmds:
                continue
            found_cmd_names.add(cmd_name)
            if doc_text:
                desc = doc_text.replace("\n", " ").strip()
            else:
                desc = await describe_command(cmd_name, working_content)
            formatted_cmd = f"Команда «{html.escape(cmd_name)}» | {html.escape(desc)}"
            command_lines.append(formatted_cmd)

        if not has_loader_cmds:
            classic_cmds = async_cmd_re.findall(working_content)
            if not classic_cmds:
                classic_cmds = sync_cmd_re.findall(working_content)
        else:
            classic_cmds = []

        clean_classic_cmds = []
        for name in classic_cmds:
            base = name[:-3] if name.endswith("cmd") else name
            clean_classic_cmds.append(base)

        for cmd in clean_classic_cmds:
            if cmd in found_cmd_names or cmd in ignored_cmds:
                continue
            desc = await describe_command(cmd, working_content)
            formatted_cmd = f"Команда «{html.escape(cmd)}» | {html.escape(desc)}"
            command_lines.append(formatted_cmd)

        text = (
            "📄 <b>Информация о модуле</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Имя:</b> {html.escape(display_name)}\n"
            f"<b>Размер:</b> {size_str}\n"
            f"<b>Страниц:</b> {pages}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
        )

        if not module_config.get("api_key"):
            text += (
                "Для AI Анализа\n"
                "Пожалуйста, настройте Api Key\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )
        else:
            text += (
                f"🤖 <b>AI-Анализ | {status}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )

            text += "🔹<b>Назначение модуля:</b>\n"
            text += f"<blockquote>{purpose}</blockquote>\n"

            if general_caps or command_lines:
                text += "⚙️<b> Возможности и Команды:</b>\n"
                combined_list = [f"• {c}" for c in command_lines]
                combined_list.extend([f"• {html.escape(c)}" for c in general_caps])
                cmds_str = "\n".join(combined_list)
                text += f"<blockquote>{cmds_str}</blockquote>\n"

            if ai_risks:
                dangers_str = "\n".join([f"• {html.escape(d)}" for d in ai_risks])
                text += "☢️ <b>Опасные или рискованные действия:</b>\n"
                text += f"<blockquote>{dangers_str}</blockquote>\n"

            all_heur = crit_list + warn_list + susp_list
        if all_heur:
            heur_str = "\n".join([f"• {html.escape(d)}" for d in all_heur])
            text += "🧪 <b>Статический анализ (эвристика):</b>\n"
            text += f"<blockquote>{heur_str}</blockquote>"


        buttons = [[Button.inline("↩️ Назад к коду", f"rf_page_{return_index}".encode())]]

        await event.edit(
            text=text,
            buttons=buttons,
            parse_mode='html'
        )

    kernel.register_callback_handler("rf_", handle_callback)

    async def cleanup():
        nonlocal file_path, http_client

        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        if http_client:
            try:
                await http_client.aclose()
            except Exception:
                pass

    #load_config()

    return {
        'rf': rf_handler,
        'rfcache': rfcache_handler,
        'rfconfig': rfconfig_handler,
        'cleanup': cleanup
    }
