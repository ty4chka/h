# meta: name=adapter version=1.0.0 author=hydra-team framework=noop
"""
🔄 Универсальный адаптер модулей для Hydra UserBot
"""

import re
import ast
import logging
import sys as _sys
import types as _types

logger = logging.getLogger(__name__)


def detect_module_type(code: str) -> str:
    if re.search(r'core\.lib\.loader|class\s+\w+\s*\(\s*ModuleBase\s*\)|def\s+register\s*\(\s*kernel\s*\)', code):
        return "mcub_core"
    if re.search(r'class\s+\w+\s*\(\s*dragon\.Module\s*\)|@dragon\.command|from\s+dragon\s+import', code):
        return "dragon"
    if re.search(r'class\s+\w+\s*\(\s*loader\.Module\s*\)|@loader\.tds|@loader\.command', code):
        if 'hikkatl' in code or 'hikka' in code.lower():
            return "hikka"
        return "heroku"
    if re.search(r'from\s+pyrogram|import\s+pyrogram|@Client\.on_message', code):
        return "mcub"
    if 'modules_help' in code and re.search(r'async def \w+_handler\s*\(', code):
        return "hydra"
    return "unknown"


def adapt_hikka(code: str, module_name: str) -> tuple:
    original, adapted = code, code
    replacements = [
        (r'from hikkatl\.types import Message', 'from telethon.tl.types import Message'),
        (r'from hikkatl\.tl\.types import Message', 'from telethon.tl.types import Message'),
        (r'from hikkatl\.errors', 'from telethon.errors'),
        (r'from hikkatl\.tl\.functions', 'from telethon.tl.functions'),
        (r'from hikkatl import', 'from telethon import'),
        (r'from herokutl import', 'from telethon import'),
        (r'from herokutl\.', 'from telethon.'),
        (r'from \.+ import loader', '# loader removed'),
        (r'from \.+ import utils', 'from utils.misc import edit_or_reply'),
        (r'from \.+\.inline import', '# inline removed'),
    ]
    for p, r in replacements:
        adapted = re.sub(p, r, adapted)

    adapted = re.sub(r'@loader\.tds\s*\n', '', adapted)
    commands = re.findall(r'@loader\.command\([^)]*\)\s*\n\s*async def (\w+)', adapted)
    adapted = re.sub(r'@loader\.command\([^)]*\)\s*\n', '', adapted)
    adapted = re.sub(r'@loader\.command\s*\n', '', adapted)
    adapted = re.sub(r'@loader\.watcher\([^)]*\)\s*\n', '# removed watcher\n', adapted)

    class_match = re.search(r'class (\w+)\(loader\.Module\):', adapted)
    if class_match:
        adapted = re.sub(r'class \w+\(loader\.Module\):\s*\n', '', adapted)
        adapted = re.sub(r'async def (\w+)\(self,\s*\w+\)', r'async def \1_handler(event)', adapted)
        adapted = re.sub(r'self\.strings\(["\']([^"\']+)["\']\)', r'"\1"', adapted)
        adapted = re.sub(r'await utils\.answer\(message,', 'await edit_or_reply(event,', adapted)
        adapted = re.sub(r'\bmessage\b', 'event', adapted)
        adapted = re.sub(r'self\._client', 'event.client', adapted)
        adapted = re.sub(r'self\._me', 'await event.client.get_me()', adapted)
        adapted = re.sub(r'self\.', '', adapted)

    if 'from utils.misc import' not in adapted:
        adapted = 'from utils.misc import edit_or_reply, rate_limit\n' + adapted

    if 'modules_help' not in adapted and commands:
        help_dict = {cmd: f"Command {cmd}" for cmd in commands}
        help_str = str(help_dict).replace("'", '"')
        adapted += f'\n\nmodules_help = {{\n    "{module_name}": {help_str}\n}}\n'

    return adapted, "hikka", adapted != original


def _ensure_core_inline():
    if 'core_inline' not in _sys.modules:
        _sys.modules['core_inline'] = _types.ModuleType('core_inline')
        _sys.modules['core_inline.api'] = _types.ModuleType('core_inline.api')
        _sys.modules['core_inline.api.inline'] = _types.ModuleType('core_inline.api.inline')
        _sys.modules['core_inline.api.inline'].make_cb_button = lambda *a, **kw: type('Btn', (), {'text':'', 'data':''})()

_CORE_INLINE_MOCK = '''
import sys as _core_inline_sys
import types as _core_inline_types
if "core_inline" not in _core_inline_sys.modules:
    _core_inline_sys.modules["core_inline"] = _core_inline_types.ModuleType("core_inline")
    _core_inline_sys.modules["core_inline.api"] = _core_inline_types.ModuleType("core_inline.api")
    _core_inline_sys.modules["core_inline.api.inline"] = _core_inline_types.ModuleType("core_inline.api.inline")
    _core_inline_sys.modules["core_inline.api.inline"].make_cb_button = lambda *a, **kw: type("Btn", (), {"text":"", "data":""})()
'''


def _safe_edit_patch_code():
    return [
        "def _safe_edit_patch(event):",
        "    orig_edit = getattr(event, 'edit', None)",
        "    if not orig_edit: return",
        "    async def safe_edit(*args, **kwargs):",
        "        try: return await orig_edit(*args, **kwargs)",
        "        except Exception as e:",
        "            if 'not modified' not in str(e).lower(): raise e",
        "    event.edit = safe_edit",
        "",
    ]


def _inline_mock_code():
    return [
        "class _ArticleMock:",
        "    def __init__(self, title, description='', text='', **kw):",
        "        self.title = title; self.description = description; self.text = text",
        "class _BuilderMock:",
        "    def article(self, title, description='', text='', **kw): return _ArticleMock(title, description, text, **kw)",
        "class _InlineEventMock:",
        "    def __init__(self, orig, query_name=''):",
        "        self.original_event = orig; self.builder = _BuilderMock()",
        "        parts = getattr(orig, 'text', '').split(maxsplit=1)",
        "        self.text = f'{query_name} {parts[1]}' if len(parts) > 1 and query_name else getattr(orig, 'text', '')",
        "    async def answer(self, articles, **kw):",
        "        if not articles: return",
        "        out = '🤖 <b>Результаты (инлайн):</b>\\n\\n'",
        "        for art in articles[:5]:",
        "            out += f'▪️ <b>{art.title}</b>\\n'",
        "            if art.description: out += f'<i>{art.description}</i>\\n'",
        "            out += f'📄 {art.text.replace(chr(8288), \"\")}\\n\\n'",
        "        await self.original_event.edit(out, parse_mode='html')",
        "",
    ]


def adapt_mcub_core(code: str, module_name: str) -> tuple:
    _ensure_core_inline()

    header = [
        "\n# ============================================",
        "# NATIVE MCUB BRIDGE (AUTO-GENERATED BY HYDRA)",
        "# ============================================",
        _CORE_INLINE_MOCK,
        "import sys as _hydra_sys",
        "import types as _hydra_types",
        "",
    ]
    header.extend(_safe_edit_patch_code())

    # --- 1. ФУНКЦИОНАЛЬНЫЙ СТИЛЬ (fheta, gemini, dnd, sourcetrigger, last-fm) ---
    if re.search(r'def\s+register\s*\(\s*kernel\s*\)\s*:', code):
        header.extend(_functional_bootstrapper(code, module_name))
        return code + "\n" + "\n".join(header), "mcub_core", True

    # --- 2. ООП СТИЛЬ (yamusic, sourcetrigger-oop) ---
    class_match = re.search(r'class\s+(\w+)\s*\(ModuleBase\):', code)
    if not class_match:
        return code, "mcub_core", False
    classname = class_match.group(1)
    header.extend(_oop_bootstrapper(code, classname, module_name))
    return code + "\n" + "\n".join(header), "mcub_core", True


def _functional_bootstrapper(code: str, module_name: str) -> list:
    parts = []

    parts.extend([
        "_fheta_help = {}",
        "_fheta_inline_handlers = {}",
        "_fheta_callback_handlers = {}",
        "",
    ])

    parts.extend([
        "class _KernelRegister:",
        "    def command(self, name, *args, **kwargs):",
        "        def dec(func):",
        "            async def wrapper(event):",
        "                _safe_edit_patch(event)",
        "                if not _kernel_inst.client: ",
        "                    pass",
        "                await func(event)",
        "            globals()[f'{name}_handler'] = wrapper",
        "            _fheta_help[name] = getattr(func, '__doc__', None) or f'Команда {name}'",
        "            return func",
        "        return dec",
        "",
        "    def watcher(self, *args, **kwargs):",
        "        def dec(func):",
        "            async def wrapper(event):",
        "                _safe_edit_patch(event)",
        "                await func(event)",
        "            _fheta_watchers.append(wrapper)",
        "            return func",
        "        return dec",
        "",
        "_fheta_watchers = []",
        "",
    ])

    parts.extend([
        "class _FunctionalKernel:",
        "    def __init__(self):",
        "        self.register = _KernelRegister()",
        "        self.custom_prefix = '.'",
        "        self._inline_handlers = {}",
        "        self._callback_handlers = {}",
        "        import logging",
        "        self.logger = logging.getLogger('mcub_fheta')",
        "        self.config = {}",
        "        self.parent_module = None",
        "        self._inline_bot_username = None",
        "",
        "    @property",
        "    def client(self):",
        "        if self.parent_module and getattr(self.parent_module, 'client', None):",
        "            return self.parent_module.client",
        "        from core.lib.loader.module_base import KernelMock",
        "        return KernelMock(self.parent_module or self).client",
        "",
        "    def register_command(self, name, handler, aliases=None, description='', outgoing_only=True):",
        "        async def wrapper(event):",
        "            _safe_edit_patch(event)",
        "            if not _kernel_inst.client: pass",
        "            await handler(event)",
        "        globals()[f'{name}_handler'] = wrapper",
        "        _fheta_help[name] = getattr(handler, '__doc__', None) or f'Команда {name}'",
        "        return handler",
        "",
        "    def register_watcher(self, handler, incoming_only=True, outgoing_only=False, pattern=None, chats=None):",
        "        async def wrapper(event):",
        "            _safe_edit_patch(event)",
        "            await handler(event)",
        "        _fheta_watchers.append(wrapper)",
        "        return handler",
        "",
        "    async def get_module_config(self, name, default=None):",
        "        from pathlib import Path; import json",
        "        p = Path('data/module_configs.json')",
        "        if p.exists():",
        "            try:",
        "                with open(p, 'r', encoding='utf-8') as f: return json.load(f).get(name, default or {})",
        "            except: pass",
        "        return default or {}",
        "",
        "    def store_module_config_schema(self, *a, **kw): pass",
        "",
        "    async def save_module_config(self, name, cfg_dict):",
        "        from pathlib import Path; import json",
        "        p = Path('data/module_configs.json')",
        "        p.parent.mkdir(parents=True, exist_ok=True)",
        "        all_cfg = {}",
        "        if p.exists():",
        "            try:",
        "                with open(p, 'r', encoding='utf-8') as f: all_cfg = json.load(f)",
        "            except: pass",
        "        all_cfg[name] = cfg_dict",
        "        with open(p, 'w', encoding='utf-8') as f: json.dump(all_cfg, f, ensure_ascii=False, indent=2)",
        "",
        "    async def db_get(self, *a, **kw): return None",
        "    async def db_set(self, *a, **kw): pass",
        "    def is_bot_available(self):",
        "        return self._inline_bot_username is not None",
        "    async def install_from_url(self, url): return False, 'Используйте .lm'",
        "    async def handle_error(self, exc, *a, **kw): pass",
        "    def is_admin(self, user_id): return True",
        "    def cprint(self, *a, **kw): pass",
        "    def log_error(self, *a, **kw): pass",
        "    def log_warning(self, *a, **kw): pass",
        "    def log_debug(self, *a, **kw): pass",
        "",
        "    def register_inline_handler(self, name, func):",
        "        self._inline_handlers[name] = func",
        "        async def wrapper(event):",
        "            _safe_edit_patch(event)",
        "            await func(event)",
        "        globals()[f'i_{name}_handler'] = wrapper",
        "        _fheta_help[f'i_{name}'] = f'Инлайн поиск {name}'",
        "",
        "    def register_callback_handler(self, prefix, func):",
        "        self._callback_handlers[prefix] = func",
        "",
        "    async def inline_query_and_click(self, chat_id, query, *a, **kw):",
        "        parts = query.split(maxsplit=1)",
        "        name = parts[0] if parts else ''",
        "        if name in self._inline_handlers:",
        "            class _MockEv:",
        "                def __init__(self, q):",
        "                    self.text = q",
        "                    class _BM:",
        "                        def article(self, t, d='', txt='', **k): return type('A', (), {'title':t, 'description':d, 'text':txt})()",
        "                    self.builder = _BM()",
        "                async def answer(self, articles, **kw):",
        "                    if not articles: return",
        "                    out = '🤖 <b>Результаты:</b>\\n\\n'",
        "                    for art in articles[:5]:",
        "                        out += f'▪️ <b>{art.title}</b>\\n'",
        "                        if art.description: out += f'<i>{art.description}</i>\\n'",
        "                        out += f'📄 {art.text.replace(chr(8288), \"\")}\\n\\n'",
        "                    await _kernel_inst.client.send_message(chat_id, out, parse_mode='html', disable_web_page_preview=True)",
        "            await self._inline_handlers[name](_MockEv(query))",
        "            return True, None",
        "        return False, None",
        "",
        "    async def inline_form(self, chat_id, text, buttons=None, **kw):",
        "        try:",
        "            await _kernel_inst.client.send_message(chat_id, text, parse_mode='html')",
        "            return True, None",
        "        except Exception as e:",
        "            return False, str(e)",
        "",
        "    async def conversation(self, *a, **kw):",
        "        class _ConvMock:",
        "            async def __aenter__(self): return self",
        "            async def __aexit__(self, *a): pass",
        "            async def send_message(self, *a, **kw): pass",
        "            async def get_response(self, timeout=5):",
        "                class _Resp: text = ''",
        "                return _Resp()",
        "        return _ConvMock()",
        "",
    ])

    parts.extend([
        "_kernel_inst = _FunctionalKernel()",
        "_kernel_inst._live_module_configs = {}",
        "from core.lib.loader.module_base import ModuleBase",
        "class _FakeParent(ModuleBase): pass",
        "_kernel_inst.parent_module = _FakeParent()",
        "",
        "# --- Register the module ---",
        "register(_kernel_inst)",
        "",
    ])

    if _fheta_has_watchers(code):
        parts.extend([
            "def setup(client):",
            "    from telethon import events as _ev",
            "    for _wh in _fheta_watchers:",
            "        async def _ww(event, _h=_wh):",
            "            _safe_edit_patch(event)",
            "            await _h(event)",
            "        client.add_event_handler(_ww, _ev.NewMessage())",
            "        client.add_event_handler(_ww, _ev.MessageEdited())",
            "",
        ])

    parts.append(f"modules_help = {{ '{module_name}': _fheta_help }}")
    return parts


def _fheta_has_watchers(code: str) -> bool:
    return bool(re.search(r'@kernel\.register\.watcher|\.watcher\(', code))


def _oop_bootstrapper(code: str, classname: str, module_name: str) -> list:
    parts = []

    commands, inlines, watchers = [], [], []
    for c in re.findall(r'@command\s*\(\s*[\'"]([^\'"]+)[\'"]', code):
        f_match = re.search(rf'@command\s*\(\s*[\'"]{c}[\'"].*?\n\s*async def (\w+)', code, re.DOTALL)
        if f_match:
            commands.append((c, f_match.group(1)))
    for c in re.findall(r'@inline\s*\(\s*[\'"]([^\'"]+)[\'"]', code):
        f_match = re.search(rf'@inline\s*\(\s*[\'"]{c}[\'"].*?\n\s*async def (\w+)', code, re.DOTALL)
        if f_match:
            inlines.append((c, f_match.group(1)))
    for w in re.findall(r'@watcher\s*\([^)]*\)\s*\n\s*async def (\w+)', code):
        watchers.append(w)

    parts.append(f"_mcub_inst = {classname}()")
    parts.append("_mcub_inst._live_module_configs = {}")
    help_dict = {}

    init_lines = [
        "    _safe_edit_patch(event)",
        "    if not getattr(_mcub_inst, 'client', None):",
        "        _mcub_inst._hydra_client_cache = getattr(event, 'client', None)",
        "        _mcub_inst.client = getattr(event, 'client', None)",
        "        try:",
        "            if hasattr(_mcub_inst, 'on_load'): await _mcub_inst.on_load()",
        "        except Exception as _e:",
        "            import logging",
        "            logging.getLogger('mcub_oop').error(f'on_load error: {_e}')",
    ]

    for cmd_name, method_name in commands:
        help_dict[cmd_name] = f"Команда {cmd_name}"
        parts.append(f"async def {cmd_name}_handler(event):")
        parts.extend(init_lines)
        parts.append(f"    await _mcub_inst.{method_name}(event)\n")

    for icmd, method_name in inlines:
        cmd_name = f"i_{icmd}"
        help_dict[cmd_name] = f"Инлайн {icmd}"
        parts.extend(_inline_mock_code())
        parts.extend([
            f"async def {cmd_name}_handler(event):",
            *init_lines,
            f"    mock_ev = _InlineEventMock(event, '{icmd}')",
            f"    try: await _mcub_inst.{method_name}(mock_ev)",
            "    except Exception as e:",
            "        if 'not modified' not in str(e).lower(): await event.edit(f'❌ Ошибка: {e}')",
            "",
        ])

    if watchers:
        parts.extend(["def setup(client):", "    from telethon import events"])
        for w in watchers:
            parts.extend([
                f"    async def {w}_wrapper(event):",
                f"        if not getattr(_mcub_inst, 'client', None): return",
                f"        await _mcub_inst.{w}(event)",
                f"    client.add_event_handler({w}_wrapper, events.NewMessage())",
                f"    client.add_event_handler({w}_wrapper, events.MessageEdited())",
            ])

    help_str = str(help_dict).replace("'", '"') if help_dict else "{'info': 'Модуль работает в фоне (watchers)'}"
    parts.append(f"\nmodules_help = {{ '{module_name}': {help_str} }}")
    return parts


def adapt_mcub(code: str, module_name: str) -> tuple:
    original, adapted = code, code
    replacements = [
        (r'from pyrogram import Client, filters, enums', 'from telethon import events'),
        (r'from pyrogram import Client, filters', 'from telethon import events'),
        (r'from pyrogram import filters', ''),
        (r'from pyrogram.types import Message', 'from telethon.tl.types import Message'),
        (r'from utils import modules_help, prefix', 'from utils.misc import edit_or_reply'),
    ]
    for p, r in replacements:
        adapted = re.sub(p, r, adapted)
    adapted = re.sub(
        r'@Client\.on_message\(filters\.command\(.*?\)\)\s*\n\s*async def (\w+)',
        r'async def \1_handler(event):',
        adapted,
    )
    if 'from utils.misc import' not in adapted:
        adapted = 'from utils.misc import edit_or_reply, rate_limit\n' + adapted
    return adapted, "mcub", adapted != original


def adapt_module(code: str, module_name: str) -> tuple:
    t = detect_module_type(code)
    if t == "hydra":
        return code, "hydra", False
    if t == "hikka":
        return adapt_hikka(code, module_name)
    if t == "heroku":
        return adapt_hikka(code, module_name)
    if t == "mcub_core":
        return adapt_mcub_core(code, module_name)
    if t == "mcub":
        return adapt_mcub(code, module_name)
    if t == "dragon":
        return adapt_hikka(code, module_name)
    return code, "unknown", False


def post_process(code: str, module_type: str = "unknown") -> str:
    code = re.sub(r'\n\n\n+', '\n\n', code)
    if module_type in ("hikka", "heroku", "dragon"):
        if "core.lib.loader" not in code and "ModuleBase" not in code and "def register(kernel" not in code:
            code = re.sub(r'self\.(?!(client|db|inline|me|get_prefix|invoke|lookup|request_join))', '', code)
    try:
        ast.parse(code)
    except SyntaxError as e:
        lines = code.split('\n')
        insert_idx = 0
        for i, line in enumerate(lines):
            sline = line.strip()
            if sline.startswith(('from __future__', '"""', "'''", '#')):
                continue
            insert_idx = i
            break
        lines.insert(insert_idx, f"# ⚠️ Syntax check failed: {e}")
        code = '\n'.join(lines)
    return code


def inline_to_commands(code: str, module_name: str) -> str:
    if "Button.inline" not in code and "make_cb_button" not in code:
        return code

    callback_pattern = re.compile(
        r'(?:Button\.inline|make_cb_button)\s*\(\s*["\']([^"\']+)["\']\s*,\s*(?:f["\']([^\']+)["\']|([a-zA-Z_]\w*))',
        re.DOTALL,
    )

    handlers = {}
    for match in callback_pattern.finditer(code):
        btn_text = match.group(1)
        if match.group(2):
            prefix = match.group(2).split("_")[0] if "_" in match.group(2) else match.group(2)
        elif match.group(3):
            func_name = match.group(3)
            prefix = func_name.replace("_handler", "").replace("_callback", "")
        else:
            continue
        if prefix and len(prefix) <= 20:
            handlers[prefix] = btn_text

    if not handlers:
        return code

    lines = code.split('\n')
    insert_idx = len(lines)
    for i, line in enumerate(lines):
        sline = line.strip()
        if sline.startswith('modules_help'):
            insert_idx = i
            break

    new_handlers = []
    new_handlers.append("")
    new_handlers.append("# ============================================")
    new_handlers.append("# INLINE -> COMMAND BRIDGE (AUTO-GENERATED)")
    new_handlers.append("# ============================================")

    for prefix, btn_text in handlers.items():
        cmd_name = prefix.lower().replace(" ", "_")
        new_handlers.append(f"async def {cmd_name}_cmd_handler(event):")
        new_handlers.append(f'    """Команда .{cmd_name} (замена инлайн кнопки "{btn_text}")"""')
        new_handlers.append(f"    await event.edit('⚙️ Действие: {btn_text}')")
        new_handlers.append("")

    # Find the modules_help dict and add entries before the closing }
    for i, line in enumerate(lines):
        if 'modules_help' in line and '{' in line:
            # Find the closing brace of this dict
            brace_count = 0
            found_open = False
            close_idx = i
            for j in range(i, len(lines)):
                for ch in lines[j]:
                    if ch == '{':
                        brace_count += 1
                        found_open = True
                    elif ch == '}':
                        brace_count -= 1
                        if found_open and brace_count == 0:
                            close_idx = j
                            break
                if found_open and brace_count == 0:
                    break

            # Insert new entries before the closing brace
            insert_lines = []
            for prefix, btn_text in handlers.items():
                cmd_name = prefix.lower().replace(" ", "_")
                insert_lines.append(f'    "{cmd_name}": "{btn_text} (команда)"')

            # Insert before the line with closing brace
            for entry in reversed(insert_lines):
                lines.insert(close_idx, entry)
            break

    for i, line in enumerate(lines):
        if line.strip().startswith('modules_help'):
            new_handlers.insert(0, "")
            for j, hline in enumerate(new_handlers):
                lines.insert(i + j, hline)
            break

    return '\n'.join(lines)
