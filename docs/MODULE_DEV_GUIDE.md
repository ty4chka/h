# 🧬 Hydra Module Development Guide

Полная документация по созданию модулей для Hydra UserBot.

---

## Содержание

1. [Архитектура](#архитектура)
2. [Быстрый старт](#быстрый-старт)
3. [Функциональный стиль](#функциональный-стиль)
4. [ООП стиль](#ооп-стиль)
5. [Конфигурация модулей](#конфигурация-модулей)
6. [Плейсхолдеры](#плейсхолдеры)
7. [Команды](#команды)
8. [Хэндлеры и события](#хэндлеры-и-события)
9. [Работа с БД](#работа-с-бд)
10. [Адаптация MCUB модулей](#адаптация-mcub-модулей)
11. [Справочник API](#справочник-api)
12. [Примеры](#примеры)

---

## Архитектура

Hydra поддерживает два стиля написания модулей:

| Стиль | Описание | Пример |
|-------|----------|--------|
| **Функциональный** | `def register(kernel):` | ping.py, cfg.py |
| **ООП** | `class MyModule(ModuleBase):` | yamusic.py |

Модули автоматически загружаются из папки `modules/`.

---

## Быстрый старт

### Минимальный модуль (функциональный стиль)

```python
# modules/hello.py

async def hello_handler(event):
    await event.edit("👋 Привет!")

modules_help = {
    "hello": {
        "hello": "Поприветствовать пользователя"
    }
}
```

### Минимальный модуль (ООП стиль)

```python
# modules/hello.py

from core.lib.loader.module_base import ModuleBase, command

class HelloModule(ModuleBase):
    name = "hello"
    version = "1.0.0"

    @command("hello")
    async def cmd_hello(self, event):
        await event.edit("👋 Привет!")

modules_help = {
    "hello": {
        "hello": "Поприветствовать пользователя"
    }
}
```

---

## Функциональный стиль

### Структура модуля

```python
# modules/mymodule.py

from telethon import events
from utils.misc import edit_or_reply

async def mycommand_handler(event):
    """Обработчик команды .mycommand"""
    args = event.text.split(maxsplit=1)
    text = args[1] if len(args) > 1 else "Аргумент не указан"
    await event.edit(f"Вы написали: {text}")

async def setup(client):
    """Регистрация хэндлеров (вызывается при загрузке)"""
    client.add_event_handler(
        mycommand_handler,
        events.NewMessage(pattern=r"\.mycommand", outgoing=True)
    )

modules_help = {
    "mymodule": {
        "mycommand <текст>": "Пример команды"
    }
}
```

### Доступ к клиенту

```python
async def my_handler(event):
    client = event.client
    me = await client.get_me()
    await event.edit(f"Привет, {me.first_name}!")
```

---

## ООП стиль

### Базовый класс

```python
from core.lib.loader.module_base import ModuleBase, command, watcher, loop, callback

class MyModule(ModuleBase):
    name = "mymodule"
    version = "1.0.0"
    author = "Author"
    description = {"ru": "Описание модуля"}

    config = ModuleConfig(
        ConfigValue("enabled", True, description="Включить модуль", validator=Boolean(default=True)),
        ConfigValue("api_key", "", description="API ключ", validator=Secret(default="")),
    )

    @command("hello")
    async def cmd_hello(self, event):
        await event.edit("Привет!")

    @watcher(outgoing=True)
    async def my_watcher(self, event):
        pass

    @loop(interval=300, autostart=True)
    async def background_task(self):
        pass

    async def on_load(self):
        await super().on_load()
        # Инициализация после загрузки
```

### Декораторы

| Декоратор | Описание |
|-----------|----------|
| `@command("name")` | Регистрация команды |
| `@command("name", alias=["alt"])` | Команда с псевдонимами |
| `@inline("name")` | Инлайн-хэндлер |
| `@watcher(outgoing=True)` | Наблюдатель за сообщениями |
| `@loop(interval=60)` | Фоновая задача |
| `@callback(ttl=900)` | Обработчик callback-кнопок |
| `@on_install` | Вызывается при установке |
| `@on_uninstall` | Вызывается при удалении |

---

## Конфигурация модулей

### Определение конфигурации

```python
from core.lib.loader.module_config import (
    ModuleConfig, ConfigValue,
    Boolean, Integer, Float, String, Choice, Secret, List
)

class MyModule(ModuleBase):
    config = ModuleConfig(
        ConfigValue(
            "enabled",
            True,
            description="Включить модуль",
            validator=Boolean(default=True)
        ),
        ConfigValue(
            "api_key",
            "",
            description="API ключ",
            validator=Secret(default="")
        ),
        ConfigValue(
            "timeout",
            30,
            description="Таймаут запросов",
            validator=Integer(default=30, min=1, max=300)
        ),
        ConfigValue(
            "mode",
            "default",
            description="Режим работы",
            validator=Choice(
                choices=["default", "fast", "safe"],
                default="default"
            )
        ),
    )
```

### Доступ к конфигу

```python
async def on_load(self):
    await super().on_load()
    # Конфиг загружается автоматически

async def cmd_test(self, event):
    enabled = self.config["enabled"]
    api_key = self.config["api_key"]
    await event.edit(f"Enabled: {enabled}")
```

### Справочник валидаторов

| Валидатор | Описание | Параметры |
|-----------|----------|-----------|
| `Boolean(default)` | Булево значение | `default` |
| `Integer(default, min, max)` | Целое число | `default`, `min`, `max` |
| `Float(default, min, max)` | Дробное число | `default`, `min`, `max` |
| `String(default, min_len, max_len)` | Строка | `default`, `min_len`, `max_len` |
| `Choice(choices, default)` | Выбор из списка | `choices`, `default` |
| `Secret(default)` | Секретное значение | `default` |
| `List(default, item_type)` | Список | `default`, `item_type` |
| `Link(default)` | URL ссылка | `default` |
| `Placeholders(default, placeholder_scope)` | С плейсхолдерами | `default`, `placeholder_scope` |

---

## Плейсхолдеры

### Встроенные плейсхолдеры

| Плейсхолдер | Описание |
|-------------|----------|
| `{prefix}` | Префикс команд (`.`) |
| `{time}` | Текущее время (HH:MM:SS) |
| `{date}` | Текущая дата (DD.MM.YYYY) |
| `{datetime}` | Дата и время |
| `{timestamp}` | Unix timestamp |
| `{my_name}` | Имя пользователя |
| `{my_id}` | ID пользователя |
| `{random}` | Случайное число |
| `{chat_id}` | ID чата |
| `{chat_title}` | Название чата |
| `{weekday}` | День недели |
| `{month}` | Месяц |

### Регистрация кастомных плейсхолдеров

```python
from core.lib.loader.placeholders import register_placeholder

def register(kernel):
    # Регистрация плейсхолдера
    register_placeholder(
        scope="mymodule",
        key="my_value",
        callback=lambda data: "значение",
        description="Моё значение"
    )
```

### Использование в конфиге

```python
config = ModuleConfig(
    ConfigValue(
        "welcome_message",
        "Привет, {my_name}! Сейчас {time}",
        description="Приветственное сообщение",
        validator=Placeholders(default="", placeholder_scope="mymodule")
    ),
)
```

---

## Команды

### Простая команда

```python
async def ping_handler(event):
    await event.edit("🏓 Pong!")

modules_help = {
    "mymodule": {
        "ping": "Проверка работоспособности"
    }
}
```

### Команда с аргументами

```python
async def echo_handler(event):
    args = event.text.split(maxsplit=1)
    if len(args) < 2:
        await event.edit("❌ Используйте: .echo <текст>")
        return
    await event.edit(f"📢 {args[1]}")
```

### Команда с reply

```python
async def stickerize_handler(event):
    reply = await event.get_reply_message()
    if not reply or not reply.photo:
        await event.edit("❌ Ответьте на фото")
        return
    # Обработка фото
```

---

## Хэндлеры и события

### Наблюдатель за сообщениями (ООП)

```python
@watcher(outgoing=True, incoming=True)
async def my_watcher(self, event):
    if "спам" in event.text.lower():
        await event.delete()
```

### Callback-кнопки

```python
@callback(ttl=300)
async def handle_click(self, event):
    await event.answer("✅ Нажато!")

# Создание кнопки
btn = self.Button.inline("Нажми", self.handle_click)
await event.edit("Тест", buttons=[[btn]])
```

### Фоновые задачи

```python
@loop(interval=300, autostart=True)
async def cleanup_loop(self):
    """Очистка каждые 5 минут"""
    # Код очистки
```

---

## Работа с БД

### Через kernel (функциональный стиль)

```python
async def save_data(kernel, key, value):
    await kernel.db_set("mymodule", key, value)

async def load_data(kernel, key):
    return await kernel.db_get("mymodule", key)
```

### Через self.db (ООП стиль)

```python
async def save_data(self, key, value):
    await self.db.db_set(self.name, key, value)

async def load_data(self, key):
    return await self.db.db_get(self.name, key)
```

---

## Адаптация MCUB модулей

Hydra автоматически адаптирует MCUB модули при установке:

```bash
.lm <url_or_file>
```

### Поддерживаемые форматы

| Формат | Описание |
|--------|----------|
| `def register(kernel):` | Функциональный стиль MCUB |
| `class Module(ModuleBase):` | ООП стиль MCUB |
| `class Module(loader.Module):` | Hikka/Heroku стиль |
| `@Client.on_message(...)` | Pyrogram стиль |

### Автоматические замены

- `from core.lib.loader...` — импорты эмулируются
- `Button.inline()` — конвертируется в команды
- `kernel.register.command()` — создаются хэндлеры
- `self.config` — работает через ModuleConfig

---

## Справочник API

### event (Telethon Event)

| Атрибут/метод | Описание |
|---------------|----------|
| `event.text` | Текст сообщения |
| `event.raw_text` | Текст без форматирования |
| `event.chat_id` | ID чата |
| `event.sender_id` | ID отправителя |
| `event.client` | Telegram клиент |
| `await event.edit(text)` | Редактирование сообщения |
| `await event.reply(text)` | Ответ на сообщение |
| `await event.delete()` | Удаление сообщения |
| `await event.get_reply_message()` | Получить сообщение-ответ |

### client (TelegramClient)

| Метод | Описание |
|-------|----------|
| `await client.get_me()` | Получить информацию о себе |
| `await client.get_entity(id)` | Получить сущность (юзер/чат) |
| `await client.send_message(chat, text)` | Отправить сообщение |
| `await client.send_file(chat, file)` | Отправить файл |
| `await client.download_media(msg)` | Скачать медиа |
| `await client.iter_messages(chat)` | Итерация по сообщениям |

### kernel (MCUB совместимость)

| Метод | Описание |
|-------|----------|
| `kernel.client` | Telegram клиент |
| `kernel.custom_prefix` | Префикс команд |
| `await kernel.get_module_config(name)` | Получить конфиг |
| `await kernel.save_module_config(name, data)` | Сохранить конфиг |
| `kernel.store_module_config_schema(name, config)` | Сохранить схему |
| `await kernel.db_get(module, key)` | Получить из БД |
| `await kernel.db_set(module, key, value)` | Сохранить в БД |

---

## Примеры

### Пример 1: Модуль-калькулятор

```python
# modules/calc.py

import ast
import operator

ops = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

def calc(expr):
    tree = ast.parse(expr, mode='eval')
    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.BinOp):
            return ops[type(node.op)](_eval(node.left), _eval(node.right))
        raise ValueError(f"Неизвестный узел: {node}")
    return _eval(tree)

async def calc_handler(event):
    args = event.text.split(maxsplit=1)
    if len(args) < 2:
        await event.edit("❌ Используйте: .calc <выражение>")
        return
    try:
        result = calc(args[1])
        await event.edit(f"🧮 {args[1]} = <code>{result}</code>", parse_mode='HTML')
    except Exception as e:
        await event.edit(f"❌ Ошибка: {e}")

modules_help = {
    "calc": {
        "calc <выражение>": "Калькулятор (пример: .calc 2+2*3)"
    }
}
```

### Пример 2: Модуль с конфигурацией

```python
# modules/autogreet.py

from core.lib.loader.module_base import ModuleBase, command, watcher
from core.lib.loader.module_config import ModuleConfig, ConfigValue, String, Boolean

class AutoGreet(ModuleBase):
    name = "autogreet"
    version = "1.0.0"

    config = ModuleConfig(
        ConfigValue(
            "greeting",
            "👋 Привет, {my_name}!",
            description="Приветствие",
            validator=String(default="👋 Привет, {my_name}!")
        ),
        ConfigValue(
            "enabled",
            True,
            description="Включить автоприветствие",
            validator=Boolean(default=True)
        ),
    )

    @watcher(incoming=True, outgoing=False)
    async def greet_watcher(self, event):
        if not self.config["enabled"]:
            return
        if not event.is_private:
            return
        greeting = self.config["greeting"]
        # Плейсхолдеры разрешаются автоматически
        await event.reply(greeting)

    @command("setgreeting")
    async def cmd_setgreeting(self, event):
        args = event.text.split(maxsplit=1)
        if len(args) < 2:
            await event.edit("❌ Используйте: .setgreeting <текст>")
            return
        self.config["greeting"] = args[1]
        await self.save_config()
        await event.edit(f"✅ Приветствие обновлено")

modules_help = {
    "autogreet": {
        "setgreeting <текст>": "Установить приветствие"
    }
}
```

### Пример 3: Фоновая задача

```python
# modules/cleanup.py

import time
from pathlib import Path
from core.lib.loader.module_base import ModuleBase, command, loop

class Cleanup(ModuleBase):
    name = "cleanup"
    version = "1.0.0"

    @loop(interval=3600, autostart=True)
    async def cleanup_loop(self):
        """Очистка временных файлов каждый час"""
        temp_dir = Path("/tmp")
        cleaned = 0
        for f in temp_dir.glob("hydra_*"):
            if f.is_file() and time.time() - f.stat().st_mtime > 3600:
                f.unlink()
                cleaned += 1
        if cleaned:
            self.log.info(f"Очищено {cleaned} файлов")

    @command("cleanup")
    async def cmd_cleanup(self, event):
        await event.edit("🔄 Очистка...")
        await self.cleanup_loop()
        await event.edit("✅ Очистка завершена")

modules_help = {
    "cleanup": {
        "cleanup": "Запустить очистку вручную"
    }
}
```

---

## Установка модулей

### Установка из файла

```bash
.lm <имя_файла>.py
```

### Установка из URL

```bash
.lm <url>
```

### Установка из архива

```bash
.lm <url_на_zip>
```

### Удаление модуля

```bash
.unlm <имя_модуля>
```

### Список модулей

```bash
.hmods
```

---

## Конфигурация

### Просмотр конфигов

```bash
.cfg list              # Все модули
.cfg show <module>     # Конфиг модуля
.cfg get <module> <key>  # Значение ключа
```

### Изменение конфигов

```bash
.cfg set <module> <key> <value>  # Установить
.cfg reset <module>              # Сбросить всё
.cfg reset <module> <key>        # Сбросить ключ
```

### Плейсхолдеры

```bash
.cfg placeholders  # Список плейсхолдеров
.cfg template <module>  # JSON шаблон
```

---

*Hydra UserBot — Lightning Fast Python UserBot*
