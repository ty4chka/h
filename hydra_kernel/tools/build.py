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
from hydra_kernel.compat.core_style import event_builder_pattern  # noqa: E402
from hydra_kernel.pkg.resolver import resolve, CyclicDependency  # noqa: E402
from hydra_kernel.pkg.manifest import Manifest  # noqa: E402
from hydra_kernel.pkg.scanner import scan_source, SecurityError  # noqa: E402

GREEN, RED, RESET = "\033[32m", "\033[31m", "\033[0m"


def ok(text: str) -> str:
    return f"{GREEN}OK{RESET}   {text}"


def fail(text: str) -> str:
    return f"{RED}FAIL{RESET} {text}"


def source_fixture(reference: Path, fixture: Path) -> tuple[str, Path]:
    """Прочитать внешний ref, если он есть, иначе versioned fixture из репо.

    Раньше acceptance-run безусловно читал ``../refs/...`` — путь существовал
    только на машине разработчика и превращал заявленную офлайн-сборку в два
    FileNotFoundError. Fixtures сохраняют проверку настоящего исходника,
    но делают её воспроизводимой в clean checkout и Termux.
    """

    path = reference if reference.is_file() else fixture
    if not path.is_file():
        raise FileNotFoundError(f"compat fixture is missing: {fixture}")
    return path.read_text(encoding="utf-8"), path


# ---------------------------------------------------------------- compile
def compile_trees() -> int:
    total = 0
    for rel in ("hydra_kernel", "core", "core_inline", "hydra_modules", "mcub_engine"):
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
    # Пользовательские MCUB-модули из этой папки теперь грузятся диспетчером
    # modules/mcub.py, поэтому синтаксис проверяется тем же build-прогоном.
    mcub_tree = tree / "mcub_mods"
    if mcub_tree.exists():
        for py in sorted(mcub_tree.glob("*.py")):
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


def check_android_optional_dependency_fallback() -> None:
    """Termux psutil может быть установлен, но падать при import на Android."""

    import sys as _sys
    import types as _types

    from hydra_kernel.compat import offline_deps

    probe = "_hydra_android_optional_probe"
    prior = _sys.modules.get(probe)
    _sys.modules[probe] = _types.ModuleType(probe)  # имитируем partial import
    original_import = offline_deps.importlib.import_module

    def android_failure(name, *args, **kwargs):
        if name == probe:
            raise NotImplementedError("platform android is not supported")
        return original_import(name, *args, **kwargs)

    offline_deps.importlib.import_module = android_failure
    try:
        assert offline_deps._import_or_none(probe) is None
        assert probe not in _sys.modules, "partial Android import не был очищен"
    finally:
        offline_deps.importlib.import_module = original_import
        if prior is not None:
            _sys.modules[probe] = prior
        else:
            _sys.modules.pop(probe, None)


async def check_mtproxy_fake_tls() -> None:
    """Exercise an ``ee`` handshake without contacting a public proxy."""

    import hashlib
    import hmac
    import time

    from hydra_kernel.mtproxy import (
        FakeTLSSecret,
        _FakeTLSStreamReader,
        _FakeTLSStreamWriter,
        is_fake_tls_secret,
        perform_fake_tls_handshake,
    )

    encoded = "ee" + ("13" * 16) + b"www.example.test".hex()
    secret = FakeTLSSecret.parse(encoded)
    assert is_fake_tls_secret(encoded)
    served = asyncio.get_running_loop().create_future()

    async def proxy(reader, writer) -> None:
        try:
            client_hello = await reader.readexactly(517)
            assert client_hello[:5] == b"\x16\x03\x01\x02\x00"
            zeroed = bytearray(client_hello)
            client_random = bytes(zeroed[11:43])
            zeroed[11:43] = b"\x00" * 32
            digest = hmac.new(secret.key, bytes(zeroed), hashlib.sha256).digest()
            timestamp = bytes(client_random[28 + index] ^ digest[28 + index] for index in range(4))
            assert abs(int.from_bytes(timestamp, "little") - int(time.time())) < 5

            # Same three-record welcome shape emitted by MTProxy FakeTLS.
            hello = bytearray(b"\x16\x03\x03\x00\x7a" + (b"\x00" * 122))
            hello[5] = 0x02
            hello[6:9] = b"\x00\x00\x7a"
            hello[9:11] = b"\x03\x03"
            hello[43] = 32
            hello[44:76] = client_hello[44:76]
            change_cipher_spec = b"\x14\x03\x03\x00\x01\x01"
            initial_data = b"\x17\x03\x03\x00\x02OK"
            transcript = bytearray(hello + change_cipher_spec + initial_data)
            transcript[11:43] = b"\x00" * 32
            hello[11:43] = hmac.new(
                secret.key, client_random + bytes(transcript), hashlib.sha256
            ).digest()
            writer.write(hello + change_cipher_spec + initial_data)
            await writer.drain()

            record_header = await reader.readexactly(5)
            assert record_header[:3] == b"\x17\x03\x03"
            size = int.from_bytes(record_header[3:5], "big")
            assert await reader.readexactly(size) == b"hydra"
            writer.write(b"\x17\x03\x03\x00\x05reply")
            await writer.drain()
            served.set_result(None)
        except BaseException as exc:  # propagate failures to the build caller
            if not served.done():
                served.set_exception(exc)
        finally:
            writer.close()

    server = await asyncio.start_server(proxy, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    writer = None
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        await perform_fake_tls_handshake(reader, writer, secret)
        tls_writer = _FakeTLSStreamWriter(writer)
        tls_reader = _FakeTLSStreamReader(reader)
        tls_writer.write(b"hydra")
        await tls_writer.drain()
        assert await tls_reader.readexactly(5) == b"reply"
        await asyncio.wait_for(served, timeout=3)
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # server intentionally closes after the probe
                pass
        server.close()
        await server.wait_closed()


def check_stale_native_lang_fallback() -> None:
    """MCUB nested strings survive an older compiled api.lang extension.

    Native extensions take precedence over ``.py`` and may originate from a
    prior checkout until the build's final native step refreshes them.  The
    MCUB compatibility layer must therefore retain the startup strings used by
    UpdatesMod independently of extension freshness.
    """

    import copy
    import types

    from core.lib.loader.module_base import Strings
    from hydra_kernel.api import lang

    original = copy.deepcopy(lang.GLOBAL_PACK)
    try:
        for locale in lang.GLOBAL_PACK.values():
            locale.pop("material_emoji", None)
        strings = Strings(types.SimpleNamespace(config={"language": "ru"}), {"name": "updates"})
        group = strings("material_emoji")
        assert callable(group) and group("load_3") == "🔭"
    finally:
        lang.GLOBAL_PACK.clear()
        lang.GLOBAL_PACK.update(original)


async def check_telethon_both_direction_subscription() -> None:
    """Live transport fans out through exactly two legal Telethon builders.

    Telethon rejects ``incoming=True, outgoing=True`` in one builder.  Hydra
    therefore owns one incoming and one outgoing builder and filters logical
    subscriptions in-process, rather than registering one native callback per
    command.
    """

    import types

    from hydra_kernel.kernel import transport as transport_module

    class FakeNewMessage:
        def __init__(self, **kwargs):
            if kwargs.get("incoming") and kwargs.get("outgoing"):
                raise ValueError("Telethon: incoming and outgoing are mutually exclusive")
            self.kwargs = kwargs

    class FakeEvents:
        NewMessage = FakeNewMessage

    class FakeClient:
        def __init__(self):
            self.handlers = []
            self.removed = []

        async def get_me(self):
            return types.SimpleNamespace(id=1000)

        def add_event_handler(self, callback, builder):
            self.handlers.append((callback, builder))

        def remove_event_handler(self, callback, builder):
            self.removed.append((callback, builder))

        def list_event_handlers(self):
            return list(self.handlers)

        async def send_message(self, _chat_id, _text, **_kw):
            return types.SimpleNamespace(id=999)

    old_have = transport_module._HAVE_TELETHON
    old_events = transport_module.events
    transport_module._HAVE_TELETHON = True
    transport_module.events = FakeEvents
    try:
        client = FakeClient()
        transport = transport_module.TelethonTransport(client=client)
        await transport.start()
        received = []

        async def handler(message):
            received.append(message)

        unsubscribe = transport.subscribe(
            handler, pattern=r"^\.ping$", incoming=True, outgoing=True
        )
        builders = [builder.kwargs for _, builder in client.handlers]
        assert builders == [{"incoming": True}, {"outgoing": True}], builders
        assert transport.diagnostics()["subscriptions"] == 1
        # Adding logical commands must not multiply native Telethon callbacks.
        for _ in range(20):
            transport.subscribe(handler, pattern=r"^\.other$", incoming=True, outgoing=True)
        assert len(client.handlers) == 2, client.handlers

        # Неполный sender_id — частый вид собственного события Telethon.
        outgoing = types.SimpleNamespace(
            chat_id=500,
            sender_id=None,
            raw_text=".ping",
            out=True,
            message=types.SimpleNamespace(id=77),
        )
        await client.handlers[1][0](outgoing)
        assert len(received) == 1
        msg = received[0]
        assert (msg.sender_id, msg.outgoing, msg.message_id, msg.text) == (
            1000, True, 77, ".ping",
        ), msg

        incoming = types.SimpleNamespace(
            chat_id=501,
            sender_id=2000,
            raw_text=".ping",
            out=False,
            message=types.SimpleNamespace(id=78),
        )
        await client.handlers[0][0](incoming)
        assert len(received) == 2
        msg = received[1]
        assert (msg.sender_id, msg.outgoing, msg.message_id, msg.text) == (
            2000, False, 78, ".ping",
        ), msg

        # Telemetry measures a slow logical handler, the full update and an
        # outbound RPC without adding more native Telegram subscriptions.
        async def measured_handler(_message):
            await asyncio.sleep(0)

        transport._slow_handler_after = 0
        transport._slow_rpc_after = 0
        transport.subscribe(measured_handler, pattern=r"^\.measure$", outgoing=True)
        measured = types.SimpleNamespace(
            chat_id=500,
            sender_id=1000,
            raw_text=".measure",
            out=True,
            message=types.SimpleNamespace(id=79),
        )
        previous_disabled = transport_module.logger.disabled
        transport_module.logger.disabled = True
        try:
            await client.handlers[1][0](measured)
            await transport.send(500, "telemetry")
        finally:
            transport_module.logger.disabled = previous_disabled
        metrics = transport.diagnostics()
        assert metrics["slow_handlers"] and metrics["slow_updates"] and metrics["slow_rpcs"], metrics

        unsubscribe()
        assert transport.diagnostics()["subscriptions"] == 21
        await transport.stop()
        assert len(client.removed) == 2, "shutdown did not remove shared dispatchers"

        # Real Telethon keeps a bound ``re.Pattern.match`` in ``pattern``;
        # offline builders instead expose kwargs.  Discovery must support both.
        class RealTelethonShape:
            pattern = re.compile(r"(?i)^\.cfg(?:\s|$)").match

        assert event_builder_pattern(RealTelethonShape()) == r"(?i)^\.cfg(?:\s|$)"
    finally:
        transport_module._HAVE_TELETHON = old_have
        transport_module.events = old_events


async def live_dispatcher_command_suite() -> None:
    """Boot the real ``m.py`` dispatcher shape over a fake Telethon client.

    ``NullTransport`` proves module behavior, but it cannot prove that a
    Telethon event builder reaches a command after the production dispatcher
    has loaded it.  This is deliberately a transport-shaped test: handlers are
    registered through :class:`TelethonTransport`, then raw NewMessage-like
    events are delivered through the actual registered builders.
    """

    import importlib.util
    import itertools
    import types

    from hydra_kernel.compat.offline_deps import ensure_offline_dependencies
    from hydra_kernel.kernel import transport as transport_module

    ensure_offline_dependencies()
    from telethon import events

    class FakeSent:
        def __init__(self, client, chat_id, message_id, text):
            self.client = client
            self.chat_id = int(chat_id)
            self.id = message_id
            self.message_id = message_id
            self.text = text
            self.message = text
            self.out = True

        async def edit(self, text, **kw):
            return await self.client.edit_message(self.chat_id, self.id, text, **kw)

        async def delete(self):
            return await self.client.delete_messages(self.chat_id, self.id)

    class FakeEvent(FakeSent):
        def __init__(self, client, chat_id, message_id, text, sender_id=1000, outgoing=True):
            super().__init__(client, chat_id, message_id, text)
            self.raw_text = text
            self.sender_id = sender_id
            self.out = outgoing
            self.sender = types.SimpleNamespace(id=sender_id, first_name="Owner", username="owner", bot=False)
            self.message = self
            self.reply_to_msg_id = None
            self.is_private = True
            self.is_group = False
            self.is_channel = False
            self.mentioned = False

        async def get_reply_message(self):
            return None

        async def get_sender(self):
            return self.sender

        async def get_chat(self):
            return types.SimpleNamespace(id=self.chat_id, username="audit")

        async def reply(self, text, **kw):
            return await self.client.send_message(self.chat_id, text, **kw)

    class FakeClient:
        def __init__(self):
            self.handlers = []
            self.removed = []
            self.sent = []
            self.deleted = []
            self._ids = itertools.count(100)

        async def get_me(self):
            return types.SimpleNamespace(id=1000, username="owner", first_name="Owner")

        def add_event_handler(self, callback, builder=None):
            self.handlers.append((callback, builder))
            return callback

        def remove_event_handler(self, callback, builder=None):
            self.removed.append((callback, builder))
            try:
                self.handlers.remove((callback, builder))
            except ValueError:
                pass

        def list_event_handlers(self):
            return list(self.handlers)

        def on(self, builder):
            def decorator(callback):
                self.add_event_handler(callback, builder)
                return callback

            return decorator

        async def send_message(self, entity, text, **kw):
            message = FakeSent(self, entity, next(self._ids), text)
            self.sent.append(message)
            return message

        async def edit_message(self, entity, message, text, **kw):
            message_id = message if isinstance(message, int) else getattr(message, "id", 0)
            for item in self.sent:
                if item.chat_id == int(entity) and item.id == message_id:
                    item.text = item.message = text
                    return item
            item = FakeSent(self, entity, message_id or next(self._ids), text)
            self.sent.append(item)
            return item

        async def delete_messages(self, entity, messages, **kw):
            ids = messages if isinstance(messages, (list, tuple)) else [messages]
            ids = {item if isinstance(item, int) else getattr(item, "id", 0) for item in ids}
            self.deleted.extend((int(entity), item) for item in ids)
            self.sent[:] = [item for item in self.sent if not (item.chat_id == int(entity) and item.id in ids)]
            return []

        async def send_file(self, entity, file, **kw):
            return await self.send_message(entity, kw.get("caption") or str(file), **kw)

    class NewMessage:
        """Real Telethon stores ``re.Pattern.match``, not raw kwargs."""

        def __init__(self, **kwargs):
            self.incoming = kwargs.get("incoming")
            self.outgoing = kwargs.get("outgoing")
            source = kwargs.get("pattern")
            self.pattern = re.compile(source).match if isinstance(source, str) else source

    old_events, old_have = transport_module.events, transport_module._HAVE_TELETHON
    old_new_message = events.NewMessage
    events.NewMessage = NewMessage
    transport_module.events = types.SimpleNamespace(
        NewMessage=NewMessage,
        InlineQuery=type("InlineQuery", (), {}),
        CallbackQuery=type("CallbackQuery", (), {}),
    )
    transport_module._HAVE_TELETHON = True
    hydra = None
    vector = None
    original_vector_net_req = None
    original_ensure_future = None
    try:
        client = FakeClient()
        transport = transport_module.TelethonTransport(client=client)
        hydra = Hydra(transport=transport, owner_id=1000, prefix=".")
        await hydra.start()
        spec = importlib.util.spec_from_file_location(
            "live_dispatcher_under_test", ROOT / "modules" / "mcub.py"
        )
        assert spec and spec.loader
        dispatcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dispatcher)

        # Vector schedules a real service-side ban check from ``on_load``.
        # The suite has no Vector credentials and validates dispatch only, so
        # suppress exactly that background coroutine before it reaches a URL.
        original_ensure_future = asyncio.ensure_future

        def safe_ensure_future(awaitable, *args, **kwargs):
            code = getattr(awaitable, "cr_code", None)
            qualname = getattr(code, "co_qualname", "")
            if qualname.endswith("Vector._check_ban"):
                close = getattr(awaitable, "close", None)
                if callable(close):
                    close()
                finished = asyncio.get_running_loop().create_future()
                finished.set_result(None)
                return finished
            return original_ensure_future(awaitable, *args, **kwargs)

        asyncio.ensure_future = safe_ensure_future
        try:
            records, errors = await dispatcher._load_owned_modules(hydra)
        finally:
            asyncio.ensure_future = original_ensure_future
            original_ensure_future = None
        assert not errors, f"production dispatcher loader errors: {errors}"
        assert client.handlers, "production dispatcher registered no Telethon handlers"
        live_metrics = transport.diagnostics()
        assert live_metrics["native_message_handlers"] == 2, live_metrics
        assert live_metrics["client_new_message_handlers"] >= 2, live_metrics
        assert live_metrics["subscriptions"] > 50, live_metrics
        assert any(
            "Vector.vector_install_payload_watcher" in record.get("label", "")
            for record in transport._subs
        ), "Vector watcher lost its slow-handler diagnostic label"

        # Silent Tags can wake Vector's unrelated outgoing watcher.  This suite
        # checks Telegram routing, not Vector's external bot endpoint.
        for record in records:
            candidate = record.module
            if getattr(candidate, "name", "") == "Vector":
                vector = candidate
                original_vector_net_req = candidate._net_req

                async def fake_vector_net(_method, _path, **_kw):
                    return {"username": "vector_audit_bot"}

                candidate._net_req = fake_vector_net
                break

        async def emit(text: str) -> list[str]:
            before = len(client.sent)
            raw = FakeEvent(client, 500, next(client._ids), text)
            for callback, builder in list(client.handlers):
                if type(builder).__name__ != "NewMessage":
                    continue
                if getattr(builder, "incoming", None) is True and raw.out:
                    continue
                if getattr(builder, "outgoing", None) is True and not raw.out:
                    continue
                pattern = getattr(builder, "pattern", None)
                if callable(pattern) and not pattern(text):
                    continue
                await callback(raw)
            await asyncio.sleep(0)
            return [item.text for item in client.sent[before:]]

        # These were advertised by Approve but previously had no production
        # handler.  Exercise their harmless branches through live-shaped
        # delivery, rather than only calling module methods directly.
        responses = {}
        for command in (
            ".ping", ".info", ".diag", ".modules", ".find ping", ".popular", ".allcmds",
            ".mload", ".mun", ".mls", ".mhelp", ".mcfg",
        ):
            output = await asyncio.wait_for(emit(command), timeout=5)
            assert output, f"{command}: no Telethon-shaped output"
            assert any(item.strip() != command for item in output), f"{command}: unedited echo only"
            responses[command] = "\n".join(output)
        assert "Pong" in responses[".ping"], responses[".ping"]
        assert "shared native handlers" in responses[".diag"], responses[".diag"]
        assert ".cfg" in responses[".allcmds"], "setup commands missing from allcmds catalogue"
        assert ".terminal_info" in responses[".allcmds"], "core commands missing from allcmds catalogue"
    finally:
        if original_ensure_future is not None:
            asyncio.ensure_future = original_ensure_future
        if vector is not None and original_vector_net_req is not None:
            vector._net_req = original_vector_net_req
        if hydra is not None:
            for name in list(hydra.registry.names()):
                await hydra.unload_module(name)
            await hydra.stop()
        events.NewMessage = old_new_message
        transport_module.events = old_events
        transport_module._HAVE_TELETHON = old_have


async def check_live_compatibility_shims() -> None:
    """L2 event/conversation shims keep live MCUB modules on Telethon stable."""

    import types

    from hydra_kernel.api.inline import CallbackQueryEvent
    from hydra_kernel.compat.base import ClientProxy
    from hydra_kernel.kernel.transport import Message, NullTransport

    class RawMessage:
        sender = "sender"
        reply_to = types.SimpleNamespace(reply_to_msg_id=71)
        mentioned = True
        is_group = True
        is_private = False

        async def get_reply_message(self):
            return "reply"

        async def get_chat(self):
            return "chat"

        async def get_sender(self):
            return "resolved-sender"

    native_event_client = object()
    event = types.SimpleNamespace(message=RawMessage(), client=native_event_client)
    message = Message(chat_id=500, sender_id=1000, text=".man", message_id=77, raw=event)
    assert message.id == 77
    assert message.reply_to_msg_id == 71 and message.is_reply
    assert message.sender == "sender" and message.client is native_event_client
    assert message.mentioned and message.is_group and not message.is_private
    assert await message.get_reply_message() == "reply"
    assert await message.get_chat() == "chat" and await message.get_sender() == "resolved-sender"
    assert CallbackQueryEvent("close", 1000, chat_id=500).input_chat == 500

    # Setup-style modules receive the same configurable owner identity through
    # the offline client as they do through Telethon's `get_me()`.
    offline_transport = NullTransport(me_id=2468)
    assert (await offline_transport.client.get_me()).id == 2468
    offline_proxy = ClientProxy(offline_transport)
    await offline_proxy.send_message("me", "self-alias")
    assert offline_transport.sent[-1].chat_id == 2468
    assert await offline_proxy.send_read_acknowledge(2468)

    from mcub_engine.utils_inject import parse_arguments

    parser = parse_arguments('.oa --test=reconnect --flash "hello world"')
    assert parser.raw_args == '--test=reconnect --flash "hello world"'
    assert parser.get_kwarg("test") == "reconnect" and parser.get_flag("flash")

    class NativeConversation:
        def __init__(self):
            self._pending_responses = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get_response(self):
            future = asyncio.get_running_loop().create_future()
            self._pending_responses["late"] = future
            return await future

    class NativeClient:
        def __init__(self):
            self.conversation_obj = NativeConversation()

        async def get_me(self):
            return types.SimpleNamespace(id=1000, username="real_user")

        def conversation(self, *_args, **_kwargs):
            return self.conversation_obj

    class LiveTransport:
        me_id = 1000

        def __init__(self):
            self.client = NativeClient()

    transport = LiveTransport()
    client = ClientProxy(transport)
    assert (await client.get_me()).username == "real_user"
    async with client.conversation("@example_bot") as conversation:
        try:
            await asyncio.wait_for(conversation.get_response(), timeout=0.001)
        except asyncio.TimeoutError:
            pass
        assert not transport.client.conversation_obj._pending_responses, (
            "cancelled Telethon waiter was left for a late update"
        )


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
    """Настоящий MCUB translations через адаптер (ref либо versioned fixture)."""
    src, _path = source_fixture(
        ROOT.parent / "refs" / "mcub" / "modules" / "translations.py",
        ROOT / "extras" / "mcub_pack" / "translations.py",
    )
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


# CubKit-подобный модуль (так собирают Vector/OpenAgent): относительные импорты
# в самый ранний момент, с маркером бутстрапа и без него.
RELATIVE_IMPORT_FIXTURE = '''# meta: name=relpkg_fixture version=1.0.0 framework=mcub
from core.lib.loader.module_base import ModuleBase, command
from .Const import LOADING_BANNER, _esc


class RelpkgFixture(ModuleBase):
    name = "relpkg_fixture"
    version = "1.0.0"

    @command("relpkg")
    async def cmd_relpkg(self, event):
        await event.edit(f"relative import ok: {_esc(LOADING_BANNER)}")
'''


async def relative_import_module_suite() -> None:
    """MCUB-модуль с `from .Const import ...` грузится через `.mload`.

    Регресс Termux-лога: CubKit-сборка Vector падала на
    «ModuleNotFoundError: No module named 'vector'» — Hydra выполняла исходник
    в безымянном namespace, а относительный импорт требует module-объект в
    sys.modules (в MCUB-fork загрузчик регистрирует его до exec).
    """

    import tempfile
    from pathlib import Path

    h = Hydra(owner_id=1000)
    await h.start()
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp)
        (bundle / "Const.py").write_text(
            'LOADING_BANNER = "banner-ok"\n\n\ndef _esc(text):\n    return text\n',
            encoding="utf-8",
        )
        module_file = bundle / "relpkg_fixture.py"
        module_file.write_text(RELATIVE_IMPORT_FIXTURE, encoding="utf-8")

        record = await h.loader.load_source(
            "relpkg_fixture",
            RELATIVE_IMPORT_FIXTURE,
            framework="mcub",
            file_path=str(module_file),
        )
        assert record.name == "relpkg_fixture", record.name
        assert record.module is not None

        await h.transport.inject(500, ".relpkg", sender_id=1000, outgoing=True)
        assert "relative import ok: banner-ok" in h.transport.sent[-1].text, \
            h.transport.sent[-1].text

        # `.mun` выгружает модуль и его запись в sys.modules не остаётся мусором
        await h.loader.unload("relpkg_fixture")
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

    # ``on_load`` у UpdatesMod использует вложенную группу material_emoji.
    # Lifecycle логирует исключения хуков вместо их проброса, поэтому проверяем
    # результат и не позволяем скрытому hook failure считаться успешной загрузкой.
    updates = h.registry.get("updates")
    assert updates is not None, "updates не зарегистрирован"
    assert getattr(updates.module, "PREMIUM_EMOJI", {}).get("bar") == "▰▰▰", \
        "UpdatesMod.on_load не инициализировал material_emoji"

    # LogBot должен пройти lifecycle, но не может создавать Telegram-чат через
    # NullTransport. Его offline no-op не должен оставлять фиктивный chat id.
    log_bot = h.registry.get("log_bot")
    assert log_bot is not None, "log_bot не зарегистрирован"
    assert not h.config.get("log_chat_id"), "offline LogBot создал log_chat_id"

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
    assert len(records) == 13, [r.name for r in records]
    fws = {r.framework for r in records}
    assert {"core", "setup", "mcub", "noop", "hydra"} <= fws, fws

    # метаданные: у каждого модуля version и корректное имя
    for rec in records:
        assert rec.manifest.version != "0.0.0", f"{rec.name}: нет метаданных version"
        assert rec.manifest.name == rec.name, f"{rec.name}: meta name != файла"

    # родная команда отвечает через единый транспорт
    await h.transport.inject(500, ".mylang", sender_id=1000, outgoing=True)
    assert any("🌐" in m.text for m in h.transport.sent), "родная .mylang не ответила"


async def control_manager_suite() -> None:
    """Exercise the non-menu paths of restored MCUB management commands."""

    import tempfile

    from hydra_kernel.kernel.transport import Message

    source = '''# meta: name=audit_dynamic version=1.0.0 framework=mcub
from core.lib.loader.module_base import ModuleBase, command
from core.lib.loader.module_config import ModuleConfig, ConfigValue

class AuditDynamic(ModuleBase):
    name = "audit_dynamic"
    config = ModuleConfig(ConfigValue("enabled", True, "audit setting"))

    @command("auditdyn", doc="audit command")
    async def auditdyn(self, event):
        await event.edit("audit dynamic works")
'''

    class Reply:
        raw_text = source
        text = source
        id = 901

    class Raw:
        async def get_reply_message(self):
            return Reply()

    h = Hydra(owner_id=1000)
    await h.start()
    try:
        records, errors = await h.loader.load_dir(
            ROOT / "modules", framework="auto", exclude=("mcub", "__init__"), allow_unsafe=True
        )
        assert not errors, errors
        control = h.registry.get("control").module

        # The actual command's no-reply branch is routed by Hydra; the reply
        # shape below then exercises its safe install branch without Telegram I/O.
        before = len(h.transport.sent)
        await h.transport.inject(500, ".mload", sender_id=1000, outgoing=True)
        assert len(h.transport.sent) > before and ".mload" in h.transport.sent[-1].text

        with tempfile.TemporaryDirectory() as temp_dir:
            control.modules_dir = Path(temp_dir)

            # Duplicate sources are skipped at boot to avoid double commands.
            # `.mun name --del` must nevertheless remove their orphaned file.
            orphan = Path(temp_dir) / "Vector_MCUB_Repo.py"
            orphan.write_text("# duplicate source retained on disk\n", encoding="utf-8")
            await h.transport.inject(500, ".mun vector_mcub_repo --del", sender_id=1000, outgoing=True)
            assert not orphan.exists(), "mun --del did not remove an unloaded duplicate source"
            assert "незагруженный" in h.transport.sent[-1].text

            event = Message(
                chat_id=500,
                sender_id=1000,
                text=".mload",
                outgoing=True,
                message_id=900,
                raw=Raw(),
                transport=h.transport,
            )
            await control.cmd_mload(event)
            record = h.registry.get("audit_dynamic")
            assert record is not None and record.framework == "mcub", "mload did not join unified registry"
            assert any(Path(temp_dir).glob("*.py")), "mload did not persist source for next boot"

            await h.transport.inject(500, ".mhelp audit_dynamic", sender_id=1000, outgoing=True)
            assert ".auditdyn" in h.transport.sent[-1].text, "mhelp missed installed MCUB command"
            await h.transport.inject(500, ".mcfg audit_dynamic", sender_id=1000, outgoing=True)
            assert "enabled" in h.transport.sent[-1].text and "True" in h.transport.sent[-1].text
            await h.transport.inject(500, ".mcfg audit_dynamic enabled false", sender_id=1000, outgoing=True)
            assert "False" in h.transport.sent[-1].text, "mcfg did not update config"
            await h.transport.inject(500, ".auditdyn", sender_id=1000, outgoing=True)
            assert h.transport.sent[-1].text == "audit dynamic works", "installed command is not dispatched"
            await h.transport.inject(500, ".mls", sender_id=1000, outgoing=True)
            assert "audit_dynamic" in h.transport.sent[-1].text, "mls missed installed module"
            await h.transport.inject(500, ".mun audit_dynamic --del", sender_id=1000, outgoing=True)
            assert h.registry.get("audit_dynamic") is None, "mun did not unload module"
            assert not list(Path(temp_dir).glob("*.py")), "mun --del did not remove saved source"
            before = len(h.transport.sent)
            await h.transport.inject(500, ".auditdyn", sender_id=1000, outgoing=True)
            assert len(h.transport.sent) == before, "mun left the unloaded command subscribed"

            functional_source = '''# meta: name=audit_function version=1.0.0 framework=mcub
def register(kernel):
    @kernel.register.command("auditfunc")
    async def auditfunc(event):
        await event.edit("audit functional works")
'''
            await control._install_mcub_source("audit_function", functional_source)
            await h.transport.inject(500, ".auditfunc", sender_id=1000, outgoing=True)
            assert h.transport.sent[-1].text == "audit functional works"
            await h.transport.inject(500, ".mun audit_function --del", sender_id=1000, outgoing=True)
            before = len(h.transport.sent)
            await h.transport.inject(500, ".auditfunc", sender_id=1000, outgoing=True)
            assert len(h.transport.sent) == before, "mun left functional MCUB command subscribed"

            # Vector's class-style installer passes `(url, module_name)`. It
            # must reach the same checked Control loader as `.mload`, not fail
            # with the former one-argument TypeError.
            url_source = '''# meta: name=audit_url_install version=1.0.0 framework=mcub
def register(kernel):
    @kernel.register.command("auditurl")
    async def auditurl(event):
        await event.edit("audit URL install works")
'''
            iface = control._mcub_interface()
            assert iface is not None
            control._download_source = lambda _url: url_source
            try:
                installed, detail = await iface.install_from_url(
                    "https://example.invalid/audit_url.py", "audit_url_install"
                )
            finally:
                delattr(control, "_download_source")
            assert installed, detail
            await h.transport.inject(500, ".auditurl", sender_id=1000, outgoing=True)
            assert h.transport.sent[-1].text == "audit URL install works"
            await h.transport.inject(500, ".mun audit_url_install --del", sender_id=1000, outgoing=True)
            assert h.registry.get("audit_url_install") is None

            # CubKit-style sources (Vector/OpenAgent) import helpers by relative
            # path: `from .Const import ...`. In the URL flow the module file is
            # written *after* exec, so the loader must publish a module object
            # in sys.modules with its own __path__ before running the source.
            # Before this, `.mload <url>` died with
            # «ModuleNotFoundError: No module named '<module>'».
            Path(temp_dir, "Const.py").write_text(
                'LOADING_BANNER = "banner-ok"\n', encoding="utf-8"
            )
            cubkit_source = '''# meta: name=audit_cubkit version=1.0.0 framework=mcub
from core.lib.loader.module_base import ModuleBase, command
from .Const import LOADING_BANNER


class AuditCubkit(ModuleBase):
    name = "audit_cubkit"

    @command("auditcubkit")
    async def cmd_cubkit(self, event):
        await event.edit(f"cubkit relative import: {LOADING_BANNER}")
'''
            control._download_source = lambda _url: cubkit_source
            try:
                installed, detail = await iface.install_from_url(
                    "https://example.invalid/audit_cubkit.py", "audit_cubkit"
                )
            finally:
                delattr(control, "_download_source")
            assert installed, detail
            await h.transport.inject(500, ".auditcubkit", sender_id=1000, outgoing=True)
            assert "cubkit relative import: banner-ok" in h.transport.sent[-1].text, \
                h.transport.sent[-1].text
            await h.transport.inject(500, ".mun audit_cubkit --del", sender_id=1000, outgoing=True)
            assert h.registry.get("audit_cubkit") is None

        # The command catalogue comes from all adapters, not only lifecycle
        # modules, so discovery reflects what production can actually route.
        await h.transport.inject(500, ".allcmds", sender_id=1000, outgoing=True)
        catalogue = h.transport.sent[-1].text
        assert ".cfg" in catalogue and ".terminal_info" in catalogue and ".mload" in catalogue

        # Core/setup adapters now own their subscriptions per registry record,
        # so a hot reload cannot leave old raw Telethon handlers behind.
        assert await h.loader.unload("cfg")
        assert await h.loader.unload("terminal")
        before = len(h.transport.sent)
        await h.transport.inject(500, ".cfg", sender_id=1000, outgoing=True)
        await h.transport.inject(500, ".terminal_info", sender_id=1000, outgoing=True)
        assert len(h.transport.sent) == before, "native handlers survived unload"
    finally:
        for name in list(h.registry.names()):
            await h.unload_module(name)
        await h.stop()


# Full production inventory.  Entries use harmless usage/menu branches; the
# two omitted actions are registered below but deliberately not executed by an
# automated smoke run because they replace the process or compile files.
OWNED_COMMAND_PROBES = (
    "ping", "info", "diag", "modules", "find", "popular", "allcmds",
    "mload", "mun", "mls", "mhelp", "mcfg",
    "cfg", "lm", "unlm", "hmods", "compile", "modinfo", "deps", "mcubmods",
    "mylang", "languages", "lang",
    "convert", "fix", "services", "set_key", "show_keys", "stats",
    "api_protection", "api_reset", "api_suspend", "lockdown",
    "text", "serverinfo", "sysinfo", "start",
    "terminal", "term", "shell", "exec", "terminal_info", "terminal_pwd",
    "terminal_ls", "terminal_whoami", "terminal_uname", "terminal_df", "neofetch",
    "approve", "decline", "trustlist", "untrust", "access",
    "vector", "vecupdate", "vecme", "vecdl",
    "mute", "unmute", "ban", "unban", "warn", "unwarn", "kick",
    "cleandeleted", "cleandel", "cleanup",
    "git", "wget",
    "catbox", "envs", "kappa", "0x0", "x0", "tmpfiles", "pomf", "bash", "upload",
    "man", "manhide", "manunhide", "help",
    "oa", "agent", "oaexport", "oaimport", "skills", "skillinstall", "ssinstall",
    "sendss", "imss", "delss", "oaplugin",
    "rf", "rfcache", "stags", "tictactoe", "tictacai",
    # Exercise OpenAgent's MCUB ArgumentParser without a provider request.
    "oa --test=reconnect", "oa --clear",
)
OWNED_COMMAND_NO_RUN = {
    "compileall": "writes/compiles local module files",
    "restart": "replaces the running userbot process",
}
_BRIDGE_COMMANDS = {"cb", "it", "cbf", "iqs", "iq"}


def _command_from_pattern(pattern: str) -> str | None:
    match = re.search(r"\^\\\.([A-Za-z0-9_]+)", pattern)
    return match.group(1).lower() if match else None


async def owned_mcub_modules_suite() -> None:
    """Диспетчер m.py подхватывает сохранённые modules/mcub_mods/.

    Проверяем именно production-путь, а не отдельный ``load_dir``: OpenAgent
    и ReadFile должны попасть в единый runtime, а идентичная копия Vector не
    должна зарегистрировать команды второй раз.
    """

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "hydra_owned_mcub_dispatcher", ROOT / "modules" / "mcub.py"
    )
    assert spec and spec.loader, "не удалось открыть modules/mcub.py"
    dispatcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dispatcher)

    h = Hydra(owner_id=1000)
    await h.start()
    try:
        records, errors = await dispatcher._load_owned_modules(h)
        assert not errors, f"ошибки загрузки собственных MCUB-модулей: {errors}"
        names = {record.name for record in records}
        assert {"openagent_mcub_repo", "readfile_mcub_repo"} <= names, names
        assert "vector_mcub_repo" not in names, "идентичный Vector загрузился второй раз"

        # man — реальный class-style MCUB: normalized event.reply_to_msg_id,
        # kernel._loader facade и programmatic inline form должны работать.
        before = len(h.transport.sent)
        await h.transport.inject(500, ".man", sender_id=1000, outgoing=True)
        forms = h.transport.sent[before:]
        assert len(forms) == 1, f".man отправил неожиданные ответы: {[m.text for m in forms]}"
        assert "OpenAgent" in forms[0].text and forms[0].buttons, ".man не собрал форму модулей"
        before = len(h.transport.sent)
        await h.transport.inject(500, ".man OpenAgent", sender_id=1000, outgoing=True)
        assert any("OpenAgent" in message.text for message in h.transport.sent[before:]), \
            ".man OpenAgent не показал карточку модуля"
        close_token = forms[0].buttons[-1][0]["data"]
        await h.transport.inject_callback(
            close_token, sender_id=1000, chat_id=500, message_id=forms[0].message_id
        )
        assert forms[0] not in h.transport.sent, ".man close callback не удалил форму"

        # `inline_query_and_click` returns a materialized InlineResult rather
        # than a bare normalized message.  Its programmatic click must route
        # through the actual callback dispatcher and preserve follow-up MCUB
        # buttons; Man and OpenAgent use this live-only-looking pattern.
        iface = h.loader.adapter_for("mcub").iface
        inline_ok, inline_result = await iface.inline_query_and_click(500, "man")
        assert inline_ok and getattr(inline_result, "message_id", 0), \
            "inline_query_and_click did not return an editable result"
        assert inline_result.peer_id == 500, \
            "materialized inline result lost its Telethon peer_id alias"
        assert await inline_result.click(0), \
            "programmatic inline-result click did not reach the MCUB callback"

        # Inventory is deliberately exhaustive: every production command is
        # either smoke-invoked below or explicitly classified as destructive.
        probe_names = {probe.split(maxsplit=1)[0] for probe in OWNED_COMMAND_PROBES}
        expected_commands = probe_names | set(OWNED_COMMAND_NO_RUN)
        discovered_commands = set()
        for record in h.transport._subs:
            pattern = record.get("pattern")
            if pattern is not None:
                name = _command_from_pattern(pattern.pattern)
                if name:
                    discovered_commands.add(name)
        for _handler, builder in h.transport.client.handlers:
            raw_pattern = event_builder_pattern(builder)
            if raw_pattern is not None:
                name = _command_from_pattern(raw_pattern)
                if name:
                    discovered_commands.add(name)
        discovered_commands -= _BRIDGE_COMMANDS
        assert discovered_commands == expected_commands, (
            "непокрытые/устаревшие production-команды: "
            f"missing={sorted(expected_commands - discovered_commands)}, "
            f"extra={sorted(discovered_commands - expected_commands)}"
        )

        def setup_hits(text: str) -> set[str]:
            hits = set()
            for _handler, builder in h.transport.client.handlers:
                raw_pattern = event_builder_pattern(builder)
                matcher = getattr(builder, "pattern", None)
                matches = bool(matcher(text)) if callable(matcher) else bool(
                    raw_pattern and re.search(raw_pattern, text)
                )
                if raw_pattern is not None and matches:
                    name = _command_from_pattern(raw_pattern)
                    if name:
                        hits.add(name)
            return hits

        assert setup_hits(".compileall") == {"compileall"}, ".compile перехватывает .compileall"
        assert setup_hits(".compile module") == {"compile"}, ".compile не маршрутизируется точно"
        assert not setup_hits(".cfgextra"), ".cfg перехватывает чужой префикс"

        # MCUB commands must be visible for both message directions; native
        # core/setup handlers are intentionally outgoing-only.
        for command_name in iface.command_owners:
            matching = [
                record for record in h.transport._subs
                if record.get("pattern") is not None
                and record["pattern"].match(f".{command_name}")
            ]
            assert any(record["incoming"] and record["outgoing"] for record in matching), (
                f"MCUB .{command_name} не имеет двунаправленной подписки"
            )

        import types
        import modules.terminal as terminal_module
        from utils import misc as native_utils

        def instance_named(name: str):
            return next(
                instance
                for instance in iface._class_module_instances.values()
                if getattr(instance, "name", None) == name
            )

        # Keep all smoke branches deterministic and non-destructive.  The
        # handlers themselves are still used; only external I/O is replaced.
        original_execute = terminal_module.execute_in_chroot

        async def fake_execute_in_chroot(*_args, **_kw):
            return "audit chroot output", 0

        terminal_module.execute_in_chroot = fake_execute_in_chroot
        vector = instance_named("Vector")
        original_net_req = vector._net_req

        # Regression: Vector's generic incoming watcher used to resolve its
        # remote bot ID before checking message text, causing an API request
        # and multi-second delay for every ordinary incoming message.
        lookup_calls = []

        async def slow_vector_lookup(*_args, **_kw):
            lookup_calls.append(True)
            await asyncio.sleep(0.05)
            return None

        vector.btid = 0
        vector._btid_retry_at = 0
        vector._net_req = slow_vector_lookup
        await vector.vector_install_payload_watcher(
            types.SimpleNamespace(out=False, text="ordinary incoming chat", sender_id=2000)
        )
        assert not lookup_calls, "Vector watcher queried its API for an unrelated message"

        async def fake_vector_net(method, path, **_kw):
            return {"username": "vector_audit_bot"} if path == "/api/tg-bot" else None

        vector._net_req = fake_vector_net
        uploader = instance_named("k:uploader")
        upload_globals = uploader.catbox_handler.__func__.__globals__
        missing = object()
        original_requests = upload_globals.get("requests", missing)
        # The no-reply branch then proves each handler reaches its own usage
        # response without making an upload/network request.
        upload_globals["requests"] = object()
        openagent = instance_named("OpenAgent")
        session_manager = openagent.session_manager

        async def in_memory_session_save():
            session_manager._saved_generation = session_manager._save_generation

        session_manager.save = in_memory_session_save

        async def invoke(command: str):
            # Native terminal aliases deliberately share one rate-limit bucket;
            # clear only test state so each command's own branch is exercised.
            native_utils._rate_limits.pop(1000, None)
            before = len(h.transport.sent)
            await asyncio.wait_for(
                h.transport.inject(500, f".{command}", sender_id=1000, outgoing=True),
                timeout=3,
            )
            replies = h.transport.sent[before:]
            assert replies and any(reply.text.strip() != f".{command}" for reply in replies), (
                f".{command}: нет ответа"
            )
            return replies[-1]

        try:
            for command in OWNED_COMMAND_PROBES:
                await invoke(command)

            # The `.oa` sessions panel is a real programmatic inline form.
            # Verify its input bridge as well as the command reply itself.
            panel = await invoke("oa")
            assert ".it 1" in panel.text and any(
                button.get("input")
                for row in (panel.buttons or [])
                for button in row
                if isinstance(button, dict)
            ), "OpenAgent panel lost its input callbacks"
            menu_no = h.bridge._msg_no[panel.chat_id][panel.message_id]
            await h.transport.inject(
                500, f".it 1 {menu_no} audit-session", sender_id=1000, outgoing=True
            )
            assert "audit-session" in panel.text, "OpenAgent .it input did not update its session panel"

            # Functional MCUB callback forms still use the normal callback
            # router (not an artificial direct call).
            api_form = await invoke("api_protection")
            api_menu_no = h.bridge._msg_no[api_form.chat_id][api_form.message_id]
            await h.transport.inject(
                500, f".cb 1 {api_menu_no}", sender_id=1000, outgoing=True
            )
            # Текст может быть локализован (mcub langpacks: «Зaщитa API»),
            # поэтому проверяем сам факт перерисовки формы, а не только
            # англоязычный дефолт из FALLBACK_LANG модуля.
            assert api_form.text.strip() and (
                "API" in api_form.text or "\u0417a\u0449\u0438\u0442a" in api_form.text
            ), f"API protection callback did not edit its form: {api_form.text[:120]}"

            # A tagged incoming message exercises normalized Message.mentioned,
            # get_chat/get_sender, is_private and the `me` ClientProxy alias.
            await invoke("stags on")

            class TaggedRaw:
                mentioned = True
                is_private = False
                sender = types.SimpleNamespace(bot=False, first_name="Audit sender")

                async def get_chat(self):
                    return types.SimpleNamespace(username="audit_chat", title="Audit chat")

                async def get_sender(self):
                    return self.sender

            before = len(h.transport.sent)
            await h.transport.inject(
                -100_123,
                "@hydra audit tag",
                sender_id=2000,
                outgoing=False,
                raw=TaggedRaw(),
            )
            assert any(message.chat_id == h.transport.me_id for message in h.transport.sent[before:]), (
                "silent-tags watcher did not log a normalized tagged incoming message"
            )
        finally:
            terminal_module.execute_in_chroot = original_execute
            vector._net_req = original_net_req
            if original_requests is missing:
                upload_globals.pop("requests", None)
            else:
                upload_globals["requests"] = original_requests
    finally:
        for name in list(h.registry.names()):
            await h.unload_module(name)
        await h.stop()


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
    src, _path = source_fixture(
        ROOT.parent / "refs" / "heroku" / "heroku" / "modules" / "translations.py",
        ROOT / "extras" / "heroku_pack" / "translations.py",
    )
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
    print(ok(f"compile: {n} .py файлов (hydra_kernel + core + core_inline + mcub_engine)"))

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

    try:
        check_android_optional_dependency_fallback()
        print(ok("offline deps: Android/Termux fallback для неподдерживаемого psutil"))
    except AssertionError as e:
        print(fail(f"offline deps: {e}"))
        failures += 1

    try:
        await check_mtproxy_fake_tls()
        print(ok("MTProxy FakeTLS: ee-secret handshake и TLS record bridge"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"MTProxy FakeTLS: {type(e).__name__}: {e}"))
        failures += 1

    try:
        check_stale_native_lang_fallback()
        print(ok("MCUB strings: fallback material_emoji переживает устаревший native api.lang"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"MCUB strings: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await check_telethon_both_direction_subscription()
        print(ok("Telethon transport: 2 shared live subscriptions, routing and latency telemetry work"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"Telethon transport: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await live_dispatcher_command_suite()
        print(ok("live dispatcher: centralized Telethon boot delivers .ping/.info/.diag and MCUB management"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"live dispatcher: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await check_live_compatibility_shims()
        print(ok("live compat: reply_to/id и cleanup отменённого Telethon conversation"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"live compat: {type(e).__name__}: {e}"))
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
        print(ok("real MCUB translations (vendored fixture/ref): форма языков, кнопка en, .setlang ru"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"real mcub translations: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await real_heroku_module()
        print(ok("real Heroku modules/translations.py: пакетные импорты, форма, кнопка, .setlang en"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"real heroku translations: {type(e).__name__}: {e}"))
        failures += 1

    # Языковые паки проверяются отдельным процессом: в нём реальный
    # utils.strings импортируется раньше ядра — ровно как в боевом m.py.
    r = subprocess.run(
        [sys.executable, "tools/langpacks_check.py"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if r.returncode == 0:
        print(ok("MCUB langpacks: реальный utils.strings + core.langpacks, modules/protect.py грузится"))
    else:
        print(fail(f"MCUB langpacks: {(r.stdout + r.stderr).strip()[-300:]}"))
        failures += 1

    try:
        await relative_import_module_suite()
        print(ok("MCUB относительные импорты (CubKit-стиль): модуль грузится и отвечает"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"MCUB относительные импорты: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await modules_suite()
        print(ok("родные modules/ под единым движком: 13 модулей, 0 ошибок, .mylang и .ping отвечают"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"modules suite: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await owned_mcub_modules_suite()
        print(ok("собственные modules/mcub_mods/: все 100 команд инвентаризированы; 98 safe-веток, OpenAgent input и silent-tags проверены"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"owned MCUB modules: {type(e).__name__}: {e}"))
        failures += 1

    try:
        await control_manager_suite()
        print(ok("control: .mload/.mls/.mhelp/.mcfg/.mun работают через единый реестр"))
    except Exception as e:  # noqa: BLE001
        print(fail(f"control manager: {type(e).__name__}: {e}"))
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
