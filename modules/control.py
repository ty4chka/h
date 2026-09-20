# meta: name=control version=1.0.0 author=hydra-team framework=hydra
"""Built-in discovery and legacy-MCUB management commands.

The old access menu documented these commands, but the unified startup path
never registered them.  Keeping them as a normal Hydra module means their
commands use the same transport, permissions and registry as every other
loaded module; no second ``mcub_engine`` dispatcher is started.
"""

from __future__ import annotations

import asyncio
import html
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from hydra_kernel.api import ModuleBase, OWNER, command, watcher
from hydra_kernel.pkg.loader import detect_framework
from hydra_kernel.pkg.manifest import parse_manifest


MCUB_MODULES_DIR = Path(__file__).resolve().parent / "mcub_mods"
_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_]+")


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _safe_module_name(value: str, fallback: str) -> str:
    name = Path(str(value or "")).name
    if name.lower().endswith(".py"):
        name = name[:-3]
    name = _SAFE_NAME.sub("_", name).strip("_").lower()
    if not name:
        name = fallback
    if name[0].isdigit():
        name = f"mcub_{name}"
    return name[:80]


def _trim_html(text: str, limit: int = 3900) -> str:
    """Telegram messages are bounded; keep markup intact enough for a list."""

    return text if len(text) <= limit else text[: limit - 20] + "\n<i>… список сокращён</i>"


class Control(ModuleBase):
    """User-visible runtime status plus compatibility MCUB management."""

    name = "control"
    version = "1.0.0"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._usage: Counter[str] = Counter()
        # Tests and embedders can redirect only dynamically installed modules
        # without changing the checked-in ``modules/mcub_mods`` directory.
        self.modules_dir = MCUB_MODULES_DIR

    # ---------------------------------------------------------------- status
    def _command_names(self) -> list[str]:
        hydra = self.kernel
        names = {str(name).lower() for name in hydra.command_handlers}
        names.update(str(name).lower() for name in hydra.aliases)
        return sorted(name for name in names if name)

    def _records(self):
        return list(getattr(self.kernel.registry, "_records", {}).values())

    @staticmethod
    def _command_from_event(event: Any) -> str:
        text = str(getattr(event, "text", "") or "").strip()
        prefix = "."
        if not text.startswith(prefix):
            return ""
        return text[len(prefix) :].split(maxsplit=1)[0].lower()

    @watcher(incoming=False, outgoing=True)
    async def _track_usage(self, event) -> None:
        command_name = self._command_from_event(event)
        if command_name and command_name in self._command_names():
            self._usage[command_name] += 1

    @command("info", desc="статус единого ядра", required_level=OWNER)
    async def cmd_info(self, event) -> None:
        frameworks = Counter(record.framework for record in self._records())
        framework_text = ", ".join(
            f"<code>{_escape(name)}</code>: {count}"
            for name, count in sorted(frameworks.items())
        ) or "—"
        uptime = max(0, int(self.ctx.runtime.uptime))
        hours, rest = divmod(uptime, 3600)
        minutes, seconds = divmod(rest, 60)
        await event.edit(
            "<b>ℹ️ HYDRA</b>\n"
            f"<blockquote>⏳ Аптайм: <code>{hours:02d}:{minutes:02d}:{seconds:02d}</code>\n"
            f"📦 Модулей: <code>{len(self._records())}</code>\n"
            f"⌨️ Команд: <code>{len(self._command_names())}</code>\n"
            f"🔹 Префикс: <code>{_escape(self.prefix)}</code></blockquote>\n"
            f"<b>Адаптеры:</b> {framework_text}\n\n"
            "<i>.modules — модули · .allcmds — команды · .find &lt;текст&gt;</i>"
        )

    @command("diag", desc="диагностика маршрутизации и задержек", required_level=OWNER)
    async def cmd_diag(self, event) -> None:
        """Show bounded, non-secret transport counters for live diagnosis."""

        getter = getattr(self.ctx.transport, "diagnostics", None)
        snapshot = getter() if callable(getter) else {}
        if not snapshot:
            await event.edit(
                "<b>🩺 HYDRA diagnostics</b>\n"
                "<blockquote>Этот транспорт не публикует live-метрики.</blockquote>\n"
                "<i>Полные ошибки: data/hydra.log</i>"
            )
            return

        def value(name: str, default: str = "—") -> str:
            raw = snapshot.get(name, default)
            return _escape(default if raw is None else raw)

        await event.edit(
            "<b>🩺 HYDRA diagnostics</b>\n"
            "<blockquote>"
            f"📨 Updates: <code>{value('updates', 0)}</code> · matched: "
            f"<code>{value('matched_handlers', 0)}</code>\n"
            f"🧩 Logical subscriptions: <code>{value('subscriptions', 0)}</code> "
            f"(<code>{value('patterned_subscriptions', 0)}</code> pattern, "
            f"<code>{value('watcher_subscriptions', 0)}</code> watcher)\n"
            f"🔌 shared native handlers: <code>{value('native_message_handlers', 0)}</code> · "
            f"all client NewMessage: <code>{value('client_new_message_handlers', '?')}</code>\n"
            f"⚠️ Handler errors: <code>{value('failed_handlers', 0)}</code> · "
            f"slow handlers: <code>{value('slow_handlers', 0)}</code> · "
            f"slow updates: <code>{value('slow_updates', 0)}</code>\n"
            f"📡 Slow Telegram RPCs: <code>{value('slow_rpcs', 0)}</code>\n"
            f"⏱ Thresholds: handler <code>{value('slow_handler_threshold_ms')} ms</code>, "
            f"RPC <code>{value('slow_rpc_threshold_ms')} ms</code>"
            "</blockquote>\n"
            f"<b>Last slow handler:</b> <code>{value('last_slow_handler')}</code>\n"
            f"<b>Last slow update:</b> <code>{value('last_slow_update')}</code>\n"
            f"<b>Last slow RPC:</b> <code>{value('last_slow_rpc')}</code>\n"
            f"<b>Last handler error:</b> <code>{value('last_error')}</code>\n\n"
            "<i>Full traces: data/hydra.log · thresholds: HYDRA_SLOW_HANDLER_MS / HYDRA_SLOW_RPC_MS</i>"
        )

    @command("modules", desc="список загруженных модулей", required_level=OWNER)
    async def cmd_modules(self, event) -> None:
        query = self.args_raw(event).strip().lower()
        records = self._records()
        if query:
            records = [
                record
                for record in records
                if query in record.name.lower()
                or query in str(getattr(record.module, "name", "")).lower()
                or query in record.framework.lower()
            ]
        if not records:
            await event.edit("<b>📦 Модули не найдены</b>")
            return
        lines = [f"<b>📦 Модули ({len(records)}):</b>"]
        for record in sorted(records, key=lambda item: item.name.lower()):
            version = record.manifest.version
            lines.append(
                f"• <code>{_escape(record.name)}</code> — "
                f"{_escape(record.framework)} <i>v{_escape(version)}</i>"
            )
        await event.edit(_trim_html("\n".join(lines)))

    @command("allcmds", desc="список доступных команд", required_level=OWNER)
    async def cmd_allcmds(self, event) -> None:
        commands = self._command_names()
        if not commands:
            await event.edit("<b>⌨️ Команды ещё не зарегистрированы</b>")
            return
        rows = []
        for start in range(0, len(commands), 8):
            rows.append(" · ".join(f"<code>{_escape(self.prefix)}{_escape(name)}</code>" for name in commands[start : start + 8]))
        await event.edit(_trim_html(
            f"<b>⌨️ Все команды ({len(commands)}):</b>\n\n" + "\n".join(rows)
        ))

    @command("find", desc="найти модуль или команду", required_level=OWNER)
    async def cmd_find(self, event) -> None:
        query = self.args_raw(event).strip().lower()
        if not query:
            await event.edit("<code>.find &lt;команда или модуль&gt;</code>")
            return
        commands = [name for name in self._command_names() if query in name.lower()]
        records = [
            record for record in self._records()
            if query in record.name.lower()
            or query in str(getattr(record.module, "name", "")).lower()
        ]
        if not commands and not records:
            await event.edit(f"<b>🔎 По запросу <code>{_escape(query)}</code> ничего не найдено</b>")
            return
        lines = [f"<b>🔎 Результаты для <code>{_escape(query)}</code>:</b>"]
        if commands:
            lines.append("<b>Команды:</b> " + " · ".join(
                f"<code>{_escape(self.prefix)}{_escape(name)}</code>" for name in commands
            ))
        if records:
            lines.append("<b>Модули:</b> " + " · ".join(
                f"<code>{_escape(record.name)}</code>" for record in records
            ))
        await event.edit(_trim_html("\n".join(lines)))

    @command("popular", desc="недавно используемые команды", required_level=OWNER)
    async def cmd_popular(self, event) -> None:
        entries = [(name, count) for name, count in self._usage.most_common(12) if count]
        if not entries:
            await event.edit(
                "<b>📈 Пока нет истории команд</b>\n"
                "<i>История собирается в текущем запуске Hydra.</i>"
            )
            return
        lines = ["<b>📈 Часто используемые команды:</b>"]
        lines.extend(
            f"• <code>{_escape(self.prefix)}{_escape(name)}</code> — <code>{count}</code>"
            for name, count in entries
        )
        await event.edit("\n".join(lines))

    # ----------------------------------------------------------- MCUB manager
    def _mcub_interface(self):
        try:
            return self.kernel.loader.adapter_for("mcub").iface
        except Exception:
            return None

    def _record_for(self, name: str, *, mcub_only: bool = False):
        needle = str(name or "").strip().lower()
        if not needle:
            return None
        for record in self._records():
            if mcub_only and record.framework != "mcub":
                continue
            candidates = {
                record.name,
                str(getattr(record.module, "name", "")),
                str(getattr(type(record.module), "__module__", "")),
            }
            if needle in {candidate.lower() for candidate in candidates if candidate}:
                return record
        return None

    def _stored_paths(self, record, requested_name: str = "") -> set[Path]:
        """Possible persisted source paths for a loaded MCUB record.

        A ``# meta: name=...`` may intentionally differ from the downloaded
        filename, so record.name alone is not enough for ``.mls``/``.mun``.
        """

        names = {
            record.name,
            requested_name,
            str(getattr(record.module, "name", "")),
            str(getattr(type(record.module), "__module__", "")),
        }
        return {
            self.modules_dir / f"{_safe_module_name(name, 'module')}.py"
            for name in names
            if name
        }

    def _mcub_commands(self, record) -> tuple[list[str], dict[str, list[str]], dict[str, str]]:
        iface = self._mcub_interface()
        if iface is None:
            return [], {}, {}
        try:
            return iface._loader.get_module_commands(record.name)
        except Exception:
            pass
        names = {
            record.name,
            str(getattr(record.module, "name", "")),
            str(getattr(type(record.module), "__module__", "")),
        }
        commands = [
            command_name
            for command_name, owner in getattr(iface, "command_owners", {}).items()
            if str(owner) in names
        ]
        return commands, {}, {}

    @command("mls", desc="список MCUB-модулей", required_level=OWNER)
    async def cmd_mls(self, event) -> None:
        records = [record for record in self._records() if record.framework == "mcub"]
        if not records:
            await event.edit(
                "<b>🧩 MCUB-модули не загружены</b>\n"
                "<i>Установить: reply на .py + <code>.mload</code></i>"
            )
            return
        lines = [f"<b>🧩 MCUB-модули ({len(records)}):</b>"]
        for record in sorted(records, key=lambda item: item.name.lower()):
            commands, _, _ = self._mcub_commands(record)
            saved = any(path.is_file() for path in self._stored_paths(record))
            marker = "💾" if saved else "•"
            lines.append(
                f"{marker} <code>{_escape(record.name)}</code> — "
                f"команд: <code>{len(commands)}</code>"
            )
        lines.append("\n<i>.mhelp &lt;модуль&gt; — команды · .mun &lt;модуль&gt; --del — удалить файл</i>")
        await event.edit(_trim_html("\n".join(lines)))

    @command("mhelp", desc="помощь по MCUB-модулю", required_level=OWNER)
    async def cmd_mhelp(self, event) -> None:
        name = self.args_raw(event).strip()
        if not name:
            await event.edit(
                "<b>🧩 MCUB в едином Hydra-движке</b>\n\n"
                f"<code>{_escape(self.prefix)}mload</code> — установить MCUB-модуль (reply/URL)\n"
                f"<code>{_escape(self.prefix)}mls</code> — список MCUB-модулей\n"
                f"<code>{_escape(self.prefix)}mhelp &lt;name&gt;</code> — команды модуля\n"
                f"<code>{_escape(self.prefix)}mcfg &lt;name&gt;</code> — конфиг модуля\n"
                f"<code>{_escape(self.prefix)}mun &lt;name&gt;</code> — выгрузить модуль\n\n"
                "<i>.mload принимает только MCUB-совместимый исходник; для остальных форматов используйте .lm.</i>"
            )
            return
        record = self._record_for(name, mcub_only=True)
        if record is None:
            await event.edit(f"❌ MCUB-модуль <code>{_escape(name)}</code> не найден")
            return
        commands, aliases, descriptions = self._mcub_commands(record)
        if not commands:
            await event.edit(f"<b>📦 {_escape(record.name)}</b>\n<i>Команды не зарегистрированы.</i>")
            return
        lines = [f"<b>📦 {_escape(record.name)} — команды:</b>"]
        for command_name in sorted(commands):
            alias_text = aliases.get(command_name, [])
            alias_suffix = (
                " (" + ", ".join(f"{self.prefix}{alias}" for alias in alias_text) + ")"
                if alias_text else ""
            )
            description = descriptions.get(command_name, "")
            suffix = f" — {_escape(description)}" if description else ""
            lines.append(
                f"• <code>{_escape(self.prefix)}{_escape(command_name)}</code>"
                f"{_escape(alias_suffix)}{suffix}"
            )
        await event.edit(_trim_html("\n".join(lines)))

    async def _read_mload_source(self, event) -> tuple[str, str, str]:
        """Return source, safe suggested file stem and source label."""

        argument = self.args_raw(event).strip()
        if argument:
            parsed = urlparse(argument)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("укажите http(s)-ссылку или ответьте на .py-файл/текст")
            source = await asyncio.to_thread(self._download_source, argument)
            return source, _safe_module_name(parsed.path.rsplit("/", 1)[-1], "mcub_url"), "URL"

        reply = await event.get_reply_message()
        if reply is None:
            raise ValueError("reply на .py-файл/текст или <code>.mload &lt;URL&gt;</code>")

        document = getattr(reply, "document", None)
        if document is not None:
            download = getattr(reply, "download_media", None)
            if not callable(download):
                raise ValueError("Telegram не дал скачать приложенный файл")
            path = await download()
            if not path:
                raise ValueError("не удалось скачать приложенный файл")
            path_obj = Path(str(path))
            try:
                data = await asyncio.to_thread(path_obj.read_bytes)
            finally:
                try:
                    await asyncio.to_thread(path_obj.unlink)
                except OSError:
                    pass
            if len(data) > _MAX_SOURCE_BYTES:
                raise ValueError("файл больше 2 MiB")
            filename = getattr(document, "file_name", "")
            for attribute in getattr(document, "attributes", ()) or ():
                filename = filename or getattr(attribute, "file_name", "")
            return data.decode("utf-8-sig", errors="replace"), _safe_module_name(filename, "mcub_file"), "файл"

        text = getattr(reply, "raw_text", None) or getattr(reply, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("в ответе нет исходного кода")
        if len(text.encode("utf-8")) > _MAX_SOURCE_BYTES:
            raise ValueError("текст больше 2 MiB")
        fallback = f"mcub_{getattr(reply, 'id', int(time.time()))}"
        return text, _safe_module_name(fallback, "mcub_text"), "текст"

    @staticmethod
    def _download_source(url: str) -> str:
        request = Request(url, headers={"User-Agent": "Hydra-MCUB-loader/1.0"})
        with urlopen(request, timeout=20) as response:  # noqa: S310 - owner-supplied https/http URL
            data = response.read(_MAX_SOURCE_BYTES + 1)
        if len(data) > _MAX_SOURCE_BYTES:
            raise ValueError("загруженный файл больше 2 MiB")
        return data.decode("utf-8-sig", errors="replace")

    async def _install_mcub_source(self, suggested_name: str, source: str):
        if len(source.strip()) < 10:
            raise ValueError("пустой исходный код")
        if detect_framework(source) != "mcub":
            raise ValueError("это не MCUB-модуль; для других форматов используйте .lm")
        module_name = _safe_module_name(suggested_name, "mcub_module")
        manifest = parse_manifest(module_name, source)
        if self.kernel.registry.get(manifest.name) is not None:
            raise ValueError(
                f"модуль <code>{_escape(manifest.name)}</code> уже загружен; "
                "сначала выполните <code>.mun &lt;name&gt;</code>"
            )
        self.modules_dir.mkdir(parents=True, exist_ok=True)
        target = self.modules_dir / f"{module_name}.py"
        if target.exists():
            raise ValueError(
                f"файл <code>{_escape(target.name)}</code> уже существует; "
                "сначала выполните <code>.mun &lt;name&gt; --del</code>"
            )
        record = await self.kernel.loader.load_source(
            module_name,
            source,
            framework="mcub",
            allow_unsafe=False,
            file_path=str(target),
        )
        try:
            target.write_text(source, encoding="utf-8")
        except Exception:
            await self.kernel.loader.unload(record.name)
            raise
        return record, target

    @command("mload", desc="установить MCUB-модуль", required_level=OWNER)
    async def cmd_mload(self, event) -> None:
        try:
            source, name, source_label = await self._read_mload_source(event)
            record, target = await self._install_mcub_source(name, source)
        except Exception as exc:  # User input/network/load errors should stay visible.
            await event.edit(f"<b>❌ .mload:</b> <code>{_escape(exc)}</code>")
            return
        await event.edit(
            f"<b>✅ MCUB-модуль загружен:</b> <code>{_escape(record.name)}</code>\n"
            f"<blockquote>Источник: {_escape(source_label)}\n"
            f"Файл: <code>{_escape(target)}</code>\n"
            f"Помощь: <code>{_escape(self.prefix)}mhelp {_escape(record.name)}</code></blockquote>"
        )

    @command("mun", desc="выгрузить MCUB-модуль", required_level=OWNER)
    async def cmd_mun(self, event) -> None:
        tokens = self.args_raw(event).split()
        if not tokens:
            await event.edit("<code>.mun &lt;name&gt; [--del]</code>")
            return
        name = next((token for token in tokens if not token.startswith("--")), "")
        remove_file = "--del" in tokens
        record = self._record_for(name, mcub_only=True)
        if record is None:
            await event.edit(f"❌ MCUB-модуль <code>{_escape(name)}</code> не найден")
            return
        if not await self.kernel.loader.unload(record.name):
            await event.edit(f"❌ Не удалось выгрузить <code>{_escape(record.name)}</code>")
            return
        deleted = ""
        if remove_file:
            candidates = self._stored_paths(record, name)
            for target in candidates:
                try:
                    if target.is_file() and target.parent.resolve() == self.modules_dir.resolve():
                        target.unlink()
                        deleted = "\n<i>Файл удалён.</i>"
                        break
                except OSError:
                    pass
        await event.edit(f"<b>✅ Выгружен:</b> <code>{_escape(record.name)}</code>{deleted}")

    def _module_config(self, record):
        iface = self._mcub_interface()
        candidates = [
            record.name,
            str(getattr(record.module, "name", "")),
            str(getattr(type(record.module), "__module__", "")),
        ]
        if iface is not None:
            for candidate in candidates:
                config = getattr(iface, "_live_module_configs", {}).get(candidate)
                if config is not None:
                    return candidate, config, iface
        config = getattr(record.module, "config", None)
        return record.name, config, iface

    @command("mcfg", desc="показать или изменить конфиг MCUB-модуля", required_level=OWNER)
    async def cmd_mcfg(self, event) -> None:
        parts = self.args_raw(event).split(maxsplit=2)
        if not parts:
            await event.edit("<code>.mcfg &lt;module&gt; [key] [value]</code>")
            return
        record = self._record_for(parts[0], mcub_only=True)
        if record is None:
            await event.edit(f"❌ MCUB-модуль <code>{_escape(parts[0])}</code> не найден")
            return
        owner, config, iface = self._module_config(record)
        if config is None:
            await event.edit(f"<b>⚙️ У {_escape(record.name)} нет доступного конфига</b>")
            return
        if len(parts) == 1:
            try:
                items = list(config.items())
            except Exception:
                items = []
            if not items:
                await event.edit(f"<b>⚙️ Конфиг {_escape(record.name)} пуст</b>")
                return
            lines = [f"<b>⚙️ Конфиг {_escape(record.name)}:</b>"]
            lines.extend(
                f"• <code>{_escape(key)}</code> = <code>{_escape(value)}</code>"
                for key, value in items
            )
            lines.append(f"\n<i>.mcfg {_escape(record.name)} &lt;key&gt; &lt;value&gt;</i>")
            await event.edit(_trim_html("\n".join(lines)))
            return
        if len(parts) < 3:
            await event.edit("<code>.mcfg &lt;module&gt; &lt;key&gt; &lt;value&gt;</code>")
            return
        key, value = parts[1], parts[2]
        if value.lower() in {"true", "false"}:
            value = value.lower() == "true"
        try:
            config[key] = value
            if iface is not None:
                data = config.to_dict() if hasattr(config, "to_dict") else dict(config.items())
                await iface.save_module_config(owner, data)
        except Exception as exc:
            await event.edit(f"<b>❌ Ошибка валидации:</b> <code>{_escape(exc)}</code>")
            return
        await event.edit(
            f"✅ <code>{_escape(key)}</code> = <code>{_escape(value)}</code>\n"
            f"<i>Конфиг {_escape(record.name)} сохранён.</i>"
        )
