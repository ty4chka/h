"""TUI-редактор модулей (фаза 7): подсветка синтаксиса, поиск '/',
undo (Ctrl+Z), переход ':N', сохранение с ast-валидацией и .bak.

Управление:
  список:  j/k — выбор, Enter/e — правка, v — просмотр, q — выход
  просмотр/правка: j/k/стрелки, '/' — поиск, 'n' — следующее,
                   ':' — команда (:N строка, :w сохранить, :q назад),
                   Ctrl+S — сохранить, Ctrl+Z — undo, Esc — назад
"""
from __future__ import annotations

import curses
import re
from typing import List, Optional, Tuple

from .model import EditorModel

# цветовые пары (инициализируются в run_tui)
P_KEYWORD, P_STRING, P_COMMENT, P_NUMBER, P_DEF = 1, 2, 3, 4, 5

_KEYWORDS = (
    "and", "as", "assert", "async", "await", "break", "class", "continue",
    "def", "del", "elif", "else", "except", "finally", "for", "from",
    "global", "if", "import", "in", "is", "lambda", "nonlocal", "not",
    "or", "pass", "raise", "return", "try", "while", "with", "yield",
    "None", "True", "False", "self",
)

_TOKEN_RE = re.compile(
    r"#[^\n]*"
    r"|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'"
    r"|\b(?:" + "|".join(_KEYWORDS) + r")\b"
    r"|\b\d+(?:\.\d+)?\b"
)


def line_spans(line: str) -> List[Tuple[int, int, int]]:
    """(start, end, color_pair) для подсветки строки."""
    spans: List[Tuple[int, int, int]] = []
    for m in _TOKEN_RE.finditer(line):
        tok = m.group()
        if tok.startswith("#"):
            pair = P_COMMENT
        elif tok[0] in "\"'":
            pair = P_STRING
        elif tok[0].isdigit():
            pair = P_NUMBER
        elif tok in ("def", "class"):
            pair = P_DEF
        else:
            pair = P_KEYWORD
        spans.append((m.start(), m.end(), pair))
    return spans


class EditorApp:
    def __init__(self, stdscr, model: EditorModel, status: str = ""):
        self.scr = stdscr
        self.model = model
        self.status = status
        self.files: List[str] = model.files()
        self.idx = 0
        self.mode = "list"  # list | view | edit
        self.current: Optional[str] = None
        self.lines: List[str] = []
        self.offset = 0          # скролл просмотра
        self.crow = 0
        self.ccol = 0
        self.message = ""
        self.undo_stack: List[Tuple[List[str], int, int]] = []
        self.search: Optional[str] = None
        self.prompt: Optional[str] = None   # '/' или ':'
        self.prompt_buf = ""

    # ── рисование ──────────────────────────────────────────
    def _add(self, y: int, x: int, text: str, attr: int = 0) -> None:
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        try:
            self.scr.addnstr(y, x, text, max(w - x - 1, 0), attr)
        except curses.error:
            pass

    def draw(self) -> None:
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        title = "🐉 Hydra Editor"
        self._add(0, max((w - len(title)) // 2, 0), title, curses.A_BOLD)
        if self.status:
            self._add(0, 1, self.status[: max(w - len(title) - 4, 4)], curses.color_pair(P_COMMENT))
        if self.mode == "list":
            self._draw_list(h, w)
        elif self.mode == "view":
            self._draw_view(h, w)
        else:
            self._draw_edit(h, w)
        # статусная строка
        if self.prompt is not None:
            self._add(h - 1, 0, f"{self.prompt}{self.prompt_buf}", curses.A_BOLD)
        else:
            hint = {
                "list": "Enter/e правка · v просмотр · q выход",
                "view": "/ поиск · :N строка · e правка · q назад",
                "edit": "Ctrl+S сохранить · Ctrl+Z undo · / поиск · :N строка · Esc назад",
            }[self.mode]
            left = f" {hint}"
            right = ""
            if self.mode == "edit" and self.current:
                right = f"{self.current}  {self.crow + 1}:{self.ccol + 1} "
            elif self.current:
                right = f"{self.current}  {self.offset + 1} "
            if self.message:
                left = f" {self.message}"
            self._add(h - 1, 0, left.ljust(max(w - len(right) - 1, 1))[: max(w - len(right) - 1, 1)])
            if right:
                self._add(h - 1, max(w - len(right) - 1, 0), right, curses.color_pair(P_NUMBER))
        self.scr.refresh()

    def _draw_list(self, h: int, w: int) -> None:
        self._add(2, 2, f"модули ({len(self.files)})", curses.A_BOLD | curses.color_pair(P_KEYWORD))
        top = max(0, min(self.idx - (h - 6) // 2, max(len(self.files) - (h - 5), 0)))
        for i, name in enumerate(self.files[top:top + h - 5], start=top):
            attr = curses.A_REVERSE if i == self.idx else 0
            mark = "▸ " if i == self.idx else "  "
            self._add(3 + i - top, 2, f"{mark}{name}".ljust(min(w - 4, 40))[: min(w - 4, 40)], attr)

    def _draw_text(self, h: int, w: int, top: int, cursor_at: Optional[int] = None) -> None:
        for i, line in enumerate(self.lines[top:top + h - 4], start=top):
            y = 2 + i - top
            expanded = line.replace("\t", "    ")
            base = curses.A_NORMAL
            if cursor_at is not None and i == cursor_at:
                base = curses.A_REVERSE
            self._add(y, 1, expanded[: w - 2].ljust(1), base)
            if not base & curses.A_REVERSE:
                for s, e, pair in line_spans(line):
                    if s >= w - 2:
                        break
                    seg = expanded[s:min(e, w - 2)]
                    if not seg:
                        continue
                    self._add(y, 1 + s, seg, curses.color_pair(pair))

    def _draw_view(self, h: int, w: int) -> None:
        self._draw_text(h, w, self.offset)

    def _draw_edit(self, h: int, w: int) -> None:
        self._draw_text(h, w, self.offset)
        try:
            curses.curs_set(1)
            self.scr.move(2 + self.crow - self.offset, min(1 + self.ccol, w - 2))
        except curses.error:
            pass

    # ── режимы ─────────────────────────────────────────────
    def open_view(self) -> None:
        if not self.files:
            return
        self.current = self.files[self.idx]
        self.lines = self.model.read(self.current).split("\n")
        self.offset = 0
        self.mode = "view"
        self.message = ""

    def open_edit(self) -> None:
        if self.mode == "list":
            self.open_view()
        self.mode = "edit"
        self.crow = 0
        self.ccol = 0
        self.undo_stack.clear()

    def _push_undo(self) -> None:
        self.undo_stack.append((list(self.lines), self.crow, self.ccol))
        if len(self.undo_stack) > 300:
            self.undo_stack.pop(0)

    def undo(self) -> None:
        if not self.undo_stack:
            self.message = "undo: пусто"
            return
        self.lines, self.crow, self.ccol = self.undo_stack.pop()
        self.message = "↩️ undo"

    def save(self) -> None:
        ok, info = self.model.save(self.current or "", "\n".join(self.lines))
        self.message = (
            "💾 сохранено (модули перезагрузятся при выходе)" if ok else f"🚫 {info}"
        )
        if ok:
            self.files = self.model.files()

    # ── поиск / команды ────────────────────────────────────
    def do_search(self, term: str, from_cursor: bool = True) -> None:
        if not term:
            return
        self.search = term
        n = len(self.lines)
        start = self.crow if (from_cursor and self.mode == "edit") else self.offset
        for step in range(n):
            i = (start + step) % n
            col = self.lines[i].find(term)
            if col >= 0 and not (step == 0 and from_cursor and self.mode == "edit" and col <= self.ccol):
                self.crow, self.ccol = i, col
                self.offset = i
                self.message = f"🔎 {term}"
                return
        self.message = f"🔎 не найдено: {term}"

    def run_command(self, cmd: str) -> bool:
        cmd = cmd.strip()
        if cmd in ("q", "quit"):
            return False
        if cmd in ("w", "save"):
            self.save()
            return True
        if cmd.isdigit():
            line = int(cmd) - 1
            line = max(0, min(line, len(self.lines) - 1))
            self.crow = self.offset = line
            self.ccol = 0
            self.message = f"→ строка {line + 1}"
            return True
        self.message = f"? команда: {cmd}"
        return True

    # ── клавиши ────────────────────────────────────────────
    def key_list(self, ch: int) -> bool:
        if ch in (ord("q"), ord("Q")):
            return False
        if ch in (ord("j"), curses.KEY_DOWN) and self.idx < len(self.files) - 1:
            self.idx += 1
        if ch in (ord("k"), curses.KEY_UP) and self.idx > 0:
            self.idx -= 1
        if ch in (ord("g"), ord("G")):
            self.idx = 0 if ch == ord("g") else len(self.files) - 1
        if ch in (ord("v"), curses.KEY_RIGHT):
            self.open_view()
        if ch in (10, 13, ord("e")):
            self.open_edit()
        return True

    def key_view(self, ch: int) -> bool:
        if ch in (ord("q"), 27, curses.KEY_LEFT):
            self.mode = "list"
            return True
        if ch in (ord("j"), curses.KEY_DOWN) and self.offset < len(self.lines) - 1:
            self.offset += 1
        if ch in (ord("k"), curses.KEY_UP) and self.offset > 0:
            self.offset -= 1
        if ch in (ord("e"), 10, 13):
            self.open_edit()
        if ch == ord("n") and self.search:
            self.do_search(self.search, from_cursor=False)
        if ch in (ord("/"), ord(":")):
            self.prompt = chr(ch)
            self.prompt_buf = ""
        return True

    def key_edit(self, ch: int) -> bool:
        line = self.lines[self.crow]
        if ch in (10, 13):  # Enter — новая строка
            self._push_undo()
            rest = line[self.ccol:]
            self.lines[self.crow] = line[:self.ccol]
            self.lines.insert(self.crow + 1, rest)
            self.crow += 1
            self.ccol = 0
        elif ch in (127, curses.KEY_BACKSPACE):
            if self.ccol > 0:
                self._push_undo()
                self.lines[self.crow] = line[:self.ccol - 1] + line[self.ccol:]
                self.ccol -= 1
            elif self.crow > 0:
                self._push_undo()
                prev = self.lines[self.crow - 1]
                self.ccol = len(prev)
                self.lines[self.crow - 1] = prev + line
                del self.lines[self.crow]
                self.crow -= 1
        elif ch == curses.KEY_DC:
            self._push_undo()
            self.lines[self.crow] = line[:self.ccol] + line[self.ccol + 1:]
        elif ch == curses.KEY_UP and self.crow > 0:
            self.crow -= 1
            self.ccol = min(self.ccol, len(self.lines[self.crow]))
        elif ch == curses.KEY_DOWN and self.crow < len(self.lines) - 1:
            self.crow += 1
            self.ccol = min(self.ccol, len(self.lines[self.crow]))
        elif ch == curses.KEY_LEFT and self.ccol > 0:
            self.ccol -= 1
        elif ch == curses.KEY_RIGHT and self.ccol < len(line):
            self.ccol += 1
        elif ch == curses.KEY_HOME:
            self.ccol = 0
        elif ch == curses.KEY_END:
            self.ccol = len(line)
        elif ch == 26:  # Ctrl+Z — undo
            self.undo()
        elif ch == 19:  # Ctrl+S — сохранить
            self.save()
        elif ch == 27:  # Esc — назад к просмотру
            self.mode = "view"
            self.offset = self.crow
        elif ch == ord("n") and self.search:
            self.do_search(self.search)
        elif ch in (ord("/"), ord(":")):
            self.prompt = chr(ch)
            self.prompt_buf = ""
        elif 32 <= ch < 127 or ch in (ord("а"),):
            self._push_undo()
            self.lines[self.crow] = line[:self.ccol] + chr(ch) + line[self.ccol:]
            self.ccol += 1
        return True

    def key_prompt(self, ch: int) -> bool:
        if ch in (10, 13):
            kind, buf = self.prompt, self.prompt_buf
            self.prompt, self.prompt_buf = None, ""
            if kind == "/":
                self.do_search(buf)
            elif kind == ":":
                if not self.run_command(buf):
                    self.mode = "list"
        elif ch in (127, curses.KEY_BACKSPACE):
            self.prompt_buf = self.prompt_buf[:-1]
            if not self.prompt_buf:
                self.prompt = None
        elif ch == 27:
            self.prompt, self.prompt_buf = None, ""
        elif 32 <= ch < 127:
            self.prompt_buf += chr(ch)
        return True

    def _autoscroll(self, h: int) -> None:
        visible = max(h - 5, 1)
        if self.mode == "edit":
            if self.crow < self.offset:
                self.offset = self.crow
            elif self.crow >= self.offset + visible:
                self.offset = self.crow - visible + 1
        else:
            self.offset = max(0, min(self.offset, len(self.lines) - 1))

    def loop(self) -> int:
        curses.curs_set(0)
        while True:
            h, w = self.scr.getmaxyx()
            self._autoscroll(h)
            self.draw()
            if self.mode == "edit":
                try:
                    curses.curs_set(1)
                except curses.error:
                    pass
            ch = self.scr.getch()
            if ch == curses.KEY_RESIZE:
                continue
            if self.prompt is not None:
                alive = self.key_prompt(ch)
            elif self.mode == "list":
                alive = self.key_list(ch)
            elif self.mode == "view":
                alive = self.key_view(ch)
            else:
                alive = self.key_edit(ch)
            if not alive:
                return 0
            if self.mode != "edit":
                try:
                    curses.curs_set(0)
                except curses.error:
                    pass


def run_tui(stdscr, directory: str = "modules", status: str = "") -> int:
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(P_KEYWORD, curses.COLOR_MAGENTA, -1)
    curses.init_pair(P_STRING, curses.COLOR_GREEN, -1)
    curses.init_pair(P_COMMENT, curses.COLOR_CYAN, -1)
    curses.init_pair(P_NUMBER, curses.COLOR_YELLOW, -1)
    curses.init_pair(P_DEF, curses.COLOR_BLUE, -1)
    app = EditorApp(stdscr, EditorModel(directory), status=status)
    return app.loop()
