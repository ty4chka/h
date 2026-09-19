# meta: name=translations version=2.0.0 author=hydra-team framework=hydra
"""Hydra new-shape module: language switch + custom strings (MCUB-style i18n)."""

from hydra_kernel.api import ModuleBase, command
from hydra_kernel.api.lang import Strings, get_available_locales


class Translations(ModuleBase):
    name = "translations"
    version = "2.0.0"

    @command("setlang", desc="[ru/en] — переключить язык, без аргументов — форма")
    async def cmd_setlang(self, event):
        arg = self.args_raw(event).strip()
        if arg:
            await self._switch(event, arg)
            return
        rows, row = [], []
        for locale in get_available_locales():
            row.append(
                {
                    "text": self.strings("langbutton").get(f"btn_{locale}", f"🏴 {locale}"),
                    "callback": self.cb_lang,
                    "args": (locale,),
                }
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        await self.form(event.chat_id, f"<b>{self.t('select_language')}</b>", buttons=rows)

    async def _switch(self, event, locale: str):
        if locale not in get_available_locales():
            await self.reply(event, ", ".join(get_available_locales()))
            return
        self.kernel.config["language"] = locale
        self.kernel.save_config()
        Strings.refresh_all(locale)
        await self.reply(event, self.t("lang_changed", lang=locale))

    async def cb_lang(self, call, locale=None):
        if not locale:
            return
        self.kernel.config["language"] = locale
        self.kernel.save_config()
        Strings.refresh_all(locale)
        await call.edit(self.t("lang_changed", lang=locale))

    @command("langset", desc="<module|global> <key> = <text> — кастомная строка")
    async def cmd_langset(self, event):
        raw = self.args_raw(event)
        if "=" not in raw:
            await self.reply(event, "формат: .langset <module|global> <key> = <text>")
            return
        left, _, text = raw.partition("=")
        parts = left.split()
        if len(parts) != 2:
            await self.reply(event, "формат: .langset <module|global> <key> = <text>")
            return
        scope_name, key = parts
        locale = self.kernel.config.get("language", "ru")
        custom = self.kernel.config.setdefault("lang_custom", {})
        scope = custom.setdefault(scope_name, {})
        scope.setdefault(locale, {})[key] = text.strip()
        self.kernel.save_config()
        await self.reply(event, self.strings("ok"))

    @command("reloadlang", desc="перезагрузить языковые пакеты")
    async def cmd_reloadlang(self, event):
        from hydra_kernel.api.lang import reload_packs

        reload_packs()
        await self.reply(event, self.t("reloadlang_done"))
