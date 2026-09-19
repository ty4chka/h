# modules/terminal.py
from utils.misc import edit_or_reply
import asyncio
import contextlib
import logging
import os
import re
import signal

logger = logging.getLogger(__name__)


def hash_msg(message):
    return f"{str(message.chat_id)}/{str(message.id)}"


async def read_stream(func: callable, stream, delay: float):
    last_task = None
    data = b""
    while True:
        dat = await stream.read(1)

        if not dat:
            if last_task:
                last_task.cancel()
                await func(data.decode())
            break

        data += dat

        if last_task:
            last_task.cancel()

        last_task = asyncio.ensure_future(sleep_for_task(func, data, delay))


async def sleep_for_task(func: callable, data: bytes, delay: float):
    await asyncio.sleep(delay)
    await func(data.decode())


class MessageEditor:
    def __init__(self, message, command, request_message):
        self.message = message
        self.command = command
        self.stdout = ""
        self.stderr = ""
        self.rc = None
        self.redraws = 0
        self.request_message = request_message

    async def update_stdout(self, stdout):
        self.stdout = stdout
        await self.redraw()

    async def update_stderr(self, stderr):
        self.stderr = stderr
        await self.redraw()

    async def redraw(self):
        text = f"<b>🚀 Выполняется:</b> <code>{self.command}</code>\n\n"
        
        if self.rc is not None:
            text += f"<b>✅ Завершено с кодом:</b> <code>{self.rc}</code>\n\n"

        text += "<b>📤 STDOUT:</b>\n"
        text += f"<code>{self.stdout[max(len(self.stdout) - 2048, 0):]}</code>\n\n"
        
        if self.stderr:
            text += "<b>📥 STDERR:</b>\n"
            text += f"<code>{self.stderr[max(len(self.stderr) - 1024, 0):]}</code>\n\n"

        with contextlib.suppress(Exception):
            await edit_or_reply(self.message, text)

    async def cmd_ended(self, rc):
        self.rc = rc
        await self.redraw()

    def update_process(self, process):
        pass


class SudoMessageEditor(MessageEditor):
    PASS_REQ = ["[sudo] password for", "[sudo] пароль для"]
    WRONG_PASS = [r"\[sudo\] password for (.*): Sorry, try again\.", r"\[sudo\] пароль для (.*): Попробуйте еще раз.\."]
    TOO_MANY_TRIES = [r"\[sudo\] password for (.*): sudo: [0-9]+ incorrect password attempts", r"\[sudo\] пароль для (.*): sudo: [0-9]+ неверные попытки ввода пароля"]

    def __init__(self, message, command, request_message):
        super().__init__(message, command, request_message)
        self.process = None
        self.state = 0
        self.authmsg = None

    def update_process(self, process):
        logger.debug("got sproc obj %s", process)
        self.process = process

    async def update_stderr(self, stderr):
        logger.debug("stderr update " + stderr)
        self.stderr = stderr
        lines = stderr.strip().split("\n")
        lastline = lines[-1]
        lastlines = lastline.rsplit(" ", 1)
        handled = False

        if (
            len(lines) > 1
            and any(re.fullmatch(i, lines[-2]) for i in self.WRONG_PASS)
            and any(lastlines[0] == i for i in self.PASS_REQ)
            and self.state == 1
        ):
            logger.debug("switching state to 0")
            await edit_or_reply(self.message, "❌ Неверный пароль!")
            self.state = 0
            handled = True
            await asyncio.sleep(2)
            if self.authmsg:
                await self.authmsg.delete()

        if any(lastlines[0] == i for i in self.PASS_REQ) and self.state == 0:
            logger.debug("Success to find sudo log!")
            text = "🔐 Требуется аутентификация sudo"

            try:
                await edit_or_reply(self.message, text)
            except Exception as e:
                logger.debug(e)

            logger.debug("edited message with link to self")
            command = f"<code>{self.command}</code>"
            user = lastlines[1][:-1]

            self.authmsg = await self.message.client.send_message(
                "me",
                f"🔐 **Требуется пароль sudo**\n\nКоманда: {command}\nПользователь: {user}\n\nОтправьте пароль:",
            )
            logger.debug("sent message to self")

            self.message.client.remove_event_handler(self.on_message_edited)
            self.message.client.add_event_handler(
                self.on_message_edited,
                lambda e: isinstance(e, types.MessageEdited) and e.chat_id == self.message.client.get_me().id
            )

            logger.debug("registered handler")
            handled = True

        if len(lines) > 1 and (
            any(re.fullmatch(i, lastline) for i in self.TOO_MANY_TRIES) and self.state in {1, 3, 4}
        ):
            logger.debug("password wrong lots of times")
            await edit_or_reply(self.message, "❌ Слишком много неверных попыток! Аккаунт заблокирован.")
            await self.authmsg.delete()
            self.state = 2
            handled = True

        if not handled:
            logger.debug("Didn't find sudo log.")
            if self.authmsg is not None:
                await self.authmsg.delete()
                self.authmsg = None
            self.state = 2
            await self.redraw()

        logger.debug(self.state)

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

        logger.debug("got message edit update in self %s", str(message.id))

        if hash_msg(message) == hash_msg(self.authmsg):
            try:
                self.authmsg = await edit_or_reply(message, "⏳ Проверка пароля...")
            except Exception:
                await message.delete()

            self.state = 1
            self.process.stdin.write(
                message.text.split("\n", 1)[0].encode() + b"\n"
            )


# Глобальный словарь для активных команд
activecmds = {}


async def terminal_handler(event):
    """Выполнить команду в терминале"""
    try:
        args = event.text.split(maxsplit=1)
        if len(args) == 1:
            await edit_or_reply(event, "❌ Использование: <code>.terminal <команда></code>")
            return
        
        cmd = args[1]
        await run_command(event, cmd)
        
    except Exception as e:
        await edit_or_reply(event, f"❌ Ошибка: {e}")


async def pip_handler(event):
    """Установить пакет через pip"""
    try:
        args = event.text.split(maxsplit=1)
        if len(args) == 1:
            await edit_or_reply(event, "❌ Использование: <code>.pip <пакет></code>")
            return
        
        pkg = args[1]
        cmd = ("pip " if os.geteuid() == 0 else "sudo -S pip ") + pkg
        await run_command(event, cmd)
        
    except Exception as e:
        await edit_or_reply(event, f"❌ Ошибка: {e}")


async def apt_handler(event):
    """Установить пакет через apt"""
    try:
        args = event.text.split(maxsplit=1)
        if len(args) == 1:
            await edit_or_reply(event, "❌ Использование: <code>.apt <пакет></code>")
            return
        
        pkg = args[1]
        cmd = ("apt " if os.geteuid() == 0 else "sudo -S apt ") + pkg + " -y"
        
        editor = MessageEditor(event, f"apt {pkg}", event)
        await run_command(event, cmd, editor)
        
    except Exception as e:
        await edit_or_reply(event, f"❌ Ошибка: {e}")


async def terminate_handler(event):
    """Завершить выполнение команды (ответом на сообщение)"""
    try:
        if not event.is_reply:
            await edit_or_reply(event, "❌ Ответьте на сообщение с выполняемой командой!")
            return

        reply_msg = await event.get_reply_message()
        msg_hash = hash_msg(reply_msg)
        
        if msg_hash in activecmds:
            try:
                kill_pids = activecmds[msg_hash]
                args = event.text.split()
                
                if "-f" not in args:
                    os.killpg(kill_pids.pid, signal.SIGTERM)
                else:
                    os.killpg(kill_pids.pid, signal.SIGKILL)
                    
                await edit_or_reply(event, "✅ Команда завершена!")
            except Exception:
                await edit_or_reply(event, "❌ Не удалось завершить процесс!")
        else:
            await edit_or_reply(event, "❌ Активная команда не найдена!")
            
    except Exception as e:
        await edit_or_reply(event, f"❌ Ошибка: {e}")


async def run_command(event, cmd, editor=None):
    """Основная функция выполнения команд"""
    if len(cmd.split(" ")) > 1 and cmd.split(" ")[0] == "sudo":
        needsswitch = True

        for word in cmd.split(" ", 1)[1].split(" "):
            if word[0] != "-":
                break

            if word == "-S":
                needsswitch = False

        if needsswitch:
            cmd = " ".join([cmd.split(" ", 1)[0], "-S", cmd.split(" ", 1)[1]])

    sproc = await asyncio.create_subprocess_exec(
        "/bin/bash", "-c", cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.getcwd(),
        preexec_fn=os.setsid,
    )

    if editor is None:
        editor = SudoMessageEditor(event, cmd, event)

    editor.update_process(sproc)

    activecmds[hash_msg(event)] = sproc

    await editor.redraw()

    await asyncio.gather(
        read_stream(
            editor.update_stdout,
            sproc.stdout,
            2.0,  # FLOOD_WAIT_PROTECT
        ),
        read_stream(
            editor.update_stderr,
            sproc.stderr,
            2.0,  # FLOOD_WAIT_PROTECT
        ),
    )

    await editor.cmd_ended(await sproc.wait())
    del activecmds[hash_msg(event)]


modules_help = {
    "terminal": {
        "terminal [команда]": "Выполнить команду в терминале",
        "pip [пакет]": "Установить пакет через pip",
        "apt [пакет]": "Установить пакет через apt", 
        "terminate": "Завершить команду (ответом на сообщение)",
        "terminate -f": "Принудительно завершить команду"
    }
}