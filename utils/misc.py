"""
Вспомогательные функции для модулей Hydra
"""

import time
from datetime import datetime
from functools import wraps
import asyncio
import json
import os

# Глобальное время старта бота
bot_start_time = None

# Система ограничений
_rate_limits = {}

# Система сохранения настроек
SETTINGS_FILE = "user_settings.json"

def load_settings():
    """Загрузить настройки пользователей"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_settings(settings):
    """Сохранить настройки пользователей"""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

# Глобальные настройки
user_settings = load_settings()

def set_start_time(start_time: float):
    """Установка времени старта бота"""
    global bot_start_time
    bot_start_time = start_time

def get_start_time() -> float:
    """Получение времени старта бота"""
    return bot_start_time

def get_uptime(start_time: float = None) -> str:
    """Форматирование uptime в читаемый вид"""
    if start_time is None:
        start_time = get_start_time()
        if start_time is None:
            return "00:00:00"
    
    uptime_seconds = int(time.time() - start_time)
    return datetime.utcfromtimestamp(uptime_seconds).strftime("%H:%M:%S")

async def edit_or_reply(event, text: str, **kwargs):
    """Редактирует сообщение если оно исходящее, иначе отвечает на него"""
    try:
        if event.out:
            return await event.edit(text, **kwargs)
        else:
            return await event.reply(text, **kwargs)
    except Exception:
        return await event.reply(text, **kwargs)

def rate_limit(limit: int = 20, period: int = 120):
    """Декоратор для ограничения использования команд"""
    def decorator(func):
        @wraps(func)
        async def wrapper(event, *args, **kwargs):
            user_id = event.sender_id
            current_time = time.time()
            
            if user_id not in _rate_limits:
                _rate_limits[user_id] = []
            
            # Удаляем старые записи
            _rate_limits[user_id] = [
                timestamp for timestamp in _rate_limits[user_id]
                if current_time - timestamp < period
            ]
            
            # Проверяем лимит
            if len(_rate_limits[user_id]) >= limit:
                wait_time = int(period - (current_time - _rate_limits[user_id][0]))
                
                # Пытаемся импортировать переводчик
                try:
                    from modules.lang import translator
                    limit_message = f"""
<b>⏰ {translator.get_text(user_id, 'rate_limit_exceeded')}</b>

<blockquote>🚫 <b>{translator.get_text(user_id, 'limit_reached')}</b>
⏱️ <b>{translator.get_text(user_id, 'wait_time')}:</b> <code>{wait_time}{translator.get_text(user_id, 'seconds')}</code>
📊 <b>{translator.get_text(user_id, 'current_usage')}:</b> <code>{len(_rate_limits[user_id])}/{limit}</code>
🕒 <b>{translator.get_text(user_id, 'period')}:</b> <code>{period}{translator.get_text(user_id, 'seconds')}</code></blockquote>

<b>💡 {translator.get_text(user_id, 'rate_limit_tip')}</b>
<blockquote>• {translator.get_text(user_id, 'slow_down_commands')}
• {translator.get_text(user_id, 'wait_before_retry')}
• {translator.get_text(user_id, 'contact_admin_if_issue')}</blockquote>

<blockquote>🔒 {translator.get_text(user_id, 'anti_spam_protection')}</blockquote>
"""
                except:
                    # Если переводчик не доступен, используем простой текст
                    limit_message = f"""
<b>⏰ Rate limit exceeded!</b>

<blockquote>🚫 <b>Limit reached:</b> {len(_rate_limits[user_id])}/{limit}
⏱️ <b>Wait:</b> <code>{wait_time}s</code>
🕒 <b>Period:</b> <code>{period}s</code></blockquote>

<b>💡 Tip:</b> Slow down your commands and wait before retrying.
"""
                
                await edit_or_reply(event, limit_message, parse_mode='HTML')
                return
            
            # Добавляем текущее использование
            _rate_limits[user_id].append(current_time)
            
            return await func(event, *args, **kwargs)
        
        return wrapper
    return decorator

async def fast_animation(message, emoji: str, final_text: str):
    """Сверхбыстрая анимация с одним эмодзи"""
    try:
        await message.edit(emoji)
        await asyncio.sleep(0.05)
        await message.edit(final_text)
    except Exception:
        try:
            await message.edit(final_text)
        except:
            pass

def get_user_setting(user_id, key, default=None):
    """Получить настройку пользователя"""
    return user_settings.get(str(user_id), {}).get(key, default)

def set_user_setting(user_id, key, value):
    """Установить настройку пользователя"""
    user_id = str(user_id)
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id][key] = value
    return save_settings(user_settings)

def get_rate_limit_info(user_id):
    """Получить информацию о текущих лимитах пользователя"""
    if user_id not in _rate_limits:
        return {
            'current_usage': 0,
            'max_limit': 20,
            'period': 120
        }
    
    current_time = time.time()
    recent_uses = [
        timestamp for timestamp in _rate_limits[user_id]
        if current_time - timestamp < 120
    ]
    
    return {
        'current_usage': len(recent_uses),
        'max_limit': 20,
        'period': 120,
        'reset_in': int(120 - (current_time - recent_uses[0])) if recent_uses else 0
    }

# MCUB compatibility stubs
def register_placeholder(scope, key, callback, **kwargs):
    try:
        from core.lib.loader.placeholders import register_placeholder as _reg
        _reg(scope, key, callback, **kwargs)
    except ImportError:
        pass

def register_media_placeholder(scope, key, media_type, callback, **kwargs):
    """Регистрация медиа-плейсхолдера (изображения, стикеры и т.д.)."""
    try:
        from core.lib.loader.placeholders import register_media_placeholder as _reg
        _reg(scope, key, media_type, callback, **kwargs)
    except ImportError:
        pass

def unregister_scope(scope):
    try:
        from core.lib.loader.placeholders import unregister_scope as _unreg
        return _unreg(scope)
    except ImportError:
        return 0

async def resolve_placeholders(scope, text, data=None, strict=False):
    try:
        from core.lib.loader.placeholders import resolve_placeholders as _resolve
        return await _resolve(scope, text, data=data or {}, strict=strict)
    except ImportError:
        if data:
            for k, v in (data or {}).items():
                text = text.replace("{" + str(k) + "}", str(v))
        return text

async def resolve_media_placeholders(scope, data=None):
    """Разрешить медиа-плейсхолдеры."""
    try:
        from core.lib.loader.placeholders import resolve_media_placeholders as _resolve
        return await _resolve(scope, data or {})
    except ImportError:
        return {}


# API custom_placeholders из MCUB-fork.  Настоящие модули импортируют эти
# функции прямо из ``utils``, поэтому они живут здесь вместе с прокси к
# core.lib.loader.placeholders.
def placeholders(
    key: str,
    *,
    timeout=None,
    description=None,
    cache_ttl=None,
    required: bool = False,
    on_error: str = "keep",
):
    if not isinstance(key, str) or not key.replace("_", "a").isalnum():
        raise ValueError("Invalid placeholder key. Use: letters, digits, underscore")
    if on_error not in {"keep", "empty", "raise"}:
        raise ValueError("on_error must be one of: keep, empty, raise")

    def decorator(func):
        meta = list(getattr(func, "__custom_placeholders__", []))
        meta.append(
            {
                "key": key,
                "timeout": timeout,
                "description": description,
                "cache_ttl": cache_ttl,
                "required": required,
                "on_error": on_error,
            }
        )
        func.__custom_placeholders__ = meta
        return func

    return decorator


def register_decorated_placeholders(scope, owner) -> int:
    """Зарегистрировать все методы ``@utils.placeholders`` объекта."""
    count = 0
    for attr_name in dir(owner):
        try:
            bound = getattr(owner, attr_name)
        except Exception:
            continue
        if not callable(bound):
            continue
        metas = getattr(getattr(bound, "__func__", bound), "__custom_placeholders__", None)
        if not metas:
            continue
        for meta in metas:
            register_placeholder(
                scope,
                meta["key"],
                bound,
                timeout=meta.get("timeout"),
                description=meta.get("description"),
                cache_ttl=meta.get("cache_ttl"),
                required=bool(meta.get("required", False)),
                on_error=meta.get("on_error", "keep"),
            )
            count += 1
    return count


def unregister_placeholder(scope, key=None):
    try:
        from core.lib.loader.placeholders import _REGISTRY

        items = _REGISTRY.get(scope, {})
        if key is None:
            return unregister_scope(scope)
        if key not in items:
            return False
        del items[key]
        if not items:
            _REGISTRY.pop(scope, None)
        return True
    except ImportError:
        return False


def list_placeholder_keys(scope):
    try:
        from core.lib.loader.placeholders import list_placeholder_keys as _list

        return _list(scope)
    except ImportError:
        return []


def format_placeholders(scope) -> str:
    """Компактный список ``{token}`` для поля конфигурации MCUB."""
    return ", ".join(f"{{{key}}}" for key in list_placeholder_keys(scope))


def config_placeholders(scope="any"):
    if scope == "any":
        try:
            from core.lib.loader.placeholders import _REGISTRY

            rows = []
            for scope_name, items in sorted(_REGISTRY.items()):
                rows.extend(
                    f"{{{key}}} - {meta.get('description') or 'No docs'} ({scope_name})"
                    for key, meta in sorted(items.items())
                )
            return "\n".join(rows) or None
        except ImportError:
            return None
    keys = list_placeholder_keys(scope)
    return "\n".join(f"{{{key}}}" for key in keys) or None


# Дополнительные утилиты
def format_size(size_bytes: int) -> str:
    """Форматирование размера в читаемый вид"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def clean_text(text: str) -> str:
    """Очистка текста от лишних пробелов и спецсимволов"""
    return ' '.join(text.split())

async def progress_callback(current, total, message, start_time, prefix="Uploading"):
    """Callback для отображения прогресса загрузки"""
    if time.time() - start_time > 5:
        percentage = current * 100 / total
        speed = current / (time.time() - start_time)
        eta = (total - current) / speed if speed > 0 else 0
        
        bar_length = 10
        filled = int(bar_length * current / total)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        text = f"""
<b>{prefix}...</b>

<code>{bar}</code> <b>{percentage:.1f}%</b>

📦 <b>Size:</b> {format_size(current)} / {format_size(total)}
⚡ <b>Speed:</b> {format_size(speed)}/s
⏳ <b>ETA:</b> {int(eta)}s
"""
        try:
            await message.edit(text)
        except:
            pass
        return time.time()
    return start_time
