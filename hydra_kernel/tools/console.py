"""Текстовая консоль ядра: гоняй команды без Telegram.

    python3 -m hydra_kernel.tools.console

Всё как в боте, но транспорт — NullTransport: ты печатаешь `.ping`,
ядро прогоняет реальный путь (паттерн → права → хендлер → форма),
а ответы печатаются в терминал. Кнопки «нажимаются» командой click.
"""

from __future__ import annotations

import asyncio
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAT = 500
OWNER = 1000


TAGS = re.compile(r"</?(?:b|i|u|s|code|pre|a|blockquote|span)(?:\s[^>]*)?>", re.I)


def render(msg, mark: str) -> str:
    # вид как в чате Telegram: меню кнопок уже встроено в текст мостом
    text = html.unescape(TAGS.sub("", msg.text))
    head = "✏️ изменено" if mark == "↻" else "Hydra"
    return f"{head} │ {text}".replace("\n", "\n      │ ")


async def repl() -> None:
    from hydra_kernel.app import Hydra

    h = Hydra(owner_id=OWNER)
    await h.start()
    records, errors = await h.loader.load_dir(
        ROOT / "extras" / "hydra_modules_demo", framework="hydra",
        exclude=("hydra_boot",)
    )
    for name, err in errors:
        print(f"!! модуль {name}: {err}")
    print(f"модулей: {len(records)} ({', '.join(r.name for r in records)})")
    print("чат-режим: печатай как в Telegram (.ping, .help...)")
    print(".cb N [M] — кнопка · .it N [M] текст — ввод · .cbf — скрыть меню")
    print(".iq — инлайн · .iqs — запрос в избранное по хэшу · exit — выход")
    print()

    loop = asyncio.get_event_loop()
    seen: dict = {}  # message_id -> текст (ловим edit'ы на месте)
    while True:
        try:
            line = await loop.run_in_executor(None, lambda: input("вы › "))
        except (EOFError, KeyboardInterrupt):
            break
        line = line.strip()
        if not line:
            continue
        if line in ("exit", "quit"):
            break

        if line.startswith("click "):
            try:
                _, mid, pos = line.split()
                row, col = (int(x) for x in pos.split("."))
                msg = h.transport.sent[int(mid) - 1]
                data = msg.buttons[row][col]["data"]
                await h.transport.inject_callback(data, OWNER, msg.chat_id, msg.message_id)
            except (ValueError, IndexError, KeyError) as e:
                print(f"click не удался: {e}")
        else:
            await h.transport.inject(CHAT, line, sender_id=OWNER, outgoing=True)

        # новое / изменённое / удалённое с прошлого раза
        alive = set()
        for msg in h.transport.sent:
            alive.add(msg.message_id)
            if msg.message_id not in seen:
                print(render(msg, "→"))
            elif seen[msg.message_id] != msg.text:
                print(render(msg, "↻"))
            seen[msg.message_id] = msg.text
        for mid in list(seen):
            if mid not in alive:
                print("      │ 🗑 сообщение удалено")
                seen.pop(mid)
    await h.stop()
    print("пока")


if __name__ == "__main__":
    sys.exit(asyncio.run(repl()))
