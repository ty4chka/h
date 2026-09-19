# 🧬 Hydra — Telegram UserBot с универсальным ядром

> English version: [README_EN.md](README_EN.md)

**Hydra** — userbot с собственным модульным ядром (`hydra_kernel`), которое
одинаково хорошо собирает и запускает модули **Hydra, MCUB, Hikka, Heroku и
Dragon**. Один процесс — пять экосистем модулей.

```
L4  modules/ + mcub_mods/ твои модули (Hydra и сохранённые MCUB-модули)
L3  pkg/                 loader · registry · resolver · manifest · scanner
L2  compat/              MCUB · Hikka · Heroku · Dragon · legacy Hydra
L1  api/                 ModuleBase · decorators · permissions · inline · lang
L0  kernel/              transport · db · runtime · logging · gobridge(Go)
```

Зависимости направлены строго вниз: ядро не знает о фреймворках — фреймворки
знают о ядре.

## ✨ Возможности

- **Пять целевых фреймворков** из одной сборки: `hydra / mcub / hikka / heroku / dragon`
- **Инлайн как в MCUB**: формы, callable-кнопки, роутинг inline по имени и
  callback по префиксу, фолбэк результатов сообщением
- **Кнопки текстом**: юзербот не получает CallbackQuery — ядро рендерит
  кнопки меню `.cb N M` прямо в сообщении (мост как в MCUB): несколько меню
  в чате, `.it N` — кнопки ввода, `.cbf` — скрыть подсказки, `.iq`/`.iqs` —
  инлайн-поиск, в т.ч. по хэшу из «избранного» (API-ключи не светятся в чате)
- **i18n как в MCUB**: `strings` с локалями, вложенные группы, `.setlang` с
  кнопками, **кастомные строки** `.langset`
- **Починенный терминал**: `.term` с таймаутом, ANSI-фильтром и кнопками
  «повторить / закрыть»
- **GUI-редактор при запуске**: `python3 main.py` поднимает юзербота вместе с
  TUI-редактором — список модулей, просмотр с пагинацией, правка с валидацией
  синтаксиса/scanner и автобэкапом
- **Go-часть ядра**: `gocore/` — нативный `hydracore` (JSON-RPC по stdio) для
  быстрых операций, Python-мост `gobridge` с фолбэком
- **Go-модули с полным паритетом**: SDK `gocore/hydra` — команды, формы,
  кнопки, lang как у Python-модулей; **hrul** собирает модуль из нескольких
  файлов (`module.hrul` → один бинарник)
- **Cython-компиляция**: горячие модули ядра собираются в `.so`
  (`tools/build_native.py`), импортёр подхватывает их автоматически
- **Безопасность**: AST-scanner блокирует `exec/eval/os.system/subprocess`
  до выполнения; `owner_only`-права
- **Автозагрузка своих MCUB-модулей**: `modules/mcub_mods/*.py` (включая
  OpenAgent) стартуют вместе с обычными модулями; идентичные копии не запускаются дважды
- **Офлайн-сборка**: ядро собирается и проходит smoke-тесты без telethon и сети;
  на Termux/Android неподдерживаемый `psutil` заменяется безопасным fallback
- **Пакетная система**: манифесты, зависимости (топосорт), реестр, жизненный цикл

## 🚀 Быстрый старт

```bash
# сборка + полный прогон всех целей и модулей
python3 -m hydra_kernel.tools.build

# запуск юзербота с GUI-редактором (headless: --no-tui)
python3 main.py

# нативная компиляция ядра (Cython) и Go-части
python3 tools/build_native.py
sh tools/build_go.sh
```

Зелёный вывод = ядро + все цели + набор модулей работают.

## 🌐 MTProto-прокси

Hydra принимает MTProto-прокси из `t.me/proxy` и использует для него
рекомендованный Telethon transport `ConnectionTcpMTProxyRandomizedIntermediate`.
Скопируйте `data/config.example.json` в локальный `data/config.json` (он
игнорируется Git) и заполните поля:

```json
{
  "proxy_enabled": true,
  "proxy_addr": "proxy.example.org",
  "proxy_port": 443,
  "proxy_secret": "secret-from-t-me-proxy-link"
}
```

Либо задайте те же значения только для одного запуска через
`HYDRA_PROXY_ENABLED`, `HYDRA_PROXY_ADDR`, `HYDRA_PROXY_PORT` и
`HYDRA_PROXY_SECRET`. Перезапустите Hydra после изменения. Не публикуйте
`api_hash`, session-файлы или proxy secret. Если провайдер принимает только
строгий FakeTLS (`ee…`) и разрывает соединение, запросите у него обычный или
`dd…` MTProto-secret: стандартный Telethon не реализует полный FakeTLS
handshake.

## 🧩 Установка MCUB-модуля

Запустите `.mload <raw-URL-на-py-файл>` или ответьте `.mload` на сообщение с
исходником/`.py`-файлом. Исходник проходит scanner, сохраняется в
`modules/mcub_mods/`, загружается сразу и будет автоматически загружен после
перезапуска. Управление: `.mls`, `.mhelp <модуль>`, `.mcfg <модуль>` и
`.mun <модуль> [--del]`. Поддерживаются MCUB-совместимые модули; сторонние
модули всё ещё могут требовать свои API-ключи или Python-зависимости.

## 📦 Модуль за 30 секунд

```python
from hydra_kernel.api import ModuleBase, command

class Hello(ModuleBase):
    name = "hello"
    strings = {"ru": {"hi": "Привет, {name}!"}, "en": {"hi": "Hello, {name}!"}}

    @command("hello")
    async def cmd(self, event):
        await self.form(
            event.chat_id,
            self.t("hi", name="мир"),
            buttons=[[{"text": self.strings("buttons")("close"), "callback": self.cb_close}]],
        )

    async def cb_close(self, call):
        await call.delete()
```

MCUB-модули (`from core.lib.loader.module_base import ...`, `@command`,
`@owner_only`, `self.args/answer/Button`) и Heroku-модули
(`from heroku import loader`, `@loader.command`, `self.inline.form`) загружаются
**без изменений** через адаптеры.

## 📚 Документация

| Документ | О чём |
|---|---|
| [docs/KERNEL.md](docs/KERNEL.md) | архитектура ядра, слои, inline-роутинг, lang, сборка |
| [docs/COMPAT.md](docs/COMPAT.md) | матрица совместимости + честные аппроксимации |
| [docs/MODULES.md](docs/MODULES.md) | гайд разработчика модулей, кнопки, lang, терминал |
| [docs/MIGRATION.md](docs/MIGRATION.md) | старый код → новый, что мигрирует автоматически |
| [docs/NATIVE.md](docs/NATIVE.md) | Go-ядро, Go-модули, Cython-компиляция |

## ⚠️ Безопасность

В истории репозитория были секреты (`ai_keys.json`, `config.py`, логи сессий).
**Отзовите ключи** перед любым пушем; добавьте в `.gitignore` `ai_keys.json`,
`*.log`, `openagent_sessions/`, `*.zip`. Ядро новых секретов не хранит:
конфиг — `data/kernel_config.json` (локально).

## 📄 Лицензия

См. [LICENSE](LICENSE).
