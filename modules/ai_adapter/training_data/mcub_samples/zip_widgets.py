"""
Low-level curses helpers: color scheme, box drawing, progress bar.
"""
import curses

CP_HEADER   = 1   # cyan
CP_OK       = 2   # green
CP_WARN     = 3   # yellow
CP_ERROR    = 4   # red
CP_NORMAL   = 5   # white
CP_DIM      = 6   # dark grey
CP_ACCENT   = 7   # magenta
CP_SEL      = 8   # black-on-cyan   (selected item)
CP_STATUSBG = 9   # black-on-blue   (status bar)
CP_BORDER   = 10  # bright white
CP_KW       = 11  # yellow bold     (Python keywords)
CP_STR      = 12  # green           (strings)
CP_COMMENT  = 13  # grey dim        (comments)
CP_PROGRESS = 14  # cyan-on-dark    (progress bar fill)
CP_SHADOW   = 15  # black-on-black  (shadow)
CP_OVERLAY  = 16  # white-on-dark   (modal bg)
CP_NUMLINE  = 17  # dark on default (line numbers)


def init_colors() -> None:
    """Initialize all color pairs. Call once inside curses.wrapper()."""
    curses.start_color()
    curses.use_default_colors()
    bg = -1  # transparent terminal background

    curses.init_pair(CP_HEADER,   curses.COLOR_CYAN,    bg)
    curses.init_pair(CP_OK,       curses.COLOR_GREEN,   bg)
    curses.init_pair(CP_WARN,     curses.COLOR_YELLOW,  bg)
    curses.init_pair(CP_ERROR,    curses.COLOR_RED,     bg)
    curses.init_pair(CP_NORMAL,   curses.COLOR_WHITE,   bg)
    curses.init_pair(CP_DIM,      curses.COLOR_BLACK,   bg)
    curses.init_pair(CP_ACCENT,   curses.COLOR_MAGENTA, bg)
    curses.init_pair(CP_SEL,      curses.COLOR_BLACK,   curses.COLOR_CYAN)
    curses.init_pair(CP_STATUSBG, curses.COLOR_BLACK,   curses.COLOR_BLUE)
    curses.init_pair(CP_BORDER,   curses.COLOR_WHITE,   bg)
    curses.init_pair(CP_KW,       curses.COLOR_YELLOW,  bg)
    curses.init_pair(CP_STR,      curses.COLOR_GREEN,   bg)
    curses.init_pair(CP_COMMENT,  curses.COLOR_BLACK,   bg)
    curses.init_pair(CP_PROGRESS, curses.COLOR_CYAN,    bg)
    curses.init_pair(CP_SHADOW,   curses.COLOR_BLACK,   curses.COLOR_BLACK)
    curses.init_pair(CP_OVERLAY,  curses.COLOR_WHITE,   curses.COLOR_BLACK)
    curses.init_pair(CP_NUMLINE,  curses.COLOR_BLACK,   bg)

def safe_add(win, y: int, x: int, text: str, attr: int = 0) -> None:
    """addstr that silently ignores boundary errors."""
    try:
        h, w = win.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        available = w - x - 1
        if available <= 0:
            return
        win.addstr(y, x, text[:available], attr)
    except curses.error:
        pass


def safe_hline(win, y: int, x: int, char, length: int, attr: int = 0) -> None:
    try:
        h, w = win.getmaxyx()
        if y < 0 or y >= h or x < 0:
            return
        length = min(length, w - x - 1)
        if length > 0:
            win.attron(attr)
            win.hline(y, x, char, length)
            win.attroff(attr)
    except curses.error:
        pass


def fill_rect(win, y: int, x: int, h: int, w: int, attr: int) -> None:
    """Fill a rectangle with spaces using *attr*."""
    for row in range(h):
        safe_add(win, y + row, x, ' ' * w, attr)


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))

def draw_box(win, y: int, x: int, h: int, w: int,
             title: str = "",
             border_cp: int = CP_BORDER,
             title_cp:  int = CP_HEADER) -> None:
    """
    Draw a single-line border box.
    Optionally centres *title* on the top edge.
    """
    if h < 2 or w < 2:
        return

    ba = curses.color_pair(border_cp)
    ta = curses.color_pair(title_cp) | curses.A_BOLD

    try:
        # Corners
        win.addch(y,         x,         curses.ACS_ULCORNER, ba)
        win.addch(y,         x + w - 1, curses.ACS_URCORNER, ba)
        win.addch(y + h - 1, x,         curses.ACS_LLCORNER, ba)
        # Bottom-right corner may raise at screen edge — ignore
        try:
            win.addch(y + h - 1, x + w - 1, curses.ACS_LRCORNER, ba)
        except curses.error:
            pass

        # Top / bottom edges
        for i in range(1, w - 1):
            win.addch(y,         x + i, curses.ACS_HLINE, ba)
            win.addch(y + h - 1, x + i, curses.ACS_HLINE, ba)

        # Side edges
        for i in range(1, h - 1):
            win.addch(y + i, x,         curses.ACS_VLINE, ba)
            win.addch(y + i, x + w - 1, curses.ACS_VLINE, ba)

        # Title
        if title:
            t = f" {title} "
            tx = x + max(1, (w - len(t)) // 2)
            safe_add(win, y, tx, t[:w - 2], ta)

    except curses.error:
        pass

_BAR_FILL  = "\u2588"   # █
_BAR_HALF  = "\u258c"   # ▌
_BAR_EMPTY = "\u2591"   # ░


def draw_progress_bar(win, y: int, x: int, w: int,
                      percent: float,
                      fill_cp:  int = CP_PROGRESS,
                      empty_cp: int = CP_DIM) -> None:
    """
    Render a Unicode block progress bar.
    percent: 0.0 – 1.0
    Layout: [████████░░░░░░  68%]
    """
    percent = clamp(float(percent), 0.0, 1.0)

    # Reserve space for percentage label " 100%" = 5 chars
    bar_w    = max(4, w - 6)
    filled_f = bar_w * percent
    filled   = int(filled_f)
    empty    = bar_w - filled

    bar_str  = _BAR_FILL * filled + _BAR_EMPTY * empty

    pct_str  = f" {int(percent * 100):3d}%"

    try:
        win.attron(curses.color_pair(fill_cp) | curses.A_BOLD)
        win.addstr(y, x, bar_str[:filled])
        win.attroff(curses.color_pair(fill_cp) | curses.A_BOLD)

        win.attron(curses.color_pair(empty_cp))
        win.addstr(y, x + filled, bar_str[filled:filled + empty])
        win.attroff(curses.color_pair(empty_cp))

        pct_col = CP_OK if percent >= 1.0 else CP_WARN
        win.attron(curses.color_pair(pct_col) | curses.A_BOLD)
        win.addstr(y, x + bar_w, pct_str)
        win.attroff(curses.color_pair(pct_col) | curses.A_BOLD)
    except curses.error:
        pass
