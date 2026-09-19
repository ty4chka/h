# scope: hikka_only
# meta name: Terminal
# meta developer: @bsod4ik_plugins
# meta version: 1.0.4
# ©️ Dan Gazizullin, 2021-2023
# ©️ Codrago, 2024-2025

import asyncio
import contextlib
import logging
import os
import re
import signal
import time
import typing

import herokutl
from telethon.tl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)


def hash_msg(message):
    return f"{str(utils.get_chat_id(message))}/{str(message.id)}"


async def read_stream(func: callable, stream, delay: float):
    last_task = None
    data = b""
    while True:
        chunk = await stream.read(1)

        if not chunk:
            if last_task:
                last_task.cancel()
                await func(data.decode(errors="replace"))
            break

        data += chunk

        if last_task:
            last_task.cancel()

        last_task = asyncio.ensure_future(sleep_for_task(func, data, delay))


async def sleep_for_task(func: callable, data: bytes, delay: float):
    await asyncio.sleep(delay)
    await func(data.decode(errors="replace"))


class MessageEditor:
    CALL_EMOJI = '<a href="tg://emoji?id=5395444784611480792">✏️</a>'
    STDOUT_EMOJI = '<a href="tg://emoji?id=5422439311196834318">✅</a>'
    STDERR_EMOJI = '<a href="tg://emoji?id=5210952531676504517">❌</a>'
    TIME_EMOJI = '<a href="tg://emoji?id=6012562513382612008">⏱️</a>'

    def __init__(
        self,
        message: herokutl.tl.types.Message,
        command: str,
        config,
        strings,
        request_message,
    ):
        self.message = message
        self.command = command
        self.stdout = ""
        self.stderr = ""
        self.rc = None
        self.redraws = 0
        self.config = config
        self.strings = strings
        self.request_message = request_message
        self.started_at = time.perf_counter()
        self.finished_ms = None

    def _get_result_text(self):
        if self.rc is None:
            return self.stdout or self.stderr
        if self.rc == 0:
            return self.stdout or self.stderr
        return self.stderr or self.stdout

    def _get_result_header(self):
        if self.rc is not None and self.rc != 0:
            return f"{self.STDERR_EMOJI} <b>Stderr:</b>"
        return f"{self.STDOUT_EMOJI} <b>Stdout:</b>"

    def _build_text(self):
        result = utils.escape_html(self._get_result_text())
        if len(result) > 3400:
            result = result[-3400:]

        text = (
            f"{self.CALL_EMOJI} <b>System call</b> <code>{utils.escape_html(self.command)}</code>\n"
            f"{self._get_result_header()}\n"
            f"<pre><code>{result or ' '}</code></pre>"
        )

        if self.finished_ms is not None:
            text += f"<blockquote>{self.TIME_EMOJI} <b>Completed in {self.finished_ms} ms</b></blockquote>"

        return text

    async def update_stdout(self, stdout):
        self.stdout = stdout
        await self.redraw()

    async def update_stderr(self, stderr):
        self.stderr = stderr
        await self.redraw()

    async def redraw(self):
        text = self._build_text()
        with contextlib.suppress(herokutl.errors.rpcerrorlist.MessageNotModifiedError):
            try:
                self.message = await utils.answer(self.message, text)
            except herokutl.errors.rpcerrorlist.MessageTooLongError as e:
                logger.error(e)
                logger.error(text)

    async def cmd_ended(self, rc):
        self.rc = rc
        self.state = 4
        self.finished_ms = int((time.perf_counter() - self.started_at) * 1000)
        await self.redraw()

    def update_process(self, process):
        pass


class SudoMessageEditor(MessageEditor):
    PASS_REQ = ["[sudo] password for", "[sudo] пароль для"]
    WRONG_PASS = [
        r"\[sudo\] password for (.*): Sorry, try again\.",
        r"\[sudo\] пароль для (.*): Попробуйте еще раз\.",
    ]
    TOO_MANY_TRIES = [
        r"\[sudo\] password for (.*): sudo: [0-9]+ incorrect password attempts",
        r"\[sudo\] пароль для (.*): sudo: [0-9]+ неверные попытки ввода пароля",
    ]

    def __init__(self, message, command, config, strings, request_message):
        super().__init__(message, command, config, strings, request_message)
        self.process = None
        self.state = 0
        self.authmsg = None

    def update_process(self, process):
        logger.debug("got sproc obj %s", process)
        self.process = process

    async def update_stderr(self, stderr):
        logger.debug("stderr update %s", stderr)
        self.stderr = stderr
        lines = stderr.strip().split("\n") if stderr.strip() else [""]
        lastline = lines[-1]
        lastlines = lastline.rsplit(" ", 1)
        handled = False

        if (
            len(lines) > 1
            and any(re.fullmatch(i, lines[-2]) for i in self.WRONG_PASS)
            and len(lastlines) > 1
            and any(lastlines[0] == i for i in self.PASS_REQ)
            and self.state == 1
        ):
            await utils.answer(self.message, self.strings("auth_fail"))
            self.state = 0
            handled = True
            await asyncio.sleep(2)
            if self.authmsg:
                await self.authmsg.delete()

        if len(lastlines) > 1 and any(lastlines[0] == i for i in self.PASS_REQ) and self.state == 0:
            text = self.strings("auth_needed").format(self.message.client.herokutl_me.id)

            try:
                await utils.answer(self.message, text)
            except herokutl.errors.rpcerrorlist.MessageNotModifiedError as e:
                logger.debug(e)

            command = "<code>" + utils.escape_html(self.command) + "</code>"
            user = utils.escape_html(lastlines[1][:-1])

            self.authmsg = await self.message.client.send_message(
                "me",
                self.strings("auth_msg").format(command, user),
            )

            self.message.client.remove_event_handler(self.on_message_edited)
            self.message.client.add_event_handler(
                self.on_message_edited,
                herokutl.events.messageedited.MessageEdited(chats=["me"]),
            )
            handled = True

        if len(lines) > 1 and (
            any(re.fullmatch(i, lastline) for i in self.TOO_MANY_TRIES) and self.state in {1, 3, 4}
        ):
            await utils.answer(self.message, self.strings("auth_locked"))
            if self.authmsg is not None:
                await self.authmsg.delete()
            self.state = 2
            handled = True

        if not handled:
            if self.authmsg is not None:
                await self.authmsg.delete()
                self.authmsg = None
            self.state = 2
            await self.redraw()

    async def update_stdout(self, stdout):
        self.stdout = stdout

        if self.state != 2:
            self.state = 3

        if self.authmsg is not None:
            await self.authmsg.delete()
            self.authmsg = None

        await self.redraw()

    async def on_message_edited(self, message):
        if self.authmsg is None:
            return

        if hash_msg(message) == hash_msg(self.authmsg):
            try:
                self.authmsg = await utils.answer(message, self.strings("auth_ongoing"))
            except herokutl.errors.rpcerrorlist.MessageNotModifiedError:
                await message.delete()

            self.state = 1
            self.process.stdin.write(message.message.message.split("\n", 1)[0].encode() + b"\n")


class RawMessageEditor(SudoMessageEditor):
    def __init__(
        self,
        message,
        command,
        config,
        strings,
        request_message,
        show_done=False,
    ):
        super().__init__(message, command, config, strings, request_message)
        self.show_done = show_done

    async def redraw(self):
        text = self._build_text()
        with contextlib.suppress(
            herokutl.errors.rpcerrorlist.MessageNotModifiedError,
            herokutl.errors.rpcerrorlist.MessageEmptyError,
            ValueError,
        ):
            try:
                self.message = await utils.answer(self.message, text)
            except herokutl.errors.rpcerrorlist.MessageTooLongError as e:
                logger.error(e)
                logger.error(text)


@loader.tds
class TerminalMod(loader.Module):
    """Runs commands in terminal and shows formatted output."""

    strings = {
        "name": "Terminal",
        "fw_protect": "Delay between terminal output updates in seconds.",
        "what_to_kill": "<a href=\"tg://emoji?id=5274099962655816924\">❗️</a> <b>Reply to a command message to terminate it.</b>",
        "kill_fail": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Failed to terminate process.</b>",
        "killed": "<a href=\"tg://emoji?id=5206607081334906820\">✔️</a> <b>Process terminated.</b>",
        "no_cmd": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>No active command found for this message.</b>",
        "auth_fail": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Wrong sudo password.</b>",
        "auth_needed": "<a href=\"tg://emoji?id=5778570255555105942\">🔒</a> <b>Sudo authentication required.</b> <i>Check your saved messages.</i>",
        "auth_msg": "<b>Sudo authentication for command:</b> {0}\n<b>User:</b> <code>{1}</code>\n<b>Edit this message and enter the password in the first line.</b>",
        "auth_locked": "<a href=\"tg://emoji?id=5395695537687123235\">🚨</a> <b>Sudo temporarily locked due to too many failed attempts.</b>",
        "auth_ongoing": "<a href=\"tg://emoji?id=5850309953293653168\">⚙️</a> <b>Password sent, waiting for command completion...</b>",
        "blocked_cmd": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Dangerous command is blocked.</b>",
    }

    strings_ru = {
        "fw_protect": "Задержка между обновлениями вывода терминала в секундах.",
        "what_to_kill": "<a href=\"tg://emoji?id=5274099962655816924\">❗️</a> <b>Ответьте на сообщение с командой, чтобы завершить её.</b>",
        "kill_fail": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Не удалось завершить процесс.</b>",
        "killed": "<a href=\"tg://emoji?id=5206607081334906820\">✔️</a> <b>Процесс завершён.</b>",
        "no_cmd": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Для этого сообщения нет активной команды.</b>",
        "auth_fail": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Неверный пароль sudo.</b>",
        "auth_needed": "<a href=\"tg://emoji?id=5778570255555105942\">🔒</a> <b>Требуется авторизация sudo.</b> <i>Проверьте избранное.</i>",
        "auth_msg": "<b>Авторизация sudo для команды:</b> {0}\n<b>Пользователь:</b> <code>{1}</code>\n<b>Отредактируйте это сообщение и введите пароль в первой строке.</b>",
        "auth_locked": "<a href=\"tg://emoji?id=5395695537687123235\">🚨</a> <b>Sudo временно заблокирован из-за большого числа неудачных попыток.</b>",
        "auth_ongoing": "<a href=\"tg://emoji?id=5850309953293653168\">⚙️</a> <b>Пароль отправлен, ожидаю завершения команды...</b>",
        "blocked_cmd": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Опасная команда заблокирована.</b>",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "FLOOD_WAIT_PROTECT",
                2,
                lambda: self.strings("fw_protect"),
                validator=loader.validators.Integer(minimum=0),
            ),
        )
        self.activecmds = {}
        self._blocked_commands = {
            "rm -rf /*",
            "sudo rm -rf /*",
            "rm -rf /* --no-preserve-root",
            "sudo rm -rf /* --no-preserve-root",
        }

    @loader.command(
        ru_doc="Выполнить команду в терминале",
        en_doc="Run a terminal command",
    )
    async def terminalcmd(self, message: Message):
        await self.run_command(message, utils.get_args_raw(message))

    @loader.command(
        ru_doc="Выполнить pip-команду",
        en_doc="Run a pip command",
    )
    async def pipcmd(self, message: Message):
        await self.run_command(
            message,
            ("pip " if os.geteuid() == 0 else "sudo -S pip ") + utils.get_args_raw(message),
        )

    @loader.command(
        ru_doc="Выполнить apt-команду",
        en_doc="Run an apt command",
    )
    async def aptcmd(self, message: Message):
        await self.run_command(
            message,
            ("apt " if os.geteuid() == 0 else "sudo -S apt ") + utils.get_args_raw(message) + " -y",
            RawMessageEditor(
                message,
                f"apt {utils.get_args_raw(message)}",
                self.config,
                self.strings,
                message,
                True,
            ),
        )

    def _is_blocked_command(self, cmd: str) -> bool:
        normalized = re.sub(r"\s+", " ", cmd.strip())
        return normalized in self._blocked_commands

    async def run_command(
        self,
        message: herokutl.tl.types.Message,
        cmd: str,
        editor: typing.Optional[MessageEditor] = None,
    ):
        if self._is_blocked_command(cmd):
            await utils.answer(message, self.strings("blocked_cmd"))
            return

        if len(cmd.split(" ")) > 1 and cmd.split(" ")[0] == "sudo":
            needsswitch = True

            for word in cmd.split(" ", 1)[1].split(" "):
                if not word or word[0] != "-":
                    break
                if word == "-S":
                    needsswitch = False

            if needsswitch:
                cmd = " ".join([cmd.split(" ", 1)[0], "-S", cmd.split(" ", 1)[1]])

        sproc = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "-c",
            cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=utils.get_base_dir(),
            preexec_fn=os.setsid,
        )

        if editor is None:
            editor = SudoMessageEditor(message, cmd, self.config, self.strings, message)

        editor.update_process(sproc)
        self.activecmds[hash_msg(message)] = sproc
        await editor.redraw()

        await asyncio.gather(
            read_stream(editor.update_stdout, sproc.stdout, self.config["FLOOD_WAIT_PROTECT"]),
            read_stream(editor.update_stderr, sproc.stderr, self.config["FLOOD_WAIT_PROTECT"]),
        )

        await editor.cmd_ended(await sproc.wait())
        self.activecmds.pop(hash_msg(message), None)

    @loader.command(
        ru_doc="Завершить активную команду по реплаю",
        en_doc="Terminate an active command by reply",
    )
    async def terminatecmd(self, message: Message):
        if not message.is_reply:
            await utils.answer(message, self.strings("what_to_kill"))
            return

        reply = await message.get_reply_message()
        if hash_msg(reply) in self.activecmds:
            try:
                kill_pids = self.activecmds[hash_msg(reply)]
                if "-f" not in utils.get_args_raw(message):
                    os.killpg(kill_pids.pid, signal.SIGTERM)
                else:
                    os.killpg(kill_pids.pid, signal.SIGKILL)
            except Exception:
                logger.exception("Killing process failed")
                await utils.answer(message, self.strings("kill_fail"))
            else:
                await utils.answer(message, self.strings("killed"))
        else:
            await utils.answer(message, self.strings("no_cmd"))