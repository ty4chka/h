# modules/cfg.py
import json
import os
import requests
from pathlib import Path
from telethon import events
from utils.misc import edit_or_reply

DATA_DIR = Path("data")
CONFIG_FILE = DATA_DIR / "hydra_config.json"
IMAGES_DIR = DATA_DIR / "images"

DEFAULT_CONFIG = {
    "core": {"prefix": ".", "owner_id": 0},
    "templates": {
        "ping": {
            "emoji": "🏓", "title": "Pong!", "show_network": True,
            "show_core": True, "custom_text": "", "footer": "Hydra Cython", "image_url": ""
        },
        "info": {
            "emoji": "🔱", "title": "HYDRA USERBOT", "show_uptime": True,
            "show_core": True, "show_modules": True, "show_owner": True,
            "custom_text": "", "footer": "Cython Edition", "image_url": ""
        }
    }
}

def load_config():
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                for section in DEFAULT_CONFIG:
                    if section not in loaded:
                        loaded[section] = DEFAULT_CONFIG[section]
                    elif isinstance(DEFAULT_CONFIG[section], dict):
                        for key in DEFAULT_CONFIG[section]:
                            if key not in loaded[section]:
                                loaded[section][key] = DEFAULT_CONFIG[section][key]
                return loaded
        except:
            pass
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def download_image(url, name):
    try:
        if not IMAGES_DIR.exists():
            IMAGES_DIR.mkdir(parents=True)
        response = requests.get(url, stream=True, timeout=15)
        if response.status_code == 200:
            ext = url.split('.')[-1].split('?')[0]
            if ext not in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
                ext = 'jpg'
            filename = f"{name}.{ext}"
            filepath = IMAGES_DIR / filename
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return str(filepath)
        return None
    except:
        return None

def setup(client):
    @client.on(events.NewMessage(pattern=r"\.cfg", outgoing=True))
    async def cfg_handler(event):
        args = event.text.split()
        
        if len(args) == 1:
            text = """
<b>🧬 HYDRA CONFIG PANEL</b>

<blockquote expandable>
<b>🖼️ ИЗОБРАЖЕНИЯ</b>
▫️ <code>.cfg img ping URL</code>
▫️ <code>.cfg img info URL</code>
▫️ <code>.cfg delimg ping</code>

<b>🎨 ШАБЛОНЫ</b>
▫️ <code>.cfg set ping emoji 🎯</code>
▫️ <code>.cfg set ping title "ТЕКСТ"</code>
▫️ <code>.cfg set info custom_text "ТЕКСТ"</code>

<b>📋 ПРОСМОТР</b>
▫️ <code>.cfg show</code>
▫️ <code>.cfg view ping</code>

<b>⚙️ СИСТЕМА</b>
▫️ <code>.cfg prefix /</code>
▫️ <code>.cfg reset</code>
</blockquote>
"""
            await edit_or_reply(event, text, parse_mode='HTML')
            return
        
        # Установка изображения
        elif args[1] == "img" and len(args) >= 4:
            cmd = args[2]
            url = args[3]
            if cmd not in ["ping", "info"]:
                await edit_or_reply(event, "❌ Используй ping или info")
                return
            status = await edit_or_reply(event, f"🌐 Загрузка...")
            local_path = download_image(url, f"{cmd}_custom")
            if local_path:
                cfg = load_config()
                old = cfg["templates"][cmd].get("image_url", "")
                if old and os.path.exists(old):
                    os.remove(old)
                cfg["templates"][cmd]["image_url"] = local_path
                save_config(cfg)
                await client.send_file(event.chat_id, local_path, caption=f"✅ Изображение для .{cmd} установлено!")
                await status.delete()
            else:
                await status.edit("❌ Ошибка загрузки")
        
        # Удаление изображения
        elif args[1] == "delimg" and len(args) >= 3:
            cmd = args[2]
            if cmd not in ["ping", "info"]:
                await edit_or_reply(event, "❌ Используй ping или info")
                return
            cfg = load_config()
            old = cfg["templates"][cmd].get("image_url", "")
            if old and os.path.exists(old):
                os.remove(old)
            cfg["templates"][cmd]["image_url"] = ""
            save_config(cfg)
            await edit_or_reply(event, f"✅ Изображение для .{cmd} удалено")
        
        # Установка значений
        elif args[1] == "set" and len(args) >= 5:
            cmd = args[2]
            key = args[3]
            value = ' '.join(args[4:])
            if cmd not in ["ping", "info"]:
                await edit_or_reply(event, "❌ Используй ping или info")
                return
            if value.lower() == "true": value = True
            elif value.lower() == "false": value = False
            elif value.isdigit(): value = int(value)
            cfg = load_config()
            if key in cfg["templates"][cmd]:
                cfg["templates"][cmd][key] = value
                save_config(cfg)
                await edit_or_reply(event, f"✅ <code>{cmd}.{key}</code> = <b>{value}</b>", parse_mode='HTML')
            else:
                await edit_or_reply(event, f"❌ Неизвестный ключ: {key}")
        
        # Просмотр шаблона
        elif args[1] == "view" and len(args) >= 3:
            cmd = args[2]
            if cmd not in ["ping", "info"]:
                await edit_or_reply(event, "❌ Используй ping или info")
                return
            cfg = load_config()
            tpl = cfg["templates"][cmd]
            text = f"<b>📋 ШАБЛОН .{cmd.upper()}</b>\n\n"
            for k, v in tpl.items():
                if k != "image_url":
                    text += f"<code>{k}</code> = <b>{v}</b>\n"
                else:
                    text += f"<code>{k}</code> = <b>{'✅' if v else '❌'}</b>\n"
            await edit_or_reply(event, text, parse_mode='HTML')
        
        # Показать весь конфиг
        elif args[1] == "show":
            cfg = load_config()
            for cmd in ["ping", "info"]:
                if cfg["templates"][cmd].get("image_url"):
                    cfg["templates"][cmd]["image_url"] = "✅"
            json_str = json.dumps(cfg, indent=2, ensure_ascii=False)[:4000]
            await edit_or_reply(event, f"<pre>{json_str}</pre>", parse_mode='HTML')
        
        # Сменить префикс с перезагрузкой модулей
        elif args[1] == "prefix" and len(args) >= 3:
            new_prefix = args[2]
            cfg = load_config()
            cfg["core"]["prefix"] = new_prefix
            save_config(cfg)
            
            import config
            config.reload_prefix()
            
            # Перезагружаем модули для нового префикса
            from utils.loader import reload_all_modules
            await reload_all_modules("modules", client)
            
            await edit_or_reply(
                event,
                f"✅ Префикс изменён на <code>{new_prefix}</code>\n"
                f"🔄 Все модули перезагружены!",
                parse_mode='HTML'
            )
        
        # Сброс настроек
        elif args[1] == "reset":
            cfg = load_config()
            for cmd in ["ping", "info"]:
                img = cfg["templates"][cmd].get("image_url", "")
                if img and os.path.exists(img):
                    os.remove(img)
            save_config(DEFAULT_CONFIG)
            await edit_or_reply(event, "✅ Настройки сброшены", parse_mode='HTML')
        
        else:
            await edit_or_reply(event, "❓ Неизвестная команда. Используй .cfg")

modules_help = {
    "cfg": {
        "cfg": "Панель управления",
        "cfg img (ping/info) URL": "Установить изображение",
        "cfg set (ping/info) key value": "Изменить параметр",
        "cfg view (ping/info)": "Посмотреть шаблон",
        "cfg show": "Показать конфиг",
        "cfg prefix /": "Сменить префикс",
        "cfg reset": "Сброс"
    }
}
