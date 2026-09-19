#!/usr/bin/env python3
"""Превью сессии в виде чата Telegram (не терминал!).

Прогоняет РЕАЛЬНУЮ сессию ядра (модули + настоящий Heroku-модуль + Go-модуль)
и рендерит её как чат: пузырьки сообщений, команды справа, ответы юзербота
слева. Результат — data/chat_preview.html.

    python3 tools/chatlog.py
"""

from __future__ import annotations

import asyncio
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HEROKU_TRANSLATIONS = Path.home() / "refs/heroku/heroku/modules/translations.py"

# демо inline-хендлера для .iq/.iqs (в modules/ своего инлайна пока нет)
INLINE_SRC = '''
from hydra_kernel.api import ModuleBase, inline_handler

class Search(ModuleBase):
    name = "chatsearch"

    @inline_handler("search")
    async def on_search(self, event):
        await event.answer([event.builder.article(
            title=f"Результат: {event.args or '…'}",
            description="найден в избранном",
        )])
'''


def tg(text: str) -> str:
    """Мини-разметка: <b>, <code> -> стиль Telegram."""
    out = html.escape(text)
    out = out.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    out = out.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
    out = re.sub(r"&lt;code&gt;(.*?)&lt;/code&gt;", r'<span class="cmd">\1</span>', out)
    return out.replace("\n", "<br>")


async def collect() -> list:
    from hydra_kernel.app import Hydra

    h = Hydra(owner_id=1000)
    await h.start()
    await h.loader.load_dir(ROOT / "extras" / "hydra_modules_demo", framework="hydra", exclude=("hydra_boot",))
    await h.loader.load_source("chatsearch", INLINE_SRC, framework="hydra")
    if HEROKU_TRANSLATIONS.exists():
        # свой translations unload'им: .setlang будет у настоящего Heroku-модуля
        await h.loader.unload("translations")
        await h.loader.load_source(
            "translations", HEROKU_TRANSLATIONS.read_text(encoding="utf-8"), framework="heroku"
        )
    go_bin = ROOT / "gocore/bin/echomod"
    go = None
    if go_bin.exists():
        from hydra_kernel.pkg.go_loader import GoLoader

        go = GoLoader(h)
        await go.load_binary(go_bin)

    log: list = []          # (who, text)
    shown: dict = {}        # message_id -> показанный текст

    async def say(text: str) -> None:
        log.append(("me", text))
        before = set(shown)
        await h.transport.inject(500, text, sender_id=1000, outgoing=True)
        for m in h.transport.sent:
            if shown.get(m.message_id) != m.text:
                if m.message_id in shown:
                    log.append(("edit", m.text))
                else:
                    log.append(("bot", m.text))
                shown[m.message_id] = m.text
        for mid in before - {m.message_id for m in h.transport.sent}:
            log.append(("del", ""))
            shown.pop(mid)

    for cmd in [".ping", ".cb 1", ".it 1 бро"]:
        await say(cmd)

    # вторая форма: у каждого меню свой номер — .cb/.it бьют точно в своё
    await say(".ping")
    ping2 = h.transport.sent[-1]
    no2 = re.search(r"Меню #(\d+)", ping2.text).group(1)
    await say(f".it 1 {no2} из чата Telegram")
    await say(f".cb 2 {no2}")

    # Go-модуль: форма + нажатие кнопки именно его меню (.cb N M)
    await say(".echo привет из Go")
    go_form = next(m for m in h.transport.sent if "Эхо: привет из Go" in m.text)
    no = re.search(r"Меню #(\d+)", go_form.text).group(1)
    await say(f".cb 1 {no}")
    await say(f".cb 2 {no}")

    # .iqs: запрос с «API-ключом» уходит в избранное, в чате только хэш
    await say(".iqs search мой-api-ключ-123")
    hash_m = re.search(r"\.iq ([0-9a-f]{8})", "\n".join(t for _, t in log))
    if hash_m:
        await say(f".iq {hash_m.group(1)}")

    # .cbf: скрыть/вернуть подсказки меню
    await say(".cbf")
    await say(".ping")
    await say(".cbf")

    for mod in (go.modules.values() if go else []):
        await mod.stop()
    await h.stop()
    return log


HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Hydra — чат Telegram</title>
<style>
  body {{ background:#0e1621; color:#e9edf0; font:14px/1.45 -apple-system,'Segoe UI',Roboto,sans-serif;
         margin:0; padding:0 12px 24px; }}
  .chat {{ max-width:560px; margin:0 auto; }}
  .tg-head {{ position:sticky; top:0; background:#17212b; border-bottom:1px solid #0e1621;
              padding:10px 14px; display:flex; align-items:center; gap:10px; margin:0 -12px 14px; }}
  .ava {{ width:38px; height:38px; border-radius:50%; background:linear-gradient(135deg,#5b9def,#8e6cef);
          display:flex; align-items:center; justify-content:center; font-size:18px; }}
  .tg-head .name {{ font-weight:600; }}
  .tg-head .state {{ font-size:12px; color:#7d8b99; }}
  .row {{ display:flex; margin:6px 0; }}
  .row.me {{ justify-content:flex-end; }}
  .bub {{ max-width:80%; padding:7px 11px; border-radius:12px; white-space:normal;
          word-break:break-word; position:relative; }}
  .me .bub {{ background:#2b5278; border-bottom-right-radius:4px; }}
  .bot .bub {{ background:#182533; border-bottom-left-radius:4px; }}
  .edit .bub {{ background:#182533; border:1px dashed #39506b; }}
  .edit::before {{ content:"✏️ сообщение изменено"; display:block; color:#7d8b99;
                   font-size:11px; margin:0 0 2px; }}
  .del .bub {{ background:transparent; color:#7d8b99; font-size:12px; }}
  .t {{ float:right; color:#7d8b99; font-size:11px; margin:8px 0 0 8px; }}
  .me .t::after {{ content:" ✓✓"; color:#6ab7ff; }}
  .cmd {{ font-family:ui-monospace,Menlo,Consolas,monospace; background:#0e1621;
          color:#6ab7ff; padding:1px 5px; border-radius:5px; }}
  .bot .bub b {{ color:#fff; }}
  .date {{ text-align:center; color:#7d8b99; font-size:12px; margin:12px 0; }}
</style></head><body>
<div class="chat">
  <div class="tg-head">
    <div class="ava">🧬</div>
    <div><div class="name">Избранное</div>
    <div class="state">Hydra userbot · всё ниже — реальный вывод ядра</div></div>
  </div>
  <div class="date">Сегодня</div>
  {rows}
</div></body></html>
"""


def render_svg(log: list, stamps: list) -> str:
    """Рендер сессии как картинка-чат Telegram (SVG — видно прямо в viewer)."""
    W, PAD, BW = 620, 14, 430          # ширина, отступ, макс. ширина пузыря
    FS, LH = 14, 19                    # шрифт, межстрочный
    parts = []
    y = 10
    body: list = []
    for (who, text), stamp in zip(log, stamps):
        if who == "del":
            body.append(
                f'<text x="{W//2 - 66}" y="{y+12}" fill="#7d8b99" font-size="12">'
                f'🗑 сообщение удалено</text>'
            )
            y += 26
            continue
        plain = re.sub(r"<[^>]+>", "", text)
        lines = []
        for ln in plain.split("\n"):
            while len(ln) > 46:
                cut = ln.rfind(" ", 0, 46)
                cut = cut if cut > 20 else 46
                lines.append(ln[:cut])
                ln = ln[cut:].lstrip()
            lines.append(ln)
        bw = min(BW, max(len(l) for l in lines) * 7.6 + 26)
        bh = len(lines) * LH + 20
        # без text-anchor: позиция текста явная (браузер и ImageMagick рисуют одинаково)
        if who == "me":
            x, fill = W - PAD - bw, "#2b5278"
            tx = x + 12
        else:
            x, fill = PAD, "#182533"
            tx = PAD + 12
        dash = ' stroke="#39506b" stroke-dasharray="4 3"' if who == "edit" else ""
        body.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="12" fill="{fill}"{dash}/>')
        ty = y + 17
        if who == "edit":
            body.append(f'<text x="{tx}" y="{ty}" fill="#7d8b99" font-size="11">✏️ изменено</text>')
            ty += 14
        for ln in lines:
            esc = html.escape(ln)
            color = "#6ab7ff" if ln.startswith((".cb", ".it", ".iq")) else "#e9edf0"
            body.append(f'<text x="{tx}" y="{ty}" fill="{color}" font-size="{FS}">{esc}</text>')
            ty += LH
        ts = stamp + (" ✓✓" if who == "me" else "")
        body.append(
            f'<text x="{(W - PAD - 12 if who == "me" else x + bw - 10) - len(ts) * 5}" y="{y + bh - 6}" '
            f'fill="#7d8b99" font-size="10">{ts}</text>'
        )
        y += bh + 8
    head = (
        f'<rect x="0" y="0" width="{W}" height="{y + 62}" fill="#0e1621"/>'
        f'<rect x="0" y="0" width="{W}" height="52" fill="#17212b"/>'
        f'<circle cx="30" cy="26" r="17" fill="#5b9def"/>'
        f'<text x="22" y="32" font-size="16">🧬</text>'
        f'<text x="56" y="23" fill="#e9edf0" font-size="14" font-weight="600">Избранное</text>'
        f'<text x="56" y="39" fill="#7d8b99" font-size="11">Hydra userbot · реальный вывод ядра</text>'
    )
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{y + 62}" font-family="Segoe UI,Roboto,sans-serif">')
    parts.append(head)
    parts.append(f'<g transform="translate(0,52)">{"".join(body)}</g>')
    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    log = asyncio.run(collect())
    rows = []
    hh, mm = 12, 0
    stamps = []
    for _ in log:
        stamps.append(f"{hh:02d}:{mm:02d}")
        mm += 1
        hh, mm = hh + mm // 60, mm % 60
    for (who, text), stamp in zip(log, stamps):
        cls = {"me": "me", "bot": "bot", "edit": "edit", "del": "del"}[who]
        body = "🗑 сообщение удалено" if who == "del" else tg(text)
        rows.append(
            f'<div class="row {cls}"><div class="bub">{body}'
            f'<span class="t">{stamp}</span></div></div>'
        )
    out = ROOT / "data" / "chat_preview.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HTML.format(rows="\n  ".join(rows)), encoding="utf-8")
    svg = ROOT / "data" / "chat_preview.svg"
    svg.write_text(render_svg(log, stamps), encoding="utf-8")
    print(f"чат-превью: {out} + {svg} ({len(log)} сообщений)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
