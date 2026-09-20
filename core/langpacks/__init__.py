# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Шмэлькa | @hairpin01

"""core.langpacks — поверхность MCUB-fork (порт core/langpacks/__init__.py).

Порядок сборки паков для каждой локали (позже — приоритетнее):

1. встроенные паки ядра Hydra (``hydra_kernel.api.lang``: GLOBAL_PACK/MODULE_PACKS) —
   доступны всегда, без PyYAML и без файлов на диске;
2. ``core/langpacks/icons/*.{json,yaml,yml}`` — глобальные иконочные группы;
3. ``core/langpacks/*.{json,yaml,yml}`` — паки репозитория (ru, en, ...);
4. ``data/langpacks/*`` и ``core/langpacks/custom/*`` — пользовательские паки
   (как ``CUSTOM_LANGPACKS_DIR`` в MCUB-fork).

Пак — это ``{locale: {module: {key: value}}}``; блок модуля с маркером
``__global__`` попадает в общий для всех модулей набор строк (кнопки, ошибки,
иконочки), а ``lang: xx`` задаёт базовый язык локали. YAML-файлы читаются,
только если установлен PyYAML (он в requirements.txt), JSON — всегда.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

__all__ = [
    "CUSTOM_LANGPACKS_DIR",
    "LANGPACKS",
    "clear_langpacks_cache",
    "get_all_module_strings",
    "get_available_locales",
    "get_kernel_strings",
    "get_langpacks",
    "get_module_strings",
    "reload_packs",
]

_LANGPACKS_DIR = Path(__file__).parent
_ICONS_DIR = _LANGPACKS_DIR / "icons"
# Каталог пользовательских паков: репозиторий держит их в data/langpacks,
# MCUB-fork — в core/langpacks/custom; читаем оба.
CUSTOM_LANGPACKS_DIR = Path("data/langpacks")
_CUSTOM_DIRS = (CUSTOM_LANGPACKS_DIR, _LANGPACKS_DIR / "custom")

LANGPACKS: Dict[str, Dict[str, Any]] = {}
_GLOBAL_MODULE = "__global__"
_GLOBAL_MARKER = "__global__"
_PREMIUM_EMOJI_MARKER = "__premium_emoji__"
_GROUP_VALUE = "__value__"
_PREMIUM_EMOJI_RE = re.compile(r"\[(\d+)\]\(([^()]*)\)")
_UNQUOTED_PREMIUM_EMOJI_RE = re.compile(
    r"^(?P<prefix>\s*(?:[\w.-]+|'[^']+'|\"[^\"]+\")\s*:\s*)"
    r"(?P<value>(?:\[\d+\]\([^()\r\n]*\))+)(?P<suffix>\s*(?:#.*)?)$"
)
_EXTENSIONS = ("*.json", "*.yaml", "*.yml")


def clear_langpacks_cache() -> None:
    """Сбросить кэш паков: следующий get_langpacks() перечитает файлы."""

    LANGPACKS.clear()


def reload_packs() -> None:
    """Совместимое имя MCUB-fork: сбросить кэш и (если есть) кэш utils.strings."""

    clear_langpacks_cache()
    try:
        import sys

        strings_mod = sys.modules.get("utils.strings")
        reloader = getattr(strings_mod, "reload_packs", None)
        # utils.strings.reload_packs сам вызывает clear_langpacks_cache, поэтому
        # защищаемся от рекурсии: зовём только если кэш реально сброшен.
        if callable(reloader) and getattr(strings_mod, "_LANGPACKS_CACHE", None) is not None:
            reloader()
    except Exception:  # noqa: BLE001 - перезагрузка не должна ронять вызов
        pass


def _is_global_marker(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return value == 1


def _iter_langpack_files() -> List[Path]:
    """Сначала паки репозитория, затем пользовательские (они приоритетнее)."""

    files: List[Path] = []
    for pattern in _EXTENSIONS:
        files.extend(sorted(_LANGPACKS_DIR.glob(pattern)))
    for directory in _CUSTOM_DIRS:
        if not directory.is_dir():
            continue
        for pattern in _EXTENSIONS:
            files.extend(sorted(directory.glob(pattern)))
    return files


def _quote_unquoted_premium_emoji(text: str) -> str:
    """Сделать компактную запись ``[id](alt)`` валидным YAML без кавычек."""

    lines = []
    for line in text.splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        content = line[:-1] if newline else line
        match = _UNQUOTED_PREMIUM_EMOJI_RE.fullmatch(content)
        if match:
            content = (
                f"{match['prefix']}{json.dumps(match['value'], ensure_ascii=False)}"
                f"{match['suffix']}"
            )
        lines.append(content + newline)
    return "".join(lines)


def _load_pack_file(file_path: Path, *, icon_syntax: bool = False) -> Dict[str, Any]:
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if file_path.suffix == ".json":
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        if icon_syntax:
            text = _quote_unquoted_premium_emoji(text)
        data = yaml.safe_load(text) or {}
    except Exception:  # noqa: BLE001 - битый пак не должен ронять ядро
        return {}
    return data if isinstance(data, dict) else {}


def _render_premium_emoji(value: Any) -> Any:
    if isinstance(value, str):
        return _PREMIUM_EMOJI_RE.sub(
            lambda match: (
                f'<tg-emoji emoji-id="{match.group(1)}">'
                f"{html.escape(match.group(2))}</tg-emoji>"
            ),
            value,
        )
    if isinstance(value, dict):
        return {key: _render_premium_emoji(item) for key, item in value.items()}
    return value


def _merge_pack_data(locale_data: Dict[str, Any], data: Dict[str, Any]) -> None:
    """Влить паки одной локали/иконочного набора в нормализованные данные."""

    for module_name, strings in data.items():
        if isinstance(strings, dict):
            premium_emoji = _is_global_marker(strings.get(_PREMIUM_EMOJI_MARKER))
            normalized = {
                key: _render_premium_emoji(value) if premium_emoji else value
                for key, value in strings.items()
                if key != _PREMIUM_EMOJI_MARKER
            }

            if _is_global_marker(normalized.get(_GLOBAL_MARKER)):
                normalized.pop(_GLOBAL_MARKER, None)
                global_groups = locale_data.setdefault(_GLOBAL_MODULE, {})
                current = global_groups.setdefault(module_name, {})
                if isinstance(current, dict):
                    current.update(normalized)
                else:
                    global_groups[module_name] = normalized
                continue

            module_strings = locale_data.setdefault(module_name, {})
            if not isinstance(module_strings, dict):
                module_strings = {}
                locale_data[module_name] = module_strings
            for key, value in normalized.items():
                if isinstance(value, (str, dict)):
                    module_strings[key] = value
        elif isinstance(strings, str):
            # Метаданные локали, например "lang: ru".
            locale_data[module_name] = strings


def _load_icon_packs() -> List[Dict[str, Any]]:
    if not _ICONS_DIR.is_dir():
        return []
    packs: List[Dict[str, Any]] = []
    for pattern in _EXTENSIONS:
        for file_path in sorted(_ICONS_DIR.glob(pattern)):
            packs.append(_load_pack_file(file_path, icon_syntax=True))
    return packs


def _kernel_locale_packs() -> Iterator[tuple]:
    """Встроенные паки ядра Hydra в формате паков MCUB."""

    try:
        from hydra_kernel.api import lang as _lang
    except Exception:  # noqa: BLE001 - ядро может быть недоступно в тестах
        return
    for locale, data in getattr(_lang, "GLOBAL_PACK", {}).items():
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            # Глобальная строка ядра — это и значение, и потенциальная группа,
            # как StringsGroupValue в utils.strings (маркер __value__).
            if isinstance(value, dict):
                yield locale, {key: {**value, _GLOBAL_MARKER: True}}
            else:
                yield locale, {key: {_GLOBAL_MARKER: True, _GROUP_VALUE: value}}
    for module_name, packs in getattr(_lang, "MODULE_PACKS", {}).items():
        for locale, data in packs.items():
            if isinstance(data, dict):
                yield locale, {module_name: data}


def get_langpacks(locale: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    if LANGPACKS:
        if locale and locale in LANGPACKS:
            return {locale: LANGPACKS[locale]}
        return LANGPACKS

    icon_packs = _load_icon_packs()

    def _ensure(locale_name: str) -> Dict[str, Any]:
        return LANGPACKS.setdefault(locale_name, {})

    # 1. встроенные паки ядра (доступны всегда, служат фолбэком)
    for locale_name, data in _kernel_locale_packs():
        _merge_pack_data(_ensure(locale_name), data)

    # 2. иконочные группы и файловые паки локали
    for pack_file in _iter_langpack_files():
        locale_name = pack_file.stem
        locale_data = _ensure(locale_name)
        for icon_pack in icon_packs:
            _merge_pack_data(locale_data, icon_pack)
        _merge_pack_data(locale_data, _load_pack_file(pack_file))

    if locale and locale in LANGPACKS:
        return {locale: LANGPACKS[locale]}
    return LANGPACKS


def get_available_locales() -> List[str]:
    """Локали паков на диске + локали встроенных паков ядра."""

    locales = {file_path.stem for file_path in _iter_langpack_files()}
    locales.update(get_langpacks().keys())
    return sorted(locales)


def _merge_globals(locale_data: Dict[str, Any], module_strings: Any) -> Dict[str, Any]:
    global_strings = locale_data.get(_GLOBAL_MODULE, {})
    if not isinstance(global_strings, dict):
        global_strings = {}

    if isinstance(module_strings, dict):
        result = dict(global_strings)
        for key, value in module_strings.items():
            global_value = result.get(key)
            if isinstance(global_value, dict):
                if isinstance(value, dict):
                    result[key] = {**global_value, **value}
                elif isinstance(value, str):
                    result[key] = {**global_value, _GROUP_VALUE: value}
                else:
                    result[key] = value
            else:
                result[key] = value
        return result
    if global_strings:
        return dict(global_strings)
    return {}


def get_kernel_strings(locale: str = "ru") -> Dict[str, Any]:
    """Строки ядра для локали: общие группы + блок модуля ``kernel``."""

    packs = get_langpacks()
    locale_data = packs.get(locale, {})
    return _merge_globals(locale_data, locale_data.get("kernel", {}))


def get_module_strings(module_name: str, locale: str = "ru") -> Dict[str, Any]:
    """Строки модуля: глобальные группы + сам блок, с фолбэком по языкам."""

    packs = get_langpacks()

    locale_data = packs.get(locale, {})
    result = locale_data.get(module_name, None)
    if result is not None:
        return _merge_globals(locale_data, result)

    base_lang = packs.get(locale, {}).get("lang") or packs.get("ru", {}).get("lang")
    if base_lang:
        base_data = packs.get(base_lang, {})
        result = base_data.get(module_name, None)
        if result is not None:
            return _merge_globals(base_data, result)

    for fb in ("ru", "en"):
        if fb != locale:
            fb_data = packs.get(fb, {})
            result = fb_data.get(module_name, None)
            if result is not None:
                return _merge_globals(fb_data, result)

    return _merge_globals(locale_data, {})


def get_all_module_strings(module_name: str) -> Dict[str, Dict[str, Any]]:
    """Все локали модуля с дозаполнением из базового языка локали."""

    packs = get_langpacks()
    available = get_available_locales()
    result: Dict[str, Dict[str, Any]] = {}

    for loc in available:
        loc_data = packs.get(loc, {})
        if not isinstance(loc_data, dict):
            continue
        strings = loc_data.get(module_name, {})

        if strings:
            result[loc] = _merge_globals(loc_data, strings)
        else:
            base = loc_data.get("lang") or "en"
            base_data = packs.get(base, {})
            result[loc] = _merge_globals(base_data, base_data.get(module_name, {}))

    return {k: v for k, v in result.items() if v}
