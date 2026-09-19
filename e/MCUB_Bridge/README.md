# 🧩 MCUB Engine для Hydra UserBot

Полноценная поддержка модулей **MCUB-fork** ([github.com/hairpin01/MCUB-fork](https://github.com/hairpin01/MCUB-fork), модули: [hairpin01/repo-MCUB-fork](https://github.com/hairpin01/repo-MCUB-fork)) в твоём Hydra UserBot.

- ✅ Модули загружаются **без изменения кода** (никакого regex-адаптера)
- ✅ **Все инлайн-кнопки превращаются в команды** и показываются прямо под сообщением
- ✅ Пагинация, переключатели, доски игр — всё обновляется как в настоящем MCUB
- ✅ Работают class-модули (`ModuleBase` + декораторы) и functional-модули (`register(kernel)`)
- ✅ Конфиги, вотчеры, циклы, планировщик, middleware, placeholders, БД — полное ядро

**Проверено:** 34 из 35 модулей repo-MCUB-fork загружаются и работают (98 команд),
35-й (`yamusic`) требует `pip install yandex_music` — зависимость, не баг.

---

## 📦 Установка (3 шага)

Скопируй папки из этого архива в корень Hydra (рядом с `main.py`):

```bash
# из папки MCUB_Bridge в корень Hydra:
cp -r mcub_engine /путь/к/Hydra/
cp -r core_inline /путь/к/Hydra/
cp -r core/lib/loader/module_base.py   /путь/к/Hydra/core/lib/loader/
cp -r core/lib/loader/module_config.py /путь/к/Hydra/core/lib/loader/
cp -r core/lib/loader/decorators.py    /путь/к/Hydra/core/lib/loader/
cp -r core/lib/types /путь/к/Hydra/core/lib/
cp modules/mcub.py /путь/к/Hydra/modules/
```

**Шаг 3 (опционально, но рекомендуется):** замени `modules/hloader.py`
на версию из этого пакета — тогда `.lm` будет автоматически отправлять
MCUB-модули в новый движок (с твоим обычным подтверждением `.y`/`.n`):

```bash
cp modules/hloader.py /путь/к/Hydra/modules/
```

> ⚠️ Замена `module_base.py`/`module_config.py` безопасна: старые классы
> `KernelMock`, `StringsMock`, `DBMock`, `LoopHandle` сохранены —
> существующие Hydra-модули не сломаются.

Перезапусти Hydra. Готово.

---

## 🎮 Как пользоваться

### Установка модулей

| Способ | Команда |
|---|---|
| Reply на `.py` файл | `.mload` |
| По ссылке | `.mload https://.../module.py` |
| Reply на сообщение с кодом | `.mload` |
| Через старый загрузчик | `.lm` (с заменённым hloader.py — само уйдёт в движок) |

Модули лежат в `modules/mcub_mods/` и **автозагружаются при старте**.

### Кнопки → команды

Когда модуль показывает инлайн-кнопки, под сообщением появляется меню:

```
🐻 Мишка готов играть
⚡ Кнопки → команды:
.cb 1 — 🧠 Let's go!
```

- **`.cb 1`** — «нажать» кнопку №1 (команда сама удалится)
- **`.cb`** — показать активное меню ещё раз
- 🔗 URL-кнопки показываются ссылкой
- 🔍 Инлайн-поиск: **`.iq <запрос>`**
- ✏️ Кнопки ввода: **`.it <id> <текст>`**

Меню **обновляется само**: если кнопка меняет сообщение (следующая страница,
ход в игре), нумерация `.cb N` пересчитывается под новое меню.

### Управление

| Команда | Что делает |
|---|---|
| `.mls` | Список MCUB-модулей |
| `.mhelp` | Как работает мост кнопок |
| `.mhelp <name>` | Команды конкретного модуля |
| `.mcfg <name>` | Показать конфиг модуля |
| `.mcfg <name> <key> <value>` | Изменить параметр (с валидацией) |
| `.mun <name>` | Выгрузить модуль |
| `.mun <name> --del` | Выгрузить + удалить файл |

Команды MCUB-модулей также попадают в общий `.help` Hydra.

---

## 🏗 Архитектура

```
mcub_engine/           ← эмуляция ядра MCUB поверх Telethon Hydra
├── runtime.py         ← McubKernel: register, config, db, cache, scheduler,
│                        middleware, inline_form, handle_error, Colors...
├── proxies.py         ← ClientProxy/EventProxy (перехват кнопок),
│                        CallbackEventMock, InlineQueryEventMock...
├── bridge.py          ← мост «кнопка → команда .cb N» + рендер меню
├── loader.py          ← загрузчик class/functional модулей (код не меняется)
└── utils_inject.py    ← MCUB-API внутрь пакета utils Hydra (answer,
                         parse_arguments, placeholders, arg_parser...)

core/lib/loader/       ← ТОЧНЫЕ порты из MCUB-fork (MIT):
├── module_base.py     ← ModuleBase + все декораторы + ButtonFactory
├── module_config.py   ← ModuleConfig + все валидаторы (оригинал)
└── decorators.py      ← @command/@inline/@callback/@watcher... (оригинал)

core_inline/           ← make_cb_button и др.
modules/mcub.py        ← Hydra-модуль: диспетчер + .mload/.mls/.mcfg/.cb
modules/hloader.py     ← твой hloader с веткой mcub_core → engine
```

Почему это надёжнее старого regex-адаптера: модуль исполняется **как есть**,
а вся магия — в объектах, которые он импортирует (`core.lib.loader.module_base`,
`kernel`, `utils`). Поведение ядра скопировано с оригинального MCUB-fork
включая передачу `data=` в колбэки, TTL кнопок, конфликты команд и алиасы.

---

## ❓ FAQ

**Кнопка пишет «устарела»** — у кнопок есть TTL (обычно 15 мин).
Вызови команду модуля заново — появится свежее меню.

**Модуль просит зависимость** — движок напишет какую: `pip install <пакет>`,
затем `.mload` ещё раз.

**`.iq` ничего не нашёл** — инлайн-хендлеры становятся командами вида
`.iq <имя> <запрос>`, список есть в `.mhelp <модуль>`.

**Конфликт команд** — если два MCUB-модуля регистрируют одну команду,
второй не загрузится (как в оригинальном MCUB): выгрузи первый через `.mun`.

---

Оригинальный код MCUB-fork © MItrich && hairpin01, лицензия MIT.
Порты `decorators.py` и `module_config.py` используются с сохранением копирайтов.
