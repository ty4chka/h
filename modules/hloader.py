# modules/hloader.py
# meta: name=hloader version=1.0.0 author=hydra-team framework=setup
"""
Hydra Module Loader - Installation/removal/compilation of modules
Support: Hydra, Hikka, Heroku, MCUB, Dragon
Auto-adaptation via modules/adapter.py
"""

# ============================================================
# 1. КРИТИЧЕСКАЯ ИНЪЕКЦИЯ utils.strings (ДО ВСЕГО!)
# ============================================================
import sys
import types

def _early_inject_strings():
    """Ранняя инъекция utils.strings для MCUB модулей"""
    if 'utils.strings' in sys.modules:
        return
    
    try:
        from core.lib.loader.module_base import Strings
    except ImportError:
        # Заглушка если MCUB не установлен
        class Strings:
            def __init__(self, *args, **kwargs): pass
            def __call__(self, key, **kwargs): return key
            def __getitem__(self, key): return key
            def get(self, key, default=None): return default or key
    
    # Создаём модуль utils.strings
    mod = types.ModuleType('utils.strings')
    mod.Strings = Strings
    mod.__all__ = ['Strings']
    sys.modules['utils.strings'] = mod
    
    # Добавляем в корневой utils
    try:
        import utils
        if not hasattr(utils, 'Strings'):
            utils.Strings = Strings
    except ImportError:
        pass

_early_inject_strings()

# ============================================================
# 2. ОСТАЛЬНЫЕ ИМПОРТЫ
# ============================================================
from utils.misc import edit_or_reply
import aiohttp
import asyncio
import logging
import os
import traceback
import re
import shutil
import zipfile
import subprocess
import importlib.util
from pathlib import Path
from telethon import events

# Adapter import
try:
    from modules.adapter import detect_module_type, adapt_module, post_process, inline_to_commands
    ADAPTER_AVAILABLE = True
except ImportError:
    ADAPTER_AVAILABLE = False
    def detect_module_type(c): return "unknown"
    def adapt_module(c, n): return c, "unknown", False
    def post_process(c, t="unknown"): return c
    def inline_to_commands(c, n): return c

# MCUB Engine import
try:
    from mcub_engine.loader import get_loader as get_mcub_loader
    from mcub_engine import get_kernel as get_mcub_kernel
    MCUB_AVAILABLE = True
except ImportError:
    MCUB_AVAILABLE = False
    def get_mcub_loader(): return None
    def get_mcub_kernel(): return None

# Core import
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

MCUB_MODS_DIR = Path("modules/mcub_mods")

# ============================================
# MCUB MODULES HELPERS
# ============================================

def _get_mcub_iface():
    """MCUB-интерфейс единого движка (modules.mcub -> hydra_kernel.compat.mcub).

    Новый основной маршрут: все MCUB-модули живут в едином реестре Hydra,
    так что install/unload/list проходят через adapter_for("mcub").iface.
    Возвращает iface или None, если единый движок недоступен.
    """
    try:
        from modules.mcub import get_hydra

        h = get_hydra()
        if h is None or getattr(h, "loader", None) is None:
            return None
        adapter = h.loader.adapter_for("mcub")
        return getattr(adapter, "iface", None)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"single-engine MCUB iface error: {e}")
        return None


def get_mcub_modules():
    """Get list of loaded MCUB modules: (name, mtype, ncmds, meta)-кортежи."""

    # 1) Единый движок.
    iface = _get_mcub_iface()
    if iface is not None:
        try:
            out = []
            for name, instance in iface.loaded_modules.items():
                names = iface._loader._names_for(str(name))
                ncmds = sum(
                    1 for cmd, owner in iface.command_owners.items() if str(owner) in names
                )
                meta = {
                    "version": getattr(instance, "version", None)
                    or getattr(instance, "__version__", None),
                    "author": getattr(instance, "author", None)
                    or getattr(instance, "__author__", None),
                }
                mtype = "mcub" if str(name).endswith("_mcub_repo") or hasattr(instance, "register") else "core"
                out.append((str(name), mtype, ncmds, meta))
            return out
        except Exception as e:  # noqa: BLE001
            logger.debug(f"single-engine MCUB list error: {e}")

    # 3) Легаси mcub_engine (fallback).
    if not MCUB_AVAILABLE:
        return []
    try:
        loader = get_mcub_loader()
        if loader:
            return loader.list_modules()
    except Exception as e:
        logger.debug(f"MCUB list error: {e}")
    return []

def is_mcub_module(name):
    """Check if module is MCUB"""
    mods = get_mcub_modules()
    return any(n == name for n, _, _, _ in mods)

async def unload_mcub_module(name):
    """Unload MCUB module by name"""
    # 1) Единый движок.
    try:
        from modules.mcub import get_hydra

        h = get_hydra()
        if h is not None:
            iface = _get_mcub_iface()
            if iface is not None:
                names = iface._loader._names_for(str(name))
                for candidate in names:
                    if candidate in h.registry._records or candidate in iface.loaded_modules:
                        ok = await h.loader.unload(candidate)
                        if ok:
                            return True, f"Module {candidate} unloaded (single engine)"
            else:
                # без iface — пробуем напрямую по имени
                if name in h.registry._records:
                    ok = await h.loader.unload(name)
                    if ok:
                        return True, f"Module {name} unloaded (single engine)"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"single-engine MCUB unload error: {e}")

    # 3) Легаси mcub_engine (fallback).
    if not MCUB_AVAILABLE:
        return False, "MCUB Engine not available"
    try:
        loader = get_mcub_loader()
        if not loader:
            return False, "MCUB Loader not available"
        ok, msg = await loader.unload_module(name)
        return ok, msg
    except Exception as e:
        return False, str(e)

async def load_mcub_module_file(file_path):
    """Load MCUB module from file"""
    # 1) Единый движок.
    iface = _get_mcub_iface()
    if iface is not None:
        try:
            ok, msg = await iface.load_module_from_file(file_path)
            return ok, msg
        except Exception as e:  # noqa: BLE001
            logger.debug(f"single-engine MCUB load error: {e}")

    # 3) Легаси mcub_engine (fallback).
    if not MCUB_AVAILABLE:
        return False, "MCUB Engine not available"
    try:
        loader = get_mcub_loader()
        if not loader:
            return False, "MCUB Loader not available"
        ok, msg = await loader.load_module_file(file_path)
        return ok, msg
    except Exception as e:
        return False, str(e)

# ============================================
# DEPENDENCY MANAGEMENT
# ============================================

def extract_dependencies(code: str) -> list:
    """Extract pip dependencies from module code."""
    deps = []
    patterns = [
        (r'#\s*requires:\s*(.+)', re.IGNORECASE),
        (r'#\s*dependencies:\s*(.+)', re.IGNORECASE),
        (r'#\s*pip:\s*(.+)', re.IGNORECASE),
    ]
    for pattern, flags in patterns:
        match = re.search(pattern, code, flags)
        if match:
            deps.extend([d.strip() for d in match.group(1).split(',') if d.strip()])
    # JSON format
    json_match = re.search(r'"dependencies"\s*:\s*\[(.*?)\]', code, re.DOTALL)
    if json_match:
        items = re.findall(r'["\']([^"\']+)["\']', json_match.group(1))
        deps.extend(items)
    # Deduplicate
    seen = set()
    result = []
    for dep in deps:
        key = dep.lower()
        if key not in seen:
            seen.add(key)
            result.append(dep)
    return result

def check_dependency_installed(dep_spec: str) -> tuple:
    """Check if a dependency is installed. Returns (is_installed, package_name)."""
    dep = dep_spec.strip()
    if dep.startswith('git+') or dep.startswith('http'):
        match = re.search(r'/([^/]+?)(?:\.git)?$', dep)
        pkg_name = match.group(1).replace('_', '-') if match else dep.split('/')[-1].replace('_', '-')
    else:
        pkg_name = re.split(r'[<>=!~;]', dep)[0].strip()
    import_name = pkg_name.lower().replace('-', '_')
    name_map = {
        'pillow': 'PIL',
        'beautifulsoup4': 'bs4',
        'scikit-learn': 'sklearn',
        'opencv-python': 'cv2',
        'python-telegram-bot': 'telegram',
        'yandex-music-api': 'yandex_music',
        'python-dotenv': 'dotenv',
    }
    if pkg_name.lower() in name_map:
        import_name = name_map[pkg_name.lower()]
    try:
        spec = importlib.util.find_spec(import_name)
        is_installed = spec is not None
    except (ModuleNotFoundError, ImportError):
        is_installed = False
    return is_installed, pkg_name

def get_missing_dependencies(deps: list) -> list:
    """Get list of missing dependencies. Returns [(original_spec, package_name)]."""
    result = []
    for dep in deps:
        is_installed, pkg_name = check_dependency_installed(dep)
        if not is_installed:
            result.append((dep, pkg_name))
    return result

def format_deps(deps: list, show_status: bool = True) -> str:
    """Format dependency list for display."""
    if not deps:
        return "<i>None declared</i>"
    lines = []
    for dep in deps:
        if show_status:
            status = "✅" if check_dependency_installed(dep)[0] else "❌"
            lines.append(f"{status} <code>{dep}</code>")
        else:
            lines.append(f"• <code>{dep}</code>")
    return "\n".join(lines)

async def install_deps(deps: list, event=None) -> tuple:
    """Install dependencies via pip. Returns (all_ok, errors)."""
    errors = []
    for dep in deps:
        dep_clean = dep.strip()
        if not dep_clean:
            continue
        try:
            if event:
                try:
                    await event.edit(f"<b>📦 Installing:</b> <code>{dep_clean}</code>...", parse_mode='HTML')
                except:
                    pass
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", dep_clean],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                err = result.stderr[-300:] if result.stderr else "Unknown error"
                errors.append(f"<code>{dep_clean}</code>: {err}")
        except subprocess.TimeoutExpired:
            errors.append(f"<code>{dep_clean}</code>: Timeout (120s)")
        except Exception as e:
            errors.append(f"<code>{dep_clean}</code>: {str(e)}")
    return len(errors) == 0, errors

# ============================================
# CONFIRMATION HELPERS
# ============================================

async def wait_for_confirmation(event, title, info_dict):
    """Wait for .y/.n confirmation."""
    info_text = "\n".join(["<b>" + k + ":</b> <code>" + str(v) + "</code>" for k, v in info_dict.items()])
    text = "<b>" + title + "</b>\n\n" + info_text + """
<blockquote expandable><b>.y</b> - Confirm
<b>.n</b> - Cancel</blockquote>
<blockquote>Write <code>.y</code> or <code>.n</code></blockquote>"""
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
            try: await e.delete()
            except: pass
            result = True
            confirm_event.set()
        elif t == '.n':
            try: await e.delete()
            except: pass
            result = False
            confirm_event.set()

    handler = client.add_event_handler(confirm_handler, events.NewMessage(outgoing=True))
    try:
        await asyncio.wait_for(confirm_event.wait(), timeout=60)
        return result
    except asyncio.TimeoutError:
        try: await msg.edit("<b>Time expired.</b>", parse_mode='HTML')
        except: pass
        return False
    finally:
        if handler:
            try: client.remove_event_handler(handler)
            except: pass

async def ask_install_deps(event, missing: list, module_name: str) -> bool:
    """Ask user to install missing dependencies. Returns True if confirmed."""
    if not missing:
        return True
    deps_text = "\n".join([f"❌ <code>{spec}</code>" for spec, _ in missing])
    text = (
        f"<b>⚠️ Missing dependencies for</b> <code>{module_name}</code>\n\n"
        f"{deps_text}\n\n"
        f"<blockquote expandable><b>.y</b> — Install\n<b>.n</b> — Skip</blockquote>"
    )
    msg = await edit_or_reply(event, text, parse_mode='HTML')
    chat_id = event.chat_id
    client = event.client
    result = None
    confirm_event = asyncio.Event()
    handler = None

    async def handler_fn(e):
        nonlocal result
        if e.chat_id != chat_id or not e.out:
            return
        t = e.text.lower().strip()
        if t == '.y':
            try: await e.delete()
            except: pass
            result = True
            confirm_event.set()
        elif t == '.n':
            try: await e.delete()
            except: pass
            result = False
            confirm_event.set()

    handler = client.add_event_handler(handler_fn, events.NewMessage(outgoing=True))
    try:
        await asyncio.wait_for(confirm_event.wait(), timeout=60)
        return result if result is not None else False
    except asyncio.TimeoutError:
        try: await msg.edit("<b>⏰ Time expired.</b>", parse_mode='HTML')
        except: pass
        return False
    finally:
        if handler:
            try: client.remove_event_handler(handler)
            except: pass

async def show_error(event, error_text, action="Action"):
    """Show error with file sending if text is long."""
    err = "".join(traceback.format_exception(None, error_text, error_text.__traceback__)) if isinstance(error_text, Exception) else str(error_text)
    if len(err) > 800:
        with open("error.txt", "w", encoding="utf-8") as f:
            f.write(err)
        await event.client.send_file(
            event.chat_id, "error.txt",
            caption="<b>Error " + action + "</b>",
            parse_mode='HTML', reply_to=event.id
        )
        os.remove("error.txt")
    else:
        await edit_or_reply(event, "<b>Error " + action + ":</b>\n<pre>" + err + "</pre>", parse_mode='HTML')

async def extract_module_name(code):
    """Extract module name from code."""
    m = re.search(r'modules_help\s*=\s*\{\s*[\'"](\w+)[\'"]', code)
    if m: return m.group(1).lower()
    m = re.search(r'async def (\w+)_cmd', code)
    if m: return m.group(1).lower()
    m = re.search(r'async def (\w+)_handler', code)
    if m: return m.group(1).lower()
    m = re.search(r'class\s+(\w+)Mod\s*\(', code)
    if m: return m.group(1).replace('Mod', '').lower()
    return None

def extract_archive(archive_path: Path, extract_to: Path) -> bool:
    """Extract archive (zip/rar)."""
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
        logger.error("Extract error: " + str(e))
    return False

async def compile_module_to_so(module_name: str, module_dir: Path) -> tuple:
    """Compile Python module to .so via Cython."""
    py_file = module_dir / (module_name + ".py")
    if not py_file.exists():
        return False, "<code>" + module_name + ".py</code> not found"
    try:
        try:
            from Cython.Build import cythonize
            from Cython.Compiler.Main import compile as cython_compile
        except ImportError:
            return False, "Cython not installed. Run: <code>pip install cython</code>"
        import Cython.Compiler.Main
        c_file = module_dir / (module_name + ".c")
        result = Cython.Compiler.Main.compile(
            str(py_file), output_file=str(c_file),
            options=Cython.Compiler.Main.CompilationOptions(language_level='3', always_allow_keywords=True)
        )
        if result.num_errors > 0:
            return False, "Cython errors: " + str(result.num_errors)
        if not c_file.exists():
            return False, ".c file not created"
        so_file = module_dir / (module_name + ".so")
        import sysconfig
        python_include = sysconfig.get_path('include')
        gcc_cmd = [
            'gcc', '-shared', '-fPIC', '-O3',
            '-I', python_include, str(c_file),
            '-o', str(so_file),
            '-lpython' + sysconfig.get_config_var('VERSION'),
        ]
        compile_result = subprocess.run(gcc_cmd, capture_output=True, text=True, timeout=60)
        c_file.unlink(missing_ok=True)
        if compile_result.returncode != 0:
            err = compile_result.stderr[-500:] if compile_result.stderr else "gcc failed"
            return False, "gcc error:\n<pre>" + err + "</pre>"
        if so_file.exists():
            return True, "<code>" + module_name + "</code> compiled to .so\n<code>modules/" + module_name + "/</code>"
        return False, ".so file not created"
    except subprocess.TimeoutExpired:
        return False, "Compilation timeout (60 sec)"
    except Exception as e:
        return False, "Error: " + str(e)

# ============================================
# MAIN HANDLERS
# ============================================

# ============================================
# URL NORMALIZATION
# ============================================

def _normalize_url(url: str) -> str:
    """Convert GitHub blob/gist links to raw content URLs."""
    # GitHub blob -> raw
    m = re.match(r'https?://github\.com/([^/]+)/([^/]+)/blob/(.+)', url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    # GitHub gist
    m = re.match(r'https?://gist\.github\.com/([^/]+)/([a-f0-9]+)', url)
    if m:
        return f"https://gist.githubusercontent.com/{m.group(1)}/{m.group(2)}/raw"
    return url

async def lm_handler(event):
    """Install module with auto-adaptation and dependency checking."""
    try:
        if not event.out:
            return
        args = event.text.split(maxsplit=1)
        reply = await event.get_reply_message()
        code, src, proposed_name = None, "", None
        is_archive = False
        archive_path = None
        loading = await edit_or_reply(event, "<b>🔍 Analyzing...</b>", parse_mode='HTML')

        # Load from URL
        if len(args) > 1:
            url = _normalize_url(args[1].strip())
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url) as r:
                        content = await r.read()
                url_lower = url.lower()
                if url_lower.endswith('.zip') or url_lower.endswith('.rar'):
                    is_archive = True
                    ext = '.zip' if url_lower.endswith('.zip') else '.rar'
                    archive_path = Path("/tmp/temp_module" + ext)
                    archive_path.write_bytes(content)
                    src = "Archive"
                    proposed_name = url.split('/')[-1].replace(ext, '')
                else:
                    code = content.decode('utf-8', errors='ignore')
                    src = "URL"
                    proposed_name = url.split('/')[-1].replace('.py', '')
            except Exception as e:
                return await show_error(loading, e, "Download")

        # Load from file
        elif reply and reply.document:
            path = await reply.download_media()
            file_path = Path(path)
            if file_path.suffix.lower() in ['.zip', '.rar']:
                is_archive = True
                archive_path = file_path
                src = "Archive"
                attr = reply.document.attributes
                if attr and len(attr) > 0:
                    proposed_name = getattr(attr[0], 'file_name', 'mod').rsplit('.', 1)[0]
            else:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    code = f.read()
                src = "File"
                attr = reply.document.attributes
                if attr and len(attr) > 0:
                    proposed_name = getattr(attr[0], 'file_name', 'mod').replace('.py', '')
                os.remove(path)

        # Load from text
        elif reply and reply.text:
            code = reply.text
            src = "Text"
        else:
            return await loading.edit("<b>Reply to .py file, archive or link</b>", parse_mode='HTML')

        # Process archive
        if is_archive and archive_path:
            await loading.edit("<b>📦 Extracting archive...</b>", parse_mode='HTML')
            temp_dir = Path("/tmp/hydra_extract_" + str(event.id))
            temp_dir.mkdir(exist_ok=True)
            if extract_archive(archive_path, temp_dir):
                py_files = list(temp_dir.glob("**/*.py"))
                so_files = list(temp_dir.glob("**/*.so"))
                if not py_files and not so_files:
                    shutil.rmtree(temp_dir)
                    if archive_path.parent == Path("/tmp"):
                        archive_path.unlink()
                    return await loading.edit("<b>No .py or .so files in archive</b>", parse_mode='HTML')
                module_name = proposed_name
                if not module_name:
                    module_name = py_files[0].stem if py_files else so_files[0].stem.split('.')[0]
                module_name = module_name.lower().replace(' ', '_').replace('-', '_')
                info = {"Module": module_name, "Type": "Archive", "Files": str(len(py_files) + len(so_files))}
                if not await wait_for_confirmation(loading, "Install module from archive", info):
                    shutil.rmtree(temp_dir)
                    if archive_path.parent == Path("/tmp"):
                        archive_path.unlink()
                    return await loading.edit("<b>Cancelled</b>", parse_mode='HTML')
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
                        "<b>✅ Module installed:</b> <code>" + module_name + "</code>\n"
                        "<code>modules/" + module_name + "/</code>", parse_mode='HTML'
                    )
                else:
                    await loading.edit("<b>Files copied but loading failed</b>", parse_mode='HTML')
                if archive_path.parent == Path("/tmp"):
                    archive_path.unlink()
                return
            shutil.rmtree(temp_dir)
            if archive_path.parent == Path("/tmp"):
                archive_path.unlink()
            return await loading.edit("<b>Archive extraction error</b>", parse_mode='HTML')

        # Process .py file
        if code is None:
            return await loading.edit("<b>Failed to get code</b>", parse_mode='HTML')

        module_type = detect_module_type(code) if ADAPTER_AVAILABLE else "unknown"
        final_name = proposed_name
        if not final_name or final_name.startswith("mod_"):
            extracted = await extract_module_name(code)
            if extracted:
                final_name = extracted
        if not final_name:
            final_name = "mod_" + str(event.id)
        final_name = final_name.lower().replace(' ', '_').replace('-', '_')

        # Extract dependencies
        deps = extract_dependencies(code)
        missing = get_missing_dependencies(deps)

        type_labels = {
            "hikka": "Hikka/Heroku", "mcub": "MCUB",
            "mcub_core": "MCUB Core", "hydra": "Hydra",
            "dragon": "Dragon", "unknown": "Unknown"
        }

        info = {
            "Module": final_name, "Type": src,
            "Format": type_labels.get(module_type, module_type),
            "Size": str(len(code)) + " bytes"
        }
        if deps:
            info["Dependencies"] = str(len(deps)) + " declared"
        if missing:
            info["Missing"] = str(len(missing))
        if ADAPTER_AVAILABLE and module_type != "hydra":
            info["Adaptation"] = "Will be performed"

        # Build confirmation message with deps
        confirm_text = "<b>📦 Install module</b>\n\n"
        for k, v in info.items():
            confirm_text += f"<b>{k}:</b> <code>{v}</code>\n"
        if deps:
            confirm_text += f"\n<b>📋 Dependencies:</b>\n{format_deps(deps, show_status=True)}"
        confirm_text += """
<blockquote expandable><b>.y</b> - Confirm
<b>.n</b> - Cancel</blockquote>
<blockquote>Write <code>.y</code> or <code>.n</code></blockquote>"""

        msg = await loading.edit(confirm_text, parse_mode='HTML')
        chat_id = event.chat_id
        client = event.client
        result = None
        confirm_event = asyncio.Event()
        handler = None

        async def dep_confirm_handler(e):
            nonlocal result
            if e.chat_id != chat_id or not e.out:
                return
            t = e.text.lower().strip()
            if t == '.y':
                try: await e.delete()
                except: pass
                result = True
                confirm_event.set()
            elif t == '.n':
                try: await e.delete()
                except: pass
                result = False
                confirm_event.set()

        handler = client.add_event_handler(dep_confirm_handler, events.NewMessage(outgoing=True))
        try:
            await asyncio.wait_for(confirm_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            try: await msg.edit("<b>⏰ Time expired.</b>", parse_mode='HTML')
            except: pass
            if handler:
                try: client.remove_event_handler(handler)
                except: pass
            return
        finally:
            if handler:
                try: client.remove_event_handler(handler)
                except: pass

        if not result:
            return await msg.edit("<b>❌ Cancelled</b>", parse_mode='HTML')

        # ============================================================
        # MCUB ENGINE: загружаем через mcub_engine
        # ============================================================
        if module_type == "mcub_core" or (MCUB_AVAILABLE and "core.lib.loader" in code):
            try:
                await msg.edit("<b>⚙️ Installing MCUB module (native engine)...</b>", parse_mode='HTML')
                
                # Создаём папку mcub_mods если нет
                MCUB_MODS_DIR.mkdir(parents=True, exist_ok=True)
                
                # Сохраняем файл
                target_file = MCUB_MODS_DIR / f"{final_name}.py"
                target_file.write_text(code, encoding='utf-8')
                
                # Загружаем через MCUB loader
                ok, text = await load_mcub_module_file(target_file)
                
                if ok:
                    await msg.edit(
                        f"<b>✅ {text}</b>\n"
                        f"<code>modules/mcub_mods/{final_name}.py</code>\n"
                        f"<i>Inline buttons work as <code>.cb N</code> commands</i>",
                        parse_mode='HTML'
                    )
                else:
                    await msg.edit(f"<b>❌ {text}</b>", parse_mode='HTML')
            except Exception as e:
                await msg.edit(f"<b>❌ MCUB engine error:</b> <code>{str(e)}</code>", parse_mode='HTML')
            return
        # ============================================================
        # END MCUB ENGINE
        # ============================================================

        # Install missing dependencies
        install_confirmed = False
        if missing:
            install_confirmed = await ask_install_deps(msg, missing, final_name)
            if install_confirmed:
                await msg.edit(f"<b>📦 Installing {len(missing)} dependencies...</b>", parse_mode='HTML')
                dep_specs = [spec for spec, _ in missing]
                all_ok, errors = await install_deps(dep_specs, msg)
                if not all_ok:
                    error_text = "\n".join(errors[:5])
                    if len(errors) > 5:
                        error_text += f"\n...and {len(errors) - 5} more"
                    await msg.edit(
                        f"<b>⚠️ Some dependencies failed:</b>\n{error_text}\n\n"
                        f"<b>Continuing with module installation...</b>", parse_mode='HTML'
                    )
                    await asyncio.sleep(2)

        await msg.edit("<b>🔧 Installing module...</b>", parse_mode='HTML')

        # Adapt code
        adapted = False
        if ADAPTER_AVAILABLE and module_type != "hydra":
            await msg.edit("<b>🔄 Adapting " + module_type + " -> hydra...</b>", parse_mode='HTML')
            try:
                code, _, adapted = adapt_module(code, final_name)
                code = post_process(code, module_type)
                code = inline_to_commands(code, final_name)
            except Exception as e:
                logger.error("Adaptation error: " + str(e))

        # Create module folder
        module_dir = Path('modules') / final_name
        if module_dir.exists():
            shutil.rmtree(module_dir)
        module_dir.mkdir(parents=True, exist_ok=True)
        target = module_dir / (final_name + ".py")
        with open(target, 'w', encoding='utf-8') as f:
            f.write(code)

        success = await load_single_module(final_name, target, event.client)

        if success:
            adapt_msg = "\n🔄 Adapted from " + type_labels.get(module_type, module_type) if adapted else ""
            dep_msg = ""
            if deps:
                installed_count = len(deps) - len(missing)
                dep_msg = f"\n📦 Dependencies: {installed_count}/{len(deps)} ready"
                if missing and not install_confirmed:
                    dep_msg += "\n⚠️ Some deps missing - module may not work fully"
            await msg.edit(
                "<b>✅ Installed:</b> <code>" + final_name + "</code>\n"
                "<code>modules/" + final_name + "/</code>" + adapt_msg + dep_msg,
                parse_mode='HTML'
            )
        else:
            await msg.edit("<b>❌ File created but loading failed</b>", parse_mode='HTML')

    except Exception as e:
        await show_error(event, e, "Install")

async def unlm_handler(event):
    """Remove module (including MCUB)."""
    try:
        if not event.out:
            return
        args = event.text.split()
        if len(args) != 2:
            return await edit_or_reply(event, "<code>.unlm &lt;name&gt;</code>", parse_mode='HTML')
        name = args[1].replace('.py', '').replace('.so', '').strip()
        
        # Проверяем MCUB модуль
        if is_mcub_module(name):
            info = {"Module": name, "Type": "MCUB"}
            if not await wait_for_confirmation(event, "Remove MCUB module", info):
                return await event.edit("<b>Cancelled</b>", parse_mode='HTML')
            ok, msg = await unload_mcub_module(name)
            if ok:
                # Удаляем файл
                target = MCUB_MODS_DIR / f"{name}.py"
                if target.exists():
                    target.unlink()
                await event.edit(f"<b>✅ MCUB module removed:</b> <code>{name}</code>", parse_mode='HTML')
            else:
                await event.edit(f"<b>❌ {msg}</b>", parse_mode='HTML')
            return
        
        # Обычный модуль
        module_dir = Path('modules') / name
        old_py_file = Path('modules') / (name + ".py")
        if not module_dir.exists() and not old_py_file.exists():
            return await edit_or_reply(event, "<b>Module</b> <code>" + name + "</code> <b>not found</b>", parse_mode='HTML')
        info = {"Module": name, "Type": "Folder" if module_dir.exists() else "File"}
        if not await wait_for_confirmation(event, "Remove module", info):
            return await event.edit("<b>Cancelled</b>", parse_mode='HTML')
        load_msg = await event.edit("<b>🗑 Removing...</b>", parse_mode='HTML')
        await unload_single_module_handlers(name, event.client)
        if module_dir.exists():
            shutil.rmtree(module_dir)
        if old_py_file.exists():
            old_py_file.unlink()
        for k in list(sys.modules.keys()):
            if k == "modules." + name or k == name:
                if k in sys.modules:
                    del sys.modules[k]
        if name in global_modules_help:
            del global_modules_help[name]
        await load_msg.edit("<b>✅ Module removed:</b> <code>" + name + "</code>", parse_mode='HTML')
    except Exception as e:
        await show_error(event, e, "Uninstall")

async def hmods_handler(event):
    """List ALL installed modules (including MCUB)."""
    if not event.out:
        return
    msg = await edit_or_reply(event, "📋 Scanning modules...")
    modules_info = []
    
    # Обычные модули
    for item in Path('modules').iterdir():
        if item.name.startswith('_') or item.name == '__pycache__' or item.name == 'mcub_mods':
            continue
        if item.is_dir():
            has_so = len(list(item.glob("*.so"))) > 0
            has_py = len(list(item.glob("*.py"))) > 0
            status = "🔥 Compiled" if has_so else ("🐍 Python" if has_py else "📁 Folder")
            modules_info.append(f"<code>{item.name}</code> {status}")
        elif item.suffix == '.py' and item.stem not in ['mcub', 'adapter']:
            modules_info.append(f"<code>{item.stem}</code> 🐍 Python")
        elif item.suffix == '.so':
            modules_info.append(f"<code>{item.stem.split('.')[0]}</code> 🔥 Compiled")
    
    # MCUB-модули из mcub_mods/
    if MCUB_AVAILABLE and MCUB_MODS_DIR.exists():
        mcub_mods = get_mcub_modules()
        if mcub_mods:
            for name, mtype, ncmds, meta in mcub_mods:
                ver = f" v{meta['version']}" if meta.get('version') else ""
                author = f" by {meta['author']}" if meta.get('author') else ""
                modules_info.append(
                    f"<code>{name}</code> 🧩 MCUB [{mtype}]{ver}{author} — {ncmds} cmd"
                )
        else:
            # Показываем файлы в папке даже если не загружены
            for f in MCUB_MODS_DIR.glob("*.py"):
                if not f.name.startswith('_'):
                    modules_info.append(f"<code>{f.stem}</code> 🧩 MCUB (not loaded)")
    
    if not modules_info:
        return await msg.edit("<b>No modules installed</b>", parse_mode='HTML')
    
    text = f"<b>📦 MODULES ({len(modules_info)})</b>\n\n"
    text += "\n".join(sorted(modules_info))
    text += "\n\n<i>🧩 = MCUB module | .mls for MCUB details</i>"
    await msg.edit(text, parse_mode='HTML')

async def compile_handler(event):
    """Compile module to .so via Cython."""
    if not event.out:
        return
    args = event.text.split()
    if len(args) < 2:
        return await edit_or_reply(event, "<code>.compile &lt;name&gt;</code>", parse_mode='HTML')
    name = args[1].strip()
    module_dir = Path('modules') / name
    if not module_dir.exists():
        return await edit_or_reply(event, "Module <code>" + name + "</code> not found", parse_mode='HTML')
    msg = await edit_or_reply(event, "🔧 Compiling <code>" + name + "</code>...", parse_mode='HTML')
    success, result_text = await compile_module_to_so(name, module_dir)
    await msg.edit(result_text, parse_mode='HTML')

async def compileall_handler(event):
    """Compile ALL modules to .so."""
    if not event.out:
        return
    msg = await edit_or_reply(event, "<b>🔧 Compiling all modules...</b>", parse_mode='HTML')
    results = []
    compiled = 0
    failed = 0
    for item in Path('modules').iterdir():
        if item.name.startswith('_') or item.name == '__pycache__' or item.name == 'mcub_mods':
            continue
        if item.is_dir():
            py_file = item / (item.name + ".py")
            if py_file.exists():
                success, _ = await compile_module_to_so(item.name, item)
                if success:
                    compiled += 1
                    results.append("<code>" + item.name + "</code> ✅")
                else:
                    failed += 1
                    results.append("<code>" + item.name + "</code> ❌")
    text = "<b>🔥 Compilation results</b>\n\n"
    text += "✅ OK: <code>" + str(compiled) + "</code>\n"
    text += "❌ Failed: <code>" + str(failed) + "</code>\n\n"
    text += "\n".join(results) if results else "No modules to compile"
    await msg.edit(text, parse_mode='HTML')

async def modinfo_handler(event):
    """Module info including MCUB modules."""
    if not event.out:
        return
    args = event.text.split()
    if len(args) < 2:
        return await edit_or_reply(event, "<code>.modinfo &lt;name&gt;</code>", parse_mode='HTML')
    name = args[1].strip()
    
    # Проверяем MCUB модуль
    if MCUB_AVAILABLE and is_mcub_module(name):
        loader = get_mcub_loader()
        kernel = get_mcub_kernel()
        if loader and kernel:
            mods = loader.list_modules()
            for mod_name, mtype, ncmds, meta in mods:
                if mod_name == name:
                    info_lines = []
                    info_lines.append(f"<b>🧩 MCUB Module:</b> <code>{name}</code>")
                    info_lines.append(f"<b>⚙️ Type:</b> <code>{mtype}</code>")
                    info_lines.append(f"<b>⌨️ Commands:</b> <code>{ncmds}</code>")
                    if meta.get('version'):
                        info_lines.append(f"<b>📌 Version:</b> <code>{meta['version']}</code>")
                    if meta.get('author'):
                        info_lines.append(f"<b>👤 Author:</b> <code>{meta['author']}</code>")
                    # Показываем команды
                    if kernel:
                        help_dict = loader._local_help().get(name)
                        if help_dict:
                            info_lines.append("")
                            info_lines.append("<b>⌨️ Commands:</b>")
                            for cmd, desc in help_dict.items():
                                info_lines.append(f"  <code>.{cmd}</code> — {desc}")
                    await edit_or_reply(event, "\n".join(info_lines), parse_mode='HTML')
                    return
    
    # Обычный модуль
    module_dir = Path('modules') / name
    if not module_dir.exists():
        return await edit_or_reply(event, "Module <code>" + name + "</code> not found", parse_mode='HTML')
    info_lines = []
    info_lines.append("<b>📦 Module:</b> <code>" + name + "</code>")
    total_size = 0
    file_count = 0
    for f in module_dir.rglob("*"):
        if f.is_file():
            total_size += f.stat().st_size
            file_count += 1
    size_kb = total_size / 1024
    size_str = str(round(size_kb, 1)) + " KB" if size_kb < 1024 else str(round(size_kb/1024, 2)) + " MB"
    info_lines.append("<b>📊 Size:</b> <code>" + size_str + "</code> (" + str(file_count) + " files)")
    has_py = len(list(module_dir.glob("*.py"))) > 0
    has_so = len(list(module_dir.glob("*.so"))) > 0
    type_str = "🐍 Python" if has_py else ""
    if has_so:
        type_str += " + 🔥 Compiled" if type_str else "🔥 Compiled"
    info_lines.append("<b>⚙️ Type:</b> " + type_str)
    py_file = module_dir / (name + ".py")
    if py_file.exists():
        code = py_file.read_text(encoding='utf-8', errors='ignore')
        deps = extract_dependencies(code)
        if deps:
            info_lines.append("")
            info_lines.append("<b>📋 Dependencies:</b>")
            for dep in deps:
                status = "✅" if check_dependency_installed(dep)[0] else "❌"
                info_lines.append(f"  {status} <code>{dep}</code>")
        module_type = detect_module_type(code) if ADAPTER_AVAILABLE else "unknown"
        if module_type != "hydra":
            info_lines.append("<b>🔄 Source:</b> <code>" + module_type + "</code>")
    if name in global_modules_help:
        help_dict = global_modules_help[name]
        info_lines.append("")
        info_lines.append("<b>⌨️ Commands:</b>")
        for cmd, desc in help_dict.items():
            info_lines.append("  <code>." + cmd + "</code> — " + desc)
    await edit_or_reply(event, "\n".join(info_lines), parse_mode='HTML')

async def deps_handler(event):
    """Check and install dependencies for a module."""
    if not event.out:
        return
    args = event.text.split()
    if len(args) < 2:
        return await edit_or_reply(
            event,
            "<code>.deps &lt;name&gt;</code> — check/install dependencies\n"
            "<code>.deps --all</code> — check all modules",
            parse_mode='HTML'
        )
    if args[1] == '--all':
        msg = await edit_or_reply(event, "<b>🔍 Checking all modules...</b>", parse_mode='HTML')
        all_missing = []
        # Обычные модули
        for item in Path('modules').iterdir():
            if item.name.startswith('_') or item.name == '__pycache__' or item.name == 'mcub_mods':
                continue
            py_file = item / (item.name + ".py")
            if py_file.exists():
                try:
                    code = py_file.read_text(encoding='utf-8', errors='ignore')
                    deps = extract_dependencies(code)
                    missing = get_missing_dependencies(deps)
                    if missing:
                        all_missing.append((item.name, missing))
                except:
                    pass
        # MCUB модули
        if MCUB_AVAILABLE and MCUB_MODS_DIR.exists():
            for f in MCUB_MODS_DIR.glob("*.py"):
                if f.name.startswith('_'):
                    continue
                try:
                    code = f.read_text(encoding='utf-8', errors='ignore')
                    deps = extract_dependencies(code)
                    missing = get_missing_dependencies(deps)
                    if missing:
                        all_missing.append((f.stem + " (MCUB)", missing))
                except:
                    pass
        if not all_missing:
            return await msg.edit("<b>✅ All modules have their dependencies satisfied!</b>", parse_mode='HTML')
        text = "<b>⚠️ Missing dependencies found:</b>\n\n"
        for mod_name, missing in all_missing:
            text += f"<b>📦 {mod_name}:</b>\n"
            for spec, pkg in missing:
                text += f"  ❌ <code>{spec}</code>\n"
            text += "\n"
        total_missing = sum(len(m) for _, m in all_missing)
        text += f"<b>Total missing:</b> <code>{total_missing}</code>\n"
        text += "<i>Use <code>.lm</code> to reinstall a module with dependency check</i>"
        await msg.edit(text, parse_mode='HTML')
        return
    name = args[1].strip()
    
    # Проверяем MCUB модуль
    mcub_file = MCUB_MODS_DIR / f"{name}.py"
    if mcub_file.exists():
        try:
            code = mcub_file.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            return await edit_or_reply(event, f"<b>❌ Error reading file:</b> <code>{e}</code>", parse_mode='HTML')
        deps = extract_dependencies(code)
        if not deps:
            return await edit_or_reply(
                event,
                f"<b>🧩 MCUB {name}</b>\n\n<i>No dependencies declared</i>",
                parse_mode='HTML'
            )
        missing = get_missing_dependencies(deps)
        if not missing:
            return await edit_or_reply(
                event,
                f"<b>🧩 MCUB {name}</b>\n\n<b>✅ All {len(deps)} dependencies are installed!</b>\n\n"
                + format_deps(deps, show_status=True),
                parse_mode='HTML'
            )
        install_confirmed = await ask_install_deps(event, missing, name)
        if install_confirmed:
            msg = await edit_or_reply(event, f"<b>📦 Installing {len(missing)} dependencies...</b>", parse_mode='HTML')
            dep_specs = [spec for spec, _ in missing]
            all_ok, errors = await install_deps(dep_specs, msg)
            if all_ok:
                await msg.edit(
                    f"<b>✅ All dependencies for</b> <code>{name}</code> <b>installed!</b>",
                    parse_mode='HTML'
                )
            else:
                error_text = "\n".join(errors[:5])
                if len(errors) > 5:
                    error_text += f"\n...and {len(errors) - 5} more"
                await msg.edit(
                    f"<b>⚠️ Some dependencies failed:</b>\n{error_text}",
                    parse_mode='HTML'
                )
        else:
            await edit_or_reply(
                event,
                f"<b>🧩 MCUB {name}</b>\n\n<b>❌ Installation skipped</b>\n\n"
                + format_deps(deps, show_status=True),
                parse_mode='HTML'
            )
        return
    
    # Обычный модуль
    module_dir = Path('modules') / name
    py_file = module_dir / (name + ".py")
    if not py_file.exists():
        return await edit_or_reply(
            event,
            f"<b>❌ Module</b> <code>{name}</code> <b>not found or has no .py file</b>",
            parse_mode='HTML'
        )
    try:
        code = py_file.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        return await edit_or_reply(event, f"<b>❌ Error reading file:</b> <code>{e}</code>", parse_mode='HTML')
    deps = extract_dependencies(code)
    if not deps:
        return await edit_or_reply(
            event,
            f"<b>📦 {name}</b>\n\n<i>No dependencies declared in module</i>",
            parse_mode='HTML'
        )
    missing = get_missing_dependencies(deps)
    if not missing:
        return await edit_or_reply(
            event,
            f"<b>📦 {name}</b>\n\n<b>✅ All {len(deps)} dependencies are installed!</b>\n\n"
            + format_deps(deps, show_status=True),
            parse_mode='HTML'
        )
    install_confirmed = await ask_install_deps(event, missing, name)
    if install_confirmed:
        msg = await edit_or_reply(event, f"<b>📦 Installing {len(missing)} dependencies...</b>", parse_mode='HTML')
        dep_specs = [spec for spec, _ in missing]
        all_ok, errors = await install_deps(dep_specs, msg)
        if all_ok:
            await msg.edit(
                f"<b>✅ All dependencies for</b> <code>{name}</code> <b>installed!</b>",
                parse_mode='HTML'
            )
        else:
            error_text = "\n".join(errors[:5])
            if len(errors) > 5:
                error_text += f"\n...and {len(errors) - 5} more"
            await msg.edit(
                f"<b>⚠️ Some dependencies failed:</b>\n{error_text}",
                parse_mode='HTML'
            )
    else:
        await edit_or_reply(
            event,
            f"<b>📦 {name}</b>\n\n<b>❌ Installation skipped</b>\n\n"
            + format_deps(deps, show_status=True),
            parse_mode='HTML'
        )

async def mcubmods_handler(event):
    """Show MCUB modules only."""
    if not event.out:
        return
    if not MCUB_AVAILABLE:
        return await edit_or_reply(event, "❌ MCUB Engine not installed", parse_mode='HTML')
    
    loader = get_mcub_loader()
    if not loader:
        return await edit_or_reply(event, "❌ MCUB Loader not available", parse_mode='HTML')
    
    mods = loader.list_modules()
    if not mods:
        return await edit_or_reply(
            event,
            "<b>🧩 No MCUB modules loaded</b>\n"
            "<i>Install with .lm (MCUB Core) or .mload</i>",
            parse_mode='HTML'
        )
    
    lines = [f"<b>🧩 MCUB MODULES ({len(mods)})</b>\n"]
    for name, mtype, ncmds, meta in mods:
        ver = f" v{meta['version']}" if meta.get('version') else ""
        author = f" by {meta['author']}" if meta.get('author') else ""
        lines.append(
            f"▪️ <code>{name}</code>{ver}{author} "
            f"[{mtype}] — {ncmds} cmds"
        )
    lines.append("\n<i>.mhelp &lt;name&gt; — commands</i>")
    await edit_or_reply(event, "\n".join(lines), parse_mode='HTML')

# ============================================
# SETUP
# ============================================

def setup(client):
    """Register handlers with exact command boundaries.

    A bare ``\\.compile`` also matches ``.compileall`` in Telethon, which
    used to run both handlers for the latter command.  Keep setup-style native
    modules on the same exact-command routing contract as Hydra's adapters.
    """
    def command_pattern(name: str) -> str:
        return rf"(?i)^\.{name}(?:\s|$)"

    client.add_event_handler(lm_handler, events.NewMessage(pattern=command_pattern("lm"), outgoing=True))
    client.add_event_handler(unlm_handler, events.NewMessage(pattern=command_pattern("unlm"), outgoing=True))
    client.add_event_handler(hmods_handler, events.NewMessage(pattern=command_pattern("hmods"), outgoing=True))
    client.add_event_handler(compile_handler, events.NewMessage(pattern=command_pattern("compile"), outgoing=True))
    client.add_event_handler(compileall_handler, events.NewMessage(pattern=command_pattern("compileall"), outgoing=True))
    client.add_event_handler(modinfo_handler, events.NewMessage(pattern=command_pattern("modinfo"), outgoing=True))
    client.add_event_handler(deps_handler, events.NewMessage(pattern=command_pattern("deps"), outgoing=True))
    client.add_event_handler(mcubmods_handler, events.NewMessage(pattern=command_pattern("mcubmods"), outgoing=True))

modules_help = {
    "module_loader": {
        "lm": "Install module (auto-adapt + MCUB support)",
        "unlm <name>": "Remove module (including MCUB)",
        "hmods": "List ALL modules (Hydra + MCUB)",
        "mcubmods": "List only MCUB modules",
        "compile <name>": "Compile to .so (Cython)",
        "compileall": "Compile ALL modules",
        "modinfo <name>": "Module info + dependencies",
        "deps <name>": "Check/install dependencies for module",
        "deps --all": "Check all modules for missing deps"
    }
}


