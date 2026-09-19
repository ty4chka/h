"""Запуск TUI: python3 -m hydra_kernel.tui [modules_dir]"""

import curses
import sys

from .app import run_tui

if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else "modules"
    sys.exit(curses.wrapper(run_tui, directory))
