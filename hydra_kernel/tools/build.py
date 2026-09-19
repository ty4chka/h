"""Сборка ядра: compile + smoke-цели Hydra / MCUB / Hikka / Heroku / Dragon.

Запуск из корня репозитория:
    python3 -m hydra_kernel.tools.build

Шаги:
  1. py_compile всего hydra_kernel + старого core/ и core_inline/
     («ядро собирается» — байткод, без выполнения импортов telethon).
  2. unit-проверки L3: resolver (топосорт + цикл) и scanner (exec/eval).
  3. Smoke по целям: поднимается Hydra с NullTransport, ставится адаптер
     фреймворка, грузится эталонный модуль, шлётся «.ping», проверяется ответ.
Выход: 0 — все цели зелёные.
"""

from __future__ import annotations

import asyncio
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hydra_kernel import Hydra  # noqa: E402
from hydra_kernel.pkg.resolver import resolve, CyclicDependency  # noqa: E402
from hydra_kernel.pkg.manifest import Manifest  # noqa: E402
from hydra_kernel.pkg.scanner import scan_source, SecurityError  # noqa: E402

GREEN, RED, RESET = "\033[32m", "\033[31m", "\033[0m"


def ok(text: str) -> str:
    return f"{GREEN}OK{RESET}   {text}"


def fail(text: str) -> str:
    return f"{RED}FAIL{RESET} {text}"


# ---------------------------------------------------------------- compile
def compile_trees() -> int:
    total = 0
    for rel in ("hydra_kernel", "core", "core_inline", "hydra_modules"):
        tree = ROOT / rel
        if not tree.exists():
            continue
        for py in sorted(tree.rglob("*.py")):
            py_compile.compile(str(py), doraise=True)
            total += 1
    # modules/ — родные модули HYDRA: m.py грузит только верхний уровень,
    # сабпакеты (ai_adapter, yamusic...) не трогаем
    tree = ROOT / "modules"
    if tree.exists():
        for py in sorted(tree.glob("*.py")):
            py_compile.compile(str(py), doraise=True)
            total += 1
    return total


# ---------------------------------------------------------------- L3 checks
def check_resolver() -> None:
    mans = {
        "a": Manifest("a", requires=["b", "c"]),
        "b": Manifest("b", requires=["c"]),
        "c": Manifest("c"),
    }
    order = resolve(mans)
    assert order.index("c") < order.index("b") < order.index("a"), order

    cyclic = {"x": Manifest("x", requires=["y"]), "y": Manifest("y", requires=["x"])}
    try:
        resolve(cyclic)
        raise AssertionError("цикл не обнаружен")
    except CyclicDependency:
        pass


def check_scanner() -> None:
    bad = "import os\nos.system('rm -rf ~')\nexec('x=1')\nimport subprocess\n"
    findings = scan_source(bad)
    rules = {f.rule for f in findings if f.severity == "critical"}
    assert {"os.system", "exec", "subprocess"} <= rules, rules
    assert scan_source("x = 1\n") == []


# ---------------------------------------------------------------- smoke
HYDRA_SRC = """
from hydra_kernel.api import ModuleBase, command, inline_handler, callback

class Ping(ModuleBase):
    name = "ping"
    version = "1.0.0"

    @command("ping", desc="pong")
    async def ping(self, event):
        await self.reply(event, "pong (hydra)")

    @inline_handler("pingi")
    async def pingi(self, event):
        await event.answer([event.builder.article("Ping", description=event.args, text="pong-inline")])

    @callback("pingcb:")
    async def pingcb(self, event):
        await event.answer("cb-ok")
"""

MCUB_SRC = """
# meta: name=ping version=1.0.0 framework=mcub
def register(kernel):
    async def ping(event):
        await kernel.client.send_message(event.chat_id, "pong (mcub)")
    kernel.register_command("ping", ping)

    async def search(event):
        await event.answer([event.builder.article("MCUB Search", text="found")])
    kernel.register_inline_handler("search", search)

    async def cb(event):
        await event.answer("mcub-cb")
    kernel.register_callback_handler("mcb:", cb)
"""

HIKKA_SRC = """
from hikka import loader

class PingMod(loader.Module):
    strings = {"name": "ping"}

    @loader.command()
    async def pingcmd(self, message):
        await message.reply("pong (hikka)")

    @loader.inline_handler("hsearch")
    async def hsearch(self, event):
        await event.answer([event.builder.article("Hikka Search", text="h")])
"""

HEROKU_SRC = HIKKA_SRC.replace("hikka", "heroku").replace("pong (hikka)", "pong (heroku)").replace("hsearch", "hesearch").replace("Hikka Search", "Heroku Search")
DRAGON_SRC = HIKKA_SRC.replace("hikka", "dragon").replace("pong (hikka)", "pong (dragon)").replace("hsearch", "dsearch").replace("Hikka Search", "Dragon Search")

# class-style MCUB по API hairpin01/MCUB-fork: декораторы, self.args/answer,
# owner_only, @method
MCUB_CLASS_SRC = """
# meta: name=summod framework=mcub
from core.lib.loader.module_base import ModuleBase, command, owner_only, method

class SumMod(ModuleBase):
    name = "summod"
    version = "1.0.0"
    author = "@build"

    @method
    async def setup(self):
        self.log.info("setup ok")

    @command("sum", doc_ru="Сумма", doc_en="Sum")
    async def cmd_sum(self, event):
        nums = [int(n) for n in self.args(event)]
        await self.answer(event, f"Sum: {sum(nums)}")

    @command("topsecret", alias="ts")
    @owner_only()
    async def cmd_secret(self, event):
        await self.reply(event, "secret-ok")
"""

# Heroku по API coddrago/Heroku: utils.escape_html, self.inline.form
# с callable-кнопкой, нажатие через callback
HEROKU_RICH_SRC = """
from heroku import loader, utils

class EchoMod(loader.Module):
    strings = {"name": "echo"}

    @loader.command()
    async def echocmd(self, message):
        await message.reply(utils.escape_html("<b>ok</b>"))

    @loader.command()
    async def menucmd(self, message):
        await self.inline.form("Menu", message.chat_id, reply_markup=[[
            {"text": "Go", "callback": self.go_cb},
        ]])

    async def go_cb(self, call):
        await call.answer("go-ok")
"""


async def check_mcub_class(h: "Hydra") -> None:
    await h.transport.inject(500, ".sum 1 2 3", sender_id=1000, outgoing=True)
    assert any("Sum: 6" in m.text for m in h.transport.sent), "self.args/answer не сработали"
    before = len(h.transport.sent)
    await h.transport.inject(500, ".topsecret", sender_id=999, outgoing=True)
    assert len(h.transport.sent) == before, "owner_only пропустил чужого"
    await h.transport.inject(500, ".ts", sender_id=1000, outgoing=True)
    assert any("secret-ok" in m.text for m in h.transport.sent), "alias owner-команды не работает"


async def check_heroku_rich(h: "Hydra") -> None:
    await h.transport.inject(500, ".echo", sender_id=1000, outgoing=True)
    assert any("&lt;b&gt;ok&lt;/b&gt;" in m.text for m in h.transport.sent), "utils.escape_html"
    await h.transport.inject(500, ".menu", sender_id=1000, outgoing=True)
    form = h.transport.sent[-1]
    assert form.buttons, "inline.form не прикрепил кнопки"
    data = form.buttons[0][0]["data"]
    await h.transport.inject_callback(data, sender_id=1000, chat_id=500, message_id=form.message_id)
    assert (data, "go-ok", False) in h.transport.callback_answers, "callable-кнопка не нажалась"


# (framework, source, expected_ping, inline, cb, extra)
TARGETS = [
    ("hydra", HYDRA_SRC, "pong (hydra)", ("pingi hello", "pingi", "Ping"), ("pingcb:1", "cb-ok"), None),
    ("mcub", MCUB_SRC, "pong (mcub)", ("search q", "search", "MCUB Search"), ("mcb:1", "mcub-cb"), None),
    ("mcub-class", MCUB_CLASS_SRC, None, None, None, check_mcub_class),
    ("hikka", HIKKA_SRC, "pong (hikka)", ("hsearch q", "hsearch", "Hikka Search"), None, None),
    ("heroku", HEROKU_SRC, "pong (heroku)", ("hesearch q", "hesearch", "Heroku Search"), None, None),
    ("heroku-rich", HEROKU_RICH_SRC, None, None, None, check_heroku_rich),
    ("dragon", DRAGON_SRC, "pong (dragon)", ("dsearch q", "dsearch", "Dragon Search"), None, None),
]


async def smoke(framework: str, source: str, expected, inline=None, cb=None, extra=None) -> None:
    hydra = Hydra(owner_id=1000)
    await hydra.start()
    await hydra.loader.load_source("ping", source, framework=framework)

    if expected:
        await hydra.transport.inject(chat_id=500, text=".ping", sender_id=1000, outgoing=True)
        assert hydra.transport.sent, f"{framework}: нет исходящих"
        last = hydra.transport.sent[-1].text
        assert expected in last, f"{framework}: {last!r} != {expected!r}"

    if inline:
        text, name, title = inline
        await hydra.transport.inject_inline(text, sender_id=1000)
        assert (name, [title]) in hydra.transport.inline_answers, (
            f"{framework}: inline {hydra.transport.inline_answers}"
        )
        # .iq — тот же инлайн текстовой командой (мост кнопок)
        await hydra.transport.inject(500, f".iq {text}", sender_id=1000, outgoing=True)
        assert title in hydra.transport.sent[-1].text, (
            f"{framework}: .iq не отрендерил результат: {hydra.transport.sent[-1].text!r}"
        )
        # .iqs — запрос сохраняется в «избранное», запуск по хэшу
        await hydra.transport.inject(500, f".iqs {text}", sender_id=1000, outgoing=True)
        m = re.search(r"\.iq ([0-9a-f]{8})", hydra.transport.sent[-1].text)
        assert m, f"{framework}: .iqs без хэша: {hydra.transport.sent[-1].text!r}"
        await hydra.transport.inject(500, f".iq {m.group(1)}", sender_id=1000, outgoing=True)
        last = hydra.transport.sent[-1].text
        assert title in last and "из избранного" in last, f"{framework}: .iq хэш: {last!r}"

    if cb:
        data, answer_text = cb
        await hydra.transport.inject_callback(data, sender_id=1000, chat_id=500, message_id=1)
        assert (data, answer_text, False) in hydra.transport.callback_answers, (
            f"{framework}: callback {hydra.transport.callback_answers}"
        )

    if extra:
        await extra(hydra)

    await hydra.stop()


async def real_mcub_module() -> None:
    """Настоящий модуль из hairpin01/MCUB-fork через адаптер."""
    src = (ROOT.parent / "refs" / "mcub" / "modules" / "translations.py").read_text(encoding="utf-8")
    h = Hydra(owner_id=1000)
    await h.start()
    await h.loader.load_source("translations", src, framework="mcub")

    await h.transport.inject(500, ".setlang", sender_id=1000, outgoing=True)
    form = h.transport.sent[-1]
    assert form.buttons, "нет кнопок языков"
    btn = [b for row in form.buttons for b in row if str(b.get("text", "")).endswith("en")][0]
    await h.transport.inject_callback(btn["data"], 1000, chat_id=500, message_id=form.message_id)
    assert h.config["language"] == "en", h.config

    await h.transport.inject(500, ".setlang ru", sender_id=1000, outgoing=True)
    assert h.config["language"] == "ru", h.config
    await h.stop()


async def real_hikka_dragon() -> None:
    """Фаза 3: настоящие модули Hikka (hikkatl) и Dragon (pyrogram)."""
    h = Hydra(owner_id=1000)
    await h.start()
    hikka_src = (ROOT / "extras" / "hikka_pack" / "translate.py").read_text(encoding="utf-8")
    await h.loader.load_source("translate", hikka_src, framework="hikka")
    dragon_ping = (ROOT / "extras" / "dragon_pack" / "ping.py").read_text(encoding="utf-8")
    await h.loader.load_source("dping", dragon_ping, framework="dragon")
    dragon_afk = (ROOT / "extras" / "dragon_pack" / "afk.py").read_text(encoding="utf-8")
    await h.loader.load_source("dafk", dragon_afk, framework="dragon")

    # hikka .tr: офлайн перевод недоступен — модуль отвечает своей ошибкой
    await h.transport.inject(500, ".tr ru привет", sender_id=1000, outgoing=True)
    assert h.transport.sent[-1].text.strip() != ".tr ru привет", "hikka .tr не ответил"

    # dragon .ping через pyrogram-шим (фильтры command & me)
    await h.transport.inject(500, ".ping", sender_id=1000, outgoing=True)
    assert any("Pong!" in m.text for m in h.transport.sent), "dragon .ping не ответил"
    # алиас .p
    await h.transport.inject(500, ".p", sender_id=1000, outgoing=True)
    assert any("Pong!" in m.text for m in h.transport.sent[-1:]), "dragon алиас .p не сработал"
    await h.stop()


async def mcub_pack_suite() -> None:
    """Фаза 4: полный пак настоящих MCUB-модулей (extras/mcub_pack)."""
    pack = ROOT / "extras" / "mcub_pack"
    files = sorted(p for p in pack.glob("*.py") if p.name != "__init__.py")
    assert files, "extras/mcub_pack пуст"
    h = Hydra(owner_id=1000)
    await h.start()
    errors = []
    for f in files:
        try:
            await h.loader.load_source(
                f.stem, f.read_text(encoding="utf-8"),
                framework="mcub", allow_unsafe=True,
            )
        except Exception as e:  # noqa: BLE001
            errors.append((f.stem, f"{type(e).__name__}: {e}"))
    assert not errors, f"не загрузились: {errors}"
    await h.transport.inject(500, ".info", sender_id=1000, outgoing=True)
    assert h.transport.sent and h.transport.sent[-1].text.strip() != ".info", \
        ".info из пака не ответил"
    await h.stop()


async def modules_suite() -> None:
    """Новый набор модулей Hydra (modules/): lang + кнопки + терминал."""
    h = Hydra(owner_id=1000)
    await h.start()
    # единый движок: ВСЕ родные модули через compat (core/setup/mcub/noop)
    records, errors = await h.loader.load_dir(
        ROOT / "modules", framework="auto",
        exclude=("mcub", "__init__"), allow_unsafe=True,
    )
    assert not errors, f"ошибки загрузки: {errors}"
    assert len(records) == 11, [r.name for r in records]
    fws = {r.framework for r in records}
    assert {"core", "setup", "mcub", "noop", "hydra"} <= fws, fws

    # метаданные: у каждого модуля version и корректное имя
    for rec in records:
        assert rec.manifest.version != "0.0.0", f"{rec.name}: нет метаданных version"
        assert rec.manifest.name == rec.name, f"{rec.name}: meta name != файла"

    # родная команда отвечает через единый транспорт
    await h.transport.inject(500, ".mylang", sender_id=1000, outgoing=True)
    assert any("🌐" in m.text for m in h.transport.sent), "родная .mylang не ответила"


NATIVE_AUDIT = [
    (".mylang", "lang"), (".languages", "lang"), (".lang ru", "lang"),
    (".start", "start"), (".serverinfo", "ServerInfo"), (".sysinfo", "ServerInfo"),
    (".services", "convert"), (".stats", "convert"), (".show_keys", "convert"),
    (".terminal_info", "terminal"), (".terminal_whoami", "terminal"),
    (".terminal_uname", "terminal"), (".terminal_df", "terminal"),
    (".terminal_ls", "terminal"),
    (".hmods", "hloader"), (".mcubmods", "hloader"),
    (".cfg", "cfg"),
    (".api_protection", "protect"), (".api_reset", "protect"),
    (".trustlist", "approve"), (".approve", "approve"),
    (".text upper привет", "text"), (".text mock ха-ха", "text"), (".text", "text"),
]


async def native_audit_suite() -> None:
    """Фаза 2: каждая родная команда даёт ответ через единый движок."""
    h = Hydra(owner_id=1000)
    await h.start()
    records, errors = await h.loader.load_dir(
        ROOT / "modules", framework="auto",
        exclude=("mcub", "__init__"), allow_unsafe=True,
    )
    assert not errors, f"ошибки загрузки: {errors}"
    bad = []
    for cmd, mod in NATIVE_AUDIT:
        before = len(h.transport.sent)
        try:
            await h.transport.inject(500, cmd, sender_id=1000, outgoing=True)
            grew = len(h.transport.sent) > before
            last = h.transport.sent[-1].text if h.transport.sent else ""
            if not (grew and last.strip() != cmd):
                bad.append(f"{cmd}: нет ответа")
        except Exception as e:  # noqa: BLE001
            bad.append(f"{cmd}: {type(e).__name__}: {e}")
    assert not bad, f"родные команды не ответили: {bad}"

    # диспетчер для m.py: modules/mcub.py обязан давать setup(client)
    import importlib.util as _iu

    spec = _iu.spec_from_file_location("single_dispatcher", ROOT / "modules" / "mcub.py")
    disp = _iu.module_from_spec(spec)
    spec.loader.exec_module(disp)
    assert callable(getattr(disp, "setup", None)), "modules/mcub.py: нет setup(client)"


async def bridge_suite() -> None:
    """Текстовый мост кнопок (.cb/.it/.cbf) — на демо-модулях ядра из extras."""
    h = Hydra(owner_id=1000)
    await h.start()
    records, errors = await h.loader.load_dir(
        ROOT / "extras" / "hydra_modules_demo", framework="hydra",
        exclude=("hydra_boot",),
    )
    assert not errors, f"ошибки загрузки демо: {errors}"
    assert len(records) == 6, [r.name for r in records]

    # ping: форма с кнопками, refresh редактирует на месте
    await h.transport.inject(500, ".ping", sender_id=1000, outgoing=True)
    form = h.transport.sent[-1]
    assert form.buttons, "ping без кнопок"
    await h.transport.inject_callback(
        form.buttons[0][0]["data"], 1000, chat_id=500, message_id=form.message_id
    )
    assert "♻️" in form.text, "refresh не отредактировал форму"

    # текстовый мост кнопок (как в MCUB): меню .cb N в тексте, нажатие текстом
    await h.transport.inject(500, ".ping", sender_id=1000, outgoing=True)
    form2 = h.transport.sent[-1]
    assert ".cb 1" in form2.text and "Меню" in form2.text, "меню кнопок не отрендерилось"
    await h.transport.inject(500, ".cb 1", sender_id=1000, outgoing=True)
    assert "♻️" in form2.text, ".cb 1 не нажал кнопку"
    await h.transport.inject(500, ".cb 99", sender_id=1000, outgoing=True)
    assert "не найдена" in h.transport.sent[-1].text, ".cb 99 без ошибки"
    await h.transport.inject(500, ".cb", sender_id=1000, outgoing=True)
    assert ".cb 1" in h.transport.sent[-1].text, ".cb не показал меню"

    # несколько меню в чате: .cb N M бьёт по конкретному меню
    import re as _re

    await h.transport.inject(500, ".ping", sender_id=1000, outgoing=True)
    form_a = h.transport.sent[-1]
    await h.transport.inject(500, ".ping", sender_id=1000, outgoing=True)
    form_b = h.transport.sent[-1]
    no_a = _re.search(r"Меню #(\d+)", form_a.text).group(1)
    no_b = _re.search(r"Меню #(\d+)", form_b.text).group(1)
    assert no_a != no_b, "меню не получили разные номера"
    await h.transport.inject(500, f".cb 1 {no_a}", sender_id=1000, outgoing=True)
    assert "♻️" in form_a.text and "♻️" not in form_b.text, ".cb N M нажал не то меню"

    # input-кнопка: .it 1 текст и .it 1 M текст (конкретное меню)
    await h.transport.inject(500, ".it 1 бро", sender_id=1000, outgoing=True)
    assert "🏓 бро" in form_b.text, ".it не доставил текст в input-кнопку"
    await h.transport.inject(500, ".ping", sender_id=1000, outgoing=True)
    form_c = h.transport.sent[-1]
    no_c = _re.search(r"Меню #(\d+)", form_c.text).group(1)
    await h.transport.inject(500, f".it 1 {no_c} чат", sender_id=1000, outgoing=True)
    assert "🏓 чат" in form_c.text, ".it N M не сработал по номеру меню"

    # .cbf — скрыть подсказки меню (кнопки работают вслепую)
    await h.transport.inject(500, ".cbf", sender_id=1000, outgoing=True)
    assert "скрыты" in h.transport.sent[-1].text
    await h.transport.inject(500, ".ping", sender_id=1000, outgoing=True)
    hidden = h.transport.sent[-1]
    assert ".cb 1" not in hidden.text, ".cbf не скрыл меню"
    await h.transport.inject(500, ".cb 1", sender_id=1000, outgoing=True)
    assert "♻️" in hidden.text, "вслепую .cb не сработал"
    await h.transport.inject(500, ".cbf", sender_id=1000, outgoing=True)
    assert "включены" in h.transport.sent[-1].text

    # terminal: реальная команда в песочнице
    await h.transport.inject(500, ".term echo hi_hydra", sender_id=1000, outgoing=True)
    term = h.transport.sent[-1]
    assert "hi_hydra" in term.text, term.text

    # lang: переключение и custom-строки
    await h.transport.inject(500, ".setlang en", sender_id=1000, outgoing=True)
    assert h.config["language"] == "en"
    assert "Language switched to en" in h.transport.sent[-1].text

    await h.transport.inject(500, ".langset ping title = CUSTOM PONG", sender_id=1000, outgoing=True)
    await h.transport.inject(500, ".ping", sender_id=1000, outgoing=True)
    assert "CUSTOM PONG" in h.transport.sent[-1].text, "custom-строка не применилась"

    # settings: toggle кнопкой
    await h.transport.inject(500, ".settings", sender_id=1000, outgoing=True)
    sform = h.transport.sent[-1]
    await h.transport.inject_callback(
        sform.buttons[0][0]["data"], 1000, chat_id=500, message_id=sform.message_id
    )
    assert h.config.get("power_save") is True

    # help: форма со списком модулей
    await h.transport.inject(500, ".help", sender_id=1000, outgoing=True)
    assert h.transport.sent[-1].buttons, "help без кнопок"
    await h.stop()


async def real_heroku_module() -> None:
    """Настоящий модуль coddrago/Heroku (пакетные импорты) через адаптер."""
    src = (
        ROOT.parent / "refs" / "heroku" / "heroku" / "modules" / "translations.py"
    ).read_text(encoding="utf-8")
    h = Hydra(owner_id=1000)
    await h.start()
    await h.loader.load_source("translations", src, framework="heroku")
    assert "setlang" in h.command_handlers, list(h.command_handlers)

    await h.transport.inject(500, ".setlang", sender_id=1000, outgoing=True)
    form = h.transport.sent[-1]
    assert form.buttons and len(form.buttons) >= 4, "нет кнопок языков"
    # нажатие текстом через мост: первая кнопка = English
    await h.transport.inject(500, ".cb 1 1", sender_id=1000, outgoing=True)
    assert "lang_saved" in form.text, form.text

    await h.transport.inject(500, ".setlang en", sender_id=1000, outgoing=True)
    assert "lang_saved" in h.transport.sent[-1].text
    await h.stop()


async def main() -> int:
    failures = 0

    n = compile_trees()
    print(ok(f"compile: {n} .py файлов (hydra_kernel + core + core_inline)"))

    try:
        check_resolver()
        print(ok("resolver: топосорт + детект цикла"))
    except AssertionError as e:
        print(fail(f"resolver: {e}"))
        failures += 1

    try:
        check_scanner()
        print(ok("scanner: exec/os.system/subprocess помечены"))
    except AssertionError as e:
        print(fail(f"scanner: {e}"))
        failures += 1

    # демонстрация блокировки небезопасного модуля
    hydra = Hydra()
    try:
        await hydra.loader.load_source("evil", "exec('x')\n", framework="hydra")
        print(fail("scanner не заблокировал exec()"))
        failures += 1
    except SecurityError:
        print(ok("loader: модуль с exec() отклонён (SecurityError)"))

    try:
        await real_mcub_module()
        print(ok("real refs/mcub modules/translations.py: форма языков, кнопка en, .setlang ru"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"real mcub translations: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await real_heroku_module()
        print(ok("real Heroku modules/translations.py: пакетные импорты, форма, кнопка, .setlang en"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"real heroku translations: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await modules_suite()
        print(ok("родные modules/ под единым движком: 10 модулей, 0 ошибок, .mylang отвечает"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"modules suite: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await bridge_suite()
        print(ok("мост кнопок (.cb/.it/.cbf, мульти-меню) на демо-модулях ядра"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"bridge suite: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await native_audit_suite()
        print(ok(f"аудит родных модулей: {len(NATIVE_AUDIT)} команд отвечают"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"native audit: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await mcub_pack_suite()
        print(ok("пак MCUB-модулей из репозитория: все грузятся, .info отвечает"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"mcub pack: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await real_hikka_dragon()
        print(ok("настоящие Hikka (hikkatl) и Dragon (pyrogram) модули работают"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"real hikka/dragon: {type(e).__name__}: {e}"))
        failures += 1

    # реальные MCUB-модули из репозитория MCUB-fork (фаза 4)
    mcub_fork_dir = ROOT.parent / "refs" / "mcub_fork" / "modules"
    if (mcub_fork_dir / "MCUB_info.py").exists():
        try:
            h = Hydra(owner_id=1000)
            await h.start()
            for name in ("MCUB_info", "translations"):
                src = (mcub_fork_dir / f"{name}.py").read_text(encoding="utf-8")
                await h.loader.load_source(name, src, framework="mcub", allow_unsafe=True)
            await h.transport.inject(500, ".info", sender_id=1000, outgoing=True)
            assert h.transport.sent and h.transport.sent[-1].text.strip() != ".info", \
                "реальный MCUB .info не ответил"
            await h.stop()
            print(ok("реальные MCUB-модули (MCUB-fork): .info отвечает, translations грузится"))
        except Exception as e:  # noqa: BLE001
            print(fail(f"real mcub-fork modules: {type(e).__name__}: {e}"))
            failures += 1

    # TUI-редактор (GUI при запуске юба) — headless через pty
    r = subprocess.run([sys.executable, "tools/tui_check.py"], capture_output=True, text=True, cwd=ROOT)
    if r.returncode == 0:
        print(ok("TUI-редактор: старт в pty, список модулей, выход по q"))
    else:
        print(fail(f"TUI: {(r.stdout + r.stderr).strip()[-200:]}"))
        failures += 1

    # Cython-компиляция ядра
    r = subprocess.run([sys.executable, "tools/build_native.py"], capture_output=True, text=True, cwd=ROOT)
    if "NATIVE OK" in r.stdout:
        v = subprocess.run(
            [sys.executable, "-c", "from hydra_kernel.pkg import scanner; print(scanner.__file__)"],
            capture_output=True, text=True, cwd=ROOT,
        )
        kind = ".so" if v.stdout.strip().endswith(".so") else ".py"
        print(ok(f"Cython: ядро скомпилировано, scanner импортируется из {kind}"))
    elif "SKIP" in r.stdout:
        print(ok("Cython: SKIP (нет тулчейна)"))
    else:
        print(fail(f"Cython: {(r.stderr or r.stdout).strip()[-200:]}"))
        failures += 1

    # Go-часть ядра + Go-модули (hrul-сборка из нескольких файлов)
    if shutil.which("go"):
        r = subprocess.run(["sh", "tools/build_go.sh"], capture_output=True, text=True, cwd=ROOT)
        if r.returncode == 0:
            from hydra_kernel.kernel.gobridge import GoBridge

            bridge = GoBridge()
            assert await bridge.start(), "hydracore не стартовал"
            pong = await bridge.call("ping")
            await bridge.stop()
            assert pong.get("ok"), pong

            # Go-модуль с полным паритетом: команда -> форма -> .cb -> edit/delete
            from hydra_kernel.pkg.go_loader import GoLoader

            h = Hydra(owner_id=1000)
            await h.start()
            go = GoLoader(h)
            names = await go.load_dir(ROOT / "gocore/bin")
            assert "echomod" in names, names
            await h.transport.inject(500, ".echo привет", sender_id=1000, outgoing=True)
            gform = h.transport.sent[-1]
            assert "Эхо: привет" in gform.text and ".cb 1" in gform.text, gform.text
            await h.transport.inject(500, ".cb 1 1", sender_id=1000, outgoing=True)
            assert "ещё раз" in gform.text, ".cb 1 1 не отредактировал Go-форму"
            await h.transport.inject(500, ".cb 2 1", sender_id=1000, outgoing=True)
            assert gform not in h.transport.sent, ".cb 2 1 не закрыл Go-форму"
            for mod in go.modules.values():
                await mod.stop()
            await h.stop()
            print(ok("Go-ядро: hydracore + Go-модуль echomod (hrul, 2 файла): .echo форма, .cb edit/delete"))
        else:
            print(fail(f"Go: {(r.stderr or r.stdout).strip()[-200:]}"))
            failures += 1
    else:
        print(ok("Go-ядро: SKIP (нет toolchain; сборка — sh tools/build_go.sh)"))

    for framework, source, expected, inline, cb, extra in TARGETS:
        try:
            base_fw = framework.split("-")[0]
            await smoke(base_fw, source, expected, inline, cb, extra)
            note = []
            if expected:
                note.append(f"'.ping' -> '{expected}'")
            if inline:
                note.append(f"inline '{inline[0]}' -> [{inline[2]}]")
            if cb:
                note.append(f"callback '{cb[0]}' -> '{cb[1]}'")
            if extra:
                note.append("расширенные проверки ok")
            print(ok(f"target {framework}: {', '.join(note)}"))
        except Exception as e:  # noqa: BLE001
            print(fail(f"target {framework}: {type(e).__name__}: {e}"))
            failures += 1

    print()
    if failures:
        print(f"{RED}СБОРКА ЗАВЕРШЕНА С ОШИБКАМИ: {failures}{RESET}")
        return 1
    print(f"{GREEN}СБОРКА УСПЕШНА: ядро + все цели (hydra, mcub, hikka, heroku, dragon){RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
