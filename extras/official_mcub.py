# modules/mcub.py
"""
🧩 MCUB Engine — полноценная поддержка модулей MCUB-fork в Hydra.

- Загружает модули MCUB (class-style и register(kernel)) БЕЗ изменений кода
- Все инлайн-кнопки превращаются в команды: .cb N (показаны прямо в сообщении)
- Инлайн-поиск: .iq <запрос> | ввод для кнопок: .it <id> <текст>

Команды:
  .mload (reply на .py / текст / URL) — установить MCUB-модуль
  .mun <name> — выгрузить модуль
  .mls — список MCUB-модулей
  .mhelp [name] — команды модуля + помощь по кнопкам
  .mcfg <name> [key] [value] — конфиг модуля
  .cb [N] — нажать кнопку N / показать меню
"""

import asyncio
import html
import logging
import re
import json

import aiohttp
from telethon import events

from utils.misc import edit_or_reply

logger = logging.getLogger("mcub.mod")

_KERNEL = None
_LOADER = None
_AUTOLOAD_STARTED = False
_CLIENT = None


# ============================================================
# ИНИЦИАЛИЗАЦИЯ MCUB ENGINE
# ============================================================

def _init_engine(client):
    """Инициализировать MCUB Engine"""
    global _KERNEL, _LOADER, _CLIENT
    
    if _KERNEL is not None:
        return _KERNEL
    
    _CLIENT = client
    
    try:
        from mcub_engine import install, get_kernel
        import mcub_engine as _mcub_engine_pkg
        from mcub_engine.loader import get_loader, set_loader_kernel
        
        # Получаем префикс
        prefix = "."
        try:
            import config
            prefix = getattr(config, "prefix", ".") or "."
        except Exception:
            pass
        
        # ВАЖНО: не создаём новое ядро, если оно уже было создано раньше
        # (например, boot_hydra() в main_tabbed.py уже вызвал install()).
        # Иначе получаем два независимых кернела с двумя диспетчерами —
        # отсюда были задвоенные ответы на .mls/.mhelp и т.п.
        existing = getattr(_mcub_engine_pkg, "_kernel", None)
        _KERNEL = existing if existing is not None else install(client, prefix)

        set_loader_kernel(_KERNEL)
        _LOADER = get_loader()

        # man.py и другие модули ожидают self.kernel._loader — но нигде
        # в движке это не назначается на сам объект ядра. Фиксим явно.
        try:
            _KERNEL._loader = _LOADER
        except Exception:
            pass
        
        if _KERNEL:
            logger.info(f"MCUB Engine initialized (prefix={prefix})")
            print(f"    🧩 MCUB Engine initialized (prefix={prefix})")
        else:
            logger.error("MCUB Engine initialization FAILED")
            print("    ❌ MCUB Engine initialization FAILED")
            
    except Exception as e:
        logger.error(f"MCUB Engine init error: {e}", exc_info=True)
        print(f"    ❌ MCUB Engine init error: {e}")
    
    return _KERNEL


def _engine():
    """Получить ядро и загрузчик"""
    global _KERNEL, _LOADER
    if _KERNEL is None:
        _init_engine(_CLIENT)
    return _KERNEL, _LOADER


async def _autoload():
    """Автозагрузка всех MCUB-модулей при старте."""
    global _AUTOLOAD_STARTED
    if _AUTOLOAD_STARTED:
        return
    _AUTOLOAD_STARTED = True
    
    await asyncio.sleep(1)  # дать Hydra догрузиться
    
    try:
        kernel, loader = _engine()
        if kernel is None or loader is None:
            logger.error("MCUB Engine not available for autoload")
            return
            
        await kernel.get_me_cached()
        results = await loader.autoload_all()
        ok_count = sum(1 for _, ok, _ in results if ok)
        if results:
            logger.info(f"MCUB autoload: {ok_count}/{len(results)} OK")
            print(f"    🧩 MCUB autoload: {ok_count}/{len(results)} modules loaded")
    except Exception as e:
        logger.error(f"MCUB autoload failed: {e}", exc_info=True)


# ============================================================
# ГЛАВНЫЙ ДИСПЕТЧЕР КОМАНД MCUB
# ============================================================

async def _mcub_dispatcher(event):
    """Единая точка входа: .cb/.it/.iq + все команды MCUB-модулей."""
    print(f"[MCUB DEBUG] dispatcher fired, out={event.out}")
    if not event.out:
        return
    text = event.raw_text or ""
    print(f"[MCUB DEBUG] text={text!r}")
    if not text:
        return
    
    kernel, loader = _engine()
    print(f"[MCUB DEBUG] kernel={kernel!r} id={id(kernel) if kernel else None}")
    if kernel is None:
        return
        
    prefix = kernel.custom_prefix
    print(f"[MCUB DEBUG] prefix={prefix!r} startswith={text.startswith(prefix)}")
    if not text.startswith(prefix):
        return

    body = text[len(prefix):]
    parts = body.split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    args_str = parts[1] if len(parts) > 1 else ""
    print(f"[MCUB DEBUG] cmd={cmd!r} args={args_str!r}")

    # ---- команды моста кнопок ----
    if cmd == "cb" or cmd == "кн":
        try:
            await event.delete()
        except Exception:
            pass
        if args_str.strip().isdigit():
            await kernel.bridge.handle_cb(event, int(args_str.strip()))
        else:
            await kernel.bridge.show_menu(event)
        return

    if cmd == "it":
        sub = args_str.split(maxsplit=1)
        if sub:
            short = sub[0]
            payload = sub[1] if len(sub) > 1 else ""
            try:
                await event.delete()
            except Exception:
                pass
            await kernel.bridge.handle_it(event, short, payload)
        return

    if cmd == "iq":
        if not args_str.strip():
            await edit_or_reply(
                event,
                f"<b>Использование:</b> <code>{prefix}iq &lt;модуль&gt; [запрос]</code>\n"
                f"<i>Например: {prefix}iq man</i>",
                parse_mode="HTML",
            )
            return
        await kernel.bridge.handle_iq(event, args_str)
        return

    # ---- команды MCUB-модулей ----
    if not hasattr(kernel, 'command_handlers'):
        return
        
    target = kernel.command_handlers.get(cmd)
    if target is None:
        if hasattr(kernel, 'aliases'):
            target = kernel.command_handlers.get(kernel.aliases.get(cmd, ""), None)
    if target is None:
        return  # не наша команда — пусть обработает Hydra

    print(f"[MCUB DEBUG] target found: {target!r}")
    from mcub_engine.proxies import EventProxy
    proxy = EventProxy(event, kernel)
    try:
        if hasattr(kernel, 'middleware_chain') and kernel.middleware_chain:
            await kernel.process_with_middleware(proxy, target)
        else:
            await target(proxy)
        print("[MCUB DEBUG] target executed OK")
    except Exception as e:
        import traceback
        print(f"[MCUB DEBUG] EXCEPTION in target: {e!r}")
        traceback.print_exc()
        logger.error(f"MCUB command '{cmd}' error: {e}", exc_info=True)
        if hasattr(kernel, 'handle_error'):
            await kernel.handle_error(e, source=f"команда {prefix}{cmd}", event=proxy)


# ============================================================
# КОМАНДЫ УПРАВЛЕНИЯ
# ============================================================

# ============================================================
# URL NORMALIZATION
# ============================================================

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

async def mload_handler(event):
    """.mload — установить MCUB-модуль (reply на файл/текст или URL)."""
    if not event.out:
        return
    
    kernel, loader = _engine()
    if kernel is None or loader is None:
        return await edit_or_reply(event, "❌ MCUB Engine не инициализирован", parse_mode="HTML")
    
    msg = await edit_or_reply(event, "<b>🔍 Анализ модуля...</b>", parse_mode="HTML")

    code = None
    src = ""
    name = None

    args = event.text.split(maxsplit=1)
    reply = await event.get_reply_message()

    if len(args) > 1:
        url = _normalize_url(args[1].strip())
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url) as r:
                    code = await r.text(encoding="utf-8", errors="ignore")
            src = "URL"
            name = url.split("/")[-1].replace(".py", "")
        except Exception as e:
            return await msg.edit(f"<b>❌ Ошибка загрузки:</b> <code>{e}</code>",
                                  parse_mode="HTML")
    elif reply and reply.document:
        path = await reply.download_media()
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                code = f.read()
        finally:
            import os
            try:
                os.remove(path)
            except Exception:
                pass
        src = "File"
        attr = reply.document.attributes
        if attr:
            name = getattr(attr[0], "file_name", "mod").replace(".py", "")
    elif reply and reply.text:
        code = reply.text
        src = "Text"
    else:
        return await msg.edit(
            "<b>Использование:</b>\n"
            "• reply на .py файл + <code>.mload</code>\n"
            "• <code>.mload &lt;URL&gt;</code>\n"
            "• reply на сообщение с кодом + <code>.mload</code>",
            parse_mode="HTML",
        )

    if not code or len(code) < 10:
        return await msg.edit("<b>❌ Пустой код</b>", parse_mode="HTML")

    if not loader.is_mcub_code(code):
        return await msg.edit(
            "<b>⚠️ Это не MCUB-модуль</b> (нет core.lib.loader / ModuleBase / register(kernel))\n"
            "<i>Используй обычный</i> <code>.lm</code>",
            parse_mode="HTML",
        )

    await msg.edit("<b>⚙️ Установка MCUB-модуля...</b>", parse_mode="HTML")
    ok, text = await loader.install_module_code(code, name)
    if ok:
        mod_name = loader.extract_name(code, name or "?")
        await msg.edit(
            f"<b>✅ {text}</b>\n\n"
            f"<i>Кнопки этого модуля показываются как команды <code>.cb N</code> —\n"
            f"список появляется под каждым меню. Инлайн-поиск: <code>.iq</code></i>",
            parse_mode="HTML",
        )
    else:
        await msg.edit(f"<b>❌ {text}</b>", parse_mode="HTML")


async def mun_handler(event):
    """.mun <name> — выгрузить MCUB-модуль."""
    if not event.out:
        return
    
    kernel, loader = _engine()
    if kernel is None or loader is None:
        return await edit_or_reply(event, "❌ MCUB Engine не инициализирован", parse_mode="HTML")
    
    args = event.text.split()
    if len(args) < 2:
        return await edit_or_reply(event, "<code>.mun &lt;name&gt;</code>",
                                   parse_mode="HTML")
    delete_file = "--del" in args
    name = args[1]
    ok, text = await loader.unload_module(name, delete_file=delete_file)
    await edit_or_reply(event, ("✅ " if ok else "❌ ") + text, parse_mode="HTML")


async def mls_handler(event):
    """.mls — список MCUB-модулей."""
    print(f"[MCUB DEBUG] mls_handler CALLED, handler_id={id(mls_handler)}, event_id={event.id}")
    if not event.out:
        return
    
    kernel, loader = _engine()
    if kernel is None or loader is None:
        return await edit_or_reply(event, "❌ MCUB Engine не инициализирован", parse_mode="HTML")
    
    mods = loader.list_modules()
    if not mods:
        return await edit_or_reply(
            event,
            "<b>Нет загруженных MCUB-модулей</b>\n"
            "<i>Установи: reply на .py + <code>.mload</code></i>",
            parse_mode="HTML",
        )
    lines = [f"<b>🧩 MCUB-модули ({len(mods)}):</b>\n"]
    for name, mtype, ncmds, meta in mods:
        ver = f" v{meta['version']}" if meta.get("version") else ""
        author = f" by {meta['author']}" if meta.get("author") else ""
        lines.append(
            f"▪️ <code>{name}</code>{html.escape(ver)}{html.escape(author)} "
            f"[{mtype}] — команд: {ncmds}"
        )
    lines.append("\n<i>.mhelp &lt;name&gt; — команды модуля</i>")
    await edit_or_reply(event, "\n".join(lines), parse_mode="HTML")


async def mhelp_handler(event):
    """.mhelp [name] — помощь по модулю или по мосту кнопок."""
    if not event.out:
        return

    kernel, loader = _engine()
    if kernel is None or loader is None:
        return await edit_or_reply(event, "❌ MCUB Engine не инициализирован", parse_mode="HTML")

    args = event.text.split(maxsplit=1)
    prefix = kernel.custom_prefix

    if len(args) < 2:
        text = (
            "<b>🧩 MCUB Engine — как это работает</b>\n"
            "\n"
            "Модули MCUB-fork работают без инлайн-бота:\n"
            "• <b>Кнопки</b> превращаются в команды и показываются под сообщением:\n"
            f"  <code>{prefix}cb 1</code> — «нажать» кнопку №1\n"
            f"  <code>{prefix}cb</code> — показать активное меню ещё раз\n"
            f"• <b>Инлайн-поиск</b>: <code>{prefix}iq &lt;запрос&gt;</code>\n"
            f"• <b>Ввод для кнопок</b>: <code>{prefix}it &lt;id&gt; &lt;текст&gt;</code>\n"
            "\n"
            "<b>Управление:</b>\n"
            f"<code>{prefix}mload</code> — установить модуль (reply/URL)\n"
            f"<code>{prefix}mls</code> — список модулей\n"
            f"<code>{prefix}mhelp &lt;name&gt;</code> — команды модуля\n"
            f"<code>{prefix}mcfg &lt;name&gt;</code> — конфиг модуля\n"
            f"<code>{prefix}mun &lt;name&gt;</code> — выгрузить модуль\n"
        )
        return await edit_or_reply(event, text, parse_mode="HTML")

    name = args[1].strip()
    help_dict = loader._local_help().get(name)
    if not help_dict:
        help_dict = {}
        if hasattr(kernel, 'command_owners') and hasattr(kernel, 'command_docs'):
            for cmd, owner in kernel.command_owners.items():
                if owner == name:
                    docs = kernel.command_docs.get(cmd, {})
                    help_dict[cmd] = docs.get("ru") or docs.get("en") or f"Команда {cmd}"
    if not help_dict:
        return await edit_or_reply(
            event, f"❌ Модуль <code>{html.escape(name)}</code> не найден",
            parse_mode="HTML",
        )
    lines = [f"<b>📦 {html.escape(name)} — команды:</b>\n"]
    for cmd, desc in sorted(help_dict.items()):
        lines.append(f"<code>{prefix}{html.escape(cmd)}</code> — {html.escape(str(desc))}")

    # Config section
    stored = await kernel.get_module_config(name, {})
    items = _get_module_config_items(kernel, name, stored)
    if items:
        lines.append("\n<b>⚙️ Конфигурация:</b>\n")
        for key, val in items:
            is_hidden = key in _SENSITIVE_KEYS
            live_cfg = _get_live_module_config(kernel, name)
            if _is_module_config_like(live_cfg):
                try:
                    cv = live_cfg._values.get(key)
                    if cv:
                        is_hidden = is_hidden or getattr(cv, "hidden", False)
                        validator = getattr(cv, "validator", None)
                        if validator:
                            is_hidden = is_hidden or bool(getattr(validator, "secret", False))
                except Exception:
                    pass
            if is_hidden:
                display = "••••••••"
            else:
                display = str(val) if val is not None else "null"
                if len(display) > 40:
                    display = display[:37] + "..."
            value_type = type(val).__name__ if val is not None else "NoneType"
            type_emoji = _get_type_emoji("hidden" if is_hidden else value_type)
            lines.append(f"{type_emoji} <code>{html.escape(str(key))}</code> = <code>{html.escape(display)}</code>")
        lines.append(f"\n<i><code>.mcfg {html.escape(name)} &lt;key&gt;</code> — подробнее о ключе</i>")

    await edit_or_reply(event, "\n".join(lines), parse_mode="HTML")


# ============================================================
# CONFIG DISPLAY HELPERS (MCUB-fork style)
# ============================================================

_TYPE_EMOJIS = {
    "str": "📝", "int": "🔢", "float": "🔢", "bool": "☑️",
    "list": "📚", "dict": "🗂", "NoneType": "🗳", "hidden": "🔒",
}

_SENSITIVE_KEYS = {"inline_bot_token", "api_id", "api_hash", "phone"}


def _is_module_config_like(obj):
    """Check if object is a ModuleConfig-like (MCUB or Hikka compat)."""
    if obj is None:
        return False
    if type(obj).__name__ == "ModuleConfig":
        return True
    if hasattr(obj, "_is_hikka_compat") and obj._is_hikka_compat:
        return True
    if hasattr(obj, "_config") and hasattr(obj, "_values"):
        return True
    return False


def _get_type_emoji(value_type):
    return _TYPE_EMOJIS.get(value_type, "📎")


def _wrap_long_value(display_value, raw_value):
    """Wrap long values in collapsible quote block."""
    if len(str(raw_value)) > 300:
        return f"<blockquote expandable>{display_value}</blockquote>"
    return display_value


def _format_value_html(value, is_hidden=False):
    """Format a single config value for HTML display."""
    if is_hidden:
        return "<code>••••••••</code>", "hidden"

    value_type = type(value).__name__

    if isinstance(value, (dict, list)):
        formatted = json.dumps(value, ensure_ascii=False, indent=2)
        display = f"<pre>{html.escape(formatted)}</pre>"
        display = _wrap_long_value(display, formatted)
    elif value is None:
        display = "<code>null</code>"
    elif isinstance(value, bool):
        display = "✔️ <code>true</code>" if value else "✖️ <code>false</code>"
    elif isinstance(value, str):
        escaped = html.escape(value)
        display = f"<code>{escaped}</code>"
        display = _wrap_long_value(display, value)
    else:
        raw = str(value)
        display = f"<code>{html.escape(raw)}</code>"
        display = _wrap_long_value(display, raw)

    return display, value_type


def _get_live_module_config(kernel, module_name):
    """Return live ModuleConfig-like schema for a loaded module."""
    live_cfg = getattr(kernel, "_live_module_configs", {}).get(module_name)
    if live_cfg is not None:
        return live_cfg
    live_mod = kernel.loaded_modules.get(module_name) or kernel.system_modules.get(module_name)
    if live_mod is not None:
        return getattr(live_mod, "config", None)
    return None


def _get_module_config_items(kernel, module_name, stored_config):
    """Return config keys to display, preferring live schema."""
    live_cfg = _get_live_module_config(kernel, module_name)
    if _is_module_config_like(live_cfg):
        try:
            return list(live_cfg.items())
        except Exception:
            pass
    if _is_module_config_like(stored_config):
        try:
            return list(stored_config.items())
        except Exception:
            pass
    if isinstance(stored_config, dict) and stored_config.get("__mcub_config__"):
        return [(k, v) for k, v in stored_config.items() if k != "__mcub_config__"]
    if isinstance(stored_config, dict):
        return list(stored_config.items())
    return []


async def _build_config_key_detail(kernel, module_name, key, stored_config):
    """Build detailed HTML view for a single config key (MCUB-fork style)."""
    live_cfg = _get_live_module_config(kernel, module_name)
    is_module_config = _is_module_config_like(stored_config)
    is_dict_config = isinstance(stored_config, dict) and stored_config.get("__mcub_config__")

    # Determine value and config_value descriptor
    value = None
    config_value = None
    is_hidden = False
    is_secret = False

    if is_module_config:
        if key in stored_config.keys():
            value = stored_config[key]
        config_value = stored_config._values.get(key) if hasattr(stored_config, "_values") else None
    elif is_dict_config:
        if key in stored_config and key != "__mcub_config__":
            value = stored_config[key]
    else:
        if isinstance(stored_config, dict) and key in stored_config:
            value = stored_config[key]

    # Fallback to live config for metadata
    if config_value is None and _is_module_config_like(live_cfg):
        try:
            config_value = live_cfg._values.get(key)
        except Exception:
            pass

    if config_value:
        is_hidden = getattr(config_value, "hidden", False) or False
        validator = getattr(config_value, "validator", None)
        if validator:
            is_secret = bool(getattr(validator, "secret", False))
            is_hidden = is_hidden or is_secret

    # If value still None, try live config value
    if value is None and _is_module_config_like(live_cfg):
        try:
            value = live_cfg[key]
        except Exception:
            pass

    if value is None:
        return None

    display_value, value_type = _format_value_html(value, is_hidden)
    type_emoji = _get_type_emoji(value_type)

    lines = [
        f"<b>{type_emoji} {html.escape(key)}</b>",
        f"<b>Значение:</b> {display_value}",
    ]

    # Description
    description = None
    if config_value and hasattr(config_value, "description"):
        description = config_value.description
    if description:
        lines.append(f"\n📖 <blockquote expandable><i>{html.escape(str(description))}</i></blockquote>")

    # Placeholders
    if config_value:
        validator = getattr(config_value, "validator", None)
        if validator and getattr(validator, "supports_placeholders", False):
            scope_name = getattr(validator, "placeholder_scope", None) or module_name
            placeholders_help = ""
            try:
                import utils
                if hasattr(utils, "config_placeholders"):
                    placeholders_help = utils.config_placeholders(scope_name)
            except Exception:
                pass
            # Also try module-level placeholders
            if scope_name != module_name:
                try:
                    import utils
                    if hasattr(utils, "config_placeholders"):
                        mod_ph = utils.config_placeholders(module_name)
                        if mod_ph:
                            placeholders_help = f"{mod_ph}\n{placeholders_help}" if placeholders_help else mod_ph
                except Exception:
                    pass
            if placeholders_help:
                lines.append(
                    f"\n📋 <b>Доступные плейсхолдеры:</b>"
                    f"\n<blockquote expandable><i>{html.escape(placeholders_help)}</i></blockquote>"
                )

        # Choices
        choices = getattr(validator, "choices", None) if validator else None
        if choices:
            choices_str = ", ".join(f"<code>{html.escape(str(c))}</code>" for c in choices)
            lines.append(f"\n📋 <b>Варианты:</b> {choices_str}")

        # Range
        v_min = getattr(validator, "min", None) if validator else None
        v_max = getattr(validator, "max", None) if validator else None
        if v_min is not None and v_max is not None:
            lines.append(f"🔢 <b>Диапазон:</b> <code>{v_min}</code> — <code>{v_max}</code>")
        elif v_min is not None:
            lines.append(f"🔢 <b>Минимум:</b> <code>{v_min}</code>")
        elif v_max is not None:
            lines.append(f"🔢 <b>Максимум:</b> <code>{v_max}</code>")

        # Length
        min_len = getattr(validator, "min_len", None) if validator else None
        max_len = getattr(validator, "max_len", None) if validator else None
        if min_len is not None and max_len is not None:
            lines.append(f"📝 <b>Длина:</b> от <code>{min_len}</code> до <code>{max_len}</code>")
        elif min_len is not None:
            lines.append(f"📝 <b>Мин. длина:</b> <code>{min_len}</code>")
        elif max_len is not None:
            lines.append(f"📝 <b>Макс. длина:</b> <code>{max_len}</code>")

    # Default
    if config_value and hasattr(config_value, "default"):
        default_val = config_value.default
        if default_val is not None:
            def_display, _ = _format_value_html(default_val, is_hidden=False)
            lines.append(f"\n💡 <b>По умолчанию:</b> {def_display}")

    lines.append(f"\n<i>Изменить: <code>.mcfg {html.escape(module_name)} {html.escape(key)} &lt;value&gt;</code></i>")
    return "\n".join(lines)


async def _set_config_value(kernel, module_name, key, value_str):
    """Set config value with validation via live schema."""
    stored = await kernel.get_module_config(module_name, {})
    live_cfg = _get_live_module_config(kernel, module_name)

    # Determine expected type
    expected_type = None
    if _is_module_config_like(live_cfg):
        try:
            expected_type = type(live_cfg[key]).__name__ if key in live_cfg.keys() else None
        except Exception:
            pass
    elif isinstance(stored, dict) and key in stored:
        expected_type = type(stored[key]).__name__

    # Parse value
    raw = value_str.strip()
    if raw.lower() == "null":
        parsed = None
    elif expected_type == "bool" or (expected_type is None and raw.lower() in ("true", "false")):
        parsed = raw.lower() == "true"
    elif expected_type == "int":
        parsed = int(raw)
    elif expected_type == "float":
        parsed = float(raw)
    elif raw.startswith("{") and raw.endswith("}"):
        parsed = json.loads(raw)
    elif raw.startswith("[") and raw.endswith("]"):
        parsed = json.loads(raw)
    else:
        parsed = raw
        # Unescape - ИСПРАВЛЕННЫЕ регулярные выражения
        parsed = re.sub(r"(?<!\\)\\n", "\n", parsed)  # \n -> реальный перевод строки
        parsed = re.sub(r"(?<!\\)\\t", "\t", parsed)  # \t -> реальная табуляция

    # Try to set via live config (validates automatically)
    if _is_module_config_like(live_cfg):
        try:
            live_cfg[key] = parsed
            if hasattr(live_cfg, "to_dict"):
                data = live_cfg.to_dict()
                data.pop("__mcub_config__", None)
                await kernel.save_module_config(module_name, data)
            else:
                await kernel.save_module_config(module_name, dict(live_cfg))
            return True, parsed
        except Exception as e:
            return False, e

    # Fallback: plain dict
    if isinstance(stored, dict):
        stored[key] = parsed
        await kernel.save_module_config(module_name, stored)
        return True, parsed

    await kernel.set_module_config_key(module_name, key, parsed)
    return True, parsed

async def mcfg_handler(event):
    """.mcfg <name> [key] [value] — конфиг MCUB-модуля."""
    if not event.out:
        return

    kernel, loader = _engine()
    if kernel is None or loader is None:
        return await edit_or_reply(event, "❌ MCUB Engine не инициализирован", parse_mode="HTML")

    args = event.text.split(maxsplit=3)
    if len(args) < 2:
        return await edit_or_reply(
            event,
            "<b>⚙️ Использование:</b>\n"
            "<code>.mcfg &lt;name&gt;</code> — показать конфиг модуля\n"
            "<code>.mcfg &lt;name&gt; &lt;key&gt;</code> — детали ключа\n"
            "<code>.mcfg &lt;name&gt; &lt;key&gt; &lt;value&gt;</code> — установить значение",
            parse_mode="HTML",
        )

    name = args[1]
    stored = await kernel.get_module_config(name, {})
    items = _get_module_config_items(kernel, name, stored)

    if not items and not stored:
        return await edit_or_reply(
            event, f"❌ У модуля <code>{html.escape(name)}</code> нет конфига",
            parse_mode="HTML",
        )

    # Mode 1: show all config keys
    if len(args) == 2:
        lines = [f"<b>⚙️ Конфиг <code>{html.escape(name)}</code> ({len(items)} ключей):</b>\n"]
        for key, val in items:
            # Check hidden
            is_hidden = key in _SENSITIVE_KEYS
            live_cfg = _get_live_module_config(kernel, name)
            if _is_module_config_like(live_cfg):
                try:
                    cv = live_cfg._values.get(key)
                    if cv:
                        is_hidden = is_hidden or getattr(cv, "hidden", False)
                        validator = getattr(cv, "validator", None)
                        if validator:
                            is_hidden = is_hidden or bool(getattr(validator, "secret", False))
                except Exception:
                    pass

            value_type = type(val).__name__ if val is not None else "NoneType"
            type_emoji = _get_type_emoji("hidden" if is_hidden else value_type)

            if is_hidden:
                display = "<code>••••••••</code>"
            else:
                display, _ = _format_value_html(val)
                # Truncate for list view
                display_text = re.sub(r"<[^>]+>", "", display)
                if len(display_text) > 60:
                    display = f"<code>{html.escape(display_text[:57])}...</code>"
                else:
                    display = f"<code>{html.escape(display_text)}</code>"

            lines.append(f"{type_emoji} <code>{html.escape(str(key))}</code> = {display}")

        lines.append(f"\n<i><code>.mcfg {html.escape(name)} &lt;key&gt;</code> — подробнее о ключе</i>")
        return await edit_or_reply(event, "\n".join(lines), parse_mode="HTML")

    key = args[2]

    # Mode 2: show key detail
    if len(args) == 3:
        detail = await _build_config_key_detail(kernel, name, key, stored)
        if detail is None:
            return await edit_or_reply(
                event, f"❌ Ключ <code>{html.escape(key)}</code> не найден в модуле <code>{html.escape(name)}</code>",
                parse_mode="HTML",
            )
        return await edit_or_reply(event, detail, parse_mode="HTML")

    # Mode 3: set value
    value_str = args[3]
    ok, result = await _set_config_value(kernel, name, key, value_str)
    if not ok:
        err = str(result)
        return await edit_or_reply(
            event, f"❌ <b>Ошибка валидации:</b> <code>{html.escape(err[:300])}</code>",
            parse_mode="HTML",
        )

    # Show updated key detail
    stored = await kernel.get_module_config(name, {})
    detail = await _build_config_key_detail(kernel, name, key, stored)
    if detail:
        await edit_or_reply(event, f"✅ <b>Значение обновлено</b>\n\n{detail}", parse_mode="HTML")
    else:
        await edit_or_reply(
            event, f"✅ <code>{html.escape(key)}</code> = <code>{html.escape(str(result))}</code>",
            parse_mode="HTML",
        )

# ============================================================
# SETUP (вызывается загрузчиком Hydra)
# ============================================================

_SETUP_DONE = False

def setup(client):
    global _CLIENT, _SETUP_DONE
    # Модуль-глобал не спасёт, если чужой загрузчик исполняет этот файл
    # как отдельный namespace (свой собственный _SETUP_DONE=False) — но
    # client всегда один и тот же реальный объект, поэтому дублируем
    # проверку и на нём тоже.
    if _SETUP_DONE or getattr(client, "_mcub_dispatcher_registered", False):
        print("    🧩 MCUB setup() уже был выполнен — пропускаю повторную регистрацию")
        return
    _SETUP_DONE = True
    try:
        client._mcub_dispatcher_registered = True
    except Exception:
        pass
    _CLIENT = client

    # КРИТИЧЕСКИ ВАЖНО: ИНИЦИАЛИЗИРУЕМ MCUB ENGINE
    try:
        kernel = _init_engine(client)
        if kernel:
            print(f"    🧩 MCUB Engine ready")
        else:
            print(f"    ❌ MCUB Engine NOT ready!")
    except Exception as e:
        print(f"    ❌ MCUB Engine init error: {e}")
        logger.error(f"MCUB Engine init error: {e}", exc_info=True)

    try:
        import config as _cfg
        prefix = getattr(_cfg, "prefix", ".") or "."
    except Exception:
        prefix = "."
    p = re.escape(prefix)

# диспетчер MCUB — одним хендлером на все исходящие
    print(f"[MCUB] registering dispatcher, client id={id(client)}")
    client.add_event_handler(_mcub_dispatcher, events.NewMessage(outgoing=True))
    # команды управления

    # автозагрузка модулей
    try:
        asyncio.get_event_loop().create_task(_autoload())
    except RuntimeError:
        pass


modules_help = {
    "mcub": {
        "mload": "Установить MCUB-модуль (reply на .py / текст / URL)",
        "mun <name>": "Выгрузить MCUB-модуль",
        "mls": "Список MCUB-модулей",
        "mhelp [name]": "Помощь по модулю и мосту кнопок",
        "mcfg <name> [key] [value]": "Конфиг MCUB-модуля",
        "cb [N]": "Нажать inline-кнопку N (меню показывается под сообщением)",
        "iq <запрос>": "Инлайн-поиск как команда",
        "it <id> <текст>": "Ввод для input-кнопки",
    }
}
