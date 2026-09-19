# 🔌 Совместимость с фреймворками

Поддерживаются **MCUB** (функциональный и class-style, i18n, kernel-поверхность)
и семейство **Hikka / Heroku / Dragon**, а также legacy Hydra.

Heroku поддерживается **полностью на уровне модулей**: настоящие модули с
пакетными импортами (`from .. import loader, utils, translations`,
`from herokutl.tl.types import Message`) исполняются в синтетическом пакетном
контексте (`heroku.*`, `herokutl.*`) и работают: команды, inline-формы,
callable-кнопки, синхронный `self._db`, `internal_init()`, `strings` с
фолбэком ключа. Проверено настоящим модулем translations (см. ниже).

## Что поддерживается

### MCUB (адаптер `compat/mcub.py` + shim `compat/legacy_hydra.py`)

- функциональный стиль `def register(kernel)` и `kernel.register.command/watcher`;
- class-style: `from core.lib.loader.module_base import ModuleBase, command,
  bot_command, owner_only, permissions, event, method, on_install, on_uninstall,
  inline, callback, watcher, loop`;
- хелперы инстанса: `args/args_raw/args_html/answer/edit(as_html)/reply/invoke/
  lookup_module/require_module/log/Button/subinline.form/inline/get_prefix/get_lang`;
- `Button.inline(text, callback, data=...)` — callable получает `(call, data)`;
- kernel-поверхность по `doc/api/kernel.md`: `loaded_modules, command_handlers,
  inline_handlers, callback_handlers, aliases, custom_prefix, config, client,
  handle_error, inline_form, inline_query_and_click, conversation (context
  manager), db_get/db_set, get/save_module_config, is_admin, log_*, cprint,
  VERSION, start_time, save_config`;
- `utils.strings.Strings` + `get_available_locales` + `reload_packs`
  (семантика `doc/guides/i18n.md`, включая вложенные группы и кастом).

**Проверено настоящим модулем:** MCUB `translations.py` — форма
выбора языка, нажатие кнопки, `.setlang ru` (см. build).

### Hikka / Heroku / Dragon (адаптер `compat/frameworks.py`)

- `from <pkg> import loader, utils`; `loader.Module`, `strings`;
- `@loader.command/watcher/inline_handler/callback_handler/loop/ratelimit/tag`;
- `self.client/db/get_prefix/get_prefixes/lookup/translate/allmodules`;
- `self.inline.form/gallery/list` с кнопками `{"text","callback"}` — callable
  получает `call` (`answer/edit/delete`);
- `utils.escape/escape_html/get_inner_text/edit_or_reply`.

**Проверено:** эталонные и rich-модули (form + callable-кнопка + escape_html).

### legacy Hydra

Старые импорты `core.lib.loader.module_base` работают через shim: те же
декораторы пишут L1-метаданные и подключаются штатным Lifecycle.

## Аппроксимации (честно)

| Что | Как |
|---|---|
| `@event("chataction", ...)` MCUB | сведено к watcher (транспорт L0 — NewMessage-модель) |
| `ratelimit`, `tag` Heroku | no-op метки |
| `conversation.get_response` | требует живой транспорт (NullTransport — NotImplementedError) |
| native inline-ответы | NullTransport записывает в `inline_answers`; TelethonTransport — `event.answer` |
| модули Heroku с пакетными относительными импортами (`from .. import ...`, `herokutl`) | вне офлайн-прогона: это ядро Heroku, а не модуль; покрытие — API-эквивалентность |
