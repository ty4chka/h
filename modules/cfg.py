# modules/cfg.py
# meta: name=cfg version=1.0.0 author=hydra-team framework=setup
"""
🧬 Hydra Config Manager — Полноценный менеджер конфигурации модулей
Поддержка плейсхолдеров, валидации, красивого UI
"""

import json
import asyncio
from pathlib import Path
from telethon import events
from utils.misc import edit_or_reply

DATA_DIR = Path("data")
CONFIG_FILE = DATA_DIR / "module_configs.json"

_PLACEHOLDER_RE = __import__('re').compile(r"\{([A-Za-z0-9_]+)\}")

_MODULE_SCHEMAS: dict = {}
_MODULE_CONFIGS: dict = {}


def register_module_schema(module_name: str, schema: dict):
    _MODULE_SCHEMAS[module_name] = schema


def get_module_config(module_name: str) -> dict:
    if module_name in _MODULE_CONFIGS:
        return _MODULE_CONFIGS[module_name]
    return {}


def set_module_config(module_name: str, config: dict):
    _MODULE_CONFIGS[module_name] = config
    _save_all()


def _load_all():
    global _MODULE_CONFIGS
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                _MODULE_CONFIGS = json.load(f)
        except Exception:
            _MODULE_CONFIGS = {}


def _save_all():
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(_MODULE_CONFIGS, f, ensure_ascii=False, indent=2)


def _resolve_placeholders(text: str, data: dict = None) -> str:
    if not text or not isinstance(text, str):
        return str(text) if text is not None else ""
    data = data or {}

    from core.lib.loader.placeholders import _REGISTRY
    for scope_items in _REGISTRY.values():
        for key, meta in scope_items.items():
            if key not in data:
                try:
                    callback = meta["callback"]
                    result = callback(data) if callable(callback) else callback
                    if asyncio.iscoroutine(result):
                        result = "..."
                    data[key] = str(result)
                except Exception:
                    data[key] = "{" + key + "}"

    def repl(match):
        token = match.group(1)
        return str(data.get(token, match.group(0)))

    return _PLACEHOLDER_RE.sub(repl, text)


def _type_icon(validator_type: str) -> str:
    icons = {
        "boolean": "🔘",
        "integer": "🔢",
        "float": "🔣",
        "string": "📝",
        "choice": "📋",
        "secret": "🔒",
        "list": "📃",
        "link": "🔗",
    }
    return icons.get(validator_type, "⚙️")


def _format_value(value, max_len: int = 50) -> str:
    s = str(value)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s


async def cfg_handler(event):
    args = event.text.split(maxsplit=1)
    _load_all()

    if len(args) == 1:
        await _show_menu(event)
        return

    subcmd = args[1].strip()

    if subcmd == "list" or subcmd == "ls":
        await _show_all_modules(event)
    elif subcmd.startswith("show "):
        module_name = subcmd[5:].strip()
        await _show_module(event, module_name)
    elif subcmd.startswith("set "):
        await _handle_set(event, subcmd[4:].strip())
    elif subcmd.startswith("get "):
        await _handle_get(event, subcmd[4:].strip())
    elif subcmd.startswith("reset "):
        await _handle_reset(event, subcmd[6:].strip())
    elif subcmd.startswith("template "):
        await _show_template(event, subcmd[9:].strip())
    elif subcmd == "placeholders" or subcmd == "ph":
        await _show_placeholders(event)
    elif subcmd.startswith("help"):
        await _show_help(event, subcmd[4:].strip())
    else:
        await _show_module(event, subcmd)


async def _show_menu(event):
    text = (
        "<b>🧬 HYDRA CONFIG MANAGER</b>\n\n"
        "<blockquote expandable>"
        "<b>📋 Просмотр:</b>\n"
        "<code>.cfg list</code> — все модули\n"
        "<code>.cfg show &lt;module&gt;</code> — конфиг модуля\n"
        "<code>.cfg get &lt;module&gt; &lt;key&gt;</code> — значение ключа\n\n"
        "<b>✏️ Изменение:</b>\n"
        "<code>.cfg set &lt;module&gt; &lt;key&gt; &lt;value&gt;</code> — установить\n"
        "<code>.cfg reset &lt;module&gt;</code> — сбросить модуль\n"
        "<code>.cfg reset &lt;module&gt; &lt;key&gt;</code> — сбросить ключ\n\n"
        "<b>🧩 Плейсхолдеры:</b>\n"
        "<code>.cfg placeholders</code> — все плейсхолдеры\n"
        "<code>.cfg template &lt;module&gt;</code> — шаблон с плейсхолдерами\n\n"
        "<b>📖 Справка:</b>\n"
        "<code>.cfg help</code> — подробная справка\n"
        "</blockquote>\n\n"
        "<blockquote>⚡ Hydra Config Manager v2.0</blockquote>"
    )
    await edit_or_reply(event, text, parse_mode='HTML')


async def _show_all_modules(event):
    if not _MODULE_SCHEMAS and not _MODULE_CONFIGS:
        await edit_or_reply(event, "<b>📭 Нет зарегистрированных модулей</b>", parse_mode='HTML')
        return

    lines = ["<b>📋 МОДУЛИ С КОНФИГУРАЦИЕЙ</b>\n"]

    all_modules = set(list(_MODULE_SCHEMAS.keys()) + list(_MODULE_CONFIGS.keys()))
    for module_name in sorted(all_modules):
        schema = _MODULE_SCHEMAS.get(module_name, {})
        config = _MODULE_CONFIGS.get(module_name, {})
        key_count = len(schema) if schema else len(config)
        lines.append(f"  <b>📦 {module_name}</b> — <code>{key_count}</code> параметров")

    lines.append(f"\n<blockquote>📊 Всего модулей: <code>{len(all_modules)}</code></blockquote>")
    lines.append("<blockquote>💡 <code>.cfg show &lt;module&gt;</code> — подробнее</blockquote>")

    await edit_or_reply(event, "\n".join(lines), parse_mode='HTML')


async def _show_module(event, module_name: str):
    schema = _MODULE_SCHEMAS.get(module_name, {})
    config = _MODULE_CONFIGS.get(module_name, {})

    if not schema and not config:
        available = sorted(set(list(_MODULE_SCHEMAS.keys()) + list(_MODULE_CONFIGS.keys())))
        if available:
            mod_list = ", ".join(f"<code>{m}</code>" for m in available[:10])
            await edit_or_reply(
                event,
                f"<b>❌ Модуль <code>{module_name}</code> не найден</b>\n\n"
                f"<b>Доступные:</b> {mod_list}",
                parse_mode='HTML'
            )
        else:
            await edit_or_reply(event, "<b>📭 Нет модулей с конфигурацией</b>", parse_mode='HTML')
        return

    lines = [f"<b>📦 {module_name.upper()}</b>\n"]

    if schema:
        lines.append("<b>⚙️ Параметры:</b>")
        for key, info in schema.items():
            icon = _type_icon(info.get("type", "string"))
            default = info.get("default", "")
            description = info.get("description", "")
            current = config.get(key, default)
            hidden = info.get("hidden", False)

            if hidden:
                display_val = "••••••••"
            else:
                display_val = _format_value(current)

            lines.append(f"\n{icon} <code>{key}</code>")
            if description:
                lines.append(f"   <i>{description}</i>")
            lines.append(f"   Значение: <code>{display_val}</code>")

            if info.get("type") == "choice" and info.get("choices"):
                choices = ", ".join(f"<code>{c}</code>" for c in info["choices"][:5])
                lines.append(f"   Варианты: {choices}")

            lines.append(f"   <code>.cfg set {module_name} {key} &lt;value&gt;</code>")
    elif config:
        lines.append("<b>📝 Конфигурация:</b>")
        for key, value in config.items():
            display_val = _format_value(value)
            lines.append(f"  <code>{key}</code> = <code>{display_val}</code>")

    lines.append(f"\n<blockquote>💡 <code>.cfg set {module_name} &lt;key&gt; &lt;value&gt;</code></blockquote>")

    await edit_or_reply(event, "\n".join(lines), parse_mode='HTML')


async def _handle_set(event, args: str):
    parts = args.split(maxsplit=2)
    if len(parts) < 3:
        await edit_or_reply(
            event,
            "<b>❌ Использование:</b>\n<code>.cfg set &lt;module&gt; &lt;key&gt; &lt;value&gt;</code>",
            parse_mode='HTML'
        )
        return

    module_name, key, value = parts[0], parts[1], parts[2]

    schema = _MODULE_SCHEMAS.get(module_name, {})
    config = _MODULE_CONFIGS.get(module_name, {})

    if key not in schema and key not in config:
        if schema:
            available = ", ".join(f"<code>{k}</code>" for k in list(schema.keys())[:10])
            await edit_or_reply(
                event,
                f"<b>❌ Ключ <code>{key}</code> не найден в <code>{module_name}</code></b>\n\n"
                f"<b>Доступные:</b> {available}",
                parse_mode='HTML'
            )
        else:
            await edit_or_reply(
                event,
                f"<b>❌ Ключ <code>{key}</code> не найден в <code>{module_name}</code></b>",
                parse_mode='HTML'
            )
        return

    if schema and key in schema:
        info = schema[key]
        validator_type = info.get("type", "string")

        if validator_type == "boolean":
            value = value.lower() in ("true", "1", "yes", "on", "да")
        elif validator_type == "integer":
            try:
                value = int(value)
            except ValueError:
                await edit_or_reply(event, f"<b>❌ Ожидается целое число</b>", parse_mode='HTML')
                return
        elif validator_type == "float":
            try:
                value = float(value)
            except ValueError:
                await edit_or_reply(event, f"<b>❌ Ожидается число</b>", parse_mode='HTML')
                return
        elif validator_type == "choice":
            choices = info.get("choices", [])
            if value not in choices:
                choices_str = ", ".join(f"<code>{c}</code>" for c in choices)
                await edit_or_reply(
                    event,
                    f"<b>❌ Вариант <code>{value}</code> не в списке</b>\n\n"
                    f"<b>Доступные:</b> {choices_str}",
                    parse_mode='HTML'
                )
                return

    config[key] = value
    _MODULE_CONFIGS[module_name] = config
    _save_all()

    await edit_or_reply(
        event,
        f"<b>✅ {module_name}.{key} = <code>{_format_value(value)}</code></b>",
        parse_mode='HTML'
    )


async def _handle_get(event, args: str):
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await edit_or_reply(
            event,
            "<b>❌ Использование:</b>\n<code>.cfg get &lt;module&gt; &lt;key&gt;</code>",
            parse_mode='HTML'
        )
        return

    module_name, key = parts[0], parts[1]
    config = _MODULE_CONFIGS.get(module_name, {})
    schema = _MODULE_SCHEMAS.get(module_name, {})

    if key in config:
        value = config[key]
    elif key in schema:
        value = schema[key].get("default", "")
    else:
        await edit_or_reply(
            event,
            f"<b>❌ Ключ <code>{key}</code> не найден в <code>{module_name}</code></b>",
            parse_mode='HTML'
        )
        return

    await edit_or_reply(
        event,
        f"<b>📦 {module_name}.{key} = <code>{_format_value(value)}</code></b>",
        parse_mode='HTML'
    )


async def _handle_reset(event, args: str):
    parts = args.split(maxsplit=1)
    module_name = parts[0]
    key = parts[1] if len(parts) > 1 else None

    if module_name not in _MODULE_CONFIGS:
        await edit_or_reply(
            event,
            f"<b>❌ Модуль <code>{module_name}</code> не найден</b>",
            parse_mode='HTML'
        )
        return

    if key:
        if key in _MODULE_CONFIGS[module_name]:
            del _MODULE_CONFIGS[module_name][key]
            _save_all()
            await edit_or_reply(
                event,
                f"<b>✅ Ключ <code>{key}</code> сброшен в <code>{module_name}</code></b>",
                parse_mode='HTML'
            )
        else:
            await edit_or_reply(
                event,
                f"<b>❌ Ключ <code>{key}</code> не найден</b>",
                parse_mode='HTML'
            )
    else:
        _MODULE_CONFIGS[module_name] = {}
        _save_all()
        await edit_or_reply(
            event,
            f"<b>✅ Конфиг <code>{module_name}</code> сброшен</b>",
            parse_mode='HTML'
        )


async def _show_template(event, module_name: str):
    schema = _MODULE_SCHEMAS.get(module_name, {})
    config = _MODULE_CONFIGS.get(module_name, {})

    if not schema and not config:
        await edit_or_reply(
            event,
            f"<b>❌ Модуль <code>{module_name}</code> не найден</b>",
            parse_mode='HTML'
        )
        return

    template = {}
    for key, info in (schema or {}).items():
        template[key] = info.get("default", "")
    template.update(config)

    json_str = json.dumps(template, indent=2, ensure_ascii=False)
    text = (
        f"<b>📋 Шаблон: {module_name}</b>\n\n"
        f"<pre language=\"json\">{json_str}</pre>\n\n"
        f"<blockquote>💡 Скопируйте и измените нужные значения</blockquote>"
    )
    await edit_or_reply(event, text, parse_mode='HTML')


async def _show_placeholders(event):
    from core.lib.loader.placeholders import _REGISTRY

    lines = ["<b>🧩 ПЛЕЙСХОЛДЕРЫ</b>\n"]

    if "global" in _REGISTRY:
        lines.append("<b>🌍 Глобальные:</b>")
        for key, meta in sorted(_REGISTRY["global"].items()):
            desc = meta.get("description", "")
            lines.append(f"  <code>{{{key}}}</code>" + (f" — {desc}" if desc else ""))

    other_scopes = [s for s in _REGISTRY if s != "global"]
    if other_scopes:
        lines.append("\n<b>📦 Модульные:</b>")
        for scope in sorted(other_scopes):
            for key, meta in sorted(_REGISTRY[scope].items()):
                desc = meta.get("description", "")
                lines.append(f"  <code>{{{key}}}</code> ({scope})" + (f" — {desc}" if desc else ""))

    lines.append(
        "\n<blockquote>💡 Используйте в шаблонах: <code>{prefix}</code>, <code>{time}</code>, "
        "<code>{date}</code>, <code>{my_name}</code>, <code>{random}</code></blockquote>"
    )

    await edit_or_reply(event, "\n".join(lines), parse_mode='HTML')


async def _show_help(event, topic: str = ""):
    if topic == "placeholders" or topic == "ph":
        await _show_placeholders(event)
        return

    text = (
        "<b>📖 HYDRA CONFIG — СПРАВКА</b>\n\n"
        "<blockquote expandable>"
        "<b>📋 Просмотр:</b>\n"
        "<code>.cfg list</code> — список всех модулей\n"
        "<code>.cfg show &lt;module&gt;</code> — параметры модуля\n"
        "<code>.cfg get &lt;module&gt; &lt;key&gt;</code> — текущее значение\n\n"
        "<b>✏️ Изменение:</b>\n"
        "<code>.cfg set &lt;module&gt; &lt;key&gt; &lt;value&gt;</code> — установить\n"
        "<code>.cfg reset &lt;module&gt;</code> — сбросить все ключи\n"
        "<code>.cfg reset &lt;module&gt; &lt;key&gt;</code> — сбросить ключ\n\n"
        "<b>🧩 Плейсхолдеры:</b>\n"
        "<code>.cfg placeholders</code> — список плейсхолдеров\n"
        "<code>.cfg template &lt;module&gt;</code> — JSON шаблон\n\n"
        "<b>📌 Типы значений:</b>\n"
        "🔘 <code>boolean</code> — true/false/1/0/yes/no\n"
        "🔢 <code>integer</code> — целые числа\n"
        "🔣 <code>float</code> — дробные числа\n"
        "📝 <code>string</code> — текст\n"
        "📋 <code>choice</code> — выбор из списка\n"
        "🔒 <code>secret</code> — скрытые значения\n\n"
        "<b>💡 Примеры:</b>\n"
        "<code>.cfg set ping emoji 🏓</code>\n"
        "<code>.cfg set ping animate_loading true</code>\n"
        "<code>.cfg get ping template</code>\n"
        "</blockquote>\n\n"
        "<blockquote>⚡ Hydra Config Manager v2.0</blockquote>"
    )
    await edit_or_reply(event, text, parse_mode='HTML')


def setup(client):
    _load_all()
    # Do not claim unrelated commands that merely start with `.cfg`.
    client.add_event_handler(cfg_handler, events.NewMessage(pattern=r"(?i)^\.cfg(?:\s|$)", outgoing=True))


modules_help = {
    "cfg": {
        "cfg": "Меню конфигурации",
        "cfg list": "Все модули с конфигурацией",
        "cfg show <module>": "Параметры модуля",
        "cfg set <module> <key> <value>": "Установить значение",
        "cfg get <module> <key>": "Получить значение",
        "cfg reset <module>": "Сбросить конфиг модуля",
        "cfg reset <module> <key>": "Сбросить ключ",
        "cfg placeholders": "Список плейсхолдеров",
        "cfg template <module>": "JSON шаблон модуля",
        "cfg help": "Справка по командам"
    }
}
