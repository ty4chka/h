"""
🖥️ Терминальный модуль Hydra UserBot с PTY эмуляцией
Поддерживает proot-distro, bash, python и другие команды
"""

from utils.misc import edit_or_reply, fast_animation, rate_limit
from modules.lang import translator
import asyncio
import os
import re
import time
from datetime import datetime
import pty
import select
import subprocess
import termios
import fcntl
import struct
import signal

# ============================================
# ГЛОБАЛЬНЫЕ НАСТРОЙКИ И ПЕРЕМЕННЫЕ
# ============================================

os.environ.update({
    'TERM': 'xterm-256color',
    'HOME': '/data/data/com.termux/files/home',
    'SHELL': '/data/data/com.termux/files/usr/bin/bash',
    'PATH': '/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets:/data/data/com.termux/files/usr/local/bin:/system/bin:/system/xbin:' + os.environ.get('PATH', ''),
    'PREFIX': '/data/data/com.termux/files/usr',
    'TMPDIR': '/data/data/com.termux/files/usr/tmp',
    'LD_LIBRARY_PATH': '/data/data/com.termux/files/usr/lib',
    'LANG': 'en_US.UTF-8',
    'ANDROID_ROOT': '/system',
    'ANDROID_DATA': '/data',
    'EXTERNAL_STORAGE': '/sdcard',
    'PROOT_TMP_DIR': '/data/data/com.termux/files/usr/var/lib/proot-distro',
    'TERMUX_VERSION': '0.118.0',
    'TERMUX_APP_PID': str(os.getpid()),
    'COLORTERM': 'truecolor',
    'PAGER': 'cat',
    'CI': 'true',
    # КРИТИЧЕСКИЕ переменные для proot
    'PROOT_NO_SECCOMP': '1',
    'PROOT_TMP_DIR': '/tmp',
    'TMPDIR': '/tmp',
    'TEMP': '/tmp',
    'TMP': '/tmp',
})

# Хранилище текущих директорий для каждого пользователя
user_current_dirs = {}

def get_user_dir(user_id):
    """Получить текущую директорию пользователя"""
    return user_current_dirs.get(user_id, os.path.expanduser("~"))

def set_user_dir(user_id, new_dir):
    """Установить директорию пользователя"""
    try:
        if os.path.exists(new_dir):
            user_current_dirs[user_id] = new_dir
            return True
        os.makedirs(new_dir, exist_ok=True)
        user_current_dirs[user_id] = new_dir
        return True
    except Exception:
        return False

def clean_ansi_codes(text):
    """Очищает ВСЕ ANSI escape-коды из текста - УЛУЧШЕННАЯ ВЕРСИЯ"""
    if not text or not isinstance(text, str):
        return text
    
    # 1. Убираем ВСЕ escape последовательности (включая (B, (C и т.д.)
    ansi_escape = re.compile(r'''
        \x1B  # ESC
        (?:   # 7-bit C1 Fe (except CSI)
            [@-Z\\-_]
        |     # or [ for CSI
            \[
            [0-?]*  # Parameter bytes
            [ -/]*  # Intermediate bytes
            [@-~]   # Final byte
        )
        |     # или (B, (C и т.д.
        \( [A-Z] \)
        |     # или цветовые коды [0m, [1m и т.д.
        \[[0-9;]*m
        |     # или дополнительные управляющие последовательности
        \][0-9;]*[a-zA-Z]
    ''', re.VERBOSE)
    
    text = ansi_escape.sub('', text)
    
    # 2. Убираем управляющие символы
    control_chars = re.compile(r'[\x00-\x09\x0B\x0C\x0E-\x1F\x7F-\x9F]')
    text = control_chars.sub('', text)
    
    # 3. Убираем лишние пробелы и переносы
    text = re.sub(r'\n\s*\n+', '\n\n', text)  # Сохраняем двойные переносы
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n +', '\n', text)
    
    return text.strip()

# ============================================
# PTY ДВИЖОК С УЛУЧШЕНИЯМИ ДЛЯ PROOT
# ============================================

def set_winsize(fd, rows, cols):
    """Установка размера терминала"""
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        return True
    except Exception:
        return False

async def execute_with_pty(cmd, timeout=30, rows=24, cols=80, cwd=None):
    """
    Выполнить команду с PTY (улучшенная для proot)
    Возвращает: (output, returncode)
    """
    master = slave = None
    proc = None
    
    try:
        master, slave = pty.openpty()
        set_winsize(slave, rows, cols)
        
        if cwd is None:
            cwd = os.path.expanduser("~")
        
        # Создаем окружение
        env = os.environ.copy()
        
        # Специальная обработка для proot-distro команд
        if cmd.startswith('proot-distro'):
            env.update({
                'PROOT_NO_SECCOMP': '1',
                'PROOT_TMP_DIR': '/tmp',
                'HOME': '/root',
                'TERM': 'xterm-256color',
                'SHELL': '/bin/bash',
                'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                'TMPDIR': '/tmp',
            })
        
        proc = subprocess.Popen(
            ['/data/data/com.termux/files/usr/bin/bash', '-c', cmd],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            preexec_fn=os.setsid,
            env=env,
            cwd=cwd,
            bufsize=0,
            universal_newlines=False,
            close_fds=True
        )
        
        os.close(slave)
        slave = None
        
        output_chunks = []
        start_time = time.time()
        
        # Чтение с таймаутом
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
        
        # Таймаут
        if proc.poll() is None:
            try:
                os.write(master, b'\x03')  # Ctrl+C
                await asyncio.sleep(0.1)
                
                for _ in range(5):
                    if proc.poll() is not None:
                        break
                    await asyncio.sleep(0.1)
                
                if proc.poll() is None:
                    try:
                        os.write(master, b'\x04')  # Ctrl+D
                        await asyncio.sleep(0.1)
                    except:
                        pass
                
                if proc.poll() is None:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except:
                        pass
                    proc.wait(timeout=1)
            except Exception:
                pass
        
        # Читаем оставшиеся данные
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
        
        # Ждем завершения процесса
        try:
            proc.wait(timeout=2)
        except:
            pass
        
    except Exception as e:
        output_chunks.append(f"\nPTY Error: {str(e)}".encode())
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
            
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except:
                pass
    
    # Декодируем результат
    result = b''.join(output_chunks)
    try:
        decoded = result.decode('utf-8', errors='replace')
    except:
        try:
            decoded = result.decode('latin-1', errors='replace')
        except:
            decoded = str(result)
    
    return clean_ansi_codes(decoded), proc.returncode if proc else 1

# ============================================
# ОСНОВНОЙ ХЭНДЛЕР ТЕРМИНАЛА
# ============================================

@rate_limit(limit=10, period=30)
async def terminal_handler(event):
    """
    .terminal [команда] - Выполнить команду в терминале
    """
    try:
        user_id = event.sender_id
        args = event.text.split(maxsplit=1)
        
        if len(args) == 1:
            help_text = f"""<b>{translator.get_text(user_id, 'terminal_help_title')}</b>

<blockquote>⚡ <b>{translator.get_text(user_id, 'terminal_help_usage')}:</b>
<code>.terminal {translator.get_text(user_id, 'command')}</code>

📋 <b>{translator.get_text(user_id, 'terminal_help_examples')}:</b>
<code>.terminal ls -la</code>
<code>.terminal cd /sdcard</code>
<code>.terminal proot-distro list</code>
<code>.terminal proot-distro install archlinux</code>
<code>.terminal proot-distro login archlinux</code>
<code>.terminal bash</code>
<code>.terminal python3 -c "print('Hello')"</code>

🔧 <b>{translator.get_text(user_id, 'terminal_help_permissions')}:</b> <code>{'🛡️ ROOT' if os.geteuid() == 0 else '👤 USER'}</code>
📁 <b>{translator.get_text(user_id, 'terminal_help_current_path')}:</b> <code>{get_user_dir(user_id)}</code></blockquote>

<b>{translator.get_text(user_id, 'terminal_help_features')}:</b>
<blockquote>• <b>{translator.get_text(user_id, 'terminal_live_updates')}</b>
• {translator.get_text(user_id, 'terminal_animations_support')}
• {translator.get_text(user_id, 'terminal_ansi_cleanup')}
• {translator.get_text(user_id, 'terminal_long_commands')}
• {translator.get_text(user_id, 'terminal_hang_protection')}</blockquote>

<b>🐧 PROOT-DISTRO {translator.get_text(user_id, 'terminal_available_commands').upper()}:</b>
<blockquote><code>.terminal proot-distro list</code>
<code>.terminal proot-distro install archlinux</code>
<code>.terminal proot-distro login archlinux -- your_command</code>
<code>.terminal proot-distro --help</code></blockquote>

<b>⚡ ВАЖНО для proot-distro:</b>
<blockquote>• Добавлен <code>PROOT_NO_SECCOMP=1</code> для устранения предупреждений
• Используйте <code>--</code> для разделения команд
• <code>.terminal proot-distro login ubuntu -- whoami</code></blockquote>"""
            
            await edit_or_reply(event, help_text, parse_mode='HTML')
            return
        
        cmd = args[1].strip()
        current_dir = get_user_dir(user_id)
        
        # Проверка опасных команд
        dangerous_commands = [
            'rm -rf /', 'rm -rf /*', 'dd if=', 'mkfs', 
            ':(){:|:&};:', 'chmod -R 777 /',
            '> /dev/sda', 'mkfs.ext4 /dev/sda'
        ]
        
        for danger in dangerous_commands:
            if danger in cmd.lower():
                await edit_or_reply(event, f"🚫 <b>{translator.get_text(user_id, 'terminal_dangerous_blocked')}!</b>", parse_mode='HTML')
                return
        
        # Обработка proot-distro команд
        if cmd.startswith('proot-distro'):
            await handle_proot_command(event, cmd, user_id, current_dir)
            return
        
        # Обработка cd команд
        if cmd.strip().startswith('cd '):
            await handle_cd_command(event, cmd, user_id, current_dir)
            return
        
        # Выполнение обычной команды
        await execute_command(event, cmd, user_id, current_dir)
        
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ {translator.get_text(event.sender_id, 'error')}:</b>\n<code>{str(e)[:500]}</code>", parse_mode='HTML')

async def execute_command(event, cmd, user_id, current_dir):
    """Выполнить команду и показать результат"""
    loading_msg = await edit_or_reply(event, "🖥️")
    await fast_animation(loading_msg, "🖥️", f"🖥️ {translator.get_text(user_id, 'terminal_executing_command')}...")
    
    start_time = datetime.now()
    current_user = os.getenv('USER', 'termux')
    
    try:
        # Выполняем команду
        result, returncode = await execute_with_pty(cmd, timeout=60, rows=40, cols=120, cwd=current_dir)
        
        # Форматируем результат
        exec_time = (datetime.now() - start_time).total_seconds()
        
        # Разделяем вывод на категории
        lines = result.split('\n')
        stdout_lines = []
        stderr_lines = []
        proot_warnings = []
        
        for line in lines:
            line_lower = line.lower()
            if any(warning in line_lower for warning in ['proot warning:', 'shell-init:', 'job-working-directory:', 'getcwd:', 'function not implemented']):
                proot_warnings.append(line)
            elif any(error in line_lower for error in ['error:', 'fail:', 'cannot', 'no such', 'not found', 'permission denied']):
                stderr_lines.append(line)
            else:
                stdout_lines.append(line)
        
        stdout_text = '\n'.join(stdout_lines).strip()
        stderr_text = '\n'.join(stderr_lines).strip()
        proot_warnings_text = '\n'.join(proot_warnings).strip()
        
        # Определяем статус
        status_icon = "✅" if returncode == 0 else "❌"
        status_color = "🟢" if returncode == 0 else "🔴"
        status_text = translator.get_text(user_id, 'terminal_success') if returncode == 0 else translator.get_text(user_id, 'terminal_failed')
        
        # Форматируем вывод с красивым синтаксисом
        final_output = f"""<b>🖥️ {translator.get_text(user_id, 'terminal_result')}</b>

<blockquote>🔧 <b>{translator.get_text(user_id, 'command')}:</b>
<code>{cmd}</code>

{status_color} <b>{translator.get_text(user_id, 'status')}:</b> <code>{status_text}</code>
📊 <b>{translator.get_text(user_id, 'exit_code')}:</b> <code>{returncode}</code>
⏱️ <b>{translator.get_text(user_id, 'execution_time')}:</b> <code>{exec_time:.2f}секунд</code>
👤 <b>{translator.get_text(user_id, 'user')}:</b> <code>{current_user}</code>
📁 <b>{translator.get_text(user_id, 'path')}:</b> <code>{current_dir}</code></blockquote>

"""
        
        # Добавляем стандартный вывод
        if stdout_text:
            if len(stdout_text) > 3000:
                stdout_text = stdout_text[:3000] + f"\n... ({translator.get_text(user_id, 'output_truncated')})"
            final_output += f"""<b>📨 {translator.get_text(user_id, 'standard_output')}:</b>
<pre><code class="language-bash">{stdout_text}</code></pre>

"""
        
        # Добавляем ошибки
        if stderr_text:
            if len(stderr_text) > 2000:
                stderr_text = stderr_text[:2000] + f"\n... ({translator.get_text(user_id, 'errors_truncated')})"
            final_output += f"""<b>🚨 {translator.get_text(user_id, 'error_output')}:</b>
<pre><code class="language-bash">{stderr_text}</code></pre>

"""
        
        # Добавляем предупреждения proot
        if proot_warnings_text:
            if len(proot_warnings_text) > 1000:
                proot_warnings_text = proot_warnings_text[:1000] + "\n... (предупреждения обрезаны)"
            final_output += f"""<b>⚠️ {translator.get_text(user_id, 'proot_warnings')}:</b>
<pre><code class="language-bash">{proot_warnings_text}</code></pre>

"""
        
        # Если нет вывода
        if not stdout_text and not stderr_text and not proot_warnings_text:
            final_output += f"""<b>📨 {translator.get_text(user_id, 'standard_output')}:</b>
<pre><code class="language-bash">Команда выполнена, но не вернула вывод</code></pre>

"""
        
        # Финальный статус
        final_output += f"""<blockquote>{status_icon} <i>{translator.get_text(user_id, 'terminal_completed_with_code')}: {returncode}</i></blockquote>"""
        
        await loading_msg.edit(final_output, parse_mode='HTML')
        
    except asyncio.TimeoutError:
        await loading_msg.edit(f"""<b>⏰ Таймаут выполнения</b>

<blockquote>🔧 <b>{translator.get_text(user_id, 'command')}:</b>
<code>{cmd}</code>

🚫 <b>Причина:</b> Команда заняла слишком много времени
⏱️ <b>Прошло времени:</b> 60 секунд
📁 <b>{translator.get_text(user_id, 'path')}:</b> <code>{current_dir}</code></blockquote>

<blockquote>💡 <i>Для длительных операций используйте серверный терминал</i></blockquote>""", parse_mode='HTML')
        
    except Exception as e:
        await loading_msg.edit(f"""<b>❌ {translator.get_text(user_id, 'error')} выполнения</b>

<blockquote>🔧 <b>{translator.get_text(user_id, 'command')}:</b>
<code>{cmd}</code>

🚫 <b>{translator.get_text(user_id, 'error')}:</b> <code>{str(e)[:200]}</code>
📁 <b>{translator.get_text(user_id, 'path')}:</b> <code>{current_dir}</code></blockquote>

<blockquote>💡 <i>Проверьте синтаксис команды и доступность ресурсов</i></blockquote>""", parse_mode='HTML')

# ============================================
# ОБРАБОТЧИК CD КОМАНД
# ============================================

async def handle_cd_command(event, cmd, user_id, current_dir):
    """Обработка команды cd"""
    loading_msg = await edit_or_reply(event, "📁")
    await fast_animation(loading_msg, "📁", f"📁 {translator.get_text(user_id, 'terminal_scanning_directory')}...")
    
    try:
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            result = f"""<b>📁 {translator.get_text(user_id, 'terminal_current_directory')}</b>

<blockquote>🛣️ <b>{translator.get_text(user_id, 'terminal_full_path')}:</b>
<code>{current_dir}</code>

💡 <b>{translator.get_text(user_id, 'terminal_available_commands')}:</b>
<code>.terminal cd /{translator.get_text(user_id, 'path')}</code> - {translator.get_text(user_id, 'terminal_change_directory')}
<code>.terminal cd ..</code> - {translator.get_text(user_id, 'terminal_up_one_level')}
<code>.terminal cd ~</code> - {translator.get_text(user_id, 'terminal_home_directory')}</blockquote>"""
            
            await loading_msg.edit(result, parse_mode='HTML')
            return
        
        target_dir = parts[1].strip()
        
        if target_dir == '~':
            target_dir = os.path.expanduser('~')
        elif target_dir == '-':
            target_dir = os.path.expanduser('~')
        elif not target_dir.startswith('/'):
            target_dir = os.path.join(current_dir, target_dir)
        
        target_dir = os.path.abspath(os.path.expanduser(target_dir))
        
        if not os.path.exists(target_dir):
            await loading_msg.edit(f"<b>❌ {translator.get_text(user_id, 'terminal_directory_not_exists')}:</b>\n<code>{target_dir}</code>", parse_mode='HTML')
            return
        
        if not os.path.isdir(target_dir):
            await loading_msg.edit(f"<b>❌ {translator.get_text(user_id, 'terminal_not_a_directory')}:</b>\n<code>{target_dir}</code>", parse_mode='HTML')
            return
        
        old_dir = current_dir
        set_user_dir(user_id, target_dir)
        
        try:
            items = os.listdir(target_dir)
            dirs = [i for i in items if os.path.isdir(os.path.join(target_dir, i))]
            files = [i for i in items if os.path.isfile(os.path.join(target_dir, i))]
            
            result = f"""<b>✅ {translator.get_text(user_id, 'terminal_directory_changed')}</b>

<blockquote>📁 <b>{translator.get_text(user_id, 'terminal_old')}:</b> <code>{old_dir}</code>
📁 <b>{translator.get_text(user_id, 'terminal_new')}:</b> <code>{target_dir}</code>
📊 <b>{translator.get_text(user_id, 'terminal_items_count')}:</b> <code>{len(dirs)} {translator.get_text(user_id, 'terminal_folders')}, {len(files)} {translator.get_text(user_id, 'terminal_files')}</code></blockquote>

<b>💡 {translator.get_text(user_id, 'terminal_quick_commands')}:</b>
<blockquote><code>.terminal_ls</code> - {translator.get_text(user_id, 'terminal_directory_content')}
<code>.terminal "ls -la"</code> - {translator.get_text(user_id, 'terminal_detailed_view')}</blockquote>"""
            
        except PermissionError:
            result = f"""<b>✅ {translator.get_text(user_id, 'terminal_directory_changed')}</b>

<blockquote>📁 <b>{translator.get_text(user_id, 'terminal_old')}:</b> <code>{old_dir}</code>
📁 <b>{translator.get_text(user_id, 'terminal_new')}:</b> <code>{target_dir}</code>
⚠️ <b>{translator.get_text(user_id, 'terminal_no_read_access')}</b></blockquote>"""
        
        await loading_msg.edit(result, parse_mode='HTML')
        
    except Exception as e:
        await loading_msg.edit(f"<b>❌ {translator.get_text(user_id, 'terminal_cd_error')}:</b>\n<code>{str(e)}</code>", parse_mode='HTML')

# ============================================
# ОБРАБОТЧИК PROOT-DISTRO КОМАНД
# ============================================

async def handle_proot_command(event, cmd, user_id, current_dir):
    """Обработка всех proot-distro команд"""
    loading_msg = await edit_or_reply(event, "🐧")
    await fast_animation(loading_msg, "🐧", f"🐧 {translator.get_text(user_id, 'terminal_checking_proot')}...")
    
    try:
        # Авто-исправление для proot-distro login
        if 'login' in cmd and not cmd.endswith('--') and '--' not in cmd:
            parts = cmd.split()
            if len(parts) >= 4:
                login_index = parts.index('login') if 'login' in parts else -1
                if login_index != -1 and login_index + 1 < len(parts):
                    distro = parts[login_index + 1]
                    if login_index + 2 < len(parts):
                        cmd = f"proot-distro login {distro} -- {' '.join(parts[login_index+2:])}"
        
        # Выполняем команду
        start_time = datetime.now()
        current_user = os.getenv('USER', 'termux')
        
        result, returncode = await execute_with_pty(cmd, timeout=60, rows=40, cols=120, cwd=current_dir)
        
        # Форматируем результат
        exec_time = (datetime.now() - start_time).total_seconds()
        
        # Специальная обработка для разных команд proot-distro
        if 'list' in cmd:
            # Обработка вывода proot-distro list
            cleaned_result = result
            
            # Улучшаем форматирование списка
            lines = cleaned_result.split('\n')
            formatted_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('Supported') and not line.startswith('Install'):
                    if '*' in line:
                        line = f"✅ {line.replace('*', '').strip()}"
                    formatted_lines.append(line)
            
            if formatted_lines:
                cleaned_result = '\n'.join(formatted_lines)
            
            status_text = translator.get_text(user_id, 'terminal_proot_list_title')
            output_title = translator.get_text(user_id, 'standard_output')
        elif 'login' in cmd and 'neofetch' in cmd:
            # Специальная обработка для neofetch
            if 'neofetch: command not found' in result or 'env: ‘bash’: Function not implemented' in result:
                parts = cmd.split()
                distro = parts[parts.index('login') + 1] if 'login' in parts else 'archlinux'
                result = f"""{result}\n\n💡 {translator.get_text(user_id, 'terminal_proot_neofetch_not_installed')}
📦 {translator.get_text(user_id, 'terminal_proot_install_neofetch')}:
<code>proot-distro login {distro} -- pacman -S neofetch --noconfirm</code>"""
            status_text = "Proot-distro Login"
            output_title = translator.get_text(user_id, 'standard_output')
        else:
            status_text = "Proot-distro Command"
            output_title = translator.get_text(user_id, 'standard_output')
        
        # Определяем статус
        status_icon = "✅" if returncode == 0 else "❌"
        status_color = "🟢" if returncode == 0 else "🔴"
        
        # Форматируем вывод
        final_output = f"""<b>🐧 {status_text}</b>

<blockquote>🔧 <b>{translator.get_text(user_id, 'command')}:</b>
<code>{cmd}</code>

{status_color} <b>{translator.get_text(user_id, 'status')}:</b> <code>{'Успешно' if returncode == 0 else 'Ошибка'}</code>
📊 <b>{translator.get_text(user_id, 'exit_code')}:</b> <code>{returncode}</code>
⏱️ <b>{translator.get_text(user_id, 'execution_time')}:</b> <code>{exec_time:.2f}секунд</code>
👤 <b>{translator.get_text(user_id, 'user')}:</b> <code>{current_user}</code>
📁 <b>{translator.get_text(user_id, 'path')}:</b> <code>{current_dir}</code></blockquote>

"""
        
        # Добавляем вывод
        if result:
            if len(result) > 3000:
                result = result[:3000] + f"\n... ({translator.get_text(user_id, 'output_truncated')})"
            
            # Используем код с классом языка для подсветки синтаксиса
            final_output += f"""<b>📨 {output_title}:</b>
<pre><code class="language-bash">{result}</code></pre>

"""
        else:
            final_output += f"""<b>📨 {output_title}:</b>
<pre><code class="language-bash">Команда выполнена, но не вернула вывод</code></pre>

"""
        
        # Добавляем подсказку для proot-distro login
        if 'login' in cmd and '--' not in cmd:
            final_output += f"""<b>💡 {translator.get_text(user_id, 'terminal_proot_login_help')}:</b>
<blockquote><code>{cmd} -- your_command</code></blockquote>

"""
        
        # Финальный статус
        final_output += f"""<blockquote>{status_icon} <i>{translator.get_text(user_id, 'terminal_completed_with_code')}: {returncode}</i></blockquote>"""
        
        await loading_msg.edit(final_output, parse_mode='HTML')
        
    except Exception as e:
        await loading_msg.edit(f"<b>❌ {translator.get_text(user_id, 'error')}:</b>\n<code>{str(e)}</code>", parse_mode='HTML')

# ============================================
# ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ
# ============================================

@rate_limit(limit=5, period=30)
async def term_handler(event):
    """Короткая версия terminal команды"""
    await terminal_handler(event)

@rate_limit(limit=5, period=30)
async def shell_handler(event):
    """Альтернативное имя для terminal"""
    await terminal_handler(event)

@rate_limit(limit=5, period=30)
async def exec_handler(event):
    """Альтернативное имя для terminal"""
    await terminal_handler(event)

@rate_limit(limit=3, period=60)
async def terminal_info_handler(event):
    """Информация о терминальном окружении"""
    loading_msg = await edit_or_reply(event, "🔍")
    await fast_animation(loading_msg, "🔍", f"🔍 {translator.get_text(event.sender_id, 'terminal_gathering_info')}...")
    
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        
        shell_info = os.getenv('SHELL', 'unknown')
        term_info = os.getenv('TERM', 'unknown')
        user_info = os.getenv('USER', 'termux')
        home_dir = os.getenv('HOME', 'unknown')
        
        # Проверяем proot-distro
        try:
            check = subprocess.run(['which', 'proot-distro'], capture_output=True, text=True, timeout=5)
            proot_available = check.returncode == 0
            proot_status = "✅ Available" if proot_available else "❌ Not installed"
        except:
            proot_status = "⚠️ Unknown"
        
        info_text = f"""<b>🔍 {translator.get_text(user_id, 'terminal_environment')}</b>

<blockquote>🐚 <b>{translator.get_text(user_id, 'terminal_shell')}:</b> <code>{shell_info}</code>
🖥️ <b>{translator.get_text(user_id, 'terminal_terminal')}:</b> <code>{term_info}</code>
👤 <b>{translator.get_text(user_id, 'user')}:</b> <code>{user_info}</code>
🏠 <b>{translator.get_text(user_id, 'terminal_home_directory')}:</b> <code>{home_dir}</code>
📁 <b>{translator.get_text(user_id, 'terminal_current_directory')}:</b> <code>{current_dir}</code>
🔧 <b>{translator.get_text(user_id, 'terminal_permissions')}:</b> <code>{'🛡️ ROOT' if os.geteuid() == 0 else '👤 USER'}</code>
🐧 <b>Proot-distro:</b> <code>{proot_status}</code></blockquote>

<b>⚡ {translator.get_text(user_id, 'terminal_quick_commands')}:</b>
<blockquote><code>.terminal_pwd</code> - {translator.get_text(user_id, 'terminal_current_directory')}
<code>.terminal_ls</code> - {translator.get_text(user_id, 'terminal_directory_content')}
<code>.terminal_proot</code> - {translator.get_text(user_id, 'terminal_check_proot')}</blockquote>"""
        
        await loading_msg.edit(info_text, parse_mode='HTML')
        
    except Exception as e:
        await loading_msg.edit(f"<b>❌ {translator.get_text(event.sender_id, 'error')}:</b> {str(e)}", parse_mode='HTML')

@rate_limit(limit=10, period=30)
async def terminal_pwd_handler(event):
    """Показать текущую директорию"""
    loading_msg = await edit_or_reply(event, "📁")
    await fast_animation(loading_msg, "📁", f"📁 {translator.get_text(event.sender_id, 'terminal_checking_path')}...")
    
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        
        exists = os.path.exists(current_dir)
        writable = os.access(current_dir, os.W_OK) if exists else False
        readable = os.access(current_dir, os.R_OK) if exists else False
        executable = os.access(current_dir, os.X_OK) if exists else False
        
        # Получаем размер директории
        total_size = 0
        if exists and readable:
            try:
                for dirpath, dirnames, filenames in os.walk(current_dir):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        try:
                            total_size += os.path.getsize(fp)
                        except:
                            pass
            except:
                total_size = 0
        
        size_mb = total_size / (1024 * 1024)
        size_gb = total_size / (1024 * 1024 * 1024)
        size_str = f"{size_mb:.1f} MB" if size_mb < 1024 else f"{size_gb:.2f} GB"
        
        result = f"""<b>📁 {translator.get_text(user_id, 'terminal_current_directory')}</b>

<blockquote>🛣️ <b>{translator.get_text(user_id, 'terminal_full_path')}:</b>
<code>{current_dir}</code>

📊 <b>{translator.get_text(user_id, 'terminal_directory_info')}:</b>
• <b>{translator.get_text(user_id, 'terminal_exists')}:</b> <code>{'✅ Да' if exists else '❌ Нет'}</code>
• <b>{translator.get_text(user_id, 'terminal_writable')}:</b> <code>{'✅ Да' if writable else '❌ Нет'}</code>
• <b>{translator.get_text(user_id, 'terminal_readable')}:</b> <code>{'✅ Да' if readable else '❌ Нет'}</code>
• <b>{translator.get_text(user_id, 'terminal_executable')}:</b> <code>{'✅ Да' if executable else '❌ Нет'}</code>
• <b>Примерный размер:</b> <code>{size_str}</code></blockquote>

<b>🚀 {translator.get_text(user_id, 'terminal_quick_commands')}:</b>
<blockquote><code>.terminal_ls</code> - {translator.get_text(user_id, 'terminal_directory_content')}
<code>.terminal "cd /{translator.get_text(user_id, 'path')}"</code> - {translator.get_text(user_id, 'terminal_change_directory')}
<code>.terminal "pwd"</code> - {translator.get_text(user_id, 'terminal_show_path')}</blockquote>"""
        
        await loading_msg.edit(result, parse_mode='HTML')
        
    except Exception as e:
        await loading_msg.edit(f"<b>❌ {translator.get_text(event.sender_id, 'error')}:</b> {str(e)}", parse_mode='HTML')

@rate_limit(limit=10, period=30)
async def terminal_ls_handler(event):
    """Показать содержимое текущей директории"""
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        
        await execute_command(event, f'ls -la "{current_dir}"', user_id, current_dir)
        
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ {translator.get_text(event.sender_id, 'error')}:</b> {str(e)}", parse_mode='HTML')

@rate_limit(limit=3, period=60)
async def terminal_proot_handler(event):
    """Проверка proot-distro"""
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        
        await execute_command(event, 'proot-distro list', user_id, current_dir)
        
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ {translator.get_text(event.sender_id, 'error')}:</b>\n<code>{str(e)}</code>", parse_mode='HTML')

@rate_limit(limit=10, period=30)
async def terminal_whoami_handler(event):
    """Показать текущего пользователя"""
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        
        await execute_command(event, 'whoami', user_id, current_dir)
        
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ {translator.get_text(event.sender_id, 'error')}:</b> {str(e)}", parse_mode='HTML')

@rate_limit(limit=10, period=30)
async def terminal_uname_handler(event):
    """Показать информацию о системе"""
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        
        await execute_command(event, 'uname -a', user_id, current_dir)
        
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ {translator.get_text(event.sender_id, 'error')}:</b> {str(e)}", parse_mode='HTML')

@rate_limit(limit=5, period=60)
async def terminal_df_handler(event):
    """Показать использование диска"""
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        
        await execute_command(event, 'df -h', user_id, current_dir)
        
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ {translator.get_text(event.sender_id, 'error')}:</b> {str(e)}", parse_mode='HTML')

# ============================================
# СПЕЦИАЛЬНАЯ КОМАНДА ДЛЯ NEOFETCH
# ============================================

@rate_limit(limit=3, period=60)
async def neofetch_handler(event):
    """Запустить neofetch в proot-distro"""
    try:
        user_id = event.sender_id
        current_dir = get_user_dir(user_id)
        
        args = event.text.split()
        distro = 'archlinux'
        
        if len(args) > 1:
            distro = args[1]
        
        cmd = f"proot-distro login {distro} -- neofetch"
        await execute_command(event, cmd, user_id, current_dir)
        
    except Exception as e:
        await edit_or_reply(event, f"<b>❌ Ошибка neofetch:</b>\n<code>{str(e)}</code>", parse_mode='HTML')

# ============================================
# МОДУЛЬНАЯ СПРАВКА
# ============================================

modules_help = {
    "terminal": {
        "terminal [command]": "Выполнить команду в терминале",
        "term [command]": "Короткая версия terminal",
        "shell [command]": "Выполнить shell команду", 
        "exec [command]": "Выполнить системную команду",
        "neofetch [distro]": "Запустить neofetch в proot-distro",
        "terminal_info": "Информация о терминальном окружении",
        "terminal_pwd": "Показать текущую директорию",
        "terminal_ls": "Показать содержимое директории",
        "terminal_proot": "Проверить proot-distro",
        "terminal_whoami": "Показать текущего пользователя",
        "terminal_uname": "Информация о системе",
        "terminal_df": "Использование диска"
    }
}

print("✅ Terminal module loaded with directory persistence and enhanced proot-distro support!")
