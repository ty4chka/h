# modules/adapter.py
"""
Hydra Module Adapter - Конвертация Heroku/Hikka/MCUB → Hydra
Полная совместимость с loader, db, client
"""

import re
import shutil
from pathlib import Path
from telethon import events


def detect_module_type(code: str) -> str:
    """Определяет тип модуля по коду"""
    if re.search(r'class\s+\w+Mod\s*\(', code):
        return "hikka"
    if re.search(r'from\s+core\s+import', code) or re.search(r'from\s+\.\.\s+import', code):
        return "mcub"
    if re.search(r'def\s+setup\s*\(\s*client\s*\)', code):
        return "hydra"
    return "unknown"


def adapt_heroku_hikka_module(code: str, module_name: str) -> str:
    """Конвертирует Heroku/Hikka модуль в Hydra формат"""
    
    # Извлекаем имя класса
    class_match = re.search(r'class\s+(\w+Mod)\s*\(', code)
    class_name = class_match.group(1) if class_match else f"{module_name.capitalize()}Mod"
    
    # Добавляем совместимость
    compat_code = '''
# ============================================
# HYDRA COMPATIBILITY LAYER FOR HEROKU/HIKKA
# ============================================
class LoaderStub:
    def __init__(self):
        self.db = {}
        self.client = None
        self.modules = {}
    
    def __getattr__(self, name):
        return None

loader = LoaderStub()

class FakeMessage:
    def __init__(self, event):
        self.event = event
        self.text = event.text
        self.chat_id = event.chat_id
        self.sender_id = event.sender_id
        self.out = event.out
        self.client = event.client
        self.reply_to_msg_id = event.reply_to_msg_id
        self.id = event.id
    
    async def edit(self, text, **kwargs):
        return await self.event.edit(text, **kwargs)
    
    async def reply(self, text, **kwargs):
        return await self.event.reply(text, **kwargs)
    
    async def answer(self, text, **kwargs):
        from utils.misc import edit_or_reply
        return await edit_or_reply(self.event, text, **kwargs)
    
    async def delete(self):
        return await self.event.delete()

# Совместимость с Hikka
class HikkaCompat:
    @staticmethod
    def get_text(user_id, key):
        return key

translator = HikkaCompat()

# Совместимость с Heroku
class HerokuCompat:
    pass

heroku = HerokuCompat()
hikka = HerokuCompat()
'''
    
    # Убираем проблемные импорты
    code = re.sub(r'from\s+hikka\s+import.*\n', '', code)
    code = re.sub(r'from\s+heroku\s+import.*\n', '', code)
    code = re.sub(r'from\s+\.\.\s+import.*\n', '', code)
    code = re.sub(r'import\s+hikka.*\n', '', code)
    code = re.sub(r'import\s+heroku.*\n', '', code)
    
    # Находим все команды
    commands = []
    for line in code.split('\n'):
        m = re.search(r'async def (\w+)_cmd', line)
        if m:
            commands.append(m.group(1))
        m = re.search(r'async def (\w+)_handler', line)
        if m:
            commands.append(m.group(1))
        m = re.search(r'def (\w+)_cmd', line)
        if m:
            commands.append(m.group(1))
    
    # Генерируем код регистрации
    handlers_code = ""
    for cmd in set(commands):
        handlers_code += f'''
    # Регистрация команды {cmd}
    try:
        if hasattr(module, '{cmd}_cmd'):
            func_{cmd} = getattr(module, '{cmd}_cmd')
        elif hasattr(module, '{cmd}_handler'):
            func_{cmd} = getattr(module, '{cmd}_handler')
        elif '{cmd}_cmd' in globals():
            func_{cmd} = globals()['{cmd}_cmd']
        elif '{cmd}_handler' in globals():
            func_{cmd} = globals()['{cmd}_handler']
        else:
            func_{cmd} = None
        
        if func_{cmd} is not None:
            async def handler_{cmd}(event):
                fake_msg = FakeMessage(event)
                try:
                    # Пробуем вызвать как метод класса
                    import inspect
                    sig = inspect.signature(func_{cmd})
                    if len(sig.parameters) == 2:
                        await func_{cmd}(module, fake_msg)
                    elif len(sig.parameters) == 1:
                        await func_{cmd}(fake_msg)
                    else:
                        await func_{cmd}()
                except Exception as e:
                    from utils.misc import edit_or_reply
                    await edit_or_reply(event, f"❌ Ошибка в {cmd}: {{e}}")
            
            client.add_event_handler(
                handler_{cmd},
                events.NewMessage(pattern=r"\\\\.{cmd}", outgoing=True)
            )
    except Exception as e:
        print(f"Error registering {cmd}: {{e}}")
'''
    
    setup_code = f'''

# ============================================
# AUTO-ADAPTED FROM HEROKU/HIKKA TO HYDRA
# ============================================

from telethon import events
from utils.misc import edit_or_reply

{compat_code}

def setup(client):
    loader.client = client
    
    module = {class_name}()
    # Передаём клиент в модуль если есть метод
    if hasattr(module, 'client'):
        module.client = client
    if hasattr(module, 'loader'):
        module.loader = loader
    
{handlers_code}

    # Регистрируем справку
    try:
        from utils.loader import modules_help
        help_dict = {{}}
'''
    
    for cmd in set(commands):
        setup_code += f"        help_dict['{cmd}'] = 'Команда .{cmd}'\n"
    
    setup_code += f'''
        modules_help["{module_name}"] = help_dict
    except:
        pass
'''
    
    return code + setup_code


def adapt_mcub_module(code: str, module_name: str) -> str:
    """Конвертирует MCUB модуль в Hydra формат"""
    
    # Добавляем совместимость
    compat_code = '''
# ============================================
# HYDRA COMPATIBILITY LAYER FOR MCUB
# ============================================
class LoaderStub:
    def __init__(self):
        self.db = {}
        self.client = None
        self.modules = {}
    
    def __getattr__(self, name):
        return None

loader = LoaderStub()

from utils.misc import edit_or_reply
'''
    
    # Исправляем импорты
    code = re.sub(r'from\s+\.\.\s+import\s+loader.*\n', '', code)
    code = re.sub(r'from\s+\.\.\s+import.*\n', '', code)
    code = re.sub(r'from\s+core\s+import\s+loader.*\n', '', code)
    code = re.sub(r'from\s+core\s+import', 'from utils.loader import', code)
    
    # Исправляем методы
    code = code.replace('await message.answer', 'await edit_or_reply(event')
    code = code.replace('await message.edit', 'await event.edit')
    code = code.replace('await message.reply', 'await event.reply')
    code = code.replace('message.chat_id', 'event.chat_id')
    code = code.replace('message.sender_id', 'event.sender_id')
    code = code.replace('message.text', 'event.text')
    code = code.replace('message.out', 'event.out')
    code = code.replace('message.reply_to_msg_id', 'event.reply_to_msg_id')
    code = code.replace('message.id', 'event.id')
    code = code.replace('@loader.command', '# @loader.command')
    code = code.replace('@loader.command()', '# @loader.command')
    code = code.replace('loader.db', '{}')
    code = code.replace('self.db', '{}')
    
    # Находим команды
    commands = []
    for line in code.split('\n'):
        m = re.search(r'async def (\w+)_cmd', line)
        if m:
            commands.append(m.group(1))
        m = re.search(r'async def (\w+)_handler', line)
        if m:
            commands.append(m.group(1))
        m = re.search(r'def (\w+)_cmd', line)
        if m:
            commands.append(m.group(1))
    
    # Генерируем регистрацию
    handlers_code = ""
    for cmd in set(commands):
        handlers_code += f'''
    # Регистрация команды {cmd}
    try:
        if '{cmd}_cmd' in globals():
            func = globals()['{cmd}_cmd']
        elif '{cmd}_handler' in globals():
            func = globals()['{cmd}_handler']
        else:
            func = None
        
        if func is not None:
            async def handler_{cmd}(event):
                try:
                    await func(event)
                except Exception as e:
                    await edit_or_reply(event, f"❌ Ошибка в {cmd}: {{e}}")
            
            client.add_event_handler(
                handler_{cmd},
                events.NewMessage(pattern=r"\\\\.{cmd}", outgoing=True)
            )
    except Exception as e:
        print(f"Error registering {cmd}: {{e}}")
'''
    
    if 'def setup' not in code:
        code = compat_code + code + f'''

# ============================================
# AUTO-ADAPTED FROM MCUB TO HYDRA
# ============================================

from telethon import events

def setup(client):
    loader.client = client
{handlers_code}

    # Регистрируем справку
    try:
        from utils.loader import modules_help
        help_dict = {{}}
'''
        for cmd in set(commands):
            code += f"        help_dict['{cmd}'] = 'Команда .{cmd}'\n"
        
        code += f'''
        modules_help["{module_name}"] = help_dict
    except:
        pass
'''
    
    return code


def adapt_module(code: str, module_name: str) -> tuple:
    """Адаптирует модуль любого типа под Hydra"""
    module_type = detect_module_type(code)
    
    if module_type == "hydra":
        return code, module_type, False
    elif module_type == "hikka":
        adapted = adapt_heroku_hikka_module(code, module_name)
        return adapted, module_type, True
    elif module_type == "mcub":
        adapted = adapt_mcub_module(code, module_name)
        return adapted, module_type, True
    
    return code, "unknown", False


async def detect_handler(event):
    """Определение типа модуля"""
    if not event.out:
        return
    
    from utils.misc import edit_or_reply
    
    reply = await event.get_reply_message()
    if not reply:
        return await edit_or_reply(event, "❌ Ответьте на файл модуля", parse_mode='HTML')
    
    msg = await edit_or_reply(event, "🔍 Анализ...", parse_mode='HTML')
    
    if reply.document:
        path = await reply.download_media()
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()
        Path(path).unlink()
    elif reply.text:
        code = reply.text
    else:
        return await msg.edit("❌ Ответьте на .py файл или текст", parse_mode='HTML')
    
    module_type = detect_module_type(code)
    
    # Дополнительный анализ
    has_class = 'class' in code and 'Mod' in code
    has_setup = 'def setup' in code
    has_loader = 'loader' in code
    
    features = []
    if has_class:
        features.append("📦 Класс модуля")
    if has_setup:
        features.append("⚙️ setup() функция")
    if has_loader:
        features.append("🔗 Использует loader")
    
    type_emoji = {
        "hikka": "🟣 Heroku/Hikka",
        "mcub": "🔵 MCUB",
        "hydra": "🟢 Hydra",
        "unknown": "⚪ Неизвестный"
    }
    
    features_text = "\n".join([f"  • {f}" for f in features]) if features else "  • Базовый модуль"
    
    await msg.edit(
        f"<b>📋 АНАЛИЗ МОДУЛЯ</b>\n\n"
        f"<blockquote>"
        f"🔍 <b>Тип:</b> {type_emoji.get(module_type, module_type)}\n\n"
        f"<b>Характеристики:</b>\n{features_text}\n"
        f"</blockquote>\n\n"
        f"<i>💡 При установке через .lm адаптация выполнится автоматически</i>",
        parse_mode='HTML'
    )


async def adapt_handler(event):
    """Ручная адаптация модуля"""
    if not event.out:
        return
    
    from utils.misc import edit_or_reply
    
    args = event.text.split()
    if len(args) < 2:
        return await edit_or_reply(event, "❌ <code>.adapt &lt;имя&gt;</code>", parse_mode='HTML')
    
    module_name = args[1].strip()
    module_path = Path('modules') / module_name / f"{module_name}.py"
    
    if not module_path.exists():
        module_path = Path('modules') / f"{module_name}.py"
    
    if not module_path.exists():
        return await edit_or_reply(event, f"❌ Модуль <code>{module_name}</code> не найден", parse_mode='HTML')
    
    msg = await edit_or_reply(event, f"🔄 Адаптация <code>{module_name}</code>...", parse_mode='HTML')
    
    with open(module_path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    module_type = detect_module_type(code)
    
    if module_type == "hydra":
        await msg.edit(f"✅ <code>{module_name}</code> уже в Hydra формате", parse_mode='HTML')
        return
    
    adapted, detected, _ = adapt_module(code, module_name)
    
    # Сохраняем бэкап
    backup_path = module_path.with_suffix('.py.bak')
    
    if module_path.parent.name == module_name:
        module_path.rename(backup_path)
        with open(module_path, 'w', encoding='utf-8') as f:
            f.write(adapted)
    else:
        module_dir = Path('modules') / module_name
        module_dir.mkdir(exist_ok=True)
        shutil.copy2(module_path, module_dir / f"{module_name}.py")
        with open(module_dir / f"{module_name}.py", 'w', encoding='utf-8') as f:
            f.write(adapted)
    
    type_emoji = {"hikka": "🟣 Heroku/Hikka", "mcub": "🔵 MCUB"}
    
    await msg.edit(
        f"✅ <b>Адаптирован!</b>\n"
        f"📦 <code>{module_name}</code>\n"
        f"🔄 {type_emoji.get(detected, detected)} → 🟢 Hydra\n"
        f"💾 Бэкап: <code>{backup_path.name}</code>",
        parse_mode='HTML'
    )


def setup(client):
    client.add_event_handler(detect_handler, events.NewMessage(pattern=r"\.detect", outgoing=True))
    client.add_event_handler(adapt_handler, events.NewMessage(pattern=r"\.adapt", outgoing=True))

modules_help = {
    "adapter": {
        "detect": "🔍 Определить тип модуля (Heroku/Hikka/MCUB)",
        "adapt <имя>": "🔄 Адаптировать модуль под Hydra"
    }
}
