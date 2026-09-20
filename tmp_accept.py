# -*- coding: utf-8 -*-
"""Финальная приёмка совместимости с MCUB-fork (ручная, не в сборке)."""
import asyncio
import re
import sys

sys.path.insert(0, "")
from hydra_kernel.app import Hydra

OK = 0
FAIL = []


def check(name, cond, detail=""):
    global OK
    if cond:
        OK += 1
        print(f"  OK   {name}")
    else:
        FAIL.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")


# --- Модуль 1: URL-кнопки (vecme-паттерн) ---
URL_SRC = r'''
from core.lib.loader.module_base import ModuleBase, command
from telethon import Button

class UrlMod(ModuleBase):
    name = "urlmod"
    version = "1.0.0"

    @command("vecme2")
    async def cmd_vecme(self, event):
        await event.edit(
            "🛡 Vector Mini App",
            buttons=[
                [Button.url("🛡 Vector Mini App", "https://t.me/vector/app")],
                [{"text": "🌐 dict url", "url": "https://example.com/page"}],
            ],
        )
'''

# --- Модуль 2: approve-паттерн (кнопки через команду + клик с bytes data) ---
APPROVE_SRC = r'''
from core.lib.loader.module_base import ModuleBase, command
from telethon import Button

class Approve2Mod(ModuleBase):
    name = "approve2"
    version = "1.0.0"

    @command("approve2")
    async def cmd_approve(self, event):
        await event.edit(
            "Одобрить @user как доверенного?",
            buttons=[[
                Button.inline("✅ Одобрить", b"appr2_yes"),
                Button.inline("❌ Отказ", b"appr2_no"),
            ]],
        )

    async def callback_handler(self, event):
        if event.data == b"appr2_yes":
            await event.answer("cb-approved")
        elif event.data == b"appr2_no":
            await event.answer("cb-rejected")
'''

# --- Модуль 3: switch-inline + raw-data + args + rich({
#   query,unicode-название по префиксу
# }) ---
MIX_SRC = r'''
from core.lib.loader.module_base import ModuleBase, command
from telethon import Button

class MixMod(ModuleBase):
    name = "mixmod"
    version = "1.0.0"

    @command("mix")
    async def cmd_mix(self, event):
        parsed = self.args(event)
        total = len(parsed.args) + len(parsed.flags) + len(parsed.kwargs)
        await event.edit(
            f"args ok: {total}",
            buttons=[
                [Button.switch_inline("🔍 поиск", query="hello")],
                [Button.inline("🎲 raw", b"raw_unquiet_1")],
                [self.Button.rich().inline("💎 rich cb", self.on_rich)],
            ],
        )

    async def on_rich(self, event, **kw):
        await event.answer("rich-fired")
'''


async def main():
    h = Hydra(owner_id=1000)
    await h.start()
    iface = h.loader.adapter_for("mcub").iface
    try:
        # 1) URL-кнопка через телеграф-совместимый event.edit
        await h.loader.load_source("urlmod", URL_SRC, framework="mcub", allow_unsafe=True)
        before = len(h.transport.sent)
        await h.transport.inject(500, ".vecme2", sender_id=1000, outgoing=True)
        forms = h.transport.sent[before:]
        txt = forms[0].text
        check("url button в тексте (↗ ... : url)",
              "https://t.me/vector/app" in txt and "🛡 Vector Mini App" in txt, txt)
        check("dict-уровневый url тоже рендерится", "https://example.com/page" in txt, txt)

        # 2) approve-паттерн: команда edit с inline-кнопками → меню с токенами → клик
        await h.loader.load_source("approve2", APPROVE_SRC, framework="mcub", allow_unsafe=True)
        iface.register_callback_handler("appr2_", iface.loaded_modules["approve2"].callback_handler)
        before = len(h.transport.sent)
        await h.transport.inject(500, ".approve2", sender_id=1000, outgoing=True)
        forms = h.transport.sent[before:]
        m = re.search(r"<code>\.cb 1 (\d+)</code>", forms[0].text)
        check("меню сгенерировано для approve-промпта", m is not None, forms[0].text)
        if m:
            before_ans = len(h.transport.callback_answers)
            await h.transport.inject(500, f".cb 1 {m.group(1)}", sender_id=1000, outgoing=True)
            answers = h.transport.callback_answers[before_ans:]
            check("клик .cb 1 вызывает обработчик (answer)",
                  any(a[1] == "cb-approved" for a in answers), repr(answers))
        m2 = re.search(r"<code>\.cb 2 (\d+)</code>", forms[0].text)
        if m2:
            before_ans = len(h.transport.callback_answers)
            await h.transport.inject(500, f".cb 2 {m2.group(1)}", sender_id=1000, outgoing=True)
            answers = h.transport.callback_answers[before_ans:]
            check("клик .cb 2 → reject", any(a[1] == "cb-rejected" for a in answers), repr(answers))

        # 3) mixed: args iterable + switch-inline → .iq + raw Data + rich()
        await h.loader.load_source("mixmod", MIX_SRC, framework="mcub", allow_unsafe=True)
        iface.register_callback_handler("raw_unquiet_", lambda e: e.answer("raw-fired"))
        before = len(h.transport.sent)
        await h.transport.inject(500, ".mix a b --flag x=1", sender_id=1000, outgoing=True)
        forms = h.transport.sent[before:]
        txt = forms[0].text
        check("args() даёт iterable-парсер (2 args+0 flags+1 kwarg=3)", "args ok: 3" in txt, txt)
        check("switch-inline рендерится как .iq-строка", ".iq hello" in txt, txt)
        check("ButtonBridge.cbf-строка для rich() присутствует", ".cb" in txt, txt)
        buttons = forms[0].buttons or []
        rich_btns = [b for row in buttons for b in row if "rich" in str(b.get("text", ""))]
        check("rich() кнопка отрисована как обычный callback-токен", len(rich_btns) == 1, repr(buttons))
        if rich_btns and rich_btns[0].get("data"):
            before_ans = len(h.transport.callback_answers)
            await h.transport.inject_callback(
                rich_btns[0]["data"], sender_id=1000, chat_id=500, message_id=1
            )
            answers = h.transport.callback_answers[before_ans:]
            check("rich() клик вызывает handler", any(a[1] == "rich-fired" for a in answers), repr(answers))
        raw_btns = [b for row in buttons for b in row if str(b.get("text", "")).startswith("🎲")]
        if raw_btns and raw_btns[0].get("data"):
            before_ans = len(h.transport.callback_answers)
            await h.transport.inject_callback(
                raw_btns[0]["data"], sender_id=1000, chat_id=500, message_id=1
            )
            answers = h.transport.callback_answers[before_ans:]
            check("raw-data callback → generic registry", any(a[1] == "raw-fired" for a in answers), repr(answers))

        # 4) register.method вызывается после register(kernel)
        METHOD_SRC = r'''
_methods_called = []

def setup(kernel):
    _methods_called.append(kernel.custom_prefix)

def register(kernel):
    at = kernel.register
    at.command("mtest")
    @kernel.register.method
    def bench(kernel):
        _methods_called.append("method-ok")

class _Sink:  # заглушка чтобы registered() не падал
    pass

def _mtest(event):
    pass

mtest = None

def at_command_probe():
    return _methods_called
'''
        # функциональный стиль: register(kernel) + @register.method
        src_fn = '''
from core.lib.loader.module_base import ModuleBase  # noqa

def register(kernel):
    @kernel.register.command("mmethod")
    async def mmethod(event):
        await event.edit("mm ok")

    @kernel.register.method
    async def _setup(kernel):
        kernel._method_probe = "invoked"

'''
        await h.loader.load_source("mixmethod", src_fn, framework="mcub", allow_unsafe=True)
        check("register.method вызван при загрузке", getattr(iface, "_method_probe", None) == "invoked",
              repr(getattr(iface, "_method_probe", None)))
        check("mmethod зарегистрирован", "mmethod" in h.command_handlers, repr(list(h.command_handlers)[:5]))
        # KernelRegister extras
        check("register.get_command", iface.register.get_command("mmethod") != {}, iface.register.get_command("mmethod"))
        check("register.get_all_aliases словарь", isinstance(iface.register.get_all_aliases(), dict))
        check("register.get_watchers list", isinstance(iface.register.get_watchers(), list))
        check("register.unregister_command", iface.register.unregister_command("mmethod") is True)
        check("unregister_command удалил обработчик", "mmethod" not in h.command_handlers)
        check("iface._inline.form api", hasattr(iface.inline, "form"))
        check("iface._log api", hasattr(iface._log, "log_module") and hasattr(iface._log, "send_error_log"))
        check("iface repositories дефолт", iface.repositories and iface.repositories[0] == iface.default_repo)
        check("iface ADMIN_ID == owner", str(iface.ADMIN_ID) == "1000")
        # utils поверхность
        import utils
        check("utils.parse_arguments (real)", hasattr(utils.parse_arguments, "__call__"))
        from utils.arg_parser import ArgumentParser
        p = ArgumentParser(".cmd a b --flag --n=5 -x rest", ".")
        check("ArgumentParser tuple-протокол", [x for x in p] == p.args, p.args)
        check("ArgumentParser flags/kwargs",
              "flag" in p.flags and p.kwargs.get("n") == 5 and p.kwargs.get("x") == "rest",
              (p.flags, p.kwargs))
        check("ArgumentParser.get_flag/get_kwarg api",
              p.get_flag("flag") is True and p.get_kwarg("n") == 5, (p.flags, p.kwargs))
        from utils.helpers import escape_html, get_prefix
        check("utils.helpers.escape_html", escape_html("<b>") == "&lt;b&gt;")
        from utils.platform import get_platform, get_platform_info
        check("utils.platform", isinstance(get_platform(), str) and isinstance(get_platform_info(), dict), get_platform())
        from utils.strings import Strings
        s = Strings("ru", {"ru": {"hi": "Привет {n}"}})
        check("utils.Strings (real)", s("hi", n="X") == "Привет X", s("hi", n="X"))
        from utils.custom_placeholders import register_placeholder, list_placeholder_keys
        check("utils.custom_placeholders", callable(register_placeholder))
        from utils.security import get_db_path, safe_extract_archive
        check("utils.security extras", isinstance(get_db_path(), str))
        from core.lib.types import Client, Event, Kernel, Message, Register
        check("core.lib.types полный", all(x is not None for x in (Client, Event, Kernel, Message, Register)))
        from core.lib.base.permissions import check_trust, CallbackPermissionManager
        check("core.lib.base.permissions", callable(check_trust) and CallbackPermissionManager is not None)
        from core.lib.rich_buttons import RichCallbackButton, RichButtonRow
        check("core.lib.rich_buttons", RichButtonRow is not None)
        from core.lib.time import TTLCache, TaskScheduler
        check("core.lib.time", TTLCache is not None and TaskScheduler is not None)
        from core.lib.loader.hikka_compat import is_hikka_module
        check("core.lib.loader.hikka_compat", is_hikka_module("from .. import loader\nclass M(loader.Module):") is True)
        from core.lib.loader.repository import parse_repo_modules_list, RepositoryManager
        check("repository extras", parse_repo_modules_list("a.py\n# x\nb") == ["a", "b"])
        # Button factory extras
        from core.lib.loader.module_base import ModuleBase as MB
        bf = MB.__dict__.get("ButtonFactory")
        check("Button.copy/request_phone/rich", all(hasattr(bf, n) for n in ("copy", "request_phone", "request_location", "request_poll", "game", "unknown", "with_icon", "style", "rich")))
        check("RichButtonFactory", hasattr(MB, "RichButtonFactory"))
        # make_cb_button реальной сигнатуры
        from core_inline.api.inline import make_cb_button
        check("make_cb_button(text, callback)", callable(make_cb_button))
        btn = make_cb_button("t", lambda e: None)
        btn_data = getattr(btn, "data", None) or getattr(btn, "token", None)
        check("make_cb_button возвращает inline-кнопку с токеном", btn_data is not None, repr(btn))
        # старая форма (kernel, text, callback) тоже работает
        btn2 = make_cb_button(iface, "t2", lambda e: None)
        check("make_cb_button(kernel, ...) legacy-форма", (getattr(btn2, "data", None) or getattr(btn2, "token", None)) is not None, repr(btn2))
        # restart_kernel real
        from utils import restart_kernel
        import inspect as _inspect
        check("utils.restart_kernel(async, kernel-арг)", _inspect.iscoroutinefunction(restart_kernel))

    finally:
        await h.stop()

    print(f"\n=== PASSED {OK} / FAILED {len(FAIL)} ===")
    if FAIL:
        for f in FAIL:
            print(" -", f)
        sys.exit(1)


asyncio.run(main())
