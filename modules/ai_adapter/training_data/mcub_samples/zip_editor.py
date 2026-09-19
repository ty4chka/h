"""
Multi-line code editor widget with Python syntax highlighting.
Embedded inside the Studio TUI right panel.
"""

from __future__ import annotations

import curses
import re
from typing import List, Tuple

from .widgets import (
    CP_NORMAL, CP_KW, CP_STR, CP_COMMENT, CP_HEADER,
    CP_WARN, CP_ACCENT, CP_ERROR, CP_NUMLINE, CP_OK,
    safe_add, clamp,
)


# Python syntax data 
_KEYWORDS = frozenset({
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield",
})

_SOFT_KW = frozenset({"self", "super", "cls"})

_BUILTINS = frozenset({
    "print", "len", "range", "str", "int", "float", "list", "dict",
    "set", "tuple", "bool", "type", "isinstance", "hasattr", "getattr",
    "setattr", "open", "enumerate", "zip", "map", "filter", "any", "all",
    "max", "min", "sum", "abs", "round", "sorted", "reversed", "next",
    "iter", "repr", "id", "hex", "oct", "bin", "chr", "ord", "input",
})

# Default module template
MODULE_TEMPLATE = """\
# Module:      my_module
# Author:      @your_username
# Version:     1.0.0
# Description: Short description of what this module does

def register(kernel):
    client = kernel.client

    @kernel.register.command("hello")
    async def hello_handler(event):
        \"\"\"Say hello.\"\"\"
        await event.edit("Hello from my_module!")
"""



Token = Tuple[str, int]   # (text, curses_attr)


def _tokenise(line: str) -> List[Token]:
    """Return a list of (text, attr) tokens for one source line."""
    tokens: List[Token] = []

    stripped = line.lstrip()
    if stripped.startswith("#"):
        idx = line.index("#")
        if idx:
            tokens.append((line[:idx], curses.color_pair(CP_NORMAL)))
        tokens.append((line[idx:], curses.color_pair(CP_COMMENT) | curses.A_DIM))
        return tokens

    i = 0
    n = len(line)

    while i < n:
        ch = line[i]

        if ch == "#":
            tokens.append((line[i:], curses.color_pair(CP_COMMENT) | curses.A_DIM))
            break

        if ch in ('"', "'"):
            # Detect triple quote
            if line[i:i+3] in ('"""', "'''"):
                q, step = line[i:i+3], 3
            else:
                q, step = ch, 1
            j = i + step
            end = line.find(q, j)
            if end == -1:
                end = n - step
            end = end + step
            tokens.append((line[i:end], curses.color_pair(CP_STR)))
            i = end
            continue

        if ch.isdigit() or (ch == '-' and i + 1 < n and line[i+1].isdigit()):
            j = i + (1 if ch == '-' else 0)
            while j < n and (line[j].isdigit() or line[j] in ".xXoObBeEjJ_"):
                j += 1
            tokens.append((line[i:j], curses.color_pair(CP_WARN)))
            i = j
            continue

        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            word = line[i:j]
            if word in _KEYWORDS:
                tokens.append((word, curses.color_pair(CP_KW) | curses.A_BOLD))
            elif word in _SOFT_KW:
                tokens.append((word, curses.color_pair(CP_ACCENT)))
            elif word in _BUILTINS:
                tokens.append((word, curses.color_pair(CP_HEADER)))
            else:
                tokens.append((word, curses.color_pair(CP_NORMAL)))
            i = j
            continue
          
        if ch == "@":
            j = i + 1
            while j < n and (line[j].isalnum() or line[j] in "._"):
                j += 1
            tokens.append((line[i:j], curses.color_pair(CP_ACCENT) | curses.A_BOLD))
            i = j
            continue
          
        if ch in "=<>!+-*/%&|^~":
            tokens.append((ch, curses.color_pair(CP_WARN)))
            i += 1
            continue

        # Anything else — normal
        tokens.append((ch, curses.color_pair(CP_NORMAL)))
        i += 1

    return tokens

class TextEditor:
    """
    Curses multi-line editor with Python syntax highlighting.

    Keybindings (when render() is active):
      Arrow keys      — move cursor
      Home / End      — start / end of line
      Page Up/Down    — ±20 lines
      Backspace       — delete left / join lines
      Delete          — delete right
      Tab             — insert 4 spaces + smart indent
      Enter           — new line + auto-indent (adds +4 after ':')
      Ctrl+A          — start of line
      Ctrl+E          — end of line
      Ctrl+K          — kill to end of line
      Ctrl+U          — kill to start of line
      Ctrl+Z          — undo (single level)
      Ctrl+S          — (caller checks, returns KEY_SAVE sentinel)
      Ctrl+Q / ESC    — (caller checks, returns KEY_QUIT sentinel)
    """

    KEY_SAVE  = -1000   # sentinel: save requested
    KEY_QUIT  = -1001   # sentinel: quit editor

    def __init__(self, text: str = "") -> None:
        self._lines: List[List[str]] = [list(l) for l in text.split("\n")]
        if not self._lines:
            self._lines = [[]]
        self.row = 0
        self.col = 0
        self._scroll_row = 0
        self._scroll_col = 0
        self._modified   = False
        # single-level undo
        self._undo_buf: List[List[str]] | None = None

    @property
    def modified(self) -> bool:
        return self._modified

    def get_text(self) -> str:
        return "\n".join("".join(line) for line in self._lines)

    def set_text(self, text: str) -> None:
        self._lines   = [list(l) for l in text.split("\n")]
        self.row      = 0
        self.col      = 0
        self._modified = False

    def handle_key(self, key: int) -> int:
        """
        Process one keypress.
        Returns KEY_SAVE, KEY_QUIT, or 0 (consumed) or the raw key (unhandled).
        """
        # Save before modifying for undo
        def _snapshot():
            self._undo_buf = [list(l) for l in self._lines]

        if key == 19:   return self.KEY_SAVE   # Ctrl+S
        if key in (17, 27):  return self.KEY_QUIT  # Ctrl+Q / ESC

        if key == curses.KEY_UP:
            if self.row > 0:
                self.row -= 1
                self._clamp_col()
            return 0

        if key == curses.KEY_DOWN:
            if self.row < len(self._lines) - 1:
                self.row += 1
                self._clamp_col()
            return 0

        if key == curses.KEY_LEFT:
            if self.col > 0:
                self.col -= 1
            elif self.row > 0:
                self.row -= 1
                self.col = len(self._lines[self.row])
            return 0

        if key == curses.KEY_RIGHT:
            if self.col < len(self._lines[self.row]):
                self.col += 1
            elif self.row < len(self._lines) - 1:
                self.row += 1
                self.col = 0
            return 0

        if key in (curses.KEY_HOME, 1):   # Home / Ctrl+A
            self.col = 0
            return 0

        if key in (curses.KEY_END, 5):    # End / Ctrl+E
            self.col = len(self._lines[self.row])
            return 0

        if key == curses.KEY_PPAGE:
            self.row = max(0, self.row - 20)
            self._clamp_col()
            return 0

        if key == curses.KEY_NPAGE:
            self.row = min(len(self._lines) - 1, self.row + 20)
            self._clamp_col()
            return 0

        if key == 11:   # Ctrl+K — kill to end
            _snapshot()
            self._lines[self.row] = self._lines[self.row][:self.col]
            self._modified = True
            return 0

        if key == 21:   # Ctrl+U — kill to start
            _snapshot()
            self._lines[self.row] = self._lines[self.row][self.col:]
            self.col = 0
            self._modified = True
            return 0

        if key == 26:   # Ctrl+Z
            if self._undo_buf is not None:
                self._lines    = self._undo_buf
                self._undo_buf = None
                self.row       = clamp(self.row, 0, len(self._lines) - 1)
                self._clamp_col()
                self._modified = True
            return 0

        if key in (10, 13, curses.KEY_ENTER):
            _snapshot()
            current = self._lines[self.row]
            joined  = "".join(current)
            indent  = len(joined) - len(joined.lstrip())
            # Extra indent after colon
            extra = 4 if joined.rstrip().endswith(":") else 0
            new_indent = " " * (indent + extra)

            rest = current[self.col:]
            self._lines[self.row] = current[:self.col]
            self._lines.insert(self.row + 1, list(new_indent) + rest)
            self.row  += 1
            self.col   = len(new_indent)
            self._modified = True
            return 0

        if key in (127, 8, curses.KEY_BACKSPACE):
            _snapshot()
            if self.col > 0:
                # Smart de-indent: if previous 4 chars are spaces, remove all
                line = self._lines[self.row]
                if (self.col >= 4
                        and all(c == " " for c in line[self.col - 4:self.col])):
                    del line[self.col - 4:self.col]
                    self.col -= 4
                else:
                    del line[self.col - 1]
                    self.col -= 1
                self._modified = True
            elif self.row > 0:
                prev_len = len(self._lines[self.row - 1])
                self._lines[self.row - 1].extend(self._lines[self.row])
                del self._lines[self.row]
                self.row -= 1
                self.col  = prev_len
                self._modified = True
            return 0

        if key == curses.KEY_DC:
            _snapshot()
            if self.col < len(self._lines[self.row]):
                del self._lines[self.row][self.col]
                self._modified = True
            elif self.row < len(self._lines) - 1:
                self._lines[self.row].extend(self._lines[self.row + 1])
                del self._lines[self.row + 1]
                self._modified = True
            return 0

        if key == 9:
            _snapshot()
            spaces = list("    ")
            pos    = self.col
            self._lines[self.row][pos:pos] = spaces
            self.col   += 4
            self._modified = True
            return 0

        if 32 <= key <= 126:
            _snapshot()
            self._lines[self.row].insert(self.col, chr(key))
            self.col   += 1
            self._modified = True
            return 0

        return key   # unhandled — return to caller

    def render(self, win, y: int, x: int, h: int, w: int,
               line_numbers: bool = True) -> None:
        """
        Draw editor content into *win* at cell (y, x), size (h, w).
        Moves the real terminal cursor to the editor caret position.
        """
        LN_W    = 5 if line_numbers else 0  # "  42 "
        CODE_W  = w - LN_W

        # Scroll to keep cursor visible
        if self.row < self._scroll_row:
            self._scroll_row = self.row
        if self.row >= self._scroll_row + h:
            self._scroll_row = self.row - h + 1
        if self.col < self._scroll_col:
            self._scroll_col = self.col
        if self.col >= self._scroll_col + CODE_W:
            self._scroll_col = self.col - CODE_W + 1

        n_lines = len(self._lines)

        for screen_row in range(h):
            doc_row = screen_row + self._scroll_row
            sy      = y + screen_row
            is_cur  = (doc_row == self.row)

            # Background for current line
            if is_cur:
                line_bg = curses.color_pair(CP_NORMAL) | curses.A_REVERSE | curses.A_DIM
            else:
                line_bg = curses.color_pair(CP_NORMAL)

            # Clear the line
            safe_add(win, sy, x, " " * (w - 1), line_bg)

            if doc_row >= n_lines:
                # Empty row beyond file end
                if line_numbers:
                    safe_add(win, sy, x, " " * LN_W,
                             curses.color_pair(CP_NUMLINE) | curses.A_DIM)
                    safe_add(win, sy, x + LN_W, "~",
                             curses.color_pair(CP_DIM) | curses.A_DIM)
                continue

            if line_numbers:
                ln_attr = (curses.color_pair(CP_WARN) | curses.A_BOLD
                           if is_cur
                           else curses.color_pair(CP_NUMLINE) | curses.A_DIM)
                safe_add(win, sy, x, f"{doc_row + 1:4d} ", ln_attr)

            line_str  = "".join(self._lines[doc_row])
            visible   = line_str[self._scroll_col:self._scroll_col + CODE_W]
            tokens    = _tokenise(visible)

            cx = x + LN_W
            for tok_text, tok_attr in tokens:
                avail = (x + w - 1) - cx
                if avail <= 0:
                    break
                drawn = tok_text[:avail]
                try:
                    win.addstr(sy, cx, drawn, tok_attr)
                except curses.error:
                    pass
                cx += len(drawn)

        cur_screen_row = self.row - self._scroll_row
        cur_screen_col = self.col - self._scroll_col
        if 0 <= cur_screen_row < h and 0 <= cur_screen_col < CODE_W:
            try:
                win.move(y + cur_screen_row, x + LN_W + cur_screen_col)
            except curses.error:
                pass

    def _clamp_col(self) -> None:
        self.col = clamp(self.col, 0, len(self._lines[self.row]))
