"""L1 — lang: локализация в семантике MCUB (doc/guides/i18n.md).

- `Strings(kernel, packs)` — доступ `lang['key']`, `lang('key', **kw)`,
  `lang.get`, `lang.has`, `lang.locale`;
- вложенные группы: `self.strings('buttons')('close')`;
- активный язык берётся из `kernel.config['language']` (дефолт ru),
  фолбэк ru → первый ключ;
- встроенные глобальные и модульные паки сливаются с паком модуля;
- кастомные строки пользователя: `kernel.config['lang_custom']`
  ({module: {locale: {key: text}}}) — поверх всего;
- `Strings.refresh_all(lang)` переключает все живые экземпляры.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

DEFAULT_LOCALE = "ru"

GLOBAL_PACK: Dict[str, Dict[str, Any]] = {
    "ru": {
        "buttons": {"close": "❌ Закрыть", "back": "⬅️ Назад", "refresh": "🔄 Обновить"},
        "error": {"generic": "⚠️ Ошибка: {error}"},
        "ok": "✅ Готово",
    },
    "en": {
        "buttons": {"close": "❌ Close", "back": "⬅️ Back", "refresh": "🔄 Refresh"},
        "error": {"generic": "⚠️ Error: {error}"},
        "ok": "✅ Done",
    },
}

MODULE_PACKS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "translations": {
        "ru": {
            "select_language": "🌐 Выберите язык",
            "lang_changed": "🌐 Язык переключён на {lang}",
            "reloadlang_done": "Языковые пакеты перезагружены",
            "langbutton": {"btn_ru": "🇷 ru", "btn_en": "🇬🇧 en"},
        },
        "en": {
            "select_language": "🌐 Select language",
            "lang_changed": "🌐 Language switched to {lang}",
            "reloadlang_done": "Language packs reloaded",
            "langbutton": {"btn_ru": "🇷 ru", "btn_en": "🇬🇧 en"},
        },
    },
    "terminal": {
        "ru": {
            "running": "🖨 Выполняю…",
            "result": "🖨 <b>Команда:</b> <code>{cmd}</code>\n<b>Код:</b> {code}\n<pre>{out}</pre>",
            "timeout": "⚠️ Таймаут ({sec} c)",
            "no_command": "❌ Команда не указана",
        },
        "en": {
            "running": "🖨 Running…",
            "result": "🖨 <b>Command:</b> <code>{cmd}</code>\n<b>Code:</b> {code}\n<pre>{out}</pre>",
            "timeout": "⚠️ Timeout ({sec} s)",
            "no_command": "❌ No command given",
        },
    },
    "ping": {
        "ru": {"title": "🏓 Понг!", "uptime": "⏱ Аптайм: {uptime}", "ping_ms": "📶 {ms} мс"},
        "en": {"title": "🏓 Pong!", "uptime": "⏱ Uptime: {uptime}", "ping_ms": "📶 {ms} ms"},
    },
    "info": {
        "ru": {"title": "🧬 Hydra", "version": "Версия ядра: {version}", "modules": "Модулей: {count}"},
        "en": {"title": "🧬 Hydra", "version": "Kernel version: {version}", "modules": "Modules: {count}"},
    },
    "help": {
        "ru": {"title": "📚 Модули", "module": "📦 {name}", "no_commands": "Нет команд"},
        "en": {"title": "📚 Modules", "module": "📦 {name}", "no_commands": "No commands"},
    },
    "settings": {
        "ru": {"title": "⚙️ Настройки", "on": "✅", "off": "❌"},
        "en": {"title": "⚙️ Settings", "on": "✅", "off": "❌"},
    },
}


class Group:
    """Вызываемая вложенная группа строк: g('key', **kw) / g('sub')('key')."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def __call__(self, key: str, **kw: Any) -> Any:
        value = self._data.get(key, key)
        if isinstance(value, dict):
            return Group(value)
        try:
            return value.format(**kw)
        except (KeyError, IndexError, ValueError):
            return value

    def get(self, key: str, default: Any = None) -> Any:
        value = self._data.get(key, default)
        return Group(value) if isinstance(value, dict) else value

    def __getitem__(self, key: str) -> Any:
        value = self._data.get(key, key)  # как в MCUB: нет ключа -> сам ключ
        return Group(value) if isinstance(value, dict) else value

    def has(self, key: str) -> bool:
        return key in self._data


class Strings:
    _instances: List["Strings"] = []

    def __init__(self, kernel: Any, packs: Optional[Dict[str, Any]] = None, module_name: Optional[str] = None):
        self.kernel = kernel
        self.module_name = module_name or (packs or {}).get("name")
        self._packs = packs or {}
        Strings._instances.append(self)

    # -- локаль --
    @property
    def locale(self) -> str:
        cfg = getattr(self.kernel, "config", {}) or {}
        return cfg.get("language", DEFAULT_LOCALE)

    def _merged(self, locale: str) -> Dict[str, Any]:
        def pick(pack: Dict[str, Any]) -> Dict[str, Any]:
            return pack.get(locale, pack.get(DEFAULT_LOCALE, next(iter(pack.values()), {})))

        merged: Dict[str, Any] = {}
        for pack in (GLOBAL_PACK, MODULE_PACKS.get(self.module_name or "", {})):
            _deep_merge(merged, pick(pack))
        # паки модуля: {locale: {...}} или плоские
        if self._packs and all(isinstance(v, dict) for v in self._packs.values()):
            _deep_merge(merged, pick(self._packs))
        custom = (getattr(self.kernel, "config", {}) or {}).get("lang_custom", {}) or {}
        for scope in ("global", self.module_name or ""):
            blob = (custom.get(scope) or {}).get(locale, {})
            _deep_merge(merged, blob)
        return merged

    def _group(self) -> Group:
        return Group(self._merged(self.locale))

    @property
    def _active(self) -> Dict[str, Any]:
        """Активный словарь строк текущей локали (поверхность MCUB)."""
        return self._merged(self.locale)

    # -- API как в MCUB --
    def __getitem__(self, key: str) -> Any:
        return self._group()[key]

    def __call__(self, key: str, **kw: Any) -> Any:
        return self._group()(key, **kw)

    def get(self, key: str, default: Any = None) -> Any:
        return self._group().get(key, default)

    def has(self, key: str) -> bool:
        return self._group().has(key)

    @classmethod
    def refresh_all(cls, lang: Optional[str] = None) -> None:
        if lang is not None:
            for inst in cls._instances:
                cfg = getattr(inst.kernel, "config", None)
                if isinstance(cfg, dict):
                    cfg["language"] = lang


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = value


def get_available_locales() -> List[str]:
    locales = {DEFAULT_LOCALE}
    for pack in (GLOBAL_PACK, *MODULE_PACKS.values()):
        locales.update(pack.keys())
    return sorted(locales)


def reload_packs() -> None:
    """Паки встроены в ядро; оставлено для совместимости импортов."""
    return None
