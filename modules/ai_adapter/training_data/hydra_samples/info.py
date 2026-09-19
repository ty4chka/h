# modules/info.py
"""
Hydra Info Module - Полная кастомизация через JSON
"""

import time
import json
import os
from pathlib import Path
from telethon import events
from utils.misc import edit_or_reply, get_uptime, get_start_time

DATA_DIR = Path("data")
CONFIG_FILE = DATA_DIR / "hydra_config.json"

def load_config():
    """Загрузка конфига с дефолтными значениями"""
    default_info = {
        "emoji": "🔱",
        "title": "HYDRA USERBOT",
        "show_uptime": True,
        "show_core": True,
        "show_modules": True,
        "show_owner": True,
        "custom_text": "",
        "footer": "Cython Edition",
        "image_url": ""
    }
    
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                return cfg.get("templates", {}).get("info", default_info)
        except:
            pass
    return default_info

def setup(client):
    @client.on(events.NewMessage(pattern=r"\.info", outgoing=True))
    async def info_handler(event):
        # Загружаем настройки
        tpl = load_config()
        
        emoji = tpl.get("emoji", "🔱")
        title = tpl.get("title", "HYDRA USERBOT")
        show_uptime = tpl.get("show_uptime", True)
        show_core = tpl.get("show_core", True)
        show_modules = tpl.get("show_modules", True)
        show_owner = tpl.get("show_owner", True)
        custom_text = tpl.get("custom_text", "")
        footer = tpl.get("footer", "")
        image_path = tpl.get("image_url", "")
        
        msg = await edit_or_reply(event, f"{emoji} <b>Загрузка...</b>", parse_mode='HTML')
        
        # Собираем данные
        me = await client.get_me()
        owner = f"@{me.username}" if me.username else me.first_name
        
        uptime = get_uptime(get_start_time()) if get_start_time() else "00:00:00"
        
        core_speed = ""
        if show_core:
            try:
                c_start = time.perf_counter()
                _ = sum(range(100000))
                core_speed = f"{(time.perf_counter() - c_start) * 1000:.2f}ms"
            except:
                core_speed = "N/A"
        
        modules_count = 0
        if show_modules:
            mp = Path("modules")
            modules_count = len([f for f in mp.glob("*.py") if not f.name.startswith("_")]) if mp.exists() else 0
        
        # Формируем текст
        lines = [f"<b>{emoji} {title}</b>"]
        
        if custom_text:
            lines.append("")
            lines.append(custom_text)
        
        lines.append("")
        lines.append("<blockquote>")
        
        if show_owner:
            lines.append(f"👤 <b>Владелец:</b> <code>{owner}</code>")
        
        if show_uptime:
            lines.append(f"⏰ <b>Аптайм:</b> <code>{uptime}</code>")
        
        if show_core:
            lines.append(f"⚡ <b>Ядро:</b> <code>{core_speed}</code>")
        
        if show_modules:
            lines.append(f"📦 <b>Модулей:</b> <code>{modules_count}</code>")
        
        # Добавляем информацию о прокси
        try:
            from config import PROXY_ENABLED, PROXY
            if PROXY_ENABLED:
                lines.append(f"🛡️ <b>Прокси:</b> <code>{PROXY.get('addr', 'N/A')}</code>")
        except:
            pass
        
        lines.append("</blockquote>")
        
        if footer:
            lines.append("")
            lines.append(f"<i>{footer}</i>")
        
        text = "\n".join(lines)
        
        # Отправка с картинкой или без
        if image_path and os.path.exists(image_path):
            await client.send_file(
                event.chat_id,
                image_path,
                caption=text,
                parse_mode='HTML'
            )
            await msg.delete()
        else:
            await msg.edit(text, parse_mode='HTML')
    
    @client.on(events.NewMessage(pattern=r"\.i", outgoing=True))
    async def i_handler(event):
        """Короткая версия информации"""
        me = await client.get_me()
        owner = f"@{me.username}" if me.username else me.first_name
        await edit_or_reply(
            event,
            f"<b>🔱 Hydra</b>\n<code>{owner}</code>",
            parse_mode='HTML'
        )

modules_help = {
    "info": {
        "info": "🔱 Полная информация о боте с кастомизацией",
        "i": "📱 Короткая информация"
    }
}
