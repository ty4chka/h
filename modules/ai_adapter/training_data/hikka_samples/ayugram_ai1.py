__id__ = "unified_ai_plugin"
__name__ = "Unified AI Assistant + Media Tools"
__description__ = "Продвинутый ИИ ассистент с историей диалогов, автоматическим обновлением статуса и скачиванием медиа"
__icon__ = "remusic/3"
__version__ = "3.0.0"
__author__ = "@Niepriddd, @Aubeig, @V_ladiSLAVE, @itsv1eds"

import base64
import requests
import os
import time
import threading
import json
import re
import socket
import datetime
import uuid
import traceback
from android_utils import log as logcat
from base_plugin import BasePlugin, HookResult, HookStrategy, MenuItemData, MenuItemType
from client_utils import get_file_loader, get_messages_controller, send_message, send_request, get_user_config, get_last_fragment
from java.io import File
from typing import List, Optional, Any, Callable, Dict, Tuple
from ui.settings import Divider, Header, Input, Switch, Text, Selector
from ui.bulletin import BulletinHelper
from org.telegram.messenger import LocaleController, ApplicationLoader
from org.telegram.tgnet.tl import TL_account
from org.telegram.tgnet import TLRPC
from org.telegram.messenger import SendMessagesHelper
from java.util import ArrayList
from android.content import ClipData, Context, Intent
from com.exteragram.messenger.plugins import PluginsController
from com.exteragram.messenger.plugins.ui import PluginSettingsActivity
from android.net import Uri
from android.app import DownloadManager
from android.os import Environment

# ==================== Общие настройки ====================
MEMORY_DIR = "/storage/emulated/0/Documents/AIPlugin_History"
CHAT_HISTORY_FILE = os.path.join(MEMORY_DIR, "chat_history.json")
MAX_HISTORY_PER_CHAT = 20
MAX_IMAGE_SIZE = 15 * 1024 * 1024  # 15 МБ
SUPPORTED_IMAGE_TYPES = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
setting_getter: Optional[Callable] = None
active_request_lock = threading.Lock()
IMAGE_CACHE = {}  # Кэш для base64 изображений
TEMP_DIR_NAME = "DownloaderTemp"

# ==================== Поддерживаемые платформы ИИ ====================
SUPPORTED_PROVIDERS = {
    "OpenRouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {
            "HTTP-Referer": "https://exteragram.app",
            "X-Title": "AIPlugin for Exteragram"
        },
        "models": ["google/gemini-2.0-flash-exp:free", "mistralai/mixtral-8x7b-instruct", "openai/gpt-3.5-turbo"]
    },
    "Google": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "headers": {},
        "models": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0", "gemini-2.5"]
    },
    "OpenAI": {
        "url": "https://api.openai.com/v1/chat/completions",
        "headers": {},
        "models": ["gpt-4-turbo", "gpt-4o", "gpt-4-vision", "gpt-3.5-turbo-0125"]
    },
    "Anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "headers": {"anthropic-version": "2023-06-01"},
        "models": ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"]
    },
    "Groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "headers": {},
        "models": ["llama3-70b-8192", "llama3-8b-8192", "mixtral-8x7b-32768"]
    },
    "DeepSeek": {
        "url": "https://api.deepseek.com/v1/chat/completions",
        "headers": {},
        "models": ["deepseek-chat", "deepseek-coder"]
    }
}

# ==================== Настройки Media Downloader ====================
DEFAULT_COBALT_API = "https://co.itsv1eds.ru"
COBALT_API = [DEFAULT_COBALT_API, "https://co.eepy.today", "https://co.otomir23.me", "https://cobalt.255x.ru"]
VIDEO_QUALITY_OPTIONS = ["144","240","360","480","720","1080","1440","2160","4320","max"]
DOWNLOAD_MODE_OPTIONS = ["auto","audio","mute"]
AUDIO_BITRATE_OPTIONS = ["64","96","128","192","256","320"]
YOUTUBE_VIDEO_CODEC_OPTIONS = ["h264","av1","vp9"]
SERVICES_INFO = "YouTube (maybe), TikTok, Instagram, Twitter/X, VK (Video/Clips), Reddit, SoundCloud, Facebook, Pinterest, RuTube"
progress_dialog = None

MEDIA_DOWNLOADER_TRANSLATIONS = {
    "api_title": ("Настройки API", "API Settings"),
    "api_url": ("Cobalt API URL", "Cobalt API URL"),
    "api_key": ("API ключ", "API Key"),
    "api_help": ("Справка", "Help"),
    "api_desc": ("Укажите URL и API (если требуется) вашего Cobalt инстанса. Узнать больше: github.com/imputnet/cobalt", "Enter URL and API (if needed) for your Cobalt instance. Learn more: github.com/imputnet/cobalt"),
    "custom_api": ("Свой API", "Custom API"),
    "custom_api_url": ("Свой URL API", "Custom API URL"),
    "auto_fallback": ("Автопереключение API", "Auto API Fallback"),
    "auto_fallback_desc": ("Автоматически переключаться на другой API при ошибке", "Automatically switch to another API on error"),
    "proxy_title": ("Настройки прокси", "Proxy Settings"),
    "proxy_type": ("Тип прокси", "Proxy Type"),
    "proxy_type_items": (["Нет", "HTTP", "HTTPS", "SOCKS", "MTProto"], ["None", "HTTP", "HTTPS", "SOCKS", "MTProto"]),
    "proxy_url": ("URL прокси", "Proxy URL"),
    "proxy_url_desc": ("Введите прокси host:port", "Enter proxy host:port"),
    "proxy_user": ("Логин прокси", "Proxy Username"),
    "proxy_password": ("Пароль прокси", "Proxy Password"),
    "proxy_secret": ("MTProto Secret", "MTProto Secret"),
    "proxy_secret_desc": ("Секретный ключ MTProto прокси", "MTProto proxy secret key"),
    "settings_title": ("Настройки загрузки", "Download Settings"),
    "show_settings_buttons": ("Кнопка настроек в меню", "Settings button in menu"),
    "show_settings_buttons_desc": ("Добавляет кнопку открытия настроек плагина в меню", "Adds plugin settings button to menu"),
    "include_source": ("Включить ссылку источника", "Include source link"),
    "include_source_desc": ("Добавить ссылку источника в подпись сообщения", "Add source link to message caption"),
    "send_as_file": ("Отправлять как файл", "Send as file"),
    "send_as_file_desc": ("Скачанный контент будет отправлен как документ", "Downloaded media will be sent as document"),
    "disable_metadata": ("Отключить метаданные", "Disable metadata"),
    "disable_metadata_desc": ("Название, исполнитель и другие данные не будут добавлены в файл", "Title, artist, and other info will not be added to the file"),
    "advanced_settings": ("Дополнительные настройки", "Advanced Settings"),
    "advanced_settings_desc": ("Показать качество видео и битрейт аудио", "Show video quality and audio bitrate"),
    "video_quality": ("Качество видео", "Video Quality"),
    "audio_bitrate": ("Битрейт аудио", "Audio Bitrate"),
    "services": ("Поддерживаемые сервисы", "Supported services"),
    "usage_cmd": (".down/.dl [URL] - Скачивает и отправляет медиа\nПример: .dl youtube.com/watch?v=dQw4w9WgXcQ", "Command: .down/.dl [URL] - Download and send video/audio\nExample: .dl youtube.com/watch?v=dQw4w9WgXcQ"),
    "donate_title": ("Поддержать разработку", "Support development"),
    "donate_info": ("Другая информация и реквизиты", "Other info and requisites"),
    "test_proxy": ("Тест подключения", "Test Connection"),
    "test_proxy_desc": ("Проверить доступность прокси", "Test proxy availability"),
}

def Z_downloader(key):
    lang = LocaleController.getInstance().getCurrentLocale().getLanguage()
    if lang.startswith('ru'):
        idx = 0
    else:
        idx = 1
    return MEDIA_DOWNLOADER_TRANSLATIONS.get(key, (None, None))[idx]

# ==================== Класс для логирования ====================
class DebugLogger:
    @staticmethod
    def debug(message):
        global setting_getter
        if setting_getter and setting_getter("enable_debug_logging", False):
            logcat(f"[AIPlugin] {message}")
    
    @staticmethod
    def error(message):
        logcat(f"[AIPlugin] {message}")

# ==================== Менеджер памяти ====================
class MemoryManager:
    MAX_TOKENS = 8000  # Лимит токенов для истории
    
    @staticmethod
    def ensure_dir():
        if not os.path.exists(MEMORY_DIR):
            os.makedirs(MEMORY_DIR)
    
    @staticmethod
    def load_chat_history() -> Dict[str, list]:
        MemoryManager.ensure_dir()
        try:
            if os.path.exists(CHAT_HISTORY_FILE):
                with open(CHAT_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            DebugLogger.error(f"Ошибка загрузки истории: {str(e)}")
        return {}

    @staticmethod
    def save_chat_history(history: Dict[str, list]):
        try:
            with open(CHAT_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            DebugLogger.error(f"Ошибка сохранения истории: {str(e)}")
    
    @staticmethod
    def add_to_history(chat_id: str, user_msg: str, ai_msg: str):
        history = MemoryManager.load_chat_history()
        
        if chat_id not in history:
            history[chat_id] = []
        
        # Рассчитываем длину в токенах (упрощенный метод)
        def count_tokens(text): 
            return len(text) // 4
            
        total_tokens = sum(count_tokens(msg["content"]) for msg in history.get(chat_id, []))
        new_tokens = count_tokens(user_msg) + count_tokens(ai_msg)
        
        # Автоматическая очистка истории при превышении лимита
        while total_tokens + new_tokens > MemoryManager.MAX_TOKENS and history.get(chat_id):
            removed = history[chat_id].pop(0)
            total_tokens -= count_tokens(removed["content"])
        
        history[chat_id].append({"role": "user", "content": user_msg})
        history[chat_id].append({"role": "assistant", "content": ai_msg})
        
        # Ограничиваем количество сообщений
        if len(history[chat_id]) > MAX_HISTORY_PER_CHAT * 2:
            history[chat_id] = history[chat_id][-MAX_HISTORY_PER_CHAT * 2:]
        
        MemoryManager.save_chat_history(history)
        return history
    
    @staticmethod
    def get_history(chat_id: str) -> list:
        history = MemoryManager.load_chat_history()
        return history.get(chat_id, [])
    
    @staticmethod
    def clear_chat_history(chat_id: str):
        history = MemoryManager.load_chat_history()
        if chat_id in history:
            del history[chat_id]
        MemoryManager.save_chat_history(history)
    
    @staticmethod
    def clear_all_history():
        if os.path.exists(CHAT_HISTORY_FILE):
            try:
                os.remove(CHAT_HISTORY_FILE)
            except Exception as e:
                DebugLogger.error(f"Ошибка удаления файла: {str(e)}")
        MemoryManager.save_chat_history({})

# ==================== Форматирование ответа ИИ ====================
def format_ai_response(response_data, provider: str):
    try:
        content = ""
        if provider == "Anthropic":
            content = response_data["content"][0]["text"]
        elif provider == "Google":
            if "candidates" in response_data and response_data["candidates"]:
                candidate = response_data["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    content = candidate["content"]["parts"][0]["text"]
        else: # OpenAI, Groq, DeepSeek, OpenRouter
            content = response_data["choices"][0]["message"]["content"]
        
        if not content:
            return f"оɯибᴋᴀ: пустой ответ от {provider}"

        # Улучшенное Markdown форматирование
        content = re.sub(r'```(.*?)```', r'```\n\1\n```', content, flags=re.DOTALL)
        content = re.sub(r'`(.*?)`', r'`\1`', content)
        content = re.sub(r'\*\*(.*?)\*\*', r'**\1**', content)
        content = re.sub(r'\*(.*?)\*', r'*\1*', content)
        
        # Авто-исправление длинных URL
        content = re.sub(r'(https?://\S{50,})', r'<\1>', content)
        
        header = setting_getter("response_header", "ии ᴀᴄᴄиᴄᴛᴇнᴛ")
        return (
            f"**{header}**\n"
            "══════════════════════\n"
            f"{content}\n"
            "══════════════════════"
        )
    except (KeyError, IndexError, Exception) as e:
        DebugLogger.error(f"Ошибка форматирования ответа от {provider}: {str(e)}\nDATA: {response_data}")
        return f"оɯибᴋᴀ обᴩᴀбоᴛᴋи\n{str(e)}"

# ==================== Кэширование изображений ====================
def encode_image(image_path: str) -> str:
    """Кодирует изображение в base64 с кэшированием"""
    if image_path in IMAGE_CACHE:
        return IMAGE_CACHE[image_path]
        
    try:
        with open(image_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode('utf-8')
            IMAGE_CACHE[image_path] = encoded
            return encoded
    except Exception as e:
        DebugLogger.error(f"Ошибка кэширования изображения: {str(e)}")
        return ""

# ==================== Извлечение текста и изображений ====================
def extract_context_from_message(account: int, message: Any) -> Tuple[Optional[str], List[str]]:
    """Извлекает контекст для запроса (до 3 изображений)"""
    text = None
    image_paths = []

    if hasattr(message, 'message') and message.message:
        text = message.message

    file_loader = get_file_loader()
    
    # Обработка медиа в сообщении
    if hasattr(message, 'media') and message.media:
        if hasattr(message.media, 'document') and message.media.document:
            document = message.media.document
            if hasattr(document, 'thumb') and document.thumb:
                try:
                    image_path = str(file_loader.getPathToAttach(document.thumb, True))
                    if os.path.exists(image_path):
                        image_paths.append(image_path)
                except Exception as e:
                    DebugLogger.debug(f"Ошибка получения thumbnail: {str(e)}")
        
        elif hasattr(message.media, 'photo') and message.media.photo:
            photo = message.media.photo
            if hasattr(photo, 'sizes') and photo.sizes and photo.sizes.size() > 0:
                size = photo.sizes.get(photo.sizes.size() - 1)
                try:
                    image_path = str(file_loader.getPathToAttach(size.location, True))
                    if os.path.exists(image_path):
                        image_paths.append(image_path)
                except Exception as e:
                    DebugLogger.debug(f"Ошибка получения фото: {str(e)}")

    # Обработка прикрепленных файлов
    if hasattr(message, 'attachPath') and message.attachPath:
        try:
            attach_path = str(message.attachPath)
            if os.path.exists(attach_path):
                # Проверяем что это изображение
                ext = os.path.splitext(attach_path)[1].lower()
                if ext in SUPPORTED_IMAGE_TYPES:
                    if os.path.getsize(attach_path) <= MAX_IMAGE_SIZE:
                        image_paths.append(attach_path)
                    else:
                        DebugLogger.debug("Прикрепленное изображение слишком большое")
        except Exception as e:
            DebugLogger.debug(f"Ошибка обработки вложения: {str(e)}")
    
    # Фильтрация изображений по размеру и типу
    filtered_paths = []
    for path in image_paths:
        try:
            if os.path.exists(path):
                # Проверка типа файла
                ext = os.path.splitext(path)[1].lower()
                if ext not in SUPPORTED_IMAGE_TYPES:
                    continue
                    
                # Проверка размера
                if os.path.getsize(path) > MAX_IMAGE_SIZE:
                    DebugLogger.debug("Изображение слишком большое, пропускаем")
                    continue
                    
                filtered_paths.append(path)
        except Exception as e:
            DebugLogger.debug(f"Ошибка проверки изображения: {str(e)}")
    
    # Возвращаем до 3 изображений
    return text, filtered_paths[:3]

# ==================== Настройка кастомного DNS ====================
def setup_custom_dns(dns_server: str) -> Optional[requests.Session]:
    if not dns_server:
        return None
        
    try:
        session = requests.Session()
        
        def custom_adapter_get(self, url, **kwargs):
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            hostname = parsed_url.hostname
            
            try:
                addr_info = socket.getaddrinfo(hostname, 443, socket.AF_INET, socket.SOCK_STREAM)
                ip = addr_info[0][4][0]
                kwargs['headers'] = kwargs.get('headers', {})
                kwargs['headers']['Host'] = hostname
                new_url = url.replace(hostname, ip, 1)
                return super(type(self), self).get(new_url, **kwargs)
            except Exception as e:
                DebugLogger.error(f"Ошибка DNS резолвинга: {str(e)}")
                return super(type(self), self).get(url, **kwargs)
        
        adapter = session.get_adapter('https://')
        adapter.get = custom_adapter_get.__get__(adapter, type(adapter))
        return session
    except Exception as e:
        DebugLogger.error(f"Ошибка настройки DNS: {str(e)}")
        return None

# ==================== Запрос к ИИ платформе ====================
def fetch_ai_response(
    prompt: str, 
    api_key: str, 
    ai_model: str, 
    provider: str,
    history: List[dict],
    context_text: Optional[str] = None, 
    image_paths: Optional[List[str]] = None, 
    callback: Optional[Callable] = None,
    custom_dns: Optional[str] = None
):
    if not active_request_lock.acquire(blocking=False):
        BulletinHelper.show_info("Дождитесь завершения предыдущего запроса!")
        return

    def run_request():
        try:
            BulletinHelper.show_info(f"Запрос к {provider}...")
            
            provider_config = SUPPORTED_PROVIDERS.get(provider, SUPPORTED_PROVIDERS["OpenRouter"])
            url = provider_config["url"]
            headers = { "Content-Type": "application/json" }
            payload = {}

            system_prompt = setting_getter("system_prompt", "Ты полезный ассистент. Отвечай на русском языке.")

            # Получаем параметры из настроек
            temperature_str = setting_getter("temperature", "")
            top_p_str = setting_getter("top_p", "")
            max_tokens_str = setting_getter("max_tokens", "")

            try:
                temperature = float(temperature_str) if temperature_str else 0.7
            except ValueError:
                temperature = 0.7

            try:
                top_p = float(top_p_str) if top_p_str else 1.0
            except ValueError:
                top_p = 1.0

            try:
                max_tokens = int(max_tokens_str) if max_tokens_str else 2048
            except ValueError:
                max_tokens = 2048

            if provider in ["OpenAI", "OpenRouter", "Groq", "DeepSeek"]:
                headers.update(provider_config.get("headers", {}))
                headers["Authorization"] = f"Bearer {api_key}"

                messages = [{"role": "system", "content": system_prompt}] + history.copy()
                current_content = [{"type": "text", "text": prompt}]
                
                if context_text:
                    current_content[0]["text"] = f"Контекст: {context_text}\n\nЗапрос: {prompt}"
                
                if image_paths:
                    for img_path in image_paths:
                        try:
                            encoded_string = encode_image(img_path)
                            if encoded_string:
                                current_content.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{encoded_string}"}
                                })
                        except Exception as e:
                            DebugLogger.debug(f"Ошибка кодирования изображения: {str(e)}")
                
                messages.append({"role": "user", "content": current_content})
                payload = {
                    "model": ai_model,
                    "messages": messages,
                    "stream": False,
                    "temperature": temperature,
                    "top_p": top_p,
                    "max_tokens": max_tokens
                }

            elif provider == "Google":
                url = url.format(model=ai_model) + f"?key={api_key}"
                
                # Формат истории для Gemini
                contents = []
                for msg in history:
                    role = "model" if msg["role"] == "assistant" else "user"
                    contents.append({"role": role, "parts": [{"text": msg["content"]}]})
                
                # Текущий запрос
                current_parts = [{"text": prompt}]
                if context_text:
                    current_parts[0]["text"] = f"Контекст: {context_text}\n\nЗапрос: {prompt}"
                
                if image_paths:
                    for img_path in image_paths:
                        try:
                            encoded_string = encode_image(img_path)
                            if encoded_string:
                                current_parts.append({
                                    "inline_data": {
                                        "mime_type": "image/jpeg",
                                        "data": encoded_string
                                    }
                                })
                        except Exception as e:
                            DebugLogger.debug(f"Ошибка кодирования изображения для Google: {str(e)}")
                
                contents.append({"role": "user", "parts": current_parts})
                
                payload = {
                    "contents": contents,
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "generationConfig": {
                        "temperature": temperature,
                        "topP": top_p,
                        "maxOutputTokens": max_tokens
                    }
                }

            elif provider == "Anthropic":
                headers.update(provider_config["headers"])
                headers["Authorization"] = f"Bearer {api_key}"
                
                messages = history.copy()
                if context_text:
                    system_prompt += f"\n\nКонтекст: {context_text}"
                
                content = [{"type": "text", "text": prompt}]
                
                # Anthropic поддерживает только одно изображение
                if image_paths and len(image_paths) > 0:
                    try:
                        img_path = image_paths[0]
                        encoded_string = encode_image(img_path)
                        if encoded_string:
                            content.append({
                                "type": "image",
                                "source": { 
                                    "type": "base64", 
                                    "media_type": "image/jpeg", 
                                    "data": encoded_string 
                                }
                            })
                    except Exception as e:
                        DebugLogger.debug(f"Ошибка кодирования изображения: {str(e)}")
                
                messages.append({"role": "user", "content": content})
                payload = {
                    "model": ai_model,
                    "messages": messages,
                    "system": system_prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "top_p": top_p
                }

            # Логирование для отладки
            DebugLogger.debug(f"Payload для {provider}: {json.dumps(payload, indent=2)}")

            # --- Отправка запроса ---
            response_data = None
            session = setup_custom_dns(custom_dns) if custom_dns else requests
            
            for attempt in range(3):
                try:
                    response = session.post(url, headers=headers, json=payload, timeout=90)
                    
                    if response.status_code == 200:
                        response_data = response.json()
                        break
                    elif response.status_code == 429:
                        # Рассчитываем время ожидания
                        retry_after = int(response.headers.get('Retry-After', '30'))
                        BulletinHelper.show_info(
                            f"Лимит запросов! Повторите через {retry_after} сек."
                        )
                        time.sleep(retry_after)
                        continue
                    else:
                        try:
                            error_data = response.json()
                            error_msg = error_data.get("error", {}).get("message", "нᴇ удᴀᴧоᴄь ᴨоᴧучиᴛь оᴛʙᴇᴛ")
                        except:
                            error_msg = f"{response.status_code}: {response.text[:200]}..."
                        response_data = {"error": f"{provider} ошибка: {error_msg}"}
                        break
                except Exception as e:
                    response_data = {"error": f"Сетевая ошибка: {str(e)}"}
                    time.sleep(1)

            if not response_data:
                response_data = {"error": "нᴇ удᴀᴧоᴄь ᴨоᴧучиᴛь оᴛʙᴇᴛ"}

            if callback:
                callback(response_data, prompt)

        finally:
            active_request_lock.release()

    threading.Thread(target=run_request, daemon=True).start()

# ==================== AI Status Functions ====================
AI_API_URL = "https://text.pollinations.ai/openai/v1/chat/completions"
MEMORY_LIMIT = 15  # сохранять последние 15 генераций

def parse_interval(interval_str):
    pattern = r'(\d+)\s*(d|h|m|s)'
    matches = re.findall(pattern, interval_str.lower())
    if not matches:
        raise ValueError("Неверный формат")
    total = 0
    for v, u in matches:
        v = int(v)
        if u=='d': total += v*86400
        elif u=='h': total += v*3600
        elif u=='m': total += v*60
        elif u=='s': total += v
    return max(total, 30)

def clean_ai_text(text):
    if not text: return ""
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'http[s]?://\S+', '', text)
    text = re.sub(r'[*_~`#]', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\(\)', '', text)
    return text.strip()
    
def status_tr():
    lang = LocaleController.getInstance().getCurrentLocale().getLanguage()
    strings = {
        'ru': {
            'enable_name': "Включить обновление Имени",
            'head_enable_name': "Настройки Имени",
            'sett_name': "Настроить Имя/Фамилию",
            'head_enable_bio': "Настройки Био",
            'enable_bio': "Включить обновление Био",
            'sett_bio': "Настроить Био",
            'head_enable_geo': "Настройки Гео (TgPremium)",
            'enable_geo': "Включить обновление Гео",
            'sett_geo': "Настроить Гео",
            'head_enable_un': "Настройки Юзернейма",
            'enable_un': "Включить обновление Юзернейма",
            'sett_un': "Настроить Юзернейм",
            'head_other': "Дополнительно",
            'debug_mode': "Отладка",
            'debug_mode_desc': "Показывать отладочную информацию",
            
            'interval': "Интервал",
            'sub_interval': "Формат: 1d 2h 3m 4s",
            'div_interval': "Настройте, через какой промежуток времени текст будет меняться.",
            't_prompt': "Промпт",
            'def_name': "Придумай креативное имя",
            'sub_name': "Напр.: Придумай креативный никнейм",
            'text_on_error': "Текст при ошибке",
            't_search': "Доступ в интернет",
            'sub_search': "Если включено, AI будет иметь доступ к поиску в интернете.",
            't_memory': "Память",
            'sub_memory': "Помогает от частых повторов",
            'generate_now': "Сгенерировать сейчас",
            'div_un': "Рекомендуется менять не чаще 1 дня.",
            'def_un': "Придумай юзернейм. Одно слово, на English, без символов. В конце добавь: _AiS",
            'def_bio': "Сгенерируй креативный статус для телеграм",
            'ai_error': "ИИ недоступен",
            'generating': "Генерация",
            'generated': "сгенерировано"
        },
        'en': {
            'enable_name': "Enable Name Update",
            'head_enable_name': "Name Settings",
            'sett_name': "Set First/Last Name",
            'head_enable_bio': "Bio Settings",
            'enable_bio': "Enable Bio Update",
            'sett_bio': "Set Bio",
            'head_enable_geo': "Geo Settings (TgPremium)",
            'enable_geo': "Enable Geo Update",
            'sett_geo': "Set Geo",
            'head_enable_un': "Username Settings",
            'enable_un': "Enable Username Update",
            'sett_un': "Set Username",
            'head_other': "Additional",
            'debug_mode': "Debug",
            'debug_mode_desc': "Show debug information",

            'interval': "Interval",
            'sub_interval': "Format: 1d 2h 3m 4s",
            'div_interval': "Set the time interval for changing the text.",
            't_prompt': "Prompt",
            'def_name': "Come up with a creative name",
            'sub_name': "E.g.: Come up with a creative nickname",
            'text_on_error': "Text on error",
            't_search': "Internet Access",
            'sub_search': "If enabled, AI will have access to web search.",
            't_memory': "Memory",
            'sub_memory': "Helps avoid frequent repetitions",
            'generate_now': "Generate Now",
            'div_un': "It is recommended to change no more than once per day.",
            'def_un': "Come up with a username. One word, in English, no symbols. Add at the end: _AiS",
            'def_bio': "Generate a creative Telegram status",
            'ai_error': "AI Unavailable",
            'generating': "Generating",
            'generated': "generated"
        },

    }
    lang_key = 'ru' if lang.startswith('ru') else 'en'
    return strings[lang_key]

# ==================== Медиа загрузчик ====================
class MediaDownloader:
    def __init__(self, get_setting_func):
        self.get_setting = get_setting_func
        self._temp_dir = None
        self._cancel_requested = False
        self._drawer_settings_item = None
        self._chat_settings_item = None

    def _get_temp_dir(self):
        try:
            base_dir = ApplicationLoader.getFilesDirFixed()
            if not base_dir:
                return None
            temp_dir = File(base_dir, TEMP_DIR_NAME)
            if not temp_dir.exists() and not temp_dir.mkdirs():
                return None
            return temp_dir
        except Exception as e:
            logcat(f"Error creating temp dir: {e}")
            return None

    def _cleanup_old_files(self, max_age_hours=12):
        try:
            now = time.time()
            max_age_seconds = max_age_hours * 3600
            for file in self._temp_dir.listFiles():
                if file.isFile() and now - file.lastModified() / 1000 > max_age_seconds:
                    file.delete()
        except Exception as e:
            logcat(f"Cleanup error: {e}")

    def _socks_create_connection(self, dest_host, dest_port):
        sock = None
        try:
            url_setting = self.get_setting('proxy_url_set','').strip()
            if not url_setting or ':' not in url_setting:
                return socket.create_connection((dest_host, dest_port))
            
            if '://' in url_setting:
                url_setting = url_setting.split('://', 1)[1]
            
            user = self.get_setting('proxy_username_set','').strip()
            pwd = self.get_setting('proxy_password_set','').strip()
            
            if ':' not in url_setting:
                logcat(f"[MediaDownloader] Invalid proxy URL format: {url_setting}")
                return socket.create_connection((dest_host, dest_port))
                
            host, port_str = url_setting.split(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                logcat(f"[MediaDownloader] Invalid proxy port: {port_str}")
                return socket.create_connection((dest_host, dest_port))
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(15)
            sock.connect((host, port))
            
            methods = b'\x02' if user and pwd else b'\x00'
            sock.send(b'\x05\x01' + methods)
            response = sock.recv(2)
            if len(response) < 2:
                raise Exception("Invalid SOCKS5 response")
            
            version, method = response
            if version != 5:
                raise Exception(f"Unsupported SOCKS version: {version}")
            
            if method == 2:
                if not user or not pwd:
                    raise Exception("Username/password required but not provided")
                
                auth_request = b'\x01' + bytes([len(user)]) + user.encode() + bytes([len(pwd)]) + pwd.encode()
                sock.send(auth_request)
                auth_response = sock.recv(2)
                if len(auth_response) < 2 or auth_response[1] != 0:
                    raise Exception("SOCKS5 authentication failed")
            
            try:
                dest_ip = socket.inet_aton(dest_host)
                addr_type = b'\x01'
                addr_data = dest_ip
            except socket.error:
                addr_type = b'\x03'
                addr_data = bytes([len(dest_host)]) + dest_host.encode()
            
            connect_request = b'\x05\x01\x00' + addr_type + addr_data + int(dest_port).to_bytes(2, 'big')
            sock.send(connect_request)
            
            connect_response = sock.recv(10)
            if len(connect_response) < 4:
                raise Exception("Invalid SOCKS5 connect response")
            
            if connect_response[1] != 0:
                raise Exception(f"SOCKS5 connect failed with code: {connect_response[1]}")
            
            return sock
            
        except Exception as e:
            logcat(f"[MediaDownloader] SOCKS proxy error: {e}")
            if sock:
                try:
                    sock.close()
                except:
                    pass
            return socket.create_connection((dest_host, dest_port))

    def _mtproto_create_connection(self, dest_host, dest_port):
        sock = None
        try:
            url_setting = self.get_setting('proxy_url_set','').strip()
            if not url_setting or ':' not in url_setting:
                return socket.create_connection((dest_host, dest_port))
            
            if '://' in url_setting:
                url_setting = url_setting.split('://', 1)[1]
            
            secret = self.get_setting('proxy_username_set','').strip()
            pwd = self.get_setting('proxy_password_set','').strip()
            
            if ':' not in url_setting:
                logcat(f"[MediaDownloader] Invalid MTProto proxy URL format: {url_setting}")
                return socket.create_connection((dest_host, dest_port))
                
            host, port_str = url_setting.split(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                logcat(f"[MediaDownloader] Invalid MTProto proxy port: {port_str}")
                return socket.create_connection((dest_host, dest_port))
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(15)
            sock.connect((host, port))
            
            if secret:
                secret_bytes = secret.encode('utf-8')
                header = b'\xef\xef\xef\xef' + bytes([len(secret_bytes)]) + secret_bytes
                sock.send(header)
                
                response = sock.recv(1)
                if response != b'\xef':
                    logcat(f"[MediaDownloader] MTProto secret authentication failed")
                    sock.close()
                    return socket.create_connection((dest_host, dest_port))
            
            dest_info = f"{dest_host}:{dest_port}".encode('utf-8')
            connect_packet = b'\xdd\xdd\xdd\xdd' + bytes([len(dest_info)]) + dest_info
            sock.send(connect_packet)
            
            response = sock.recv(1)
            if response != b'\xdd':
                logcat(f"[MediaDownloader] MTProto connection setup failed")
                sock.close()
                return socket.create_connection((dest_host, dest_port))
            
            logcat(f"[MediaDownloader] MTProto proxy connection established to {dest_host}:{dest_port}")
            return sock
            
        except Exception as e:
            logcat(f"[MediaDownloader] MTProto proxy error: {e}")
            if sock:
                try:
                    sock.close()
                except:
                    pass
            return socket.create_connection((dest_host, dest_port))

    def _test_proxy_connection(self, proxies):
        try:
            if not proxies:
                return True
                
            proxy_type = self.get_setting("proxy_type_set", 0)
            
            if proxy_type == 4:
                return self._test_mtproto_connection()
            
            test_url = "http://httpbin.org/ip"
            logcat(f"[MediaDownloader] Testing proxy connection to {test_url}")
            
            response = requests.get(test_url, proxies=proxies, timeout=10)
            if response.status_code == 200:
                logcat(f"[MediaDownloader] Proxy test successful: {response.json()}")
                return True
            else:
                logcat(f"[MediaDownloader] Proxy test failed with status: {response.status_code}")
                return False
                
        except Exception as e:
            logcat(f"[MediaDownloader] Proxy test failed: {e}")
            return False

    def _test_mtproto_connection(self):
        try:
            url_setting = self.get_setting('proxy_url_set','').strip()
            if not url_setting or ':' not in url_setting:
                return False
            
            if '://' in url_setting:
                url_setting = url_setting.split('://', 1)[1]
            
            host, port_str = url_setting.split(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                return False
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((host, port))
            sock.close()
            
            logcat(f"[MediaDownloader] MTProto proxy connection test successful")
            return True
            
        except Exception as e:
            logcat(f"[MediaDownloader] MTProto proxy connection test failed: {e}")
            return False

    def _get_proxies(self):
        try:
            proxy_type = self.get_setting("proxy_type_set", 0)
            url = self.get_setting("proxy_url_set", "").strip()
            user = self.get_setting("proxy_username_set", "").strip()
            pwd = self.get_setting("proxy_password_set", "").strip()
            
            if not url or proxy_type == 0:
                return None
                
            proxies = None
            
            if proxy_type == 3:
                try:
                    import requests_html
                    hostport = url.split('://', 1)[-1] if '://' in url else url
                    if user and pwd:
                        scheme = f"socks5://{user}:{pwd}@{hostport}"
                    else:
                        scheme = f"socks5://{hostport}"
                    proxies = {"http": scheme, "https": scheme}
                    logcat(f"[MediaDownloader] SOCKS5 proxy configured: {scheme}")
                except ImportError:
                    logcat(f"[MediaDownloader] requests-html not available, using custom SOCKS implementation")
                    try:
                        m = requests.packages.urllib3.util.connection
                        original_create_connection = m.create_connection
                        m.create_connection = lambda addr, timeout=None, **kw: self._socks_create_connection(addr[0], addr[1])
                        logcat(f"[MediaDownloader] Patched urllib3 for SOCKS5 proxy")
                        return {"socks": True}
                    except Exception as e:
                        logcat(f"[MediaDownloader] Failed patching socks proxy: {e}")
                        return None
                        
            elif proxy_type in (1, 2):
                scheme = "http" if proxy_type == 1 else "https"
                
                clean_url = url
                if "://" in clean_url:
                    clean_url = clean_url.split("://", 1)[1]
                
                if user and pwd:
                    proxy_url = f"{scheme}://{user}:{pwd}@{clean_url}"
                else:
                    proxy_url = f"{scheme}://{clean_url}"
                
                proxies = {"http": proxy_url, "https": proxy_url}
                logcat(f"[MediaDownloader] HTTP/HTTPS proxy configured: {proxy_url}")
            
            elif proxy_type == 4:
                logcat(f"[MediaDownloader] MTProto proxy configured: {url}")
                try:
                    m = requests.packages.urllib3.util.connection
                    original_create_connection = m.create_connection
                    m.create_connection = lambda addr, timeout=None, **kw: self._mtproto_create_connection(addr[0], addr[1])
                    logcat(f"[MediaDownloader] Patched urllib3 for MTProto proxy")
                    return {"mtproto": True}
                except Exception as e:
                    logcat(f"[MediaDownloader] Failed patching MTProto proxy: {e}")
                    return None
            
            return proxies
            
        except Exception as e:
            logcat(f"[MediaDownloader] Error configuring proxy: {e}")
            return None

    def initialize(self):
        self._temp_dir = self._get_temp_dir()
        if self._temp_dir:
            logcat(f"[MediaDownloader] Initialized")
            self._cleanup_old_files()
        else:
            logcat("[MediaDownloader] Failed to initialize temp directory")

    def _try_download_with_api(self, api_url, video_url, payload, headers, proxies):
        try:
            resp = requests.post(f"{api_url}/", json=payload, headers=headers, timeout=30, proxies=proxies)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status")
            
            if status == "error":
                code = data.get("error", {}).get("code", "Unknown error")
                return None, f"API error: {code}"
            
            if status == "picker":
                items = data.get("picker", [])
                if not items:
                    return None, "No items to download"
                item = items[0]
                direct_url = item.get("url")
                filename = item.get("filename")
            else:
                direct_url = data.get("url")
                filename = data.get("filename")

            if not direct_url:
                return None, "Invalid API response"
                
            return {"url": direct_url, "filename": filename}, None
            
        except Exception as e:
            return None, f"Request failed: {e}"

    def _download_video(self, video_url, mode_override=None):
        try:
            api_key = self.get_setting("api_key_set", "").strip()
            proxies = self._get_proxies()
            if proxies:
                if isinstance(proxies, dict) and (proxies.get("mtproto") or proxies.get("socks")):
                    proxy_type = "MTProto" if proxies.get("mtproto") else "SOCKS"
                    proxies = None
                else:
                    if not self._test_proxy_connection(proxies):
                        proxies = None
            
            quality_setting = self.get_setting("video_quality_set", 4)
            if isinstance(quality_setting, int) and 0 <= quality_setting < len(VIDEO_QUALITY_OPTIONS):
                video_quality = VIDEO_QUALITY_OPTIONS[quality_setting]
            else:
                video_quality = str(quality_setting)
            if 'youtube.com' in video_url.lower() or 'youtu.be' in video_url.lower():
                video_quality = VIDEO_QUALITY_OPTIONS[-1]
            
            payload = {
                "url": video_url,
                "videoQuality": video_quality
            }
            
            bitrate_setting = self.get_setting("audio_bitrate_set", 5)
            if isinstance(bitrate_setting, int) and 0 <= bitrate_setting < len(AUDIO_BITRATE_OPTIONS):
                audio_bitrate = AUDIO_BITRATE_OPTIONS[bitrate_setting]
            else:
                audio_bitrate = str(bitrate_setting)
            if 'youtube.com' in video_url.lower() or 'youtu.be' in video_url.lower():
                audio_bitrate = AUDIO_BITRATE_OPTIONS[-1]
            payload["audioBitrate"] = audio_bitrate
            payload["convertGif"] = True
            
            if self.get_setting("disable_metadata_set", False):
                payload["disableMetadata"] = True

            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Api-Key {api_key}"

            api_list = []
            
            api_idx = self.get_setting("api_url_choice_set", 0)
            custom = self.get_setting("api_url_set", "")
            
            if api_idx < len(COBALT_API):
                api_list.append(COBALT_API[api_idx].rstrip('/'))
            else:
                if custom:
                    api_list.append(custom.rstrip('/'))
            
            if self.get_setting("auto_fallback_set", True):
                for i, api in enumerate(COBALT_API):
                    if i != api_idx:
                        api_list.append(api.rstrip('/'))
                if api_idx >= len(COBALT_API) and custom:
                    pass
                elif api_idx < len(COBALT_API) and custom:
                    api_list.append(custom.rstrip('/'))
            
            last_error = None
            for i, api_url in enumerate(api_list):
                try:
                    result, error = self._try_download_with_api(api_url, video_url, payload, headers, proxies)
                    if result:
                        direct_url = result["url"]
                        filename = result["filename"]
                        break
                    else:
                        last_error = error
                        continue
                except Exception as e:
                    last_error = f"API {api_url} failed: {e}"
                    continue
            else:
                if len(api_list) > 1:
                    BulletinHelper.show_error(f"All {len(api_list)} APIs failed. Last error: {last_error}")
                else:
                    BulletinHelper.show_error(f"API failed: {last_error}")
                return None
            filename = filename or f"video_{uuid.uuid4()}.mp4"
            file_path = File(self._temp_dir, filename).getAbsolutePath()

            try:
                video_resp = requests.get(direct_url, stream=True, timeout=60, proxies=proxies)
                video_resp.raise_for_status()
            except Exception as e:
                if direct_url.startswith("https://"):
                    fallback_dl = direct_url.replace("https://", "http://")
                    video_resp = requests.get(fallback_dl, stream=True, timeout=60, proxies=proxies)
                    video_resp.raise_for_status()
                else:
                    raise
                
            content_length = video_resp.headers.get("content-length")
            total_length = int(content_length) if content_length else 0
            downloaded = 0

            with open(file_path, "wb") as f:
                for chunk in video_resp.iter_content(chunk_size=8192):
                    if self._cancel_requested:
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass
                        return None
                    f.write(chunk)
                    if total_length:
                        downloaded += len(chunk)
                        percent = int(downloaded * 100 / total_length)
                        run_on_ui_thread(lambda p=percent: progress_dialog.set_progress(p))

            return file_path
            
        except Exception as e:
            self._dismiss_dialog()
            logcat(f"[MediaDownloader] Download error: {e}\n{traceback.format_exc()}")
            BulletinHelper.show_error(f"Download error: {e}")
            return None

    def send_video(self, video_path: str, dialog_id: int, caption: str = None, notify: bool = True, schedule_date: int = 0, reply_to_msg=None, reply_to_top_msg=None):
        ttl = 0
        force_document = False
        has_media_spoilers = False
        cover_path = None
        quick_reply_shortcut = None
        quick_reply_shortcut_id = 0
        effect_id = 0
        stars = 0
        logcat(f"[MediaDownloader] send_video entry for path: {video_path}, dialog: {dialog_id}")
        ext = os.path.splitext(video_path)[1].lower()
        if ext in [".mp3", ".wav", ".ogg", ".opus", ".m4a"]:
            return self.send_audio(video_path, dialog_id, caption, notify, schedule_date, reply_to_msg, reply_to_top_msg)
        try:
            account_instance = get_account_instance()
            if account_instance is None:
                logcat("[MediaDownloader] Error: Could not get AccountInstance.")
                return
            entities = None
            if caption:
                mdc = get_media_data_controller()
                if mdc:
                    entities = mdc.getEntities([caption], True)

            SendMessagesHelper.prepareSendingVideo(
                account_instance,
                video_path,
                None,
                cover_path,
                None,
                dialog_id,
                reply_to_msg,
                reply_to_top_msg,
                None,
                None,
                entities,
                ttl,
                None,
                notify,
                schedule_date,
                force_document,
                has_media_spoilers,
                caption,
                quick_reply_shortcut,
                quick_reply_shortcut_id,
                effect_id,
                stars
            )
            logcat(f"[MediaDownloader] Video sending initiated for path: {video_path} to dialog: {dialog_id}")

        except Exception as e:
            logcat(f"[MediaDownloader] Error preparing video for sending: {e}\n{traceback.format_exc()}")
            BulletinHelper.show_error(f"Error sending video: {e}")

    def send_audio(self, audio_path: str, dialog_id: int, caption: str = None, notify: bool = True, schedule_date: int = 0, reply_to_msg=None, reply_to_top_msg=None):
        logcat(f"[MediaDownloader] send_audio entry for path: {audio_path}, dialog: {dialog_id}")
        try:
            account_instance = get_account_instance()
            if account_instance is None:
                logcat("[MediaDownloader] Error: Could not get AccountInstance.")
                return
            import mimetypes
            mime, _ = mimetypes.guess_type(audio_path)
            if mime is None:
                ext = os.path.splitext(audio_path)[1].lower()
                if ext == ".mp3":
                    mime = "audio/mpeg"
                elif ext == ".wav":
                    mime = "audio/wav"
                elif ext in [".ogg", ".opus", ".m4a"]:
                    mime = "audio/ogg"
                else:
                    mime = "application/octet-stream"
            ext_cache_root = ApplicationLoader.applicationContext.getExternalCacheDir()
            plugin_ext_dir = File(ext_cache_root, TEMP_DIR_NAME)
            if not plugin_ext_dir.exists() and not plugin_ext_dir.mkdirs():
                logcat("[MediaDownloader] Failed to create external temp dir")
            external_path = File(plugin_ext_dir, File(audio_path).getName()).getAbsolutePath()
            with open(audio_path, 'rb') as f_in, open(external_path, 'wb') as f_out:
                while True:
                    chunk = f_in.read(8192)
                    if not chunk:
                        break
                    f_out.write(chunk)
            audio_path = external_path
            SendMessagesHelper.prepareSendingDocument(
                account_instance,
                audio_path,
                audio_path,
                None,
                caption,
                mime,
                dialog_id,
                reply_to_msg, reply_to_top_msg, None, None, None,
                notify, schedule_date, None, None, 0, False
            )
        except Exception as e:
            logcat(f"[MediaDownloader] Error preparing audio for sending: {e}, type: {type(e)}")
            logcat(f"[MediaDownloader] {traceback.format_exc()}")
            BulletinHelper.show_error(f"Error sending audio: {e}")

    def _delete_file_delayed(self, path, delay=60):
        def action():
            try:
                time.sleep(delay)
                if os.path.exists(path):
                    os.remove(path)
                    logcat(f"[MediaDownloader] Deleted temp file: {path}")
            except Exception as e:
                logcat(f"[MediaDownloader] Delayed delete error: {e}")

        threading.Thread(target=action, daemon=True).start()

    def _process_download_and_send(self, url, dialog_id, notify, schedule_date, mode_override=None, reply_to_msg=None, reply_to_top_msg=None):
        try:
            video_path = self._download_video(url, mode_override)
            if video_path:
                if os.path.exists(video_path):
                    logcat(f"[MediaDownloader] File exists, proceeding to send: {video_path}")
                    ext = os.path.splitext(video_path)[1].lower()
                    include_source = self.get_setting("include_source_set", True)
                    caption_text = f"Source: {url}" if include_source else None
                    account_instance = get_account_instance()
                    send_as_file = self.get_setting("send_as_file_set", False)
                    
                    if ext == ".gif":
                        self._send_gif_as_document(video_path, dialog_id, caption_text, notify, schedule_date, reply_to_msg, reply_to_top_msg)
                        self._delete_file_delayed(video_path)
                        self._dismiss_dialog()
                        return
                    
                    if send_as_file:
                        lang = LocaleController.getInstance().getCurrentLocale().getLanguage()
                        BulletinHelper.show_error("Извини, я немощный, не могу отправить .gif" if lang.startswith('ru') else "Sorry, I'm powerless, I cannot send .gif")
                        self._delete_file_delayed(video_path)
                        self._dismiss_dialog()
                        return
                    
                    image_exts = [".jpg", ".jpeg", ".png"]
                    audio_exts = [".mp3", ".wav", ".ogg", ".opus", ".m4a"]
                    if ext in image_exts:
                        send_as_file = self.get_setting("send_as_file_set", False)
                        if send_as_file:
                            mime = "application/octet-stream"
                            run_on_ui_thread(lambda: SendMessagesHelper.prepareSendingDocument(
                                account_instance,
                                video_path,
                                video_path,
                                None,
                                caption_text,
                                mime,
                                dialog_id,
                                reply_to_msg, reply_to_top_msg, None, None, None,
                                notify, schedule_date, None, None, 0, False
                            ))
                            self._delete_file_delayed(video_path)
                            self._dismiss_dialog()
                            return
                        if include_source:
                            entities = ArrayList()
                            ent = TLRPC.TL_messageEntityTextUrl()
                            ent.offset = 0; ent.length = len("Source"); ent.url = url
                            entities.add(ent)
                            SendMessagesHelper.prepareSendingPhoto(
                                account_instance, video_path, None, dialog_id,
                                reply_to_msg, reply_to_top_msg, None, "Source", entities,
                                None, None, 0, None, notify, schedule_date,
                                0, None, 0
                            )
                        else:
                            SendMessagesHelper.prepareSendingPhoto(
                                account_instance, video_path, None, dialog_id,
                                reply_to_msg, reply_to_top_msg, None, None, None,
                                None, None, 0, None, notify, schedule_date,
                                0, None, 0
                            )
                    elif ext in audio_exts:
                        self.send_audio(video_path, dialog_id, caption_text, notify, schedule_date, reply_to_msg, reply_to_top_msg)
                    elif ext == ".gif":
                        lang = LocaleController.getInstance().getCurrentLocale().getLanguage()
                        BulletinHelper.show_error("Извини, я немощный, не могу отправить .gif" if lang.startswith('ru') else "Sorry, I'm powerless, I cannot send .gif")
                        self._delete_file_delayed(video_path)
                        self._dismiss_dialog()
                        return
                    else:
                        if include_source:
                            entities = ArrayList()
                            ent = TLRPC.TL_messageEntityTextUrl()
                            ent.offset = 0; ent.length = len("Source"); ent.url = url
                            entities.add(ent)
                            SendMessagesHelper.prepareSendingVideo(
                                account_instance, video_path, None, None, None, dialog_id,
                                reply_to_msg, reply_to_top_msg, None, None, entities,
                                0, None, notify, schedule_date,
                                False, False, "Source", None, 0, 0, 0
                            )
                        else:
                            self.send_video(video_path, dialog_id, None, notify, schedule_date, reply_to_msg, reply_to_top_msg)
                    self._delete_file_delayed(video_path)
                    self._dismiss_dialog()
                else:
                    logcat(f"[MediaDownloader] Downloaded file not found after download: {video_path}")
                    BulletinHelper.show_error(f"Internal error: File not found after download")
                    self._dismiss_dialog()
                    return
            else:
                logcat(f"[MediaDownloader] Failed to download video for url: {url}")
                self._dismiss_dialog()
                return

        except Exception as e:
            self._dismiss_dialog()
            logcat(f"[MediaDownloader] Error in _process_download_and_send: {e}\n{traceback.format_exc()}")
            BulletinHelper.show_error(f"An unexpected error occurred: {e}")

    def _dismiss_dialog(self):
        global progress_dialog
        def action():
            global progress_dialog
            if progress_dialog is not None:
                try:
                    dlg = progress_dialog.get_dialog() if hasattr(progress_dialog, 'get_dialog') else progress_dialog
                    if dlg and dlg.isShowing():
                        dlg.dismiss()
                except Exception:
                    pass
                finally:
                    progress_dialog = None
        run_on_ui_thread(action)

    def _show_loading_alert(self):
        global progress_dialog
        self._cancel_requested = False
        fragment = get_last_fragment()
        ctx = fragment.getContext() if fragment else ApplicationLoader.applicationContext
        builder = AlertDialogBuilder(ctx, AlertDialogBuilder.ALERT_TYPE_LOADING)
        builder.set_title("Downloading...")
        builder.set_negative_button("Cancel", self._on_progress_cancel)
        builder.set_cancelable(False)
        progress_dialog = builder.show()
        progress_dialog.set_progress(0)

    def _on_progress_cancel(self, builder, which):
        self._cancel_requested = True
        self._dismiss_dialog()

    def _copy_to_clipboard(self, label, text):
        fragment = get_last_fragment()
        ctx = fragment.getContext() if fragment else ApplicationLoader.applicationContext
        clipboard = ctx.getSystemService(Context.CLIPBOARD_SERVICE)
        clip = ClipData.newPlainText(label, text)
        clipboard.setPrimaryClip(clip)
        BulletinHelper.show_info(f"Copied {label} to clipboard")

    def _open_link(self, url):
        fragment = get_last_fragment()
        ctx = fragment.getContext() if fragment else ApplicationLoader.applicationContext
        intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
        run_on_ui_thread(lambda: ctx.startActivity(intent))

    def show_my_info_alert(self, title="TITLE", message="MESSAGE", positive_button="OK", neutral_button=None, neutral_link=None, neutral_type=None):
        fragment = get_last_fragment()
        ctx = fragment.getContext() if fragment else ApplicationLoader.applicationContext
        builder = AlertDialogBuilder(ctx, AlertDialogBuilder.ALERT_TYPE_MESSAGE)
        builder.set_title(title)
        builder.set_message(message)
        builder.set_positive_button(positive_button, lambda b, w: self._dismiss_dialog(b))
        if neutral_button:
            if neutral_type == "link":
                builder.set_neutral_button(neutral_button, lambda b, w: self._open_link(neutral_link))
            else:
                builder.set_neutral_button(neutral_button, lambda b, w: self._copy_to_clipboard(neutral_button, neutral_link))
        self.alert_builder_instance = builder.show()

    def _send_gif_as_document(self, gif_path, dialog_id, caption, notify, schedule_date, reply_to_msg=None, reply_to_top_msg=None):
        try:
            account_instance = get_account_instance()
            if account_instance is None:
                logcat("[MediaDownloader] Error: Could not get AccountInstance.")
                return
            
            ext_cache_root = ApplicationLoader.applicationContext.getExternalCacheDir()
            plugin_ext_dir = File(ext_cache_root, TEMP_DIR_NAME)
            if not plugin_ext_dir.exists() and not plugin_ext_dir.mkdirs():
                logcat("[MediaDownloader] Failed to create external temp dir")
            
            external_path = File(plugin_ext_dir, "animation.gif").getAbsolutePath()
            with open(gif_path, 'rb') as f_in, open(external_path, 'wb') as f_out:
                while True:
                    chunk = f_in.read(8192)
                    if not chunk:
                        break
                    f_out.write(chunk)
            
            SendMessagesHelper.prepareSendingDocument(
                account_instance, 
                external_path, 
                external_path, 
                None, 
                caption, 
                "image/gif", 
                dialog_id,
                reply_to_msg, 
                reply_to_top_msg, 
                None, 
                None, 
                None,
                notify, 
                schedule_date, 
                None, 
                None, 
                0, 
                False
            )
            
            logcat(f"[MediaDownloader] GIF sent successfully: {external_path}")
            
        except Exception as e:
            logcat(f"[MediaDownloader] Error sending GIF: {e}\n{traceback.format_exc()}")
            BulletinHelper.show_error(f"Error sending GIF: {e}")

    def _test_current_proxy(self):
        def test_proxy():
            try:
                proxy_type = self.get_setting("proxy_type_set", 0)
                if proxy_type == 0:
                    BulletinHelper.show_error("Прокси не настроен" if LocaleController.getInstance().getCurrentLocale().getLanguage().startswith('ru') else "No proxy configured")
                    return
                
                if proxy_type == 4:
                    success = self._test_mtproto_connection()
                elif proxy_type == 3:
                    success = self._test_socks_connection()
                else:
                    proxies = self._get_proxies()
                    if proxies and not isinstance(proxies, dict):
                        success = self._test_proxy_connection(proxies)
                    else:
                        success = False
                
                if success:
                    BulletinHelper.show_success("Тест подключения прокси успешен!" if LocaleController.getInstance().getCurrentLocale().getLanguage().startswith('ru') else "Proxy connection test successful!")
                else:
                    BulletinHelper.show_error("Тест подключения прокси не удался" if LocaleController.getInstance().getCurrentLocale().getLanguage().startswith('ru') else "Proxy connection test failed")
                    
            except Exception as e:
                logcat(f"[MediaDownloader] Proxy test error: {e}")
                BulletinHelper.show_error(f"Ошибка теста прокси: {e}" if LocaleController.getInstance().getCurrentLocale().getLanguage().startswith('ru') else f"Proxy test error: {e}")
        
        threading.Thread(target=test_proxy, daemon=True).start()

    def _test_socks_connection(self):
        try:
            url_setting = self.get_setting('proxy_url_set','').strip()
            if not url_setting or ':' not in url_setting:
                return False
            
            if '://' in url_setting:
                url_setting = url_setting.split('://', 1)[1]
            
            host, port_str = url_setting.split(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                return False
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((host, port))
            sock.close()
            
            logcat(f"[MediaDownloader] SOCKS proxy connection test successful")
            return True
            
        except Exception as e:
            logcat(f"[MediaDownloader] SOCKS proxy connection test failed: {e}")
            return False

    def process_command(self, account, params):
        if not hasattr(params, "message") or not isinstance(params.message, str):
            return HookResult()

        msg = params.message.strip()
        if msg.startswith(".down ") or msg.startswith(".dl "):
            parts = msg.split()
            mode_override = None
            if len(parts) > 2:
                mode_override = parts[2].lower()
            if len(parts) < 2 or not parts[1]:
                BulletinHelper.show_error("No URL provided")
                return HookResult(strategy=HookStrategy.CANCEL)

            url = parts[1].strip()
            dialog_id = params.peer
            notify = True
            schedule_date = 0

            logcat(f"[MediaDownloader] Received command: {msg}. Starting background thread for URL: {url}")

            thread = threading.Thread(
                target=self._process_download_and_send,
                args=(url, dialog_id, notify, schedule_date, mode_override, params.replyToMsg, params.replyToTopMsg),
                daemon=True
            )
            thread.start()

            logcat("[MediaDownloader] Background thread started. Cancelling original message.")
            run_on_ui_thread(lambda: self._show_loading_alert())
            return HookResult(strategy=HookStrategy.CANCEL)

        return HookResult()

# ==================== Основной класс плагина ====================
class UnifiedAIPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        # Для AI Status
        self.status_running = False
        self.status_memory = {"name":[], "bio":[], "geo":[], "username":[]}
        # Для Media Downloader
        self.media_downloader = MediaDownloader(self.get_setting)
        
    def on_plugin_load(self):
        global setting_getter
        setting_getter = self.get_setting
        
        # Загрузка чат-ассистента
        self.add_on_send_message_hook()
        DebugLogger.debug("Плагин загружен (ИИ Чат)")
        
        # Запуск worker для AI Status
        self.status_running = True
        threading.Thread(target=self.status_worker, daemon=True).start()

        # Инициализация Media Downloader
        self.media_downloader.initialize()

    def on_plugin_unload(self):
        self.status_running = False

    def create_settings(self):
        # Выбор раздела
        return [
            Header(text="Выберите раздел"),
            Text(text="🤖 ИИ Чат-ассистент", 
                 icon="chat", 
                 accent=True, 
                 create_sub_fragment=self.create_ai_chat_settings),
            Text(text="🌟 AI Status", 
                 icon="msg_online", 
                 accent=True, 
                 create_sub_fragment=self.create_ai_status_settings),
            Text(text="📥 Media Downloader", 
                 icon="exteraPluginsSup/0", 
                 accent=True, 
                 create_sub_fragment=self.create_media_downloader_settings),
        ]

    def create_ai_chat_settings(self):
        default_provider = "OpenRouter"
        default_model = SUPPORTED_PROVIDERS[default_provider]["models"][0]
        
        settings = [
            Header(text="нᴀᴄᴛᴩойᴋи ии"),
            Input(
                key="ai_provider",
                text="ᴨᴩоʙᴀйдᴇᴩ ии",
                subtext=f"доᴄᴛуᴨно: {', '.join(SUPPORTED_PROVIDERS.keys())}",
                default="OpenRouter",
                icon="language"
            ),
            Input(
                key="ai_model",
                text="ʍодᴇᴧь ии",
                subtext="ʙыбᴇᴩиᴛᴇ ʍодᴇᴧь",
                default=default_model,
                icon="model"
            ),
            Input(
                key="response_header",
                text="зᴀᴦоᴧоʙоᴋ оᴛʙᴇᴛᴀ",
                subtext="ᴨᴩиʍᴇᴩ: ✨ ии ᴀᴄᴄиᴄᴛᴇнᴛ",
                default="ии ᴀᴄᴄиᴄᴛᴇнᴛ",
                icon="msg2_autodelete"
            ),
            Input(
                key="custom_dns",
                text="ᴋᴀᴄᴛоʍный DNS",
                subtext="Например: 8.8.8.8 (оставьте пустым для системного DNS)",
                default="",
                icon="network"
            ),
            Switch(
                key="enable_chat_history",
                text="иᴄᴛоᴩия диᴀᴧоᴦоʙ",
                subtext="ᴄохᴩᴀниᴛь ᴋонᴛᴇᴋᴄᴛ ʍᴇжду ᴄообщᴇнияʍи",
                default=True,
                icon="chat"
            ),
            Switch(
                key="enable_markdown",
                text="📝 ɸоᴩʍᴀᴛиᴩоʙᴀниᴐ ᴍᴀʀᴋᴅᴏᴡɴ",
                subtext="ʙᴋᴧючиᴛь ɸоᴩᴄиᴩоʙᴀниᴇ",
                default=True,
                icon="text"
            ),
            Switch(
                key="enable_debug_logging",
                text="ᴧоᴦиᴩоʙᴀния зᴀᴨᴩоᴄоʋ",
                subtext="дᴧя диᴀᴦноᴄᴛиᴋи ᴨᴩобᴧᴇʍ",
                default=False,
                icon="debug"
            ),
            Header(text="РАСШИРЕННЫЕ НАСТРОЙКИ"),
            Input(
                key="system_prompt",
                text="ᴄиᴄᴛᴇʍный ᴨᴩоʍᴨᴛ",
                subtext="ᴨᴩоʍᴨᴛ, ᴋоᴛоᴩый будᴇᴛ оᴛᴨᴩᴀʙᴧᴇн ʍодᴇᴧи ᴨᴇᴩᴇд ᴋᴀждыʍ зᴀᴨᴩоᴄоʍ",
                default="Ты полезный ассистент. Отвечай на русском языке.",
                icon="prompt"
            ),
            Input(
                key="temperature",
                text="Температура",
                subtext="Контролирует случайность ответов (0.0 - 1.0)",
                default="0.7",
                icon="settings"
            ),
            Input(
                key="top_p",
                text="Top P",
                subtext="Контролирует разнообразие ответов (0.0 - 1.0)",
                default="1.0",
                icon="settings"
            ),
            Input(
                key="max_tokens",
                text="Макс. токены",
                subtext="Максимальная длина ответа",
                default="2048",
                icon="settings"
            ),
            Divider(),
            Header(text="Настройки изображений"),
            Input(
                key="max_image_size_mb",
                text="Макс. размер изображения (МБ)",
                subtext="Рекомендуется 5-15 МБ",
                default="15",
                icon="photo"
            ),
            Switch(
                key="compress_images",
                text="Сжимать изображения",
                subtext="Уменьшать размер перед отправкой",
                default=False,
                icon="compress"
            ),
            Divider(),
            Header(text="API ключи для провайдеров")
        ]

        for provider in SUPPORTED_PROVIDERS.keys():
            settings.append(
                Input(
                    key=f"api_key_{provider.lower()}",
                    text=f"API ключ для {provider}",
                    subtext=f"Ключ для доступа к {provider}",
                    default="",
                    icon="key"
                )
            )

        return settings

    def create_ai_status_settings(self):
        s = status_tr()
        return [
            Header(text=s["head_enable_name"]),
            Switch(key="enable_name", text=s['enable_name'], default=False, icon="msg_openprofile"),
            Text(text=s["sett_name"], icon="msg_download_settings", create_sub_fragment=self.create_name_settings),
            Divider(),
            Header(text=s["head_enable_bio"]),
            Switch(key="enable_bio", text=s["enable_bio"], default=False, icon="msg_online"),
            Text(text=s["sett_bio"], icon="msg_download_settings", create_sub_fragment=self.create_bio_settings),
            Divider(),
            Header(text=s["head_enable_geo"]),
            Switch(key="enable_geo", text=s["enable_geo"], default=False, icon="menu_premium_location"),
            Text(text=s["sett_geo"], icon="msg_download_settings", create_sub_fragment=self.create_geo_settings),
            Divider(),
            Header(text=s["head_enable_un"]),
            Switch(key="enable_username", text=s["enable_un"], default=False, icon="msg_openprofile"),
            Text(text=s["sett_un"], icon="msg_download_settings", create_sub_fragment=self.create_username_settings),
            Divider(),
            Header(text=s["head_other"]),
            Switch(key="debug_mode", text=s["debug_mode"], subtext=s["debug_mode_desc"], default=False, icon="msg_info"),
        ]

    def create_media_downloader_settings(self):
        lang = LocaleController.getInstance().getCurrentLocale().getLanguage()
        if lang.startswith('ru'):
            idx = 0
        else:
            idx = 1
        api_idx = self.get_setting("api_url_choice_set", 0)
        proxy_type_val = self.get_setting("proxy_type_set", 0)
        proxy_icon = "msg2_proxy_off" if proxy_type_val == 0 else "msg2_proxy_on"
        settings = [
            Header(text=Z_downloader("api_title")),
            Selector(key="api_url_choice_set", text=Z_downloader("api_url"), icon="msg2_devices", default=api_idx, items=COBALT_API + [Z_downloader("custom_api")]),
        ]
        if api_idx == len(COBALT_API):
            settings.extend([
                Input(key="api_url_set", text=Z_downloader("custom_api_url"), icon="msg_instant_link", default=self.get_setting("api_url_set", "")),
                Input(key="api_key_set", text=Z_downloader("api_key"), icon="msg_pin_code", default=self.get_setting("api_key_set", "")),
                Text(text=Z_downloader("api_help"), icon="msg_psa", accent=True, on_click=lambda view: self.media_downloader.show_my_info_alert(title=Z_downloader("api_title"), message=Z_downloader("api_desc"), neutral_button="GitHub", neutral_link="https://github.com/imputnet/cobalt", neutral_type="link")),
            ])
        settings.extend([
            Header(text=Z_downloader("proxy_title")),
            Selector(key="proxy_type_set", text=Z_downloader("proxy_type"), icon=proxy_icon, default=proxy_type_val, items=MEDIA_DOWNLOADER_TRANSLATIONS["proxy_type_items"][idx]),
        ])
        if self.get_setting("proxy_type_set", 0) != 0:
            proxy_type_val = self.get_setting("proxy_type_set", 0)
            if proxy_type_val == 4:
                settings.extend([
                    Input(key="proxy_url_set", text=Z_downloader("proxy_url"), icon="msg_link", default=self.get_setting("proxy_url_set", ""), subtext=Z_downloader("proxy_url_desc")),
                    Input(key="proxy_username_set", text=Z_downloader("proxy_secret"), icon="msg_pin_code", default=self.get_setting("proxy_username_set", ""), subtext=Z_downloader("proxy_secret_desc")),
                    Text(text=Z_downloader("test_proxy"), icon="msg_message", accent=True, on_click=lambda view: self.media_downloader._test_current_proxy()),
                ])
            else:
                settings.extend([
                    Input(key="proxy_url_set", text=Z_downloader("proxy_url"), icon="msg_link", default=self.get_setting("proxy_url_set", ""), subtext=Z_downloader("proxy_url_desc")),
                    Input(key="proxy_username_set", text=Z_downloader("proxy_user"), icon="msg_contacts", default=self.get_setting("proxy_username_set", "")),
                    Input(key="proxy_password_set", text=Z_downloader("proxy_password"), icon="msg_pin_code", default=self.get_setting("proxy_password_set", "")),
                    Text(text=Z_downloader("test_proxy"), icon="msg_message", accent=True, on_click=lambda view: self.media_downloader._test_current_proxy()),
                ])
        settings.extend([
            Header(text=Z_downloader("settings_title")),
            Switch(key="auto_fallback_set", text=Z_downloader("auto_fallback"), icon="media_flip", default=self.get_setting("auto_fallback_set", True), subtext=Z_downloader("auto_fallback_desc")),
            Switch(key="show_settings_buttons_set", text=Z_downloader("show_settings_buttons"), icon="msg_reorder", default=self.get_setting("show_settings_buttons_set", True), subtext=Z_downloader("show_settings_buttons_desc")),
            Switch(key="include_source_set", text=Z_downloader("include_source"), icon="msg_link", default=self.get_setting("include_source_set", True), subtext=Z_downloader("include_source_desc")),
            Switch(key="send_as_file_set", text=Z_downloader("send_as_file"), icon="msg_sendfile", default=self.get_setting("send_as_file_set", False), subtext=Z_downloader("send_as_file_desc")),
        ])
        if self.get_setting("send_as_file_set", False):
            settings.extend([
                Switch(key="disable_metadata_set", text=Z_downloader("disable_metadata"), icon="menu_intro", default=self.get_setting("disable_metadata_set", False), subtext=Z_downloader("disable_metadata_desc")),
            ])
        settings.extend([
            Switch(key="show_advanced_set", text=Z_downloader("advanced_settings"), icon="msg_settings_14", default=self.get_setting("show_advanced_set", False), subtext=Z_downloader("advanced_settings_desc")),
        ])
        if self.get_setting("show_advanced_set", False):
            settings.extend([
                Selector(key="video_quality_set", text=Z_downloader("video_quality"), icon="msg_video", default=self.get_setting("video_quality_set", 5), items=VIDEO_QUALITY_OPTIONS),
                Selector(key="audio_bitrate_set", text=Z_downloader("audio_bitrate"), icon="input_mic", default=self.get_setting("audio_bitrate_set", 5), items=AUDIO_BITRATE_OPTIONS),
            ])
        settings.extend([
            Text(text=Z_downloader("services"), accent=True, icon="menu_premium_main", on_click=lambda view: self.media_downloader.show_my_info_alert(title=Z_downloader("services"),message=SERVICES_INFO)),
            Divider(text=Z_downloader("usage_cmd")),
            Header(text=Z_downloader("donate_title")),
            Text(text="TON", icon="msg_ton", accent=True, on_click=lambda view: run_on_ui_thread(lambda: self.media_downloader._copy_to_clipboard("TON", "exteralover.ton"))),
            Text(text=Z_downloader("donate_info"), icon="msg_reactions", accent=True, on_click=lambda view: run_on_ui_thread(lambda: get_messages_controller().openByUserName("v1edsinfo", get_last_fragment(), 1))),
        ])
        
        return settings

    def create_name_settings(self):
        s = status_tr()
        return [
            Input(key="name_interval", text=s["interval"], default="1h", subtext=s["sub_interval"], icon="msg_recent"),
            Divider(s["div_interval"]),
            Input(key="name_prompt", text=s["t_prompt"], default=s["def_name"], subtext=s["sub_name"], icon="msg_photo_text_regular"),
            Input(key="name_fallback", text=s["text_on_error"], default="...", icon="msg_info"),
            Divider(),
            Switch(key="enable_name_search", text=s["t_search"], subtext=s["sub_search"], default=False, icon="msg_language"),
            Switch(key="mem_name", text=s["t_memory"], subtext=s["sub_memory"], default=False, icon="files_storage"),
            Divider(),
            Text(text=s["generate_now"], icon="msg_header_draw", accent=True, on_click=lambda v: self.manual_generate("name")),
        ]

    def create_username_settings(self):
        s = status_tr()
        return [
            Input(key="username_interval", text=s["interval"], default="1h", subtext=s["sub_interval"], icon="msg_recent"),
            Divider(s["div_un"]),
            Input(key="username_prompt", text=s["t_prompt"], default=s["def_un"], subtext=s["sub_name"], icon="msg_photo_text_regular"),
            Input(key="username_fallback", text=s["text_on_error"], default="user123", icon="msg_info"),
            Divider(),
            Switch(key="enable_username_search", text=s["t_search"], subtext=s["sub_search"], default=False, icon="msg_language"),
            Switch(key="mem_username", text=s["t_memory"], subtext=s["sub_memory"], default=False, icon="files_storage"),
            Divider(),
            Text(text=s["generate_now"], icon="msg_header_draw", accent=True, on_click=lambda v: self.manual_generate("username")),
        ]

    def create_bio_settings(self):
        s = status_tr()
        return [
            Input(key="bio_interval", text=s["interval"], default="30m", subtext=s["sub_interval"], icon="msg_recent"),
            Divider(s["div_interval"]),
            Input(key="bio_prompt", text=s["t_prompt"], default=s["def_bio"], subtext=s["sub_name"], icon="msg_photo_text_regular"),
            Input(key="bio_fallback", text=s["text_on_error"], default=s["ai_error"], icon="msg_info"),
            Divider(),
            Switch(key="enable_bio_search", text=s["t_search"], subtext=s["sub_search"], default=False, icon="msg_language"),
            Switch(key="mem_bio", text=s["t_memory"], subtext=s["sub_memory"], default=False, icon="files_storage"),
            Divider(),
            Text(text=s["generate_now"], icon="msg_header_draw", accent=True, on_click=lambda v: self.manual_generate("bio")),
        ]

    def create_geo_settings(self):
        s = status_tr()
        return [
            Input(key="geo_interval", text=s["interval"], default="30m", subtext=s["sub_interval"], icon="msg_recent"),
            Divider(s["div_interval"]),
            Input(key="geo_prompt", text=s["t_prompt"], default=s["def_bio"], subtext=s["sub_name"], icon="msg_photo_text_regular"),
            Input(key="geo_fallback", text=s["text_on_error"], default=s["ai_error"], icon="msg_info"),
            Divider(),
            Switch(key="enable_geo_search", text=s["t_search"], subtext=s["sub_search"], default=False, icon="msg_language"),
            Switch(key="mem_geo", text=s["t_memory"], subtext=s["sub_memory"], default=False, icon="files_storage"),
            Divider(),
            Text(text=s["generate_now"], icon="msg_header_draw", accent=True, on_click=lambda v: self.manual_generate("geo")),
        ]

    def status_worker(self):
        last = {"name":0,"username":0,"bio":0,"geo":0}
        while self.status_running:
            now = time.time()
            for mode in ("name","username","bio","geo"):
                if self.get_setting(f"enable_{mode}", False):
                    try:
                        interval = parse_interval(self.get_setting(f"{mode}_interval", "30m"))
                        if now - last[mode] >= interval:
                            getattr(self, f"update_{mode}")()
                            last[mode] = now
                    except Exception as e:
                        DebugLogger.error(f"Ошибка в status_worker: {str(e)}")
            time.sleep(5)

    def build_system_prompt(self, mode):
        t = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mem = ""
        if self.get_setting(f"mem_{mode}", False):
            mem_list = self.status_memory.get(mode, [])[-MEMORY_LIMIT:]
            if mem_list:
                mem = "Не повторяй, уже было: " + ", ".join(mem_list)
        base = f"Ты генерируель короткую, чистую, БЕЗ форматирования, лишнего текста, фразу для  {mode} в Telegram.\nНе пиши «хорошо», «привет», «```», заголовки и тому подобное, пиши ТОЛЬКО одну фразу, по скольку есть ограничение по символам. Пиши на языке пользовательского запроса.\n\nТекущее время: {t}."
        return base + ("\n\n " + mem if mem else "")

    def get_ai_status(self, prompt, mode):
        model = "searchgpt" if self.get_setting(f"enable_{mode}_search", False) else "openai-fast"
        try:
            sc = [{"role":"system","content":self.build_system_prompt(mode)},
                  {"role":"user","content":prompt}]
            resp = requests.post(AI_API_URL, json={"model":model,"messages":sc}, timeout=15)
            if resp.status_code==200:
                text = clean_ai_text(resp.json()["choices"][0]["message"]["content"])
                if self.get_setting(f"mem_{mode}", False):
                    self.status_memory.setdefault(mode, []).append(text)
                    self.status_memory[mode] = self.status_memory[mode][-MEMORY_LIMIT:]
                return text
            if self.get_setting("debug_mode", False):
                return f"Ошибка API: {resp.status_code}"
        except Exception as e:
            if self.get_setting("debug_mode", False):
                return f"Ошибка: {e}"
        return None

    def update_name(self):
        text = self.get_ai_status(self.get_setting("name_prompt",""), "name") or self.get_setting("name_fallback","")
        parts = text.split()
        req = TL_account.updateProfile()
        req.flags = (1<<0)|(1<<1)
        req.first_name = parts[0][:64]
        req.last_name = " ".join(parts[1:])[:64] if len(parts)>1 else ""
        send_request(req, ())

    def update_username(self):
        text = self.get_ai_status(self.get_setting("username_prompt",""), "username") or self.get_setting("username_fallback","")
        req = TL_account.updateUsername()
        req.username = text
        send_request(req, ())

    def update_bio(self):
        text = self.get_ai_status(self.get_setting("bio_prompt",""), "bio") or self.get_setting("bio_fallback","")
        max_len = 140 if get_user_config().isPremium() else 70
        req = TL_account.updateProfile()
        req.flags = 4
        req.about = text[:max_len]
        send_request(req, ())

    def update_geo(self):
        text = self.get_ai_status(self.get_setting("geo_prompt",""), "geo") or self.get_setting("geo_fallback","")
        req = TL_account.updateBusinessLocation()
        req.flags = 1
        req.address = text[:96]
        send_request(req, ())

    def manual_generate(self, mode):
        s = status_tr()
        BulletinHelper.show_info(f"{s['generating']} {mode}...", get_last_fragment())
        threading.Thread(target=lambda: (getattr(self, f"update_{mode}")(), BulletinHelper.show_success(f"{mode.capitalize()} {s['generated']}.", get_last_fragment())), daemon=True).start()

    def clear_all_history(self):
        MemoryManager.clear_all_history()
        BulletinHelper.show_info("ʙᴄя иᴄᴛоᴩия очищᴇнᴀ!")

    def on_send_message_hook(self, account: int, params: Any) -> HookResult:
        # Обработка команд Media Downloader
        msg = params.message.strip()
        if msg.startswith(".down ") or msg.startswith(".dl "):
            return self.media_downloader.process_command(account, params)

        # Обработка команд ИИ ассистента
        if not hasattr(params, 'message') or not params.message.startswith(".ai"):
            return HookResult()

        try:
            command_parts = params.message.strip().split(maxsplit=1)
            chat_id = str(params.peer)
            
            if len(command_parts) > 1:
                cmd = command_parts[1].lower()
                if cmd == "clear":
                    MemoryManager.clear_chat_history(chat_id)
                    BulletinHelper.show_info("иᴄᴛоᴩия чᴀᴛᴀ очищᴇнᴀ!")
                    return HookResult(strategy=HookStrategy.CANCEL)
                elif cmd == "clearall":
                    self.clear_all_history()
                    return HookResult(strategy=HookStrategy.CANCEL)

            prompt = params.message[4:].strip()
            context_text, image_paths = None, []
            
            # Обработка реплая
            if hasattr(params, 'replyToMsg') and params.replyToMsg:
                try:
                    reply_message = params.replyToMsg.messageOwner
                    if reply_message:
                        context_text, image_paths = extract_context_from_message(account, reply_message)
                        DebugLogger.debug(f"Контекст: {context_text}, Изображения: {len(image_paths)}")
                except Exception as e:
                    DebugLogger.error(f"Ошибка извлечения контекста: {str(e)}")
            
            # Обработка текущего сообщения
            if hasattr(params, 'messageOwner') and params.messageOwner:
                try:
                    _, current_images = extract_context_from_message(account, params.messageOwner)
                    image_paths.extend(current_images)
                except Exception as e:
                    DebugLogger.error(f"Ошибка извлечения вложений: {str(e)}")
            
            # Удаление дубликатов
            image_paths = list(set(image_paths))

            # Проверка на пустой запрос
            if not prompt and not image_paths:
                BulletinHelper.show_info("Введите запрос после .ai или прикрепите изображение")
                return HookResult(strategy=HookStrategy.CANCEL)

            history = []
            history_enabled = self.get_setting("enable_chat_history", True)
            if history_enabled:
                history = MemoryManager.get_history(chat_id)

            provider = self.get_setting("ai_provider", "OpenRouter")
            api_key = self.get_setting(f"api_key_{provider.lower()}", "").strip()
            ai_model = self.get_setting("ai_model", "")
            markdown_enabled = self.get_setting("enable_markdown", True)
            custom_dns = self.get_setting("custom_dns", "").strip()
            
            if not api_key:
                BulletinHelper.show_info(f"нᴇ нᴀᴄᴛᴩоᴇн ᴀᴘɪ ᴋᴧюч для {provider}!")
                return HookResult(strategy=HookStrategy.CANCEL)
            
            if provider not in SUPPORTED_PROVIDERS:
                BulletinHelper.show_info(f"ᴨᴩоʙᴀйдᴇᴩ {provider} нᴇ ᴨоддᴇᴩжиʙᴀᴇᴛᴄя")
                return HookResult(strategy=HookStrategy.CANCEL)

            def response_callback(response_data, user_prompt):
                if "error" in response_data:
                    BulletinHelper.show_info(f"{response_data['error']}")
                    return
                
                try:
                    ai_content = ""
                    if provider == "Anthropic":
                        ai_content = response_data.get("content", [{}])[0].get("text", "")
                    elif provider == "Google":
                        ai_content = response_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    else:  # OpenAI-like
                        ai_content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    if not ai_content:
                        BulletinHelper.show_info("Получен пустой ответ от ИИ.")
                        return
                    
                    # Форматирование ответа
                    if markdown_enabled:
                        ai_response = format_ai_response(response_data, provider)
                    else:
                        header = setting_getter("response_header", "ии ᴀᴄᴄиᴄᴛᴇнᴛ")
                        ai_response = f"{header}:\n\n{ai_content}"
                    
                    # Проверка на обрезанный ответ
                    is_truncated = False
                    if provider in ["OpenAI", "OpenRouter", "Groq", "DeepSeek"]:
                        finish_reason = response_data.get("choices", [{}])[0].get("finish_reason", "")
                        if finish_reason == "length":
                            is_truncated = True
                    elif provider == "Google":
                        if response_data.get("candidates", [{}])[0].get("finishReason", "") == "MAX_TOKENS":
                            is_truncated = True
                    elif provider == "Anthropic":
                        if response_data.get("stop_reason", "") == "max_tokens":
                            is_truncated = True
                    
                    if is_truncated:
                        ai_response += "\n\n⚠️ Ответ обрезан из-за ограничения токенов!"
                    
                    if history_enabled:
                        MemoryManager.add_to_history(chat_id, user_prompt, ai_content)
                        DebugLogger.debug("История сохранена")
                    
                    send_params = {"message": ai_response, "peer": params.peer}
                    if hasattr(params, 'replyToMsg') and params.replyToMsg:
                        send_params["replyToMsg"] = params.replyToMsg
                    if markdown_enabled:
                        send_params["parse_mode"] = "Markdown"
                    
                    send_message(send_params)
                    BulletinHelper.show_info("оᴛʙᴇᴛ ᴨоᴧучᴇн!")

                except Exception as e:
                    BulletinHelper.show_info(f"оɯибᴋᴀ обᴩᴀбоᴛᴋи: {str(e)}")
                    DebugLogger.error(f"Ошибка в response_callback: {str(e)}\nDATA: {response_data}")

            fetch_ai_response(
                prompt, api_key, ai_model, provider, history,
                context_text=context_text, image_paths=image_paths,
                callback=response_callback, custom_dns=custom_dns
            )
            
            return HookResult(strategy=HookStrategy.CANCEL)

        except Exception as e:
            BulletinHelper.show_info(f"оɯибᴋᴀ: {str(e)}")
            DebugLogger.error(f"Критическая ошибка в on_send_message_hook: {str(e)}")
            return HookResult(strategy=HookStrategy.CANCEL)
