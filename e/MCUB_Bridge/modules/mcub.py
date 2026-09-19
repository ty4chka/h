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

import aiohttp
from telethon import events

from utils.misc import edit_or_reply

logger = logging.getLogger("mcub.mod")

_KERNEL = None
_LOADER = None
_AUToload_started = False


# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================

def _engine():
    global _KERNEL, _LOADER
    if _KERNEL is None:
        from mcub_engine import install, get_kernel
        from mcub_engine.loader import get_loader
        install(_CLIENT)
        _KERNEL = get_kernel()
        _LOADER = get_loader()
    return _KERNEL, _LOADER


async def _autoload():
    """Автозагрузка всех MCUB-модулей при старте."""
    global _AUToload_started
    if _AUToload_started:
        return
    _AUToload_started = True
    await asyncio.sleep(1)  # дать Hydra догрузиться
    try:
        kernel, loader = _engine()
        await kernel.get_me_cached()
        results = await loader.autoload_all()
        ok_count = sum(1 for _, ok, _ in results if ok)
        if results:
            logger.info(f"MCUB autoload: {ok_count}/{len(results)} OK")
    except Exception as e:
        logger.error(f"MCUB autoload failed: {e}", exc_info=True)


# ============================================================
# ГЛАВНЫЙ ДИСПЕТЧЕР КОМАНД MCUB
# ============================================================

async def _mcub_dispatcher(event):
    """Единая точка входа: .cb/.it/.iq + все команды MCUB-модулей."""
    if not event.out:
        return
    text = event.raw_text or ""
    if not text:
        return
    kernel, loader = _engine()
    prefix = kernel.custom_prefix
    if not text.startswith(prefix):
        return

    body = text[len(prefix):]
    parts = body.split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    args_str = parts[1] if len(parts) > 1 else ""

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
        await kernel.bridge.handle_iq(event, args_str)
        return

    # ---- команды MCUB-модулей ----
    target = kernel.command_handlers.get(cmd)
    if target is None:
        target = kernel.command_handlers.get(kernel.aliases.get(cmd, ""), None)
    if target is None:
        return  # не наша команда — пусть обработает Hydra

    from mcub_engine.proxies import EventProxy
    proxy = EventProxy(event, kernel)
    try:
        if kernel.middleware_chain:
            await kernel.process_with_middleware(proxy, target)
        else:
            await target(proxy)
    except Exception as e:
        logger.error(f"MCUB command '{cmd}' error: {e}", exc_info=True)
        await kernel.handle_error(e, source=f"команда {prefix}{cmd}", event=proxy)


# ============================================================
# КОМАНДЫ УПРАВЛЕНИЯ
# ============================================================

async def mload_handler(event):
    """.mload — установить MCUB-модуль (reply на файл/текст или URL)."""
    if not event.out:
        return
    kernel, loader = _engine()
    msg = await edit_or_reply(event, "<b>🔍 Анализ модуля...</b>", parse_mode="HTML")

    code = None
    src = ""
    name = None

    args = event.text.split(maxsplit=1)
    reply = await event.get_reply_message()

    if len(args) > 1:
        url = args[1].strip()
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
    if not event.out:
        return
    kernel, loader = _engine()
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
    args = event.text.split(maxsplit=1)
    prefix = kernel.custom_prefix

    if len(args) < 2:
        text = (
            "<b>🧩 MCUB Engine — как это работает</b>\n\n"
            "Модули MCUB-fork работают без инлайн-бота:\n"
            "• <b>Кнопки</b> превращаются в команды и показываются под сообщением:\n"
            f"  <code>{prefix}cb 1</code> — «нажать» кнопку №1\n"
            f"  <code>{prefix}cb</code> — показать активное меню ещё раз\n"
            f"• <b>Инлайн-поиск</b>: <code>{prefix}iq &lt;запрос&gt;</code>\n"
            f"• <b>Ввод для кнопок</b>: <code>{prefix}it &lt;id&gt; &lt;текст&gt;</code>\n\n"
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
        # соберём напрямую из ядра
        help_dict = {}
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
    await edit_or_reply(event, "\n".join(lines), parse_mode="HTML")


async def mcfg_handler(event):
    """.mcfg <name> [key] [value] — конфиг MCUB-модуля."""
    if not event.out:
        return
    kernel, loader = _engine()
    args = event.text.split(maxsplit=3)
    if len(args) < 2:
        return await edit_or_reply(event, "<code>.mcfg &lt;name&gt; [key] [value]</code>",
                                   parse_mode="HTML")
    name = args[1]

    schema = kernel._module_schemas.get(name)
    live = kernel._live_module_configs.get(name)

    if len(args) == 2:
        # показать конфиг
        saved = await kernel.get_module_config(name, {})
        if schema is None and not saved:
            return await edit_or_reply(
                event, f"❌ У модуля <code>{html.escape(name)}</code> нет конфига",
                parse_mode="HTML",
            )
        lines = [f"<b>⚙️ Конфиг {html.escape(name)}:</b>\n"]
        if live is not None and hasattr(live, "items"):
            try:
                for key, val in live.items():
                    lines.append(f"▪️ <code>{html.escape(str(key))}</code> = "
                                 f"<code>{html.escape(str(val))}</code>")
            except Exception:
                pass
        elif saved:
            for key, val in saved.items():
                if key == "__mcub_config__":
                    continue
                lines.append(f"▪️ <code>{html.escape(str(key))}</code> = "
                             f"<code>{html.escape(str(val))}</code>")
        lines.append(f"\n<i>Изменить: .mcfg {html.escape(name)} &lt;key&gt; &lt;value&gt;</i>")
        return await edit_or_reply(event, "\n".join(lines), parse_mode="HTML")

    if len(args) < 4:
        return await edit_or_reply(event, "<code>.mcfg &lt;name&gt; &lt;key&gt; &lt;value&gt;</code>",
                                   parse_mode="HTML")

    key, value = args[2], args[3]
    # установка с валидацией через схему (если есть)
    if live is not None and hasattr(live, "__setitem__"):
        try:
            if isinstance(value, str) and value.lower() in ("true", "false"):
                value = value.lower() == "true"
            live[key] = value
            if hasattr(live, "to_dict"):
                data = live.to_dict()
                data.pop("__mcub_config__", None)
                await kernel.save_module_config(name, data)
            return await edit_or_reply(
                event, f"✅ <code>{html.escape(key)}</code> = <code>{html.escape(str(value))}</code>",
                parse_mode="HTML",
            )
        except Exception as e:
            return await edit_or_reply(
                event, f"❌ <b>Ошибка валидации:</b> <code>{html.escape(str(e))}</code>",
                parse_mode="HTML",
            )
    await kernel.set_module_config_key(name, key, value)
    await edit_or_reply(
        event, f"✅ <code>{html.escape(key)}</code> = <code>{html.escape(str(value))}</code>",
        parse_mode="HTML",
    )


# ============================================================
# SETUP (вызывается загрузчиком Hydra)
# ============================================================

_CLIENT = None


def setup(client):
    global _CLIENT
    _CLIENT = client

    try:
        import config as _cfg
        prefix = getattr(_cfg, "prefix", ".") or "."
    except Exception:
        prefix = "."
    p = re.escape(prefix)

    # диспетчер MCUB — одним хендлером на все исходящие
    client.add_event_handler(_mcub_dispatcher, events.NewMessage(outgoing=True))

    # команды управления
    client.add_event_handler(
        mload_handler, events.NewMessage(pattern=rf"(?i)^{p}mload(?:\s|$)", outgoing=True))
    client.add_event_handler(
        mun_handler, events.NewMessage(pattern=rf"(?i)^{p}mun(?:\s|$)", outgoing=True))
    client.add_event_handler(
        mls_handler, events.NewMessage(pattern=rf"(?i)^{p}mls(?:\s|$)", outgoing=True))
    client.add_event_handler(
        mhelp_handler, events.NewMessage(pattern=rf"(?i)^{p}mhelp(?:\s|$)", outgoing=True))
    client.add_event_handler(
        mcfg_handler, events.NewMessage(pattern=rf"(?i)^{p}mcfg(?:\s|$)", outgoing=True))

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
