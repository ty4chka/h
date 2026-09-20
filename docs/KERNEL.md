# 🧬 Hydra Kernel — архитектура ядра

Ядро (`hydra_kernel/`) — **отдельный компонент** в репозитории. Hydra и все
совместимые фреймворки — его потребители. Зависимости направлены строго вниз:
`L4 → L3 → L2 → L1 → L0`. Ядро не импортирует ничего из Hydra, MCUB, Hikka и т.д.

## Слои

```
L4  modules/            ping, info, terminal, translations, help, settings
L3  hydra_kernel/pkg    loader · registry · resolver · manifest · scanner
L2  hydra_kernel/compat mcub · hikka · heroku · dragon · legacy hydra
L1  hydra_kernel/api    ModuleBase · config · decorators · permissions ·
                        lifecycle · EventBus · inline · lang
L0  hydra_kernel/kernel transport · db · runtime/logging/loop
```

## L0 — Kernel

- **Transport** — абстракция над Telegram:
  - `NullTransport` — in-memory: `inject()` (входящие), `inject_inline()`,
    `inject_callback()`, очередь `sent`, `deleted`, `inline_answers`,
    `callback_answers`. Позволяет ядру **собираться и проходить smoke без сети**.
  - `TelethonTransport` — боевой (опционален: без telethon пакет импортируется).
    Он держит две shared native-подписки `NewMessage` (incoming/outgoing) и
    маршрутизирует logical command/watcher-подписки внутри ядра, чтобы не
    создавать native callback на каждую команду. `diagnostics()` выдаёт
    secret-free счётчики задержек/ошибок для `.diag`.
  - `Message` — нормализованное сообщение: `reply/edit/delete`, telethon-алиасы
    `message/raw_text/out`.
- **DB** — `MemoryDB` / `JsonDB`: async key-value с пространствами имён.
- **Runtime / logging / loop** — версия, uptime, `setup_logging()`, `run()`.

## L1 — Hydra API

- **ModuleBase** — базовый класс модуля: `self.client/db/bus/config`,
  `self.kernel` (композиция Hydra), `self.t(key, **kw)` и `self.strings(...)`
  (живая локализация, семантика MCUB i18n), `self.args/args_raw`,
  `self.form(chat_id, text, buttons)` — инлайн-форма с кнопками.
- **decorators** — `@command(name, aliases, desc, required_level)`,
  `@watcher`, `@inline_handler`, `@callback(prefix)`, `@loop(interval)`.
- **lifecycle** — сканирует метки, подписывает обработчики на транспорт,
  дёргает хуки `on_load/on_unload/on_install/on_uninstall`, `@method`-setup.
  Ошибки обработчиков логируются и отвечаются пользователю, не валяя ядро.
- **permissions** — уровни GUEST/USER/ADMIN/OWNER; `owner_only` → OWNER.
- **EventBus** — pub/sub `subscribe/emit` с wildcard `*`.
- **inline** — `InlineQueryEvent` (builder.article/photo, `answer()` с фолбэком
  сообщением), `CallbackQueryEvent` (`answer/edit/delete`), `InlineButton`.
- **lang** — см. ниже.

### Роутинг inline (как в MCUB)

- inline-запрос → первое слово = имя хэндлера (`Hydra.register_inline`);
- callback → **самый длинный префикс** data (`Hydra.register_callback`);
- кнопки формы с callable получают уникальный data-префикс автоматически.

### Lang (семантика MCUB `utils/strings.py`)

- `Strings(kernel, packs, module_name)`: `lang['key']`, `lang('key', **kw)`,
  `lang.get`, `lang.has`, `lang.locale`; вложенные группы
  `self.strings('buttons')('close')`;
- активный язык: `kernel.config['language']` (дефолт `ru`), фолбэк ru → первый;
- сливаются: глобальный пак → модульный пак → пак модуля → **кастомные строки**
  `kernel.config['lang_custom'][module|global][locale][key]`;
- `Strings.refresh_all(lang)` переключает живые экземпляры.

## L2 — Compatibility

Адаптер подменяет импорт фреймворка shim-модулями и заворачивает чужой модуль
в L1. Поддерживаемые стили:

| Фреймворк | Стили |
|---|---|
| MCUB | `def register(kernel)`, `kernel.register.command`, class-style `ModuleBase` с `@command/@owner_only/@method/@event`, `self.args/answer/edit/invoke/lookup_module/Button/subinline`, `kernel.*` по kernel.md |
| Hikka / Heroku / Dragon | `from X import loader, utils`, `loader.Module`, `@loader.command/watcher/inline_handler/callback_handler/loop`, `self.inline.form/gallery/list` с callable-кнопками, `utils.escape_html` |
| legacy Hydra | старые пути `core.lib.loader.module_base` |

## L3 — Package system

- **scanner** — AST-анализ до выполнения: `exec/eval/__import__/os.system/subprocess`
  → `SecurityError` (policy), `shutil.rmtree` → warn;
- **manifest** — `# meta: name=.. version=.. requires=a,b framework=..`;
- **resolver** — топологическая сортировка зависимостей, детект циклов;
- **loader** — scan → exec → адаптер → lifecycle → registry; `load_dir()` грузит
  каталог целиком в порядке resolver'а;
- **registry** — реестр загруженных модулей.

## Сборка и проверка

```bash
python3 -m hydra_kernel.tools.build
```

Шаги: `py_compile` ядра, старого `core/` и `mcub_engine`; unit-проверки
resolver/scanner; загрузка **настоящего** `refs/mcub/modules/translations.py`;
прогон нового набора `modules/` (формы, кнопки, терминал, lang,
custom-строки); smoke по целям `hydra / mcub / mcub-class / hikka / heroku /
heroku-rich / dragon`.

Отдельный production-аудит запускает именно путь `modules/mcub.py`: он строит
инвентарь всех команд, загруженных этим диспетчером из `modules/` и
`modules/mcub_mods/`, и падает, если новая команда не получила сценарий. В
текущем наборе это 100 команд: 98
безопасных usage/menu/UI-веток вызываются, а `.compileall` (пишет/компилирует
файлы) и `.restart` (заменяет процесс) регистрируются, но явно
классифицируются как неисполняемые в автоматическом прогоне. Терминал,
сеть/загрузчики и reply/file-зависимые операции в smoke не выдают себя за
боевую проверку: опасные внешние действия замоканы или остаются в указанной
классификации.

Проверка живой доставки команд Telethon использует API-двойник и отдельно
проверяет две shared-подписки `incoming`/`outgoing` (Telethon не допускает их
в одном `NewMessage`), logical fan-out, cleanup и latency telemetry.
Фактический Telegram-сеанс и авторизация Vector-бота требуют
настроенных в окружении учётных данных/токена и должны проверяться отдельно
на боевом аккаунте. Выход 0 означает, что все офлайн-цели зелёные.

## Конфиг ядра

`Hydra.config`: `language`, `lang_custom`, флаги настроек; `save_config()`
пишет `data/kernel_config.json`. Корневой `config.py` читает секреты только
из env/`data/config.json` — в коде их нет.

## Go-часть ядра и нативная компиляция

- **Go-ядро** (`gocore/`): бинарь `hydracore` общается с Python по stdio
  (JSON-строки): `ping`, `ansi_strip`, `sha256`, `read_file`, `write_file`,
  `modules`, `run_module`. Go-модули лежат в `gocore/modules/*` и собираются
  в `gocore/bin/` (`sh tools/build_go.sh`). Python-сторона —
  `hydra_kernel.kernel.gobridge.GoBridge`: стартует бинарь, если он есть,
  иначе ядро работает в чисто питоновом режиме.
- **Cython** (`python3 tools/build_native.py`): компилирует горячие модули
  ядра (`pkg.scanner`, `pkg.resolver`, `api.lang`) в `.so` in-place; импортёр
  автоматически подхватывает нативные версии, фолбэк — чистый Python.
- Оба шага встроены в `python3 -m hydra_kernel.tools.build` (честный SKIP,
  если тулчейна нет).

## Запуск и GUI

`python3 main.py` поднимает ядро, грузит `modules/` и открывает TUI-редактор
(список → просмотр → правка с валидацией и бэкапом). См. `docs/MODULES.md`.
