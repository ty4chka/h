# 📦 Модули нового вида — руководство разработчика

Модули живут в `modules/` и пишутся против `hydra_kernel.api` (L1).
Загрузка: `Hydra.loader.load_dir("modules")` или по одному `load_source(...)`.

## Скелет модуля

```python
from hydra_kernel.api import ModuleBase, command, watcher, callback, loop

class MyMod(ModuleBase):
    name = "mymod"
    version = "1.0.0"
    strings = {                      # локализация (MCUB-семантика)
        "ru": {"hi": "Привет, {name}!"},
        "en": {"hi": "Hello, {name}!"},
    }

    @command("mycmd", aliases=("mc",), desc="описание")
    async def cmd(self, event):
        await self.reply(event, self.t("hi", name="мир"))

    @watcher(pattern=r"(?i)hello")
    async def watch(self, event): ...

    @loop(interval=60)
    async def tick(self): ...

    async def on_load(self): ...     # хуки жизненного цикла
```

## Кнопки и формы

```python
await self.form(event.chat_id, "<b>Заголовок</b>", buttons=[[
    {"text": "Обновить", "callback": self.cb_refresh},          # callable
    {"text": "Аргумент", "callback": self.cb_x, "args": (42,)}, # + аргументы
    {"text": "Ссылка",   "url": "https://..."},
]])

async def cb_refresh(self, call):   # call: answer/edit/delete
    await call.edit("обновлено")
```

Callable-кнопка получает уникальный data-префикс; роутинг callback'ов — по
самому длинному префиксу.

## Язык и кастомные строки

- `self.t('key', **kw)` / `self.strings('group')('key')` — активная локаль;
- переключение: `.setlang [ru|en]` (без аргумента — форма с кнопками);
- **кастом**: `.langset <module|global> <key> = <text>` — строка пользователя
  поверх паков, хранится в `kernel.config['lang_custom']` и
  `data/kernel_config.json`;
- глобальные группы: `buttons` (close/back/refresh), `error`, `ok`.

## Права

`@command(..., required_level=3)` или MCUB-`@owner_only()` — только владелец.
Уровни: GUEST 0 / USER 1 / ADMIN 2 / OWNER 3 (`Hydra.permissions`).

## Встроенные модули

| Модуль | Команды | Особенности |
|---|---|---|
| `ping` | `.ping` | форма с кнопками 🔄/❌, uptime |
| `info` | `.info` | версия ядра, счётчик модулей, кнопки |
| `terminal` | `.term <cmd>`, `.t <cmd>` | **починен**: реальный subprocess с таймаутом 10 c, ANSI-фильтр, обрезка 3000, код возврата; кнопки 🔄 (повтор) и ❌; owner only |
| `translations` | `.setlang`, `.langset`, `.reloadlang` | форма языков, кастом-строки |
| `help` | `.help` | форма со списком модулей, кнопка → список команд |
| `settings` | `.settings` | toggles флагов ядра кнопками |

## GUI-редактор (не модуль!)

Редактор — **терминальный GUI**, стартует вместе с юзерботом:

```bash
python3 main.py            # ядро + модули + TUI-редактор
python3 main.py --no-tui   # headless
python3 -m hydra_kernel.tui modules   # только редактор
```

Экраны: список модулей → просмотр (пагинация) → правка. Клавиши: `j/k` и
стрелки, `Enter/e` открыть, `e` править, `Ctrl-S` сохранить (синтаксис +
security scanner + автобэкап в `data/backups/`), `Ctrl-Q` выйти без
сохранения, `q` назад/выход. Модель редактора (`tui/model.py`) отделена от
curses-рендера и переиспользует `pkg.scanner`.

## Кнопки текстом (мост, как в MCUB)

Юзербот не получает CallbackQuery — они приходят только ботам. Поэтому в
текстовом режиме ядро рендерит кнопки формы меню прямо в сообщении
(`api/button_bridge.py`, порт ButtonBridge из старого репозитория):

```
🏓 Понг!
⏱ Аптайм: 42 с

⚙️ Меню #2:
.cb 1 2 🔄 Обновить ┃ .cb 2 2 ❌ Закрыть
.it 1 2 ✏️ Подпись
```

- `.cb N` — «нажать» кнопку N **последнего** меню в чате;
- `.cb N M` — кнопка N конкретного меню #M (когда форм в чате несколько —
  каждая форма получает свой номер);
- `.cb` без номера — показать последнее меню ещё раз;
- `.it N текст` / `.it N M текст` — ввод для input-кнопок (как `.cb`,
  можно указать меню #M): в форме это кнопка
  `{"text": ..., "input": fn}` → `fn(call, текст)`;
- `.cbf` — вкл/выкл подсказки меню (кнопки продолжают работать «вслепую»,
  состояние живёт в конфиге ядра);
- `.iq <хендлер> <запрос>` — локальный инлайн-поиск текстом;
- `.iqs <хендлер> <запрос>` — сохранить запрос в «избранное» и получить
  хэш: в общем чате потом вводишь только `.iq <хэш>`, а сам запрос
  (например, с API-ключом) в нём не светится.

Мост работает на транспорте, поэтому меню получают формы **всех** видов
модулей: hydra, MCUB, Hikka, Heroku, Dragon и Go-модули. Сами модули про
мост не знают — они шлют обычные формы с callable-кнопками.

## Терминал: что починено

Старая адаптация MCUB-терминала молча ломалась на стриминге и не имела кнопок.
Новый `modules/terminal.py`:

- запуск через `asyncio.create_subprocess_shell`, `stdout+stderr` вместе;
- таймаут с `proc.kill()` и понятным сообщением;
- strip ANSI-кодов, HTML-escape, лимит вывода;
- форма результата с кнопками **повторить** (перезапуск той же команды) и
  **закрыть** (удаление сообщения);
- owner-only по умолчанию.

## Проверка модуля

```bash
python3 -m hydra_kernel.tools.build   # подхватит modules/ и прогонит smoke
```
