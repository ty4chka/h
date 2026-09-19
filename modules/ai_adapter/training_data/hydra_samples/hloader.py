# modules/hloader.py
"""
Hydra Module Loader - Установка/удаление модулей
Адаптация вынесена в modules/adapter.py
"""

from utils.misc import edit_or_reply
import aiohttp
import asyncio
import logging
import os
import sys
import traceback
import re
import shutil
import zipfile
import subprocess
from pathlib import Path
from telethon import events

# Импорт адаптера
try:
    from modules.adapter import detect_module_type, adapt_module
    ADAPTER_AVAILABLE = True
except ImportError:
    ADAPTER_AVAILABLE = False
    def detect_module_type(c): return "unknown"
    def adapt_module(c, n): return c, "unknown", False

# Импорт из ядра
try:
    from utils.loader import (
        modules_help as global_modules_help,
        load_single_module,
        unload_single_module_handlers,
    )
except ImportError:
    global_modules_help = {}
    async def load_single_module(*args, **kwargs): return True
    async def unload_single_module_handlers(*args, **kwargs): return True

logger = logging.getLogger(__name__)


# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================

async def show_error(event, error_text, action="Action"):
    """Показ ошибки"""
    err = "".join(traceback.format_exception(None, error_text, error_text.__traceback__)) if isinstance(error_text, Exception) else str(error_text)
    
    if len(err) > 800:
        with open("error.txt", "w", encoding="utf-8") as f:
            f.write(err)
        await event.client.send_file(
            event.chat_id,
            "error.txt",
            caption=f"❌ <b>Ошибка {action}</b>",
            parse_mode='HTML',
            reply_to=event.id
        )
        os.remove("error.txt")
    else:
        await edit_or_reply(event, f"❌ <b>Ошибка {action}:</b>\n<pre>{err}</pre>", parse_mode='HTML')


async def wait_for_confirmation(event, title, info_dict):
    """Ожидание подтверждения .y/.n"""
    info_text = "\n".join([f"<b>{k}:</b> <code>{v}</code>" for k, v in info_dict.items()])
    
    text = f"""<b>{title}</b>

{info_text}

<blockquote expandable>▫️ <b>.y</b> — Подтвердить
▫️ <b>.n</b> — Отменить</blockquote>

<blockquote>👉 Напишите <code>.y</code> или <code>.n</code></blockquote>"""

    msg = await edit_or_reply(event, text, parse_mode='HTML')
    chat_id = event.chat_id
    client = event.client
    
    result = None
    confirm_event = asyncio.Event()
    handler = None
    
    async def confirm_handler(e):
        nonlocal result
        if e.chat_id != chat_id or not e.out:
            return
        
        t = e.text.lower().strip()
        
        if t == '.y':
            try:
                await e.delete()
            except:
                pass
            result = True
            confirm_event.set()
        elif t == '.n':
            try:
                await e.delete()
            except:
                pass
            result = False
            confirm_event.set()

    handler = client.add_event_handler(confirm_handler, events.NewMessage(outgoing=True))
    
    try:
        await asyncio.wait_for(confirm_event.wait(), timeout=60)
        return result
    except asyncio.TimeoutError:
        try:
            await msg.edit("❌ <b>Время истекло.</b>", parse_mode='HTML')
        except:
            pass
        return False
    finally:
        if handler:
            try:
                client.remove_event_handler(handler)
            except:
                pass


async def extract_module_name(code):
    """Извлечение имени модуля из кода"""
    m = re.search(r'modules_help\s*=\s*\{[\'"](\w+)[\'"]', code)
    if m:
        return m.group(1).lower()
    
    m = re.search(r'async def (\w+)_cmd', code)
    if m:
        return m.group(1).lower()
    
    m = re.search(r'async def (\w+)_handler', code)
    if m:
        return m.group(1).lower()
    
    m = re.search(r'class\s+(\w+)Mod\s*\(', code)
    if m:
        return m.group(1).replace('Mod', '').lower()
    
    return None


def extract_archive(archive_path: Path, extract_to: Path) -> bool:
    """Распаковка архива (zip/rar)"""
    try:
        if archive_path.suffix.lower() == '.zip':
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(extract_to)
            return True
        elif archive_path.suffix.lower() == '.rar':
            result = subprocess.run(
                ['unrar', 'x', '-y', str(archive_path), str(extract_to)],
                capture_output=True, text=True
            )
            return result.returncode == 0
    except Exception as e:
        logger.error(f"Extract error: {e}")
    return False


# ============================================
# ХЭНДЛЕРЫ
# ============================================

async def lm_handler(event):
    """Установка модуля с авто-адаптацией"""
    try:
        if not event.out:
            return
        
        args = event.text.split(maxsplit=1)
        reply = await event.get_reply_message()
        code, src, proposed_name = None, "", None
        is_archive = False
        archive_path = None
        
        loading = await edit_or_reply(event, "🔄 <b>Анализ...</b>", parse_mode='HTML')

        # Загрузка из URL
        if len(args) > 1:
            url = args[1]
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url) as r:
                        content = await r.read()
                
                url_lower = url.lower()
                if url_lower.endswith('.zip') or url_lower.endswith('.rar'):
                    is_archive = True
                    ext = '.zip' if url_lower.endswith('.zip') else '.rar'
                    archive_path = Path(f"/tmp/temp_module{ext}")
                    archive_path.write_bytes(content)
                    src = "Архив"
                    proposed_name = url.split('/')[-1].replace(ext, '')
                else:
                    code = content.decode('utf-8', errors='ignore')
                    src = "URL"
                    proposed_name = url.split('/')[-1].replace('.py', '')
            except Exception as e:
                return await show_error(loading, e, "Download")
            
        # Загрузка из файла
        elif reply and reply.document:
            path = await reply.download_media()
            file_path = Path(path)
            
            if file_path.suffix.lower() in ['.zip', '.rar']:
                is_archive = True
                archive_path = file_path
                src = "Архив"
                attr = reply.document.attributes
                if attr and len(attr) > 0:
                    proposed_name = getattr(attr[0], 'file_name', 'mod').rsplit('.', 1)[0]
            else:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    code = f.read()
                src = "Файл"
                attr = reply.document.attributes
                if attr and len(attr) > 0:
                    proposed_name = getattr(attr[0], 'file_name', 'mod').replace('.py', '')
                os.remove(path)

        # Загрузка из текста
        elif reply and reply.text:
            code = reply.text
            src = "Текст"
        else:
            return await loading.edit("❌ <b>Ответьте на .py файл, архив или ссылку</b>", parse_mode='HTML')

        # Обработка архива
        if is_archive and archive_path:
            await loading.edit("📦 <b>Распаковка архива...</b>", parse_mode='HTML')
            
            temp_dir = Path(f"/tmp/hydra_extract_{event.id}")
            temp_dir.mkdir(exist_ok=True)
            
            if extract_archive(archive_path, temp_dir):
                py_files = list(temp_dir.glob("**/*.py"))
                so_files = list(temp_dir.glob("**/*.so"))
                
                if not py_files and not so_files:
                    shutil.rmtree(temp_dir)
                    if archive_path.parent == Path("/tmp"):
                        archive_path.unlink()
                    return await loading.edit("❌ <b>В архиве нет .py или .so файлов</b>", parse_mode='HTML')
                
                module_name = proposed_name
                if not module_name:
                    if py_files:
                        module_name = py_files[0].stem
                    else:
                        module_name = so_files[0].stem.split('.')[0]
                
                module_name = module_name.lower().replace(' ', '_').replace('-', '_')
                
                info = {
                    "Модуль": module_name,
                    "Тип": "Архив",
                    "Файлов": str(len(py_files) + len(so_files))
                }
                
                if not await wait_for_confirmation(loading, "📦 Установка модуля из архива", info):
                    shutil.rmtree(temp_dir)
                    if archive_path.parent == Path("/tmp"):
                        archive_path.unlink()
                    return await loading.edit("❌ <b>Отменено</b>", parse_mode='HTML')
                
                module_dir = Path('modules') / module_name
                if module_dir.exists():
                    shutil.rmtree(module_dir)
                module_dir.mkdir(parents=True, exist_ok=True)
                
                for item in temp_dir.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, module_dir / item.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, module_dir / item.name)
                
                shutil.rmtree(temp_dir)
                if archive_path.parent == Path("/tmp"):
                    archive_path.unlink()
                
                target_file = None
                so_files = list(module_dir.glob("*.so"))
                if so_files:
                    target_file = so_files[0]
                else:
                    py_files = list(module_dir.glob("*.py"))
                    if py_files:
                        target_file = py_files[0]
                
                if target_file and await load_single_module(module_name, target_file, event.client):
                    await loading.edit(
                        f"✅ <b>Модуль установлен:</b> <code>{module_name}</code>\n"
                        f"📁 <code>modules/{module_name}/</code>",
                        parse_mode='HTML'
                    )
                else:
                    await loading.edit("⚠️ <b>Файлы скопированы, но загрузка не удалась</b>", parse_mode='HTML')
                
                if archive_path.parent == Path("/tmp"):
                    archive_path.unlink()
                return
            
            shutil.rmtree(temp_dir)
            if archive_path.parent == Path("/tmp"):
                archive_path.unlink()
            return await loading.edit("❌ <b>Ошибка распаковки архива</b>", parse_mode='HTML')

        # Обработка обычного .py файла
        if code is None:
            return await loading.edit("❌ <b>Не удалось получить код</b>", parse_mode='HTML')

        module_type = detect_module_type(code) if ADAPTER_AVAILABLE else "unknown"
        
        final_name = proposed_name
        if not final_name or final_name.startswith("mod_"):
            extracted = await extract_module_name(code)
            if extracted:
                final_name = extracted
        
        if not final_name:
            final_name = f"mod_{event.id}"
        final_name = final_name.lower().replace(' ', '_').replace('-', '_')

        type_emoji = {
            "hikka": "🟣 Hikka/Heroku",
            "mcub": "🔵 MCUB",
            "hydra": "🟢 Hydra",
            "unknown": "⚪ Неизвестный"
        }

        info = {
            "Модуль": final_name,
            "Тип": src,
            "Формат": type_emoji.get(module_type, module_type),
            "Размер": f"{len(code)} байт"
        }
        
        if ADAPTER_AVAILABLE and module_type != "hydra":
            info["Адаптация"] = "✅ Будет выполнена"
        
        if not await wait_for_confirmation(loading, "📦 Установка модуля", info):
            return await loading.edit("❌ <b>Отменено</b>", parse_mode='HTML')

        await loading.edit("📥 <b>Установка...</b>", parse_mode='HTML')
        
        # Адаптация кода (если нужно)
        adapted = False
        if ADAPTER_AVAILABLE and module_type != "hydra":
            await loading.edit(f"🔄 <b>Адаптация {module_type} → hydra...</b>", parse_mode='HTML')
            try:
                code, _, adapted = adapt_module(code, final_name)
            except Exception as e:
                logger.error(f"Adaptation error: {e}")
                # Продолжаем с оригинальным кодом
        
        # Создаём папку модуля
        module_dir = Path('modules') / final_name
        if module_dir.exists():
            shutil.rmtree(module_dir)
        module_dir.mkdir(parents=True, exist_ok=True)
        
        target = module_dir / f"{final_name}.py"
        with open(target, 'w', encoding='utf-8') as f:
            f.write(code)

        success = await load_single_module(final_name, target, event.client)

        if success:
            adapt_msg = "\n🔄 Адаптирован из " + type_emoji.get(module_type, module_type) if adapted else ""
            await loading.edit(
                f"✅ <b>Установлен:</b> <code>{final_name}</code>\n"
                f"📁 <code>modules/{final_name}/</code>{adapt_msg}",
                parse_mode='HTML'
            )
        else:
            await loading.edit("⚠️ <b>Файл создан, но загрузка не удалась</b>", parse_mode='HTML')

    except Exception as e:
        await show_error(event, e, "Install")


async def unlm_handler(event):
    """Удаление модуля (папки целиком)"""
    try:
        if not event.out:
            return
        
        args = event.text.split()
        if len(args) != 2:
            return await edit_or_reply(event, "❌ <code>.unlm &lt;имя&gt;</code>", parse_mode='HTML')
        
        name = args[1].replace('.py', '').replace('.so', '').strip()
        
        module_dir = Path('modules') / name
        old_py_file = Path('modules') / f"{name}.py"
        
        if not module_dir.exists() and not old_py_file.exists():
            return await edit_or_reply(event, f"❌ <b>Модуль</b> <code>{name}</code> <b>не найден</b>", parse_mode='HTML')
        
        info = {
            "Модуль": name,
            "Тип": "Папка" if module_dir.exists() else "Файл"
        }
        
        if not await wait_for_confirmation(event, "🗑 Удаление модуля", info):
            return await event.edit("❌ <b>Отменено</b>", parse_mode='HTML')
        
        load_msg = await event.edit("🗑 <b>Удаление...</b>", parse_mode='HTML')
        
        await unload_single_module_handlers(name, event.client)
        
        if module_dir.exists():
            shutil.rmtree(module_dir)
        if old_py_file.exists():
            old_py_file.unlink()
        
        for k in list(sys.modules.keys()):
            if k == f"modules.{name}" or k == name:
                if k in sys.modules:
                    del sys.modules[k]
        if name in global_modules_help:
            del global_modules_help[name]
        
        await load_msg.edit(
            f"✅ <b>Модуль удалён:</b> <code>{name}</code>",
            parse_mode='HTML'
        )
        
    except Exception as e:
        await show_error(event, e, "Uninstall")


async def hmods_handler(event):
    """Список установленных модулей"""
    if not event.out:
        return
    
    msg = await edit_or_reply(event, "📦")
    
    modules_info = []
    
    for item in Path('modules').iterdir():
        if item.name.startswith('_') or item.name == '__pycache__':
            continue
        
        if item.is_dir():
            has_so = len(list(item.glob("*.so"))) > 0
            has_py = len(list(item.glob("*.py"))) > 0
            status = "⚡" if has_so else ("🐍" if has_py else "📁")
            modules_info.append(f"{status} <code>{item.name}</code>")
        elif item.suffix == '.py':
            modules_info.append(f"🐍 <code>{item.stem}</code>")
        elif item.suffix == '.so':
            modules_info.append(f"⚡ <code>{item.stem.split('.')[0]}</code>")
    
    if not modules_info:
        return await msg.edit("📦 <b>Нет установленных модулей</b>", parse_mode='HTML')
    
    text = f"<b>📦 МОДУЛИ ({len(modules_info)})</b>\n\n"
    text += "\n".join(sorted(modules_info))
    
    await msg.edit(text, parse_mode='HTML')


async def compile_handler(event):
    """Ручная компиляция модуля в .so"""
    if not event.out:
        return
    
    args = event.text.split()
    if len(args) < 2:
        return await edit_or_reply(event, "❌ <code>.compile &lt;имя&gt;</code>", parse_mode='HTML')
    
    name = args[1].strip()
    module_dir = Path('modules') / name
    
    if not module_dir.exists():
        return await edit_or_reply(event, f"❌ Модуль <code>{name}</code> не найден", parse_mode='HTML')
    
    py_file = module_dir / f"{name}.py"
    if not py_file.exists():
        return await edit_or_reply(event, f"❌ <code>{name}.py</code> не найден в папке", parse_mode='HTML')
    
    msg = await edit_or_reply(event, f"⚙️ Компиляция <code>{name}</code>...", parse_mode='HTML')
    
    try:
        current_dir = os.getcwd()
        os.chdir(module_dir)
        
        result = subprocess.run(
            f"cythonize -i -3 {name}.py 2>&1",
            shell=True, capture_output=True, text=True, timeout=60
        )
        
        os.chdir(current_dir)
        
        so_files = list(module_dir.glob("*.so"))
        
        if so_files:
            await msg.edit(
                f"✅ <code>{name}</code> скомпилирован в .so\n"
                f"📁 <code>modules/{name}/</code>",
                parse_mode='HTML'
            )
        else:
            await msg.edit(
                f"❌ Ошибка компиляции\n<pre>{result.stderr[:500]}</pre>",
                parse_mode='HTML'
            )
    except Exception as e:
        os.chdir(current_dir)
        await msg.edit(f"❌ Ошибка: {e}", parse_mode='HTML')


# ============================================
# ЭКСПОРТ
# ============================================

def setup(client):
    """Регистрация хэндлеров"""
    client.add_event_handler(lm_handler, events.NewMessage(pattern=r"\.lm", outgoing=True))
    client.add_event_handler(unlm_handler, events.NewMessage(pattern=r"\.unlm", outgoing=True))
    client.add_event_handler(hmods_handler, events.NewMessage(pattern=r"\.hmods", outgoing=True))
    client.add_event_handler(compile_handler, events.NewMessage(pattern=r"\.compile", outgoing=True))

modules_help = {
    "module_loader": {
        "lm": "📦 Установить модуль (авто-адаптация)",
        "unlm <имя>": "🗑 Удалить папку модуля",
        "hmods": "📋 Список модулей",
        "compile <имя>": "⚙️ Скомпилировать в .so"
    }
}
