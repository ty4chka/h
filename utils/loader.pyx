# cython: language_level=3
# utils/loader.pyx — ПОЛНЫЙ ФАЙЛ С ВСТРОЕННЫМ .cfg
import importlib.util
import importlib
import sys
import os
import asyncio
import re
import inspect
from pathlib import Path
import logging
from telethon import events
import json as _json

logger = logging.getLogger(__name__)

_modules_help = {}
_module_handlers = {}
_loaded_modules = {}

modules_help = _modules_help
module_handlers = _module_handlers

# ============================================
# CYTHON CACHE
# ============================================
cdef dict _core_cache = {
    "version": "Hydra 2.0 Cython",
    "modules_loaded": 0
}

cpdef object get_cache(str key):
    return _core_cache.get(key)

cpdef void set_cache(str key, object value):
    _core_cache[key] = value

cpdef long benchmark_core(int iterations=1000000):
    cdef long i
    cdef long x = 0
    for i in range(iterations):
        x += i
    return x

# ============================================
# КОНФИГУРАЦИЯ МОДУЛЕЙ (как в Heroku/Hikka)
# ============================================
cdef dict _module_configs = {}

class ModuleConfig:
    def __init__(self, module_name: str, defaults: dict = None):
        self.module_name = module_name
        self.config = defaults or {}
        _module_configs[module_name] = self.config
    
    def get(self, key: str, default=None):
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        self.config[key] = value
    
    def __getitem__(self, key):
        return self.config[key]
    
    def __setitem__(self, key, value):
        self.config[key] = value
    
    def __contains__(self, key):
        return key in self.config

cpdef dict get_module_config(str module_name):
    return _module_configs.get(module_name, {})

cpdef dict get_all_configs():
    return _module_configs.copy()

# ============================================
# ВСТРОЕННАЯ КОМАНДА .cfg
# ============================================
_cfg_file = Path("data/hydra_templates.json")
_cfg_defaults = {
    "ping": {
        "template": "<b>🏓 {emoji} {title}</b>\n\n<blockquote>🌐 Сеть: <code>{ping}ms</code>\n🛠 Ядро: <code>{core}ms</code>\n⏳ Аптайм: <code>{uptime}</code></blockquote>\n\n<i>{footer}</i>",
        "emoji": "🏓", "title": "РЕЗУЛЬТАТЫ", "footer": "Hydra Cython",
        "loading_emoji": "⚡", "animate_loading": False, "image_url": ""
    },
    "info": {
        "template": "<b>{emoji} {title}</b>\n\n<blockquote>👤 <code>{owner}</code>\n⏰ <code>{uptime}</code>\n⚡ <code>{core}ms</code>\n📦 <code>{modules}</code> модулей</blockquote>\n\n<i>{footer}</i>",
        "emoji": "🔱", "title": "HYDRA", "footer": "⚡ Cython Edition",
        "loading_emoji": "🔍", "animate_loading": False, "image_url": ""
    }
}

def _load_cfg():
    if _cfg_file.exists():
        try:
            with open(_cfg_file, 'r', encoding='utf-8') as f:
                return _json.load(f)
        except:
            pass
    return _cfg_defaults.copy()

def _save_cfg(cfg):
    _cfg_file.parent.mkdir(parents=True, exist_ok=True)
    with open(_cfg_file, 'w', encoding='utf-8') as f:
        _json.dump(cfg, f, ensure_ascii=False, indent=2)

_builtin_cfg_registered = False

async def _builtin_cfg_handler(event):
    """Встроенный обработчик .cfg"""
    text = event.raw_text.strip()
    cfg = _load_cfg()
    
    # Меню
    if text == ".cfg":
        await event.edit(
            "<b>🧬 HYDRA CONFIG</b>\n\n"
            "<code>.cfg ping</code> — JSON ping\n"
            "<code>.cfg info</code> — JSON info\n"
            "<code>.cfg save ping {{...}}</code> — сохранить\n"
            "<code>.cfg reset ping</code> — сбросить",
            parse_mode='HTML'
        )
        return
    
    # Показать JSON
    if text == ".cfg ping":
        t = cfg.get("ping", {})
        await event.edit(
            f"<b>🏓 PING JSON</b>\n\n"
            f"<pre language=\"json\">{_json.dumps(t, indent=2, ensure_ascii=False)}</pre>\n\n"
            f"<i>.cfg save ping {{...}}</i>",
            parse_mode='HTML'
        )
        return
    
    if text == ".cfg info":
        t = cfg.get("info", {})
        await event.edit(
            f"<b>🔱 INFO JSON</b>\n\n"
            f"<pre language=\"json\">{_json.dumps(t, indent=2, ensure_ascii=False)}</pre>\n\n"
            f"<i>.cfg save info {{...}}</i>",
            parse_mode='HTML'
        )
        return
    
    # Сохранить JSON
    if text.startswith(".cfg save ping "):
        try:
            data = _json.loads(text[15:])
            cfg["ping"].update(data)
            _save_cfg(cfg)
            await event.edit("✅ Ping сохранён!")
        except Exception as e:
            await event.edit(f"❌ {e}")
        return
    
    if text.startswith(".cfg save info "):
        try:
            data = _json.loads(text[15:])
            cfg["info"].update(data)
            _save_cfg(cfg)
            await event.edit("✅ Info сохранён!")
        except Exception as e:
            await event.edit(f"❌ {e}")
        return
    
    # Сброс
    if text == ".cfg reset ping":
        cfg["ping"] = _cfg_defaults["ping"].copy()
        _save_cfg(cfg)
        await event.edit("✅ Ping сброшен")
        return
    
    if text == ".cfg reset info":
        cfg["info"] = _cfg_defaults["info"].copy()
        _save_cfg(cfg)
        await event.edit("✅ Info сброшен")
        return
    
    if text == ".cfg reset all":
        _save_cfg(_cfg_defaults.copy())
        await event.edit("✅ Всё сброшено")
        return

# ============================================
# ЗАГРУЗКА МОДУЛЕЙ
# ============================================

async def load_all_modules(directory: str, client):
    global _builtin_cfg_registered
    
    # Регистрируем встроенный .cfg ПЕРВЫМ
    if not _builtin_cfg_registered:
        client.add_event_handler(_builtin_cfg_handler, events.NewMessage(pattern=r"\.cfg", outgoing=True))
        _builtin_cfg_registered = True
        print("    🔧 Встроенный .cfg зарегистрирован")
    
    modules_path = Path(directory)
    if not modules_path.exists():
        modules_path.mkdir(parents=True, exist_ok=True)
        return 0, 0, []

    success = 0
    loaded_list = []
    all_modules = {}
    
    for item in modules_path.iterdir():
        if item.name.startswith("_") or item.name == '__pycache__':
            continue
        
        if item.is_dir():
            so_files = list(item.glob("*.so"))
            py_files = list(item.glob("*.py"))
            
            if so_files:
                all_modules[item.name] = so_files[0]
            elif py_files:
                all_modules[item.name] = py_files[0]
        
        elif item.suffix == ".so":
            name = item.stem.split('.')[0]
            if name not in all_modules:
                all_modules[name] = item
        
        elif item.suffix == ".py":
            if item.stem not in all_modules:
                all_modules[item.stem] = item
    
    total = len(all_modules)
    print(f"    📂 Найдено модулей: {total}")
    
    for name, file_path in sorted(all_modules.items()):
        file_type = "⚡" if file_path.suffix == ".so" else "🐍"
        print(f"    📦 Загрузка {name} {file_type}...", end=" ")
        
        if await load_single_module(name, file_path, client):
            success += 1
            loaded_list.append(name)
            print("✅")
        else:
            print("❌")
    
    set_cache("modules_loaded", success)
    return success, total, loaded_list

async def load_single_module(module_name: str, file_path: Path, client, is_initial=False):
    try:
        if not is_initial:
            await unload_single_module_handlers(module_name, client)
            for k in list(sys.modules.keys()):
                if k == module_name or k == f"modules.{module_name}":
                    if k in sys.modules:
                        del sys.modules[k]
        
        parent_dir = str(file_path.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec:
            return False
        
        module = importlib.util.module_from_spec(spec)
        module.client = client
        
        module_env = os.environ.copy()
        module_env.update({
            'TERM': 'xterm-256color',
            'HOME': '/data/data/com.termux/files/home',
            'PREFIX': '/data/data/com.termux/files/usr',
        })
        module.__dict__.update({'os': os, 'sys': sys, 'Path': Path, 'environ': module_env})
        
        try:
            from utils.misc import edit_or_reply, rate_limit
            module.edit_or_reply = edit_or_reply
            module.rate_limit = rate_limit
        except:
            pass
        
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        await register_module_handlers(module, module_name, client)
        await register_module_help(module, module_name, client)
        
        _loaded_modules[module_name] = module
        return True
        
    except Exception as e:
        logger.error(f"Error loading {module_name}: {e}")
        return False

async def register_module_handlers(module, module_name: str, client):
    try:
        from config import prefix
    except:
        prefix = "."
    
    if module_name not in _module_handlers:
        _module_handlers[module_name] = []
    
    for attr_name in dir(module):
        try:
            attr = getattr(module, attr_name)
            if not callable(attr) or not asyncio.iscoroutinefunction(attr):
                continue
            
            cmd = None
            if attr_name.endswith('_handler'):
                cmd = attr_name[:-8]
            elif not attr_name.startswith('_') and len(attr_name) < 20:
                cmd = attr_name
            
            if cmd:
                pat = rf'^{re.escape(prefix)}{re.escape(cmd)}(?:\s|$)'
                
                async def wrapper(e, _f=attr, _name=attr_name):
                    try:
                        await _f(e)
                    except Exception as ex:
                        logger.error(f"Error in {_name}: {ex}")
                
                wrapper.__module__ = module_name
                wrapper.__name__ = attr_name
                
                handler = client.add_event_handler(
                    wrapper,
                    events.NewMessage(pattern=pat, outgoing=True)
                )
                _module_handlers[module_name].append(handler)
        except:
            pass

async def unload_single_module_handlers(module_name: str, client):
    if module_name in _module_handlers:
        for h in _module_handlers[module_name]:
            try:
                client.remove_event_handler(h)
            except:
                pass
        del _module_handlers[module_name]
    
    if module_name in _modules_help:
        del _modules_help[module_name]
    
    for key in list(sys.modules.keys()):
        if key == module_name or key == f"modules.{module_name}":
            if key in sys.modules:
                del sys.modules[key]
    
    return True

async def register_module_help(module, module_name: str, client):
    if hasattr(module, 'modules_help'):
        _modules_help.update(module.modules_help)
    else:
        _modules_help[module_name] = {}
        for attr_name in dir(module):
            if attr_name.endswith('_handler'):
                cmd = attr_name[:-8]
                _modules_help[module_name][cmd] = f"Команда .{cmd}"

async def reload_all_modules(directory: str, client):
    for name in list(_modules_help.keys()):
        await unload_single_module_handlers(name, client)
    return await load_all_modules(directory, client)

def get_loaded_modules():
    return list(_modules_help.keys())

__all__ = [
    'load_all_modules', 'load_single_module', 'unload_single_module_handlers',
    'reload_all_modules', 'modules_help', 'module_handlers',
    'get_cache', 'set_cache', 'benchmark_core',
    'ModuleConfig', 'get_module_config', 'get_all_configs'
]
