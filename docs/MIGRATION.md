# 🔀 Миграция на новое ядро

## Соответствие старый код → новый

| Было | Стало |
|---|---|
| `core/kernel.py` `HydraKernel` (монолит + телега в импорте) | `hydra_kernel.app.Hydra` (L0+L1+L3), транспорт опционален |
| `core.lib.loader.module_base.ModuleBase` (старая Hydra) | shim `core.lib.loader.module_base` → `hydra_kernel.api.ModuleBase` |
| MCUB class-style `ModuleBase` | тот же shim: декораторы пишут L1-метаданные |
| `kernel.register_inline_handler` / `_callback_handler` | `Hydra.register_inline/register_callback` (общий реестр всех фреймворков) |
| `InlineQueryEvent/InlineResultBuilder` из `telethon_mcub.py` | `hydra_kernel.api.inline` (тот же контракт + фолбэк сообщением) |
| `utils/strings.py` MCUB | `hydra_kernel.api.lang.Strings` (+ кастом `lang_custom`) |
| MCUB `modules/terminal.py` (стриминг, ~1000 строк) | `modules/terminal.py` нового вида (таймаут, кнопки, owner-only) |
| MCUB `modules/translations.py` | работает **без изменений** через адаптер; новый аналог — `modules/translations.py` |
| Hikka/Heroku `loader.Module` | `compat/frameworks.py` shim (`heroku/hikka/dragon`) |

## Как мигрировать свой модуль

1. Импорты: `from hydra_kernel.api import ModuleBase, command, ...`
   (или оставить MCUB-импорты — shim подхватит).
2. Декораторы остаются теми же по имени; добавились `required_level`,
   `aliases` в `@command`.
3. Строки: заменить хардкод на `strings = {"ru": {...}, "en": {...}}` + `self.t`.
4. Кнопки: `self.form(...)` вместо ручной сборки inline.
5. Проверка: `python3 -m hydra_kernel.tools.build`.

## Что не мигрирует автоматически

- Модули с `exec/eval/os.system/subprocess` — блокируются scanner'ом
  (`allow_unsafe=True` в `load_source` — осознанно).
- Пакетные модули Heroku (`from .. import ...`, `herokutl`) — это внутренности
  Heroku, а не модуль; запускать в родном ядре Heroku.

## Проверено сборкой

- настоящий MCUB-модуль `translations.py` — без изменений;
- новый набор `modules/` (6 модулей) — lang, кнопки, терминал, settings, help;
- цели `hydra / mcub / mcub-class / hikka / heroku / heroku-rich / dragon`.
