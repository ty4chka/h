# meta: name=terminal version=1.0.0 author=hydra-team framework=core requires=lang
"""
🖥️ Терминальный модуль Hydra UserBot — упрощённая версия
Все команды выполняются внутри Arch Linux chroot через proot
"""

from utils.misc import edit_or_reply, fast_animation, rate_limit
from modules.lang import translator
import asyncio
import os
import re
import time
from pathlib import Path
from datetime import datetime
import pty
import select
import subprocess
import termios
import fcntl
import struct
import signal

# ============================================
# КОНФИГУРАЦИЯ
# ============================================

def _resolve_chroot_path() -> str:
    """Pick a real local Arch root instead of another user's hard-coded path."""

    configured = os.environ.get("HYDRA_CHROOT_PATH", "").strip()
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path.home() / "arch",
        Path.home() / "termux" / "arch",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return str(candidate)
    # Keep an explicit, user-local default in diagnostics; users can set
    # HYDRA_CHROOT_PATH before launch when their proot lives elsewhere.
    return str(Path(configured).expanduser()) if configured else str(Path.home() / "arch")


# Путь к chroot (Arch Linux). Override with HYDRA_CHROOT_PATH when needed.
CHROOT_PATH = _resolve_chroot_path()

# Путь к startarch скрипту
STARTARCH_PATH = os.path.join(CHROOT_PATH, "startarch")

# Оболочка — всегда bash, не автоопределяем
SHELL_PATH = "/bin/bash"
SHELL_NAME = "bash"

# ============================================
# ОКРУЖЕНИЕ ДЛЯ CHROOT
# ============================================

# Сохраняем оригинальное окружение перед модификацией
_ORIGINAL_ENV = os.environ.copy()

CHROOT_ENV = {
    'TERM': 'xterm-256color',
    'HOME': '/root',
    'SHELL': '/bin/bash',
    'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
    'TMPDIR': '/tmp',
    'TMP': '/tmp',
    'TEMP': '/tmp',
    'LANG': 'en_US.UTF-8',
    'LC_ALL': 'en_US.UTF-8',
    'COLORTERM': 'truecolor',
    'PAGER': 'cat',
    'CI': 'true',
    'PROOT_NO_SECCOMP': '1',
    'PROOT_TMP_DIR': '/tmp',
    # Важно: убираем LD_PRELOAD чтобы не было конфликтов с proot
    'LD_PRELOAD': '',
}

# Хранилище текущих директорий для каждого пользователя (внутри chroot)
user_current_dirs = {}

def get_user_dir(user_id):
    """Получить текущую директорию пользователя внутри chroot"""
    return user_current_dirs.get(user_id, "/root")

def set_user_dir(user_id, new_dir):
    """Установить директорию пользователя внутри chroot"""
    full_path = os.path.join(CHROOT_PATH, new_dir.lstrip("/"))
    try:
        if os.path.exists(full_path) and os.path.isdir(full_path):
            user_current_dirs[user_id] = new_dir
            return True
        return False
    except Exception:
        return False

def clean_ansi_codes(text):
    """Очищает ANSI escape-коды из текста"""
    if not text or not isinstance(text, str):
        return text

    # Убираем ANSI escape последовательности
    ansi_escape = re.compile(
        chr(27) + r"(?:[@-Z\-_]|\[[0-?]*[ -/]*[@-~])"
    )
    text = ansi_escape.sub("", text)

    # Убираем управляющие символы
    control_chars = re.compile(r"[\x00-\x09\x0B\x0C\x0E-\x1F\x7F-\x9F]")
    text = control_chars.sub("", text)

    # Убираем лишние пробелы и переносы
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n +", "\n", text)

    return text.strip()

# ============================================
# PTY ДВИЖОК ДЛЯ CHROOT
# ============================================

def set_winsize(fd, rows, cols):
    """Установка размера терминала"""
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        return True
    except Exception:
        return False

async def execute_in_chroot(cmd, timeout=30, rows=24, cols=80, cwd="/root"):
    """
    Выполнить команду внутри Arch chroot через startarch
    Возвращает: (output, returncode)
    """
    master = slave = None
    proc = None
    output_chunks = []  # Инициализируем ЗДЕСЬ, до try

    if not os.path.isdir(CHROOT_PATH):
        return (
            "Arch chroot не найден: " + CHROOT_PATH
            + "\nУкажите существующий путь через HYDRA_CHROOT_PATH и перезапустите Hydra.",
            127,
        )

    # Проверяем наличие startarch
    if os.path.exists(STARTARCH_PATH):
        # Используем startarch для входа в chroot
        proot_cmd = [
            STARTARCH_PATH,
            "-w", cwd,
            SHELL_PATH, "-c", cmd
        ]
    else:
        # Fallback на proot если startarch не найден
        proot_cmd = [
            "proot",
            "-0",
            "-r", CHROOT_PATH,
            "-w", cwd,
            "-b", "/dev",
            "-b", "/dev/pts",
            "-b", "/proc",
            "-b", "/sys",
            "-b", "/sdcard",
            "-b", "/data",
            "-b", "/storage",
            SHELL_PATH, "-c", cmd
        ]

    # Объединяем окружение: сначала текущее, потом перезаписываем chroot-специфичным
    env = os.environ.copy()
    env.update(CHROOT_ENV)
    # Убираем LD_PRELOAD чтобы избежать конфликтов с proot
    if 'LD_PRELOAD' in env:
        del env['LD_PRELOAD']

    # Пробуем выполнить через PTY (для интерактивных команд)
    try:
        master, slave = pty.openpty()
        set_winsize(slave, rows, cols)

        proc = subprocess.Popen(
            proot_cmd,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            preexec_fn=os.setsid,
            env=env,
            bufsize=0,
            universal_newlines=False,
            close_fds=True
        )

        os.close(slave)
        slave = None

        start_time = time.time()

        while proc.poll() is None and (time.time() - start_time) < timeout:
            try:
                rlist, _, _ = select.select([master], [], [], 0.1)
                if rlist:
                    try:
                        chunk = os.read(master, 8192)
                        if chunk:
                            output_chunks.append(chunk)
                    except (OSError, EOFError):
                        break
                await asyncio.sleep(0.01)
            except (select.error, OSError, ValueError):
                break

        # Таймаут — шлём Ctrl+C
        if proc.poll() is None:
            try:
                os.write(master, b"\x03")
                await asyncio.sleep(0.1)
                for _ in range(5):
                    if proc.poll() is not None:
                        break
                    await asyncio.sleep(0.1)
                if proc.poll() is None:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except:
                        pass
                    proc.wait(timeout=1)
            except Exception:
                pass

        # Читаем остаток
        try:
            while True:
                rlist, _, _ = select.select([master], [], [], 0.1)
                if rlist:
                    chunk = os.read(master, 8192)
                    if not chunk:
                        break
                    output_chunks.append(chunk)
                else:
                    break
        except Exception:
            pass

        try:
            proc.wait(timeout=2)
        except:
            pass

    except Exception as e:
        # PTY не сработал — fallback на обычный subprocess
        output_chunks.append(f"\n[PTY недоступен, используем fallback]\n".encode())
        try:
            proc = subprocess.run(
                proot_cmd,
                capture_output=True,
                text=False,
                timeout=timeout,
                env=env
            )
            output_chunks.append(proc.stdout if proc.stdout else b"")
            output_chunks.append(proc.stderr if proc.stderr else b"")
        except Exception as e2:
            output_chunks.append(f"\nFallback Error: {str(e2)}".encode())
            proc = None
    finally:
        try:
            if slave is not None:
                os.close(slave)
        except:
            pass
        try:
            if master is not None:
                os.close(master)
        except:
            pass
        # proc может быть Popen или CompletedProcess
        if hasattr(proc, 'poll') and proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except:
                pass

    result = b"".join(output_chunks)
    try:
        decoded = result.decode("utf-8", errors="replace")
    except:
        try:
            decoded = result.decode("latin-1", errors="replace")
        except:
            decoded = str(result)

    # Определяем returncode
    if hasattr(proc, 'returncode'):
        rc = proc.returncode
    elif hasattr(proc, 'poll'):
        rc = proc.poll()
    else:
        rc = 1

    return clean_ansi_codes(decoded), rc if rc is not None else 1


# ============================================
# ОСНОВНОЙ ХЭНДЛЕР
# ============================================

@rate_limit(limit=10, period=30)
async def terminal_handler(event):
    """
    .terminal [команда] — Выполнить команду внутри Arch chroot
    """
    try:
        user_id = event.sender_id
        args = event.text.split(maxsplit=1)

        if len(args) == 1:
            current_dir = get_user_dir(user_id)
            help_text = ""
            help_text += "<b>🐧 Arch Linux Terminal (via proot)</b>\n\n"
            help_text += "<blockquote>⚡ <b>Использование:</b>\n"
            help_text += "<code>.terminal [команда]</code>\n\n"
            help_text += "📋 <b>Примеры:</b>\n"
            help_text += "<code>.terminal ls -la</code>\n"
            help_text += "<code>.terminal cd /etc</code>\n"
            help_text += "<code>.terminal pacman -Syu</code>\n"
            help_text += "<code>.terminal neofetch</code>\n"
            help_text += "<code>.terminal whoami</code>\n"
            help_text += "<code>.terminal uname -a</code>\n\n"
            help_text += "🔧 <b>Chroot:</b> <code>" + CHROOT_PATH + "</code>\n"
            help_text += "🐚 <b>Оболочка:</b> <code>" + SHELL_NAME + "</code>\n"
            help_text += "📁 <b>Текущий путь:</b> <code>" + current_dir + "</code></blockquote>\n\n"
            help_text += "<b>⚡ Возможности:</b>\n"
            help_text += "<blockquote>• Все команды выполняются внутри Arch chroot\n"
            help_text += "• Работа от имени root (через startarch)\n"
            help_text += "• Автоочистка ANSI-кодов\n"
            help_text += "• Таймаут 60 секунд\n"
            help_text += "• Защита от зависания</blockquote>"
            await edit_or_reply(event, help_text, parse_mode="HTML")
            return

        cmd = args[1].strip()
        current_dir = get_user_dir(user_id)

        # Проверка опасных команд
        dangerous = ["rm -rf /", "rm -rf /*", "dd if=", "mkfs", ":(){:|:&};:", "chmod -R 777 /", "> /dev/sda"]
        for d in dangerous:
            if d in cmd.lower():
                await edit_or_reply(event, "🚫 <b>Опасная команда заблокирована!</b>", parse_mode="HTML")
                return

        # Обработка cd
        if cmd.strip().startswith("cd "):
            await handle_cd_command(event, cmd, user_id, current_dir)
            return

        # Выполнение команды
        await execute_command(event, cmd, user_id, current_dir)

    except Exception as e:
        await edit_or_reply(event, f"<b>❌ Ошибка:</b>\n<code>{str(e)[:500]}</code>", parse_mode="HTML")

async def execute_command(event, cmd, user_id, current_dir):
    """Выполнить команду в chroot и показать результат"""
    loading_msg = await edit_or_reply(event, "🐧")
    await fast_animation(loading_msg, "🐧", "🐧 Выполняю в Arch chroot...")

    start_time = datetime.now()

    try:
        result, returncode = await execute_in_chroot(cmd, timeout=60, rows=40, cols=120, cwd=current_dir)

        exec_time = (datetime.now() - start_time).total_seconds()

        # Разделяем stdout/stderr
        lines = result.split("\n")
        stdout_lines = []
        stderr_lines = []

        for line in lines:
            line_lower = line.lower()
            if any(err in line_lower for err in ["error:", "fail:", "cannot", "no such", "not found", "permission denied"]):
                stderr_lines.append(line)
            else:
                stdout_lines.append(line)

        stdout_text = "\n".join(stdout_lines).strip()
        stderr_text = "\n".join(stderr_lines).strip()

        status_icon = "✅" if returncode == 0 else "❌"
        status_color = "🟢" if returncode == 0 else "🔴"
        status_text = "Успешно" if returncode == 0 else "Ошибка"

        final_output = ""
        final_output += "<b>🐧 Arch Linux (proot)</b>\n\n"
        final_output += "<blockquote>🔧 <b>Команда:</b>\n"
        final_output += "<code>" + cmd + "</code>\n\n"
        final_output += status_color + " <b>Статус:</b> <code>" + status_text + "</code>\n"
        final_output += "📊 <b>Код выхода:</b> <code>" + str(returncode) + "</code>\n"
        final_output += "⏱️ <b>Время:</b> <code>" + f"{exec_time:.2f}" + "с</code>\n"
        final_output += "📁 <b>Путь в chroot:</b> <code>" + current_dir + "</code>\n"
        final_output += "🏠 <b>Chroot:</b> <code>" + CHROOT_PATH + "</code>\n"
        final_output += "🐚 <b>Оболочка:</b> <code>" + SHELL_NAME + "</code>\n"
        final_output += "👤 <b>Пользователь:</b> <code>root (startarch)</code></blockquote>\n\n"

        if stdout_text:
            if len(stdout_text) > 3000:
                stdout_text = stdout_text[:3000] + "\n... (вывод обрезан)"
            final_output += "<b>📨 Вывод:</b>\n"
            final_output += "<pre><code class=\"language-bash\">" + stdout_text + "</code></pre>\n\n"

        if stderr_text:
            if len(stderr_text) > 2000:
                stderr_text = stderr_text[:2000] + "\n... (ошибки обрезаны)"
            final_output += "<b>🚨 Ошибки:</b>\n"
            final_output += "<pre><code class=\"language-bash\">" + stderr_text + "</code></pre>\n\n"

        if not stdout_text and not stderr_text:
            final_output += "<b>📨 Вывод:</b>\n"
            final_output += "<pre><code class=\"language-bash\">Команда выполнена без вывода</code></pre>\n\n"

        final_output += "<blockquote>" + status_icon + " <i>Завершено с кодом: " + str(returncode) + "</i></blockquote>"

        await loading_msg.edit(final_output, parse_mode="HTML")

    except asyncio.TimeoutError:
        timeout_msg = ""
        timeout_msg += "<b>⏰ Таймаут</b>\n\n"
        timeout_msg += "<blockquote>🔧 <b>Команда:</b> <code>" + cmd + "</code>\n"
        timeout_msg += "🚫 <b>Причина:</b> Команда заняла слишком много времени\n"
        timeout_msg += "⏱️ <b>Лимит:</b> 60 секунд\n"
        timeout_msg += "📁 <b>Путь:</b> <code>" + current_dir + "</code></blockquote>"
        await loading_msg.edit(timeout_msg, parse_mode="HTML")

    except Exception as e:
        error_msg = ""
        error_msg += "<b>❌ Ошибка выполнения</b>\n\n"
        error_msg += "<blockquote>🔧 <b>Команда:</b> <code>" + cmd + "</code>\n"
        error_msg += "🚫 <b>Ошибка:</b> <code>" + str(e)[:200] + "</code>\n"
        error_msg += "📁 <b>Путь:</b> <code>" + current_dir + "</code></blockquote>"
        await loading_msg.edit(error_msg, parse_mode="HTML")

# ============================================
# CD ВНУТРИ CHROOT
# ============================================

async def handle_cd_command(event, cmd, user_id, current_dir):
    """Обработка cd внутри chroot"""
    loading_msg = await edit_or_reply(event, "📁")
    await fast_animation(loading_msg, "📁", "📁 Меняю директорию...")

    try:
        parts_cmd = cmd.split(maxsplit=1)
        if len(parts_cmd) < 2:
            result = ""
            result += "<b>📁 Текущая директория (в chroot)</b>\n\n"
            result += "<blockquote>🛣️ <b>Путь:</b> <code>" + current_dir + "</code>\n"
            result += "🏠 <b>Chroot:</b> <code>" + CHROOT_PATH + "</code>\n\n"
            result += "💡 <b>Команды:</b>\n"
            result += "<code>.terminal cd /path</code> — сменить директорию\n"
            result += "<code>.terminal cd ..</code> — на уровень выше\n"
            result += "<code>.terminal cd ~</code> — домашняя директория</blockquote>"
            await loading_msg.edit(result, parse_mode="HTML")
            return

        target = parts_cmd[1].strip()

        if target == "~" or target == "-":
            target = "/root"
        elif not target.startswith("/"):
            target = os.path.join(current_dir, target)

        target = os.path.normpath(target)
        full_path = os.path.join(CHROOT_PATH, target.lstrip("/"))

        if not os.path.exists(full_path):
            await loading_msg.edit(
                "<b>❌ Директория не существует:</b>\n<code>" + target + "</code>",
                parse_mode="HTML"
            )
            return

        if not os.path.isdir(full_path):
            await loading_msg.edit(
                "<b>❌ Это не директория:</b>\n<code>" + target + "</code>",
                parse_mode="HTML"
            )
            return

        old_dir = current_dir
        set_user_dir(user_id, target)

        try:
            items = os.listdir(full_path)
            dirs = [i for i in items if os.path.isdir(os.path.join(full_path, i))]
            files = [i for i in items if os.path.isfile(os.path.join(full_path, i))]

            result = ""
            result += "<b>✅ Директория изменена</b>\n\n"
            result += "<blockquote>📁 <b>Старый путь:</b> <code>" + old_dir + "</code>\n"
            result += "📁 <b>Новый путь:</b> <code>" + target + "</code>\n"
            result += "📊 <b>Содержимое:</b> <code>" + str(len(dirs)) + " папок, " + str(len(files)) + " файлов</code></blockquote>\n\n"
            result += "<b>💡 Быстрые команды:</b>\n"
            result += "<blockquote><code>.terminal ls -la</code> — подробный список\n"
            result += "<code>.terminal pwd</code> — текущий путь</blockquote>"
        except PermissionError:
            result = ""
            result += "<b>✅ Директория изменена</b>\n\n"
            result += "<blockquote>📁 <b>Старый путь:</b> <code>" + old_dir + "</code>\n"
            result += "📁 <b>Новый путь:</b> <code>" + target + "</code>\n"
            result += "⚠️ <b>Нет доступа к чтению содержимого</b></blockquote>"

        await loading_msg.edit(result, parse_mode="HTML")

    except Exception as e:
        await loading_msg.edit(
            "<b>❌ Ошибка cd:</b>\n<code>" + str(e) + "</code>",
            parse_mode="HTML"
        )

# ============================================
# ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ
# ============================================

@rate_limit(limit=5, period=30)
async def term_handler(event):
    await terminal_handler(event)

@rate_limit(limit=5, period=30)
async def shell_handler(event):
    await terminal_handler(event)

@rate_limit(limit=5, period=30)
async def exec_handler(event):
    await terminal_handler(event)

@rate_limit(limit=3, period=60)
async def terminal_info_handler(event):
    """Информация о chroot-окружении"""
    loading_msg = await edit_or_reply(event, "🔍")
    await fast_animation(loading_msg, "🔍", "🔍 Собираю информацию...")

    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)

        chroot_exists = os.path.exists(CHROOT_PATH) and os.path.isdir(CHROOT_PATH)
        chroot_status = "✅ Существует" if chroot_exists else "❌ Не найден"

        try:
            check = subprocess.run(["which", "proot"], capture_output=True, text=True, timeout=5)
            proot_ok = check.returncode == 0
            proot_path = check.stdout.strip() if proot_ok else "не найден"
        except:
            proot_ok = False
            proot_path = "ошибка проверки"

        info_text = ""
        info_text += "<b>🔍 Информация о терминале</b>\n\n"
        info_text += "<blockquote>🏠 <b>Chroot путь:</b> <code>" + CHROOT_PATH + "</code>\n"
        info_text += "📊 <b>Статус chroot:</b> <code>" + chroot_status + "</code>\n"
        info_text += "🐚 <b>Оболочка:</b> <code>" + SHELL_NAME + " (" + SHELL_PATH + ")</code>\n"
        info_text += "🖥️ <b>Терминал:</b> <code>xterm-256color</code>\n"
        info_text += "📁 <b>Текущий путь:</b> <code>" + current_dir + "</code>\n"
        info_text += "👤 <b>Пользователь:</b> <code>root (через proot -0)</code>\n"
        info_text += "🔧 <b>Proot:</b> <code>" + ("✅ " + proot_path if proot_ok else "❌ " + proot_path) + "</code></blockquote>\n\n"
        info_text += "<b>⚡ Быстрые команды:</b>\n"
        info_text += "<blockquote><code>.terminal pwd</code> — текущий путь\n"
        info_text += "<code>.terminal ls -la</code> — содержимое директории\n"
        info_text += "<code>.terminal whoami</code> — текущий пользователь\n"
        info_text += "<code>.terminal uname -a</code> — информация о системе\n"
        info_text += "<code>.terminal neofetch</code> — красивая инфо</blockquote>"

        await loading_msg.edit(info_text, parse_mode="HTML")

    except Exception as e:
        await loading_msg.edit(f"<b>❌ Ошибка:</b> {str(e)}", parse_mode="HTML")

@rate_limit(limit=10, period=30)
async def terminal_pwd_handler(event):
    """Показать текущую директорию в chroot"""
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        msg = "<b>📁 Текущий путь в chroot:</b>\n<code>" + current_dir + "</code>"
        await edit_or_reply(event, msg, parse_mode="HTML")
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ Ошибка:</b> {str(e)}", parse_mode="HTML")

@rate_limit(limit=10, period=30)
async def terminal_ls_handler(event):
    """Показать содержимое текущей директории в chroot"""
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        await execute_command(event, f'ls -la "{current_dir}"', user_id, current_dir)
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ Ошибка:</b> {str(e)}", parse_mode="HTML")

@rate_limit(limit=10, period=30)
async def terminal_whoami_handler(event):
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        await execute_command(event, "whoami", user_id, current_dir)
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ Ошибка:</b> {str(e)}", parse_mode="HTML")

@rate_limit(limit=10, period=30)
async def terminal_uname_handler(event):
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        await execute_command(event, "uname -a", user_id, current_dir)
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ Ошибка:</b> {str(e)}", parse_mode="HTML")

@rate_limit(limit=5, period=60)
async def terminal_df_handler(event):
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        await execute_command(event, "df -h", user_id, current_dir)
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ Ошибка:</b> {str(e)}", parse_mode="HTML")

@rate_limit(limit=3, period=60)
async def neofetch_handler(event):
    """Запустить neofetch в chroot"""
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        await execute_command(event, "neofetch", user_id, current_dir)
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ Ошибка neofetch:</b>\n<code>{str(e)}</code>", parse_mode="HTML")

# ============================================
# СПРАВКА МОДУЛЯ
# ============================================

modules_help = {
    "terminal": {
        "terminal [command]": "Выполнить команду в Arch chroot",
        "term [command]": "Короткая версия",
        "shell [command]": "Выполнить shell-команду",
        "exec [command]": "Выполнить системную команду",
        "neofetch": "Запустить neofetch",
        "terminal_info": "Информация о chroot-окружении",
        "terminal_pwd": "Текущий путь в chroot",
        "terminal_ls": "Содержимое директории",
        "terminal_whoami": "Текущий пользователь",
        "terminal_uname": "Информация о системе",
        "terminal_df": "Использование диска"
    }
}

print(f"✅ Terminal module loaded! Chroot: {CHROOT_PATH} | Shell: {SHELL_NAME}")
