# modules/approve.py
# meta: name=approve version=1.0.0 author=hydra-team framework=mcub
# MCUB-модуль для управления доверенными пользователями
# Теперь полноценный ModuleBase — кнопки через self.Button.inline

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from telethon import events
from core.lib.loader.module_base import ModuleBase, callback, command
from core.lib.loader.module_config import Boolean, ConfigValue, Integer, ModuleConfig
from utils.misc import edit_or_reply

logger = logging.getLogger("approve")

# ============================================================
# КАТЕГОРИИ ПРАВ
# ============================================================

ACCESS_CATEGORIES = {
    "loader": {
        "label": "Загрузчик модулей",
        "desc": "установка/выгрузка модулей, компиляция, зависимости",
        "commands": [
            "lm", "unlm", "hmods", "mcubmods", "compile", "compileall",
            "modinfo", "deps", "mload", "mun", "mls", "mhelp", "mcfg",
        ],
    },
    "config": {
        "label": "Конфиг",
        "desc": "настройки модулей через .cfg",
        "commands": ["cfg"],
    },
    "terminal": {
        "label": "Терминал",
        "desc": "shell-команды в chroot-окружении сервера",
        "commands": [
            "terminal", "term", "shell", "exec", "neofetch",
            "terminal_info", "terminal_pwd", "terminal_ls",
            "terminal_whoami", "terminal_uname", "terminal_df",
        ],
    },
    "inline": {
        "label": "Inline / кнопки",
        "desc": "мост кнопок MCUB: .cb, .iq, .it",
        "commands": ["cb", "iq", "it"],
    },
    "info": {
        "label": "Инфо и утилиты",
        "desc": "статус бота, пинг, язык, помощь — низкий риск",
        "commands": [
            "ping", "info", "start", "serverinfo", "sysinfo",
            "help", "modules", "find", "popular", "allcmds",
            "lang", "languages", "mylang",
        ],
    },
    "security": {
        "label": "Безопасность",
        "desc": "управление доверенными пользователями",
        "commands": ["approve", "decline", "trustlist", "untrust", "access"],
    },
}

_CMD_TO_CAT: dict = {}
for _cat_key, _cat_info in ACCESS_CATEGORIES.items():
    for _cmd in _cat_info.get("commands", []):
        _CMD_TO_CAT[_cmd] = _cat_key

_CATEGORY_ROWS = [
    ("loader", "config"),
    ("terminal", "inline"),
    ("info", "security"),
]

PRESETS = {
    "guest": {"label": "👤 Гость", "access": {k: (k == "info") for k in ACCESS_CATEGORIES}},
    "trusted": {"label": "🤝 Доверенный", "access": {k: (k in ("info", "config", "inline")) for k in ACCESS_CATEGORIES}},
    "admin": {"label": "🛡 Админ", "access": {k: True for k in ACCESS_CATEGORIES}},
}

TTL = 600

# ============================================================
# ХРАНИЛИЩЕ
# ============================================================

DATA_DIR = Path("data")
TRUSTED_FILE = DATA_DIR / "approve_trusted.json"
ACCESS_FILE = DATA_DIR / "approve_access.json"


def _load(path: Path, default):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_trusted_list() -> list:
    return _load(TRUSTED_FILE, [])


def save_trusted_list(users: list) -> None:
    _save(TRUSTED_FILE, users)


def add_trusted(user_id: int) -> bool:
    users = get_trusted_list()
    if user_id in users:
        return False
    users.append(user_id)
    save_trusted_list(users)
    return True


def remove_trusted(user_id: int) -> bool:
    users = get_trusted_list()
    if user_id not in users:
        return False
    users.remove(user_id)
    save_trusted_list(users)
    return True


def get_all_access() -> dict:
    return _load(ACCESS_FILE, {})


def get_access(user_id: int) -> dict:
    all_access = get_all_access()
    stored = all_access.get(str(user_id), {})
    return {cat: bool(stored.get(cat, False)) for cat in ACCESS_CATEGORIES}


def save_access(user_id: int, access: dict) -> None:
    all_access = get_all_access()
    all_access[str(user_id)] = access
    _save(ACCESS_FILE, all_access)


# ============================================================
# МОДУЛЬ
# ============================================================

class Approve(ModuleBase):
    name = "Approve"
    version = "2.0"
    author = "Hydra"
    description = {
        "en": "Trusted users and access control.",
        "ru": "Доверенные пользователи и управление доступом.",
    }

    strings = {
        "approve_usage": "Ответьте <code>.approve</code> на сообщение пользователя.",
        "decline_usage": "Ответьте <code>.decline</code> на сообщение пользователя.",
        "untrust_usage": "<code>.untrust</code> (reply) или <code>.untrust ID</code>",
        "access_usage": (
            "<code>.access</code> (reply) — показать права\n"
            "<code>.access ID категория on|off</code>\n"
            "<code>.access ID preset guest|trusted|admin</code>"
        ),
        "no_user": "Не удалось определить пользователя.",
        "only_owner": "Только владелец.",
        "btn_approve": "✅ Одобрить",
        "btn_decline": "🚫 Отклонить",
        "btn_allow_all": "✅ Разрешить всё",
        "btn_deny_all": "🚫 Запретить всё",
        "btn_close": "❌ Закрыть",
        "trusted_empty": "📋 Список доверенных пуст.",
        "trusted_list": "📋 <b>Доверенные пользователи:</b>",
        "removed": "🚫 {} удалён(а) из доверенных.",
        "not_trusted": "ℹ️ {} не был(а) в доверенных.",
        "preset_applied": "✅ Пресет «{}» применён к {}.",
        "unknown_preset": "❌ Неизвестный пресет. Доступны: {}",
        "unknown_cmd": "❌ Не понял команду. Категории: {}",
        "request_text": "❓ Одобрить {} как доверенного пользователя?",
        "declined": "🚫 Запрос от {} отклонён.",
        "already_trusted": "{} уже в доверенных. Настройка прав:",
    }

    # ---------- хелперы ----------

    async def _get_user_display(self, user_id: int) -> str:
        try:
            user = await self.client.get_entity(user_id)
            if getattr(user, "username", None):
                return f"@{user.username}"
            return getattr(user, "first_name", None) or str(user_id)
        except Exception:
            return str(user_id)

    def _is_owner(self, sender_id: int) -> bool:
        return sender_id == self.kernel.ADMIN_ID

    def _build_access_text(self, user_display: str, access: dict) -> str:
        lines = [f"🔐 <b>Доступ пользователя {user_display}</b>"]
        body = []
        for cat_key, cat_info in ACCESS_CATEGORIES.items():
            allowed = access.get(cat_key, False)
            icon = "✅" if allowed else "🚫"
            state = "разрешено" if allowed else "запрещено"
            body.append(f"{icon} {cat_info['label']} — <em>{state}</em>\n└ {cat_info['desc']}")
        lines.append("<blockquote expandable>" + "\n".join(body) + "</blockquote>")
        lines.append("Нажмите категорию ниже (команда .cb N), чтобы переключить доступ.")
        return "\n".join(lines)

    def _build_access_buttons(self, user_id: int, access: dict) -> list:
        rows = []

        for row_cats in _CATEGORY_ROWS:
            row = []
            for cat_key in row_cats:
                cat_info = ACCESS_CATEGORIES[cat_key]
                allowed = access.get(cat_key, False)
                icon = "✅" if allowed else "🚫"
                row.append(
                    self.Button.inline(
                        f"{icon} {cat_info['label']}",
                        self._cb_toggle_cat,
                        data={"uid": user_id, "cat": cat_key},
                    )
                )
            rows.append(row)

        preset_row = []
        for preset_key, preset_info in PRESETS.items():
            preset_row.append(
                self.Button.inline(
                    preset_info["label"],
                    self._cb_preset,
                    data={"uid": user_id, "preset": preset_key},
                )
            )
        rows.append(preset_row)

        rows.append([
            self.Button.inline(self.strings["btn_allow_all"], self._cb_allow_all, data={"uid": user_id}),
            self.Button.inline(self.strings["btn_deny_all"], self._cb_deny_all, data={"uid": user_id}),
        ])
        rows.append([
            self.Button.inline(self.strings["btn_close"], self._cb_close, data={"uid": user_id}),
        ])

        return rows

    # ---------- колбэки ----------

    @callback()
    async def _cb_approve(self, event: events.CallbackQuery.Event, data: dict | None = None) -> None:
        if not data or not self._is_owner(event.sender_id):
            await event.answer(self.strings["only_owner"], alert=True)
            return
        uid = data.get("uid")
        add_trusted(uid)
        access = get_access(uid)
        name = await self._get_user_display(uid)
        await event.edit(
            self._build_access_text(name, access),
            buttons=self._build_access_buttons(uid, access),
            parse_mode="html",
        )

    @callback()
    async def _cb_decline(self, event: events.CallbackQuery.Event, data: dict | None = None) -> None:
        if not data or not self._is_owner(event.sender_id):
            await event.answer(self.strings["only_owner"], alert=True)
            return
        uid = data.get("uid")
        name = await self._get_user_display(uid)
        await event.edit(f"🚫 Запрос от {name} отклонён.", parse_mode="html")

    @callback()
    async def _cb_toggle_cat(self, event: events.CallbackQuery.Event, data: dict | None = None) -> None:
        if not data or not self._is_owner(event.sender_id):
            await event.answer(self.strings["only_owner"], alert=True)
            return
        uid = data.get("uid")
        cat_key = data.get("cat")
        cur = get_access(uid)
        cur[cat_key] = not cur.get(cat_key, False)
        save_access(uid, cur)
        name = await self._get_user_display(uid)
        await event.edit(
            self._build_access_text(name, cur),
            buttons=self._build_access_buttons(uid, cur),
            parse_mode="html",
        )

    @callback()
    async def _cb_preset(self, event: events.CallbackQuery.Event, data: dict | None = None) -> None:
        if not data or not self._is_owner(event.sender_id):
            await event.answer(self.strings["only_owner"], alert=True)
            return
        uid = data.get("uid")
        preset_key = data.get("preset")
        new_access = dict(PRESETS[preset_key]["access"])
        save_access(uid, new_access)
        name = await self._get_user_display(uid)
        await event.edit(
            self.strings["preset_applied"].format(PRESETS[preset_key]["label"], name) + "\n\n"
            + self._build_access_text(name, new_access),
            buttons=self._build_access_buttons(uid, new_access),
            parse_mode="html",
        )

    @callback()
    async def _cb_allow_all(self, event: events.CallbackQuery.Event, data: dict | None = None) -> None:
        if not data or not self._is_owner(event.sender_id):
            await event.answer(self.strings["only_owner"], alert=True)
            return
        uid = data.get("uid")
        full = dict.fromkeys(ACCESS_CATEGORIES, True)
        save_access(uid, full)
        name = await self._get_user_display(uid)
        await event.edit(
            self._build_access_text(name, full),
            buttons=self._build_access_buttons(uid, full),
            parse_mode="html",
        )

    @callback()
    async def _cb_deny_all(self, event: events.CallbackQuery.Event, data: dict | None = None) -> None:
        if not data or not self._is_owner(event.sender_id):
            await event.answer(self.strings["only_owner"], alert=True)
            return
        uid = data.get("uid")
        none_ = dict.fromkeys(ACCESS_CATEGORIES, False)
        save_access(uid, none_)
        name = await self._get_user_display(uid)
        await event.edit(
            self._build_access_text(name, none_),
            buttons=self._build_access_buttons(uid, none_),
            parse_mode="html",
        )

    @callback()
    async def _cb_close(self, event: events.CallbackQuery.Event, data: dict | None = None) -> None:
        if not self._is_owner(event.sender_id):
            await event.answer(self.strings["only_owner"], alert=True)
            return
        try:
            await event.delete()
        except Exception:
            pass

    # ---------- команды ----------

    @command(
        "approve",
        doc_en="Approve a user by reply.",
        doc_ru="Одобрить пользователя, ответив на сообщение.",
    )
    async def approve_cmd(self, event: events.NewMessage.Event) -> None:
        if not event.is_reply:
            await edit_or_reply(event, f"<b>Использование:</b> {self.strings['approve_usage']}", parse_mode="HTML")
            return

        reply = await event.get_reply_message()
        if not reply or not reply.sender_id:
            await edit_or_reply(event, self.strings["no_user"])
            return

        uid = reply.sender_id
        name = await self._get_user_display(uid)

        if uid in get_trusted_list():
            access = get_access(uid)
            await event.edit(
                self.strings["already_trusted"].format(name) + "\n\n"
                + self._build_access_text(name, access),
                buttons=self._build_access_buttons(uid, access),
                parse_mode="html",
            )
            return

        text = self.strings["request_text"].format(name)
        buttons = [[
            self.Button.inline(self.strings["btn_approve"], self._cb_approve, data={"uid": uid}),
            self.Button.inline(self.strings["btn_decline"], self._cb_decline, data={"uid": uid}),
        ]]
        await event.edit(text, buttons=buttons, parse_mode="html")

    @command(
        "decline",
        doc_en="Decline a user request by reply.",
        doc_ru="Отклонить запрос пользователя.",
    )
    async def decline_cmd(self, event: events.NewMessage.Event) -> None:
        if not event.is_reply:
            await edit_or_reply(event, f"<b>Использование:</b> {self.strings['decline_usage']}", parse_mode="HTML")
            return
        reply = await event.get_reply_message()
        if not reply or not reply.sender_id:
            await edit_or_reply(event, self.strings["no_user"])
            return
        name = await self._get_user_display(reply.sender_id)
        await edit_or_reply(event, self.strings["declined"].format(name))

    @command(
        "trustlist",
        doc_en="Show trusted users list.",
        doc_ru="Показать список доверенных.",
    )
    async def trustlist_cmd(self, event: events.NewMessage.Event) -> None:
        users = get_trusted_list()
        if not users:
            await edit_or_reply(event, self.strings["trusted_empty"])
            return
        lines = [self.strings["trusted_list"], ""]
        for uid in users:
            name = await self._get_user_display(uid)
            lines.append(f"• {name} (<code>{uid}</code>)")
        await edit_or_reply(event, "\n".join(lines), parse_mode="HTML")

    @command(
        "untrust",
        doc_en="Remove user from trusted list.",
        doc_ru="Убрать пользователя из доверенных.",
    )
    async def untrust_cmd(self, event: events.NewMessage.Event) -> None:
        uid = None
        if event.is_reply:
            reply = await event.get_reply_message()
            if reply:
                uid = reply.sender_id
        else:
            args = event.text.split(maxsplit=1)
            if len(args) > 1 and args[1].strip().lstrip("-").isdigit():
                uid = int(args[1].strip())

        if uid is None:
            await edit_or_reply(event, f"<b>Использование:</b> {self.strings['untrust_usage']}", parse_mode="HTML")
            return

        name = await self._get_user_display(uid)
        if remove_trusted(uid):
            await edit_or_reply(event, self.strings["removed"].format(name))
        else:
            await edit_or_reply(event, self.strings["not_trusted"].format(name))

    @command(
        "access",
        doc_en="Show or configure user access rights.",
        doc_ru="Показать/настроить права доверенного пользователя.",
    )
    async def access_cmd(self, event: events.NewMessage.Event) -> None:
        text = event.text.strip()
        target_uid = None
        rest = text

        if event.is_reply:
            reply = await event.get_reply_message()
            if reply:
                target_uid = reply.sender_id
            rest = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
        else:
            import re as _re
            m = _re.match(r"^\.access\s+(-?\d+)\s*(.*)$", text)
            if m:
                target_uid = int(m.group(1))
                rest = m.group(2)
            else:
                await edit_or_reply(
                    event,
                    f"<b>Использование:</b>\n{self.strings['access_usage']}",
                    parse_mode="HTML",
                )
                return

        if target_uid is None:
            await edit_or_reply(event, self.strings["no_user"])
            return

        name = await self._get_user_display(target_uid)
        rest = rest.strip()

        if not rest:
            access = get_access(target_uid)
            await event.edit(
                self._build_access_text(name, access),
                buttons=self._build_access_buttons(target_uid, access),
                parse_mode="html",
            )
            return

        parts = rest.split()

        if parts[0].lower() == "preset" and len(parts) > 1:
            preset_key = parts[1].lower()
            if preset_key not in PRESETS:
                await edit_or_reply(
                    event,
                    self.strings["unknown_preset"].format(", ".join(PRESETS.keys()))
                )
                return
            new_access = dict(PRESETS[preset_key]["access"])
            save_access(target_uid, new_access)
            await event.edit(
                self.strings["preset_applied"].format(PRESETS[preset_key]["label"], name) + "\n\n"
                + self._build_access_text(name, new_access),
                buttons=self._build_access_buttons(target_uid, new_access),
                parse_mode="html",
            )
            return

        if len(parts) >= 2 and parts[0].lower() in ACCESS_CATEGORIES and parts[1].lower() in ("on", "off"):
            cat_key = parts[0].lower()
            value = parts[1].lower() == "on"
            access = get_access(target_uid)
            access[cat_key] = value
            save_access(target_uid, access)
            await event.edit(
                self._build_access_text(name, access),
                buttons=self._build_access_buttons(target_uid, access),
                parse_mode="html",
            )
            return

        await edit_or_reply(
            event,
            self.strings["unknown_cmd"].format(", ".join(ACCESS_CATEGORIES.keys()))
        )
