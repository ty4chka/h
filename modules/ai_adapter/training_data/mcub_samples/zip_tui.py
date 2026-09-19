# console/studio/tui.py
"""
MCUB Studio — main TUI class.

Layout (80 × 24 minimum):

  ┌─ Header bar ──────────────────────────────────────────────────────────────┐
  │  MCUB Studio  v2.0.0                                     ? help  q quit   │
  ├─ Left panel ───┬─ Right panel (detail / editor / search / welcome) ───────┤
  │ USER MODULES   │                                                           │
  │ ▶ weather      │  < detail, editor, or welcome screen >                   │
  │   notes        │                                                           │
  │   ...          │                                                           │
  │ SYSTEM MODULES │                                                           │
  │   loader       │                                                           │
  │   register     │                                                           │
  │                │                                                           │
  │ [n] new        │                                                           │
  │ [/] search     │                                                           │
  ├────────────────┴───────────────────────────────────────────────────────── ┤
  │  Log                                                                       │
  │  [12:34] => Module 'weather' loaded OK                                    │
  │  [12:33] =- Unregistering old commands...                                 │
  └─ Status bar ──────────────────────────────────────────────────────────────┘

Overlays drawn on top when mode == "loading" or "confirm".
"""

from __future__ import annotations

import asyncio
import curses
import math
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .actions import ProgressReporter, StudioActions
from .editor  import MODULE_TEMPLATE, TextEditor
from .widgets  import (
    CP_ACCENT, CP_BORDER, CP_COMMENT, CP_DIM, CP_ERROR,
    CP_HEADER, CP_KW, CP_NORMAL, CP_OK, CP_OVERLAY, CP_PROGRESS,
    CP_SEL, CP_SHADOW, CP_STATUSBG, CP_WARN,
    clamp, draw_box, draw_progress_bar, fill_rect, init_colors, safe_add,
)

class Studio:
    """
    Interactive TUI module manager for MCUB.

    Vim-flavoured keybindings; runs inside the shell's asyncio event loop
    via loop.run_in_executor() so the kernel stays alive.
    """

    VERSION  = "2.0.0"
    LEFT_W   = 24    # width of the left module-list panel
    LOG_H    = 7     # height of the bottom log panel (including border)
    MIN_W    = 62
    MIN_H    = 20

    # Spinner frames (used in loading overlay)
    _SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, kernel) -> None:
        self.kernel  = kernel
        self.loop    = asyncio.get_event_loop()
        self.actions = StudioActions(kernel, self.loop)
        # Modes: list | detail | editor | new | search | loading | confirm
        self._mode        = "list"

        # Module list
        self._modules: List[Tuple[str, str]] = []  # (name, kind)
        self._sel         = 0
        self._list_scroll = 0

        # Detail panel
        self._detail_meta: dict = {}
        self._detail_scroll     = 0

        # Editor
        self._editor: Optional[TextEditor] = None
        self._edit_name = ""      # name being edited; "" → new module

        # Search panel
        self._search_query   = ""
        self._search_results: List[Tuple[str, str]] = []
        self._search_sel     = 0
        self._search_done    = False

        # Loading overlay
        self._reporter: Optional[ProgressReporter] = None
        self._load_title  = ""
        self._load_done   = False
        self._load_ok     = False

        # Confirm dialog
        self._confirm_msg: str = ""
        self._confirm_cb:  Optional[Callable] = None

        # Log
        self._log_lines: List[str] = []
        self._status_msg  = ""
        self._status_ok   = True

        # Screen geometry (set each draw cycle)
        self._H = 0
        self._W = 0

    async def start(self) -> None:
        """Run the Studio TUI. Blocks until the user quits."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: curses.wrapper(self._run))

    def _run(self, stdscr) -> None:
        curses.curs_set(0)
        curses.noecho()
        stdscr.keypad(True)
        stdscr.timeout(80)   # ms; enables animation in loading overlay

        init_colors()

        self._refresh_modules()
        self._log("MCUB Studio ready  —  press ? for help")

        while True:
            self._H, self._W = stdscr.getmaxyx()
            if self._H < self.MIN_H or self._W < self.MIN_W:
                stdscr.erase()
                msg = f"Terminal too small (min {self.MIN_W}x{self.MIN_H})"
                safe_add(stdscr, self._H // 2, max(0, (self._W - len(msg)) // 2),
                         msg, curses.color_pair(CP_ERROR) | curses.A_BOLD)
                stdscr.refresh()
                key = stdscr.getch()
                if key == ord("q"):
                    return
                continue

            try:
                stdscr.erase()
                self._draw(stdscr)
                stdscr.refresh()
            except curses.error:
                pass
              
            key = stdscr.getch()
            if key == -1:
                continue   # timeout — just redraw (spinner animation)

            if self._dispatch(key):
                return     # quit signal

    def _dispatch(self, key: int) -> bool:
        """Return True → quit the TUI."""
        m = self._mode

        if key == curses.KEY_RESIZE:
            return False

        # Loading: only dismiss when finished
        if m == "loading":
            if self._load_done and key in (10, 13, 27, ord(" "), ord("q")):
                self._mode = "list"
                self._refresh_modules()
            return False

        # Confirm
        if m == "confirm":
            if key in (ord("y"), ord("Y")):
                cb = self._confirm_cb
                self._mode = "list"
                if cb:
                    cb()
            elif key in (ord("n"), ord("N"), 27):
                self._mode = "list"
            return False

        # Editor / new
        if m in ("editor", "new"):
            return self._editor_dispatch(key)

        # Search
        if m == "search":
            return self._search_dispatch(key)

        # List / detail — global quit
        if key == ord("q"):
            if m == "detail":
                self._mode = "list"
                return False
            return True   # quit

        # Navigation
        if key in (ord("j"), curses.KEY_DOWN):
            self._navigate(+1)
        elif key in (ord("k"), curses.KEY_UP):
            self._navigate(-1)
        elif key in (curses.KEY_PPAGE,):
            self._navigate(-10)
        elif key in (curses.KEY_NPAGE,):
            self._navigate(+10)
        elif key in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT, ord("l")):
            self._open_detail()
        elif key in (27, curses.KEY_LEFT, ord("h")):
            self._mode = "list"

        # Detail scroll
        elif key == curses.KEY_SR:    self._detail_scroll = max(0, self._detail_scroll - 1)
        elif key == curses.KEY_SF:    self._detail_scroll += 1

        # Actions
        elif key == ord("n"):   self._act_new()
        elif key == ord("e"):   self._act_edit()
        elif key == ord("r"):   self._act_reload()
        elif key == ord("u"):   self._act_update()
        elif key in (ord("D"), ord("X")):
            self._act_delete()
        elif key == ord("/"):   self._act_search()
        elif key == ord("R"):   self._refresh_modules(); self._set_status("Module list refreshed")
        elif key == ord("?"):   self._show_help()

        return False

    def _editor_dispatch(self, key: int) -> bool:
        if not self._editor:
            self._mode = "list"
            return False
        result = self._editor.handle_key(key)
        if result == TextEditor.KEY_SAVE:
            self._save_and_load()
        elif result == TextEditor.KEY_QUIT:
            curses.curs_set(0)
            self._editor  = None
            self._mode    = "list"
        return False

    def _search_dispatch(self, key: int) -> bool:
        if key == 27 or key == 17:   # ESC / Ctrl+Q
            self._mode = "list"
            curses.curs_set(0)
            return False
        if key in (curses.KEY_BACKSPACE, 127, 8):
            self._search_query = self._search_query[:-1]
            self._search_done  = False
            return False
        if key in (10, 13):
            self._do_search()
            return False
        if key == curses.KEY_DOWN:
            self._search_sel = min(self._search_sel + 1, len(self._search_results) - 1)
        elif key == curses.KEY_UP:
            self._search_sel = max(self._search_sel - 1, 0)
        elif key == ord("i"):
            self._install_from_search()
        elif 32 <= key <= 126:
            self._search_query += chr(key)
            self._search_done   = False
        return False

    def _navigate(self, delta: int) -> None:
        if not self._modules:
            return
        self._sel = clamp(self._sel + delta, 0, len(self._modules) - 1)
        # Scroll list so selected is visible
        # (handled in draw based on _list_scroll)

    def _open_detail(self) -> None:
        m = self._current_module()
        if m:
            self._mode          = "detail"
            self._detail_scroll = 0
            self._detail_meta   = self.actions.get_module_metadata(m[0])

    def _refresh_modules(self) -> None:
        user   = [(n, "user")   for n in self.actions.get_user_modules()]
        system = [(n, "system") for n in self.actions.get_system_modules()]
        self._modules = user + system
        self._sel     = clamp(self._sel, 0, max(0, len(self._modules) - 1))

    def _current_module(self) -> Optional[Tuple[str, str]]:
        if self._modules and 0 <= self._sel < len(self._modules):
            return self._modules[self._sel]
        return None

    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_lines.append(f"[{ts}] {msg}")
        if len(self._log_lines) > 300:
            self._log_lines.pop(0)

    def _set_status(self, msg: str, ok: bool = True) -> None:
        self._status_msg = msg
        self._status_ok  = ok
        self._log(msg)

    def _act_new(self) -> None:
        self._edit_name = ""
        self._editor    = TextEditor(MODULE_TEMPLATE)
        self._mode      = "new"
        curses.curs_set(1)

    def _act_edit(self) -> None:
        mod = self._current_module()
        if not mod:
            return
        source = self.actions.get_module_source(mod[0])
        if source is None:
            self._set_status(f"Cannot read source for '{mod[0]}'", False)
            return
        self._edit_name = mod[0]
        self._editor    = TextEditor(source)
        self._mode      = "editor"
        curses.curs_set(1)

    def _act_reload(self) -> None:
        mod = self._current_module()
        if not mod:
            return
        name = mod[0]
        reporter = self._start_loading(f"Reload  {name}")
        self._launch(
            lambda: self.actions.reload_module(name, reporter),
            reporter,
        )

    def _act_update(self) -> None:
        mod = self._current_module()
        if not mod:
            return
        name = mod[0]
        reporter = self._start_loading(f"Update  {name}")
        self._launch(
            lambda: self.actions.update_from_repo(name, reporter),
            reporter,
        )

    def _act_delete(self) -> None:
        mod = self._current_module()
        if not mod:
            return
        name, kind = mod
        verb = "Unload only" if kind == "system" else "Delete file & unload"
        self._confirm(
            f"Delete & unload '{name}'?  [y] yes   [n] no",
            lambda: self._do_delete(name, kind),
        )

    def _do_delete(self, name: str, kind: str) -> None:
        reporter = self._start_loading(f"Delete  {name}")
        if kind == "system":
            fn = lambda: self.actions.unload_module(name, reporter)
        else:
            fn = lambda: self.actions.delete_module(name, reporter)
        self._launch(fn, reporter)

    def _act_search(self) -> None:
        self._search_query   = ""
        self._search_results = []
        self._search_sel     = 0
        self._search_done    = False
        self._mode           = "search"
        curses.curs_set(1)

    def _do_search(self) -> None:
        q = self._search_query.strip()
        if not q:
            return
        self._log(f"=- Searching repos for '{q}'...")
        results = self.actions.search_repos(q)
        self._search_results = results
        self._search_sel     = 0
        self._search_done    = True
        count = len(results)
        self._log(f"=> {count} result(s) for '{q}'" if count else f"=X No results for '{q}'")

    def _install_from_search(self) -> None:
        if not self._search_results:
            return
        idx = clamp(self._search_sel, 0, len(self._search_results) - 1)
        mod_name, repo_url = self._search_results[idx]
        self._mode = "list"
        curses.curs_set(0)
        reporter = self._start_loading(f"Install  {mod_name}")
        self._launch(
            lambda: self.actions.download_and_install(repo_url, mod_name, reporter),
            reporter,
        )

    def _save_and_load(self) -> None:
        if not self._editor:
            return
        curses.curs_set(0)
        code = self._editor.get_text()

        # Infer module name: try "# Module: <name>" header, else edit_name, else prompt
        name = self._edit_name
        if not name:
            for line in code.split("\n")[:8]:
                line = line.strip()
                if line.lower().startswith("# module:"):
                    name = line.split(":", 1)[-1].strip()
                    break
        if not name:
            name = "new_module"

        self._editor = None
        self._mode   = "list"

        reporter = self._start_loading(f"Save & load  {name}")
        self._launch(
            lambda: self.actions.create_module(name, code, reporter),
            reporter,
        )

    def _start_loading(self, title: str) -> ProgressReporter:
        reporter = ProgressReporter()
        reporter.on_update(lambda pct, msg: self._log(msg))
        self._reporter   = reporter
        self._load_title = title
        self._load_done  = False
        self._load_ok    = False
        self._mode       = "loading"
        return reporter

    def _launch(
        self,
        fn: Callable[[], Tuple[bool, str]],
        reporter: ProgressReporter,
    ) -> None:
        """Run *fn* in a daemon thread; sets _load_done when finished."""
        def _worker():
            try:
                ok, msg = fn()
            except Exception as e:
                ok, msg = False, str(e)
                reporter.step(1.0, f"=X Unhandled error: {e}")
            self._load_done = True
            self._load_ok   = ok
            self._set_status(("OK " if ok else "ERR ") + msg, ok)

        threading.Thread(target=_worker, daemon=True).start()

    def _confirm(self, msg: str, cb: Callable) -> None:
        self._confirm_msg = msg
        self._confirm_cb  = cb
        self._mode        = "confirm"

    def _show_help(self) -> None:
        lines = [
            "=- Navigation:  j/k or ↑↓ move · Enter/→ open detail · ←/Esc back",
            "=- Module ops:  e=edit · r=reload · u=update from repo · D=delete",
            "=- Global:      n=new module · /=search repo · R=refresh list · q=quit",
            "=- Editor:      Ctrl+S save&load · Ctrl+Z undo · Tab=4sp · Ctrl+Q cancel",
            "=- Search:      type query · Enter search · ↑↓ pick · i=install",
        ]
        for l in lines:
            self._log(l)

    def _draw(self, stdscr) -> None:
        H, W    = self._H, self._W
        LW      = self.LEFT_W
        LH      = self.LOG_H
        panel_h = H - LH - 2     # content rows (excl. header + status)
        rp_x    = LW + 1          # right panel start X
        rp_w    = W - rp_x - 1   # right panel width
        log_y   = H - LH - 1

        self._draw_header(stdscr, W)
        self._draw_left(stdscr, 1, 0, panel_h, LW)

        m = self._mode
        if m in ("editor", "new"):
            self._draw_editor(stdscr, 1, rp_x, panel_h, rp_w)
        elif m == "detail":
            self._draw_detail(stdscr, 1, rp_x, panel_h, rp_w)
        elif m == "search":
            self._draw_search(stdscr, 1, rp_x, panel_h, rp_w)
        else:
            self._draw_welcome(stdscr, 1, rp_x, panel_h, rp_w)

        self._draw_log(stdscr, log_y, 0, LH, W)
        self._draw_statusbar(stdscr, H - 1, W)

        # Overlays (rendered last, on top)
        if m == "loading":
            self._draw_loading(stdscr, H, W)
        elif m == "confirm":
            self._draw_confirm(stdscr, H, W)

    def _draw_header(self, win, W: int) -> None:
        attr = curses.color_pair(CP_STATUSBG) | curses.A_BOLD
        safe_add(win, 0, 0, " " * (W - 1), attr)
        title = f"  MCUB Studio  v{self.VERSION}"
        hint  = "? help  q quit  "
        safe_add(win, 0, 0, title, attr | curses.A_BOLD)
        if W - len(hint) - 2 > len(title):
            safe_add(win, 0, W - len(hint) - 1, hint, attr)

        # Mode badge
        badge_map = {
            "editor":  (" EDIT ",  CP_WARN),
            "new":     (" NEW  ",  CP_OK),
            "search":  (" SRCH ",  CP_ACCENT),
            "loading": (" LOAD ",  CP_HEADER),
            "detail":  (" INFO ",  CP_HEADER),
            "confirm": (" CONF ",  CP_ERROR),
        }
        if self._mode in badge_map:
            badge_txt, badge_cp = badge_map[self._mode]
            bx = len(title) + 2
            if bx + len(badge_txt) < W - len(hint) - 2:
                safe_add(win, 0, bx, badge_txt,
                         curses.color_pair(badge_cp) | curses.A_REVERSE | curses.A_BOLD)

    def _draw_left(self, win, y: int, x: int, h: int, w: int) -> None:
        draw_box(win, y, x, h, w, " Modules ", CP_BORDER, CP_HEADER)

        inner_h = h - 2
        visible_start = self._list_scroll

        # Scroll to keep _sel visible
        if self._sel < self._list_scroll:
            self._list_scroll = self._sel
        # Rough visible row count (accounting for section headers)
        self._ensure_sel_visible(inner_h)

        row = y + 1
        max_row = y + h - 2

        last_kind = None
        visible_idx = 0

        for idx, (name, kind) in enumerate(self._modules):
            # Section header
            if kind != last_kind:
                if visible_idx >= visible_start and row <= max_row:
                    hdr = " USER " if kind == "user" else " SYSTEM "
                    hdr_attr = (curses.color_pair(CP_OK)    | curses.A_BOLD if kind == "user"
                                else curses.color_pair(CP_WARN) | curses.A_BOLD)
                    safe_add(win, row, x + 1, hdr, hdr_attr)
                    row += 1
                last_kind = kind
                visible_idx += 1

            if visible_idx < visible_start:
                visible_idx += 1
                continue

            if row > max_row:
                break

            is_sel = (idx == self._sel)
            cmds   = self.actions.get_module_commands(name)
            n_cmds = len(cmds)

            if is_sel:
                attr   = curses.color_pair(CP_SEL) | curses.A_BOLD
                prefix = " \u25b6 "   # ▶
            else:
                attr   = curses.color_pair(CP_NORMAL)
                prefix = "   "

            label = f"{prefix}{name}"
            if n_cmds:
                label += f" ({n_cmds})"
            label = label[:w - 2].ljust(w - 2)
            safe_add(win, row, x + 1, label, attr)
            row += 1
            visible_idx += 1

        # Hint bar at bottom of left panel
        hints = [("[n]", "new"), ("[/]", "search"), ("[R]", "refresh")]
        hr = y + h - 2
        for sym, lab in reversed(hints):
            if hr <= row:
                break
            safe_add(win, hr, x + 1, sym, curses.color_pair(CP_WARN) | curses.A_BOLD)
            safe_add(win, hr, x + 1 + len(sym) + 1, lab, curses.color_pair(CP_DIM))
            hr -= 1

        # Scrollbar indicator
        n = len(self._modules) + 2   # approximate (inc. headers)
        if n > inner_h:
            pct = self._sel / max(n - 1, 1)
            sb_y = y + 1 + int((inner_h - 1) * pct)
            safe_add(win, min(sb_y, max_row), x + w - 2, "\u2588",
                     curses.color_pair(CP_ACCENT))

    def _ensure_sel_visible(self, inner_h: int) -> None:
        """Adjust _list_scroll so that _sel is in view."""
        # Each module takes ~1 row, plus 1 header per section type
        # Simple heuristic: scroll if sel > scroll + inner_h - 3
        if self._sel < self._list_scroll:
            self._list_scroll = self._sel
        if self._sel >= self._list_scroll + inner_h - 3:
            self._list_scroll = self._sel - inner_h + 3
        self._list_scroll = max(0, self._list_scroll)

    def _draw_welcome(self, win, y: int, x: int, h: int, w: int) -> None:
        draw_box(win, y, x, h, w, " MCUB Studio ", CP_BORDER, CP_HEADER)

        cy = y + h // 2 - 4
        cx = x + max(2, (w - 40) // 2)

        logo = [
            r"  __  __  ____ _   _ ____  ",
            r" |  \/  |/ ___| | | | __ ) ",
            r" | |\/| | |   | | | |  _ \ ",
            r" | |  | | |___| |_| | |_) |",
            r" |_|  |_|\____|\___/|____/ ",
            r"          S T U D I O      ",
        ]

        for i, line in enumerate(logo):
            col = CP_HEADER if i < 5 else CP_ACCENT
            safe_add(win, cy + i, cx, line[:w - 4],
                     curses.color_pair(col) | curses.A_BOLD)

        help_y = cy + len(logo) + 1
        items  = [
            ("n",      "Create a new module"),
            ("/",      "Search & install from repository"),
            ("Enter",  "Open module detail"),
            ("e",      "Edit module source"),
            ("r",      "Reload module"),
            ("?",      "Show all keybindings"),
        ]
        safe_add(win, help_y, x + 4, "Keybindings:",
                 curses.color_pair(CP_ACCENT) | curses.A_BOLD)
        for i, (k, desc) in enumerate(items):
            safe_add(win, help_y + 1 + i, x + 4,
                     f"  [{k}]",
                     curses.color_pair(CP_WARN) | curses.A_BOLD)
            safe_add(win, help_y + 1 + i, x + 12,
                     desc,
                     curses.color_pair(CP_NORMAL))

    def _draw_detail(self, win, y: int, x: int, h: int, w: int) -> None:
        mod = self._current_module()
        if not mod:
            draw_box(win, y, x, h, w, " No module selected ")
            safe_add(win, y + 2, x + 3, "Select a module with j/k then Enter",
                     curses.color_pair(CP_DIM))
            return

        name, kind = mod
        draw_box(win, y, x, h, w, f" {name} ", CP_BORDER, CP_HEADER)

        meta    = self._detail_meta
        cmds    = self.actions.get_module_commands(name)
        fpath   = self.actions.get_module_file(name)
        is_user = name in self.kernel.loaded_modules
        is_sys  = name in self.kernel.system_modules

        # ── Build content lines
        content: List[Tuple[str, int]] = []   # (text, cp)

        if is_user or is_sys:
            status_cp = CP_OK
            status_tx = "  LOADED"
        else:
            status_cp = CP_ERROR
            status_tx = "  NOT LOADED"

        content.append((status_tx, status_cp | curses.A_BOLD))
        content.append(("  " + "\u2500" * (w - 4), CP_BORDER))

        def kv(k: str, v: str, vcp: int = CP_NORMAL) -> None:
            content.append((f"  {k:<12} {v}", vcp))

        kv("Type:",    kind.upper(), CP_ACCENT)
        if meta.get("author"):
            kv("Author:",   meta["author"], CP_HEADER)
        if meta.get("version"):
            kv("Version:",  meta["version"], CP_WARN)
        if meta.get("description"):
            kv("Desc:",     meta["description"][:w - 20], CP_DIM)
        if fpath:
            kv("File:",     fpath[:w - 20], CP_DIM)

        content.append(("", 0))
        if cmds:
            content.append(("  Commands:", CP_ACCENT | curses.A_BOLD))
            prefix = self.kernel.custom_prefix
            for c in cmds:
                content.append((f"    {prefix}{c}", CP_HEADER))
        else:
            content.append(("  No commands registered", CP_DIM | curses.A_DIM))

        content.append(("", 0))
        content.append(("  " + "\u2500" * (w - 4), CP_BORDER))
        content.append(("  Actions:", CP_ACCENT | curses.A_BOLD))

        # Render with scroll
        oy    = y + 1
        avail = h - 4    # reserve 3 rows for action bar at bottom
        scroll = clamp(self._detail_scroll, 0, max(0, len(content) - avail))

        for i, (text, attr) in enumerate(content):
            si = i - scroll
            if si < 0:
                continue
            sy = oy + si
            if sy >= oy + avail:
                break
            if text:
                safe_add(win, sy, x + 1, text[:w - 2],
                         curses.color_pair(attr) if isinstance(attr, int) else attr)
        ab_y = y + h - 3
        safe_add(win, ab_y, x + 1, "\u2500" * (w - 2), curses.color_pair(CP_BORDER))
        ab_y += 1
        actions = [
            ("[e] Edit",   CP_OK),
            ("[r] Reload", CP_WARN),
            ("[u] Update", CP_HEADER),
            ("[D] Delete", CP_ERROR),
        ]
        ax = x + 2
        for label, cp in actions:
            if ax + len(label) > x + w - 2:
                break
            safe_add(win, ab_y, ax, label, curses.color_pair(cp) | curses.A_BOLD)
            ax += len(label) + 2

    def _draw_editor(self, win, y: int, x: int, h: int, w: int) -> None:
        is_new = self._mode == "new"
        label  = " NEW MODULE " if is_new else f" EDIT: {self._edit_name} "
        draw_box(win, y, x, h, w, label, CP_BORDER, CP_WARN if is_new else CP_HEADER)

        # Hint row
        hint = " Ctrl+S: save & load   Ctrl+Z: undo   Ctrl+Q / ESC: cancel "
        safe_add(win, y + h - 2, x + 2, hint[:w - 4],
                 curses.color_pair(CP_DIM) | curses.A_DIM)

        if self._editor:
            curses.curs_set(1)
            self._editor.render(
                win,
                y + 1, x + 1,
                h - 3, w - 2,
                line_numbers=True,
            )

    def _draw_search(self, win, y: int, x: int, h: int, w: int) -> None:
        draw_box(win, y, x, h, w, " Repository Search ", CP_BORDER, CP_ACCENT)
        curses.curs_set(1)

        # Query input
        safe_add(win, y + 1, x + 2, "Query: ", curses.color_pair(CP_ACCENT) | curses.A_BOLD)
        qx = x + 2 + 7
        safe_add(win, y + 1, qx, self._search_query + "\u258c",
                 curses.color_pair(CP_WARN) | curses.A_BOLD)

        # Move cursor to end of query
        try:
            win.move(y + 1, qx + len(self._search_query))
        except curses.error:
            pass

        safe_add(win, y + 2, x + 1, "\u2500" * (w - 2), curses.color_pair(CP_BORDER))

        if not self._search_done:
            tip = "Press Enter to search all repositories"
            safe_add(win, y + 3, x + 3, tip, curses.color_pair(CP_DIM) | curses.A_DIM)
        elif not self._search_results:
            safe_add(win, y + 3, x + 3,
                     f"No results for '{self._search_query}'",
                     curses.color_pair(CP_WARN))
        else:
            count = len(self._search_results)
            safe_add(win, y + 3, x + 3,
                     f"{count} result(s) found  \u2191\u2193 navigate  [i] install",
                     curses.color_pair(CP_OK))

            for i, (mod, repo) in enumerate(self._search_results):
                ry = y + 4 + i
                if ry >= y + h - 2:
                    safe_add(win, ry, x + 3,
                             f"  ... {count - i} more", curses.color_pair(CP_DIM))
                    break
                is_sel = (i == self._search_sel)
                if is_sel:
                    safe_add(win, ry, x + 2, f" \u25b6 {mod:<20}",
                             curses.color_pair(CP_SEL) | curses.A_BOLD)
                    short_repo = repo.rstrip("/").split("/")[-1]
                    safe_add(win, ry, x + 26, short_repo[:w - 30],
                             curses.color_pair(CP_DIM))
                else:
                    safe_add(win, ry, x + 2, f"   {mod}", curses.color_pair(CP_NORMAL))
                    short_repo = repo.rstrip("/").split("/")[-1]
                    safe_add(win, ry, x + 26, short_repo[:w - 30],
                             curses.color_pair(CP_DIM))

    def _draw_log(self, win, y: int, x: int, h: int, w: int) -> None:
        draw_box(win, y, x, h, w, " Log ", CP_BORDER, CP_DIM)

        visible = self._log_lines[-(h - 2):]
        for i, line in enumerate(visible):
            ly = y + 1 + i
            if ly >= y + h - 1:
                break
            # Pick colour by content prefix
            if "OK " in line[:14] or "=>" in line[:14]:
                attr = curses.color_pair(CP_OK)
            elif "=X" in line[:14] or "ERR" in line[:14]:
                attr = curses.color_pair(CP_ERROR)
            elif "=-" in line[:14]:
                attr = curses.color_pair(CP_WARN)
            elif "=!" in line[:14]:
                attr = curses.color_pair(CP_ACCENT)
            else:
                attr = curses.color_pair(CP_DIM)
            safe_add(win, ly, x + 1, line[:w - 2], attr)

    def _draw_statusbar(self, win, y: int, W: int) -> None:
        attr = curses.color_pair(CP_STATUSBG)
        safe_add(win, y, 0, " " * (W - 1), attr)

        if self._status_msg:
            col = CP_OK if self._status_ok else CP_ERROR
            sym = "\u2714" if self._status_ok else "\u2716"
            safe_add(win, y, 2, f"{sym} {self._status_msg}"[:W - 4],
                     curses.color_pair(col) | curses.A_BOLD)
        else:
            n_u = len([m for m in self._modules if m[1] == "user"])
            n_s = len([m for m in self._modules if m[1] == "system"])
            info = f"  {n_u} user  +  {n_s} system modules   mode: {self._mode}"
            safe_add(win, y, 0, info[:W - 1], attr)


    def _draw_loading(self, win, H: int, W: int) -> None:
        OW = min(W - 6, 68)
        OH = 18
        OX = (W - OW) // 2
        OY = (H - OH) // 2

        # Shadow (2px offset)
        shadow_attr = curses.color_pair(CP_SHADOW) | curses.A_DIM
        for r in range(OH):
            safe_add(win, OY + r + 1, OX + 2, " " * OW, shadow_attr)

        # Background
        bg_attr = curses.color_pair(CP_OVERLAY)
        fill_rect(win, OY, OX, OH, OW, bg_attr)

        # Border
        draw_box(win, OY, OX, OH, OW,
                 f" {self._load_title} ",
                 CP_ACCENT, CP_ACCENT)

        reporter = self._reporter
        pct      = reporter.percent if reporter else 0.0
        logs     = reporter.logs    if reporter else []

        bar_y = OY + 2
        bar_w = OW - 6
        draw_progress_bar(win, bar_y, OX + 3, bar_w, pct)
        state_y = OY + 4
      
        if self._load_done:
            ok   = self._load_ok
            col  = CP_OK if ok else CP_ERROR
            sym  = "\u2714 Done!" if ok else "\u2716 Failed"
            safe_add(win, state_y, OX + 4, sym,
                     curses.color_pair(col) | curses.A_BOLD)
            safe_add(win, state_y + 1, OX + 4,
                     "Press Space or Enter to close...",
                     curses.color_pair(CP_DIM) | curses.A_DIM)
        else:
            frame = self._SPINNER[int(time.time() * 10) % len(self._SPINNER)]
            pct_label = f"{int(pct * 100)}%"
            safe_add(win, state_y, OX + 4,
                     f"{frame}  Working...  {pct_label}",
                     curses.color_pair(CP_WARN) | curses.A_BOLD)

        # ── Log section ───────────────────────────────────────
        log_sep_y = OY + 6
        safe_add(win, log_sep_y, OX + 2,
                 "\u2500" * (OW - 4),
                 curses.color_pair(CP_BORDER))
        safe_add(win, log_sep_y, OX + 4, " Log ",
                 curses.color_pair(CP_HEADER) | curses.A_BOLD)

        log_area_h = OH - 9
        log_y      = log_sep_y + 1
        visible    = logs[-log_area_h:] if logs else []

        for i, entry in enumerate(visible):
            ly = log_y + i
            if ly >= OY + OH - 2:
                break
            if "OK " in entry[:14] or "=>" in entry[:14]:
                attr = curses.color_pair(CP_OK)
            elif "=X" in entry[:14]:
                attr = curses.color_pair(CP_ERROR)
            elif "=-" in entry[:14]:
                attr = curses.color_pair(CP_WARN)
            elif "=!" in entry[:14]:
                attr = curses.color_pair(CP_ACCENT)
            else:
                attr = curses.color_pair(CP_DIM)
            safe_add(win, ly, OX + 3, entry[:OW - 6], attr)

    def _draw_confirm(self, win, H: int, W: int) -> None:
        msg = self._confirm_msg
        OW  = max(len(msg) + 10, 44)
        OH  = 6
        OX  = (W - OW) // 2
        OY  = (H - OH) // 2

        fill_rect(win, OY, OX, OH, OW, curses.color_pair(CP_OVERLAY))
        draw_box(win, OY, OX, OH, OW, " Confirm Action ", CP_ERROR, CP_ERROR)

        safe_add(win, OY + 1, OX + 3, msg[:OW - 4],
                 curses.color_pair(CP_NORMAL) | curses.A_BOLD)
        safe_add(win, OY + 3, OX + 3,
                 "[Y] Confirm   [N] Cancel",
                 curses.color_pair(CP_WARN) | curses.A_BOLD)
