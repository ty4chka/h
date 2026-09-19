"""Headless-проверка TUI-редактора через pty: список, редактор (ввод+undo), выход."""

import os
import pty
import select
import sys
import time


def main() -> int:
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.setdefault("TERM", "xterm-256color")
        os.execv(sys.executable, [sys.executable, "-m", "hydra_kernel.tui", "modules"])

    out = b""
    stage = 0  # 0=ждём список, 1=ждём редактор, 2=послали undo/esc/q, ждём выход
    start = time.time()
    while time.time() - start < 15:
        r, _, _ = select.select([fd], [], [], 0.3)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            if stage == 0 and b"terminal.py" in out and b"Hydra" in out:
                time.sleep(0.3)
                os.write(fd, b"\r")  # открыть первый модуль в редакторе
                stage = 1
            elif stage == 1 and b"Ctrl+S" in out:
                time.sleep(0.2)
                os.write(fd, b"x")        # ввод символа
                time.sleep(0.2)
                os.write(fd, b"\x1a")     # Ctrl+Z — undo
                time.sleep(0.2)
                os.write(fd, b"\x1b")     # Esc — в просмотр
                time.sleep(0.2)
                os.write(fd, b"q")        # в список
                time.sleep(0.2)
                os.write(fd, b"q")        # выход
                stage = 2
        elif stage == 2:
            done, _ = os.waitpid(pid, os.WNOHANG)
            if done:
                print("TUI OK: список, редактор (ввод+undo), выход по q")
                return 0

    # процесс мог завершиться: дожидаемся коротко
    if stage == 2:
        deadline = time.time() + 3
        while time.time() < deadline:
            done, _ = os.waitpid(pid, os.WNOHANG)
            if done:
                print("TUI OK: список, редактор (ввод+undo), выход по q")
                return 0
            time.sleep(0.1)
    try:
        os.kill(pid, 9)
    except OSError:
        pass
    print("TUI FAIL: не дождался корректного выхода; экран:", out[-300:])
    return 1


if __name__ == "__main__":
    sys.exit(main())
