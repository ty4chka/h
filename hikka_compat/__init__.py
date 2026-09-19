"""
hikka_compat — экспериментальная (как и в оригинальном MCUB-fork, см. README
"Heroku / Hikka Module Support (beta)") прослойка для запуска модулей,
написанных под Hikka/Heroku ("loader.Module", "@loader.command",
"utils.answer", "herokutl") поверх нашего MCUB-движка.

Не все Hikka-модули будут работать — только те, что используют
распространённое подмножество API (см. hikka_compat/loader.py и utils.py).
"""

import sys

# herokutl — форк Telethon от Heroku, с теми же путями импорта что и
# обычный telethon (types/events/tl/...). Мы не ставим отдельный пакет —
# просто алиасим на уже установленный telethon.
try:
    import telethon
    import telethon.tl.types as _tt
    import telethon.events as _tev
    import telethon.tl.functions as _ttf

    sys.modules.setdefault("herokutl", telethon)
    sys.modules.setdefault("herokutl.tl", telethon.tl)
    sys.modules.setdefault("herokutl.tl.types", _tt)
    sys.modules.setdefault("herokutl.tl.functions", _ttf)
    sys.modules.setdefault("herokutl.types", _tt)
    sys.modules.setdefault("herokutl.events", _tev)
    sys.modules.setdefault("herokutl.errors", telethon.errors)
    sys.modules.setdefault("herokutl.extensions", telethon.extensions)
except Exception:
    pass
