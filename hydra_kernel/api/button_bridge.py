"""L1 — ButtonBridge: инлайн-кнопки как текстовые команды.

Юзербот не получает CallbackQuery (они приходят только ботам), поэтому в
текстовом режиме каждая кнопка формы рендерится строкой меню:

    ⚙️ Меню #2:
    .cb 1 2 🔄 Обновить ┃ .cb 2 2 ❌ Закрыть

Команды моста:
  .cb N       — нажать кнопку N последнего меню в чате
  .cb N M     — нажать кнопку N меню #M (когда меню в чате несколько)
  .cb         — показать последнее меню ещё раз
  .it N текст   — ввод для input-кнопок (кнопка {"input": fn}),
  .it N M текст — то же для конкретного меню #M
  .cbf        — вкл/выкл подсказки меню (кнопки продолжают работать вслепую)
  .iqs <запрос> — сохранить запрос в «избранное» и получить хэш
  .iq <хэш|запрос> — инлайн-поиск (хэш тянет запрос из избранного,
                     чтобы API-ключи не светились в общем чате)

Порт идеи mcub_engine/bridge.py (ButtonBridge) из старого репозитория.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .inline import CallbackQueryEvent

_HASH_RE = re.compile(r"^[0-9a-f]{6,16}$")
_MAX_MENUS = 10


@dataclass
class MenuRec:
    no: int
    message_id: int
    tokens: List[str] = field(default_factory=list)
    inputs: List[str] = field(default_factory=list)
    html: str = ""


class ButtonBridge:
    def __init__(self, hydra: Any):
        self.h = hydra
        self._menus: Dict[int, Dict[int, MenuRec]] = {}   # chat -> no -> rec
        self._msg_no: Dict[int, Dict[int, int]] = {}      # chat -> message_id -> no
        self._inputs: Dict[str, Tuple[Any, tuple]] = {}   # token -> (fn, args)

    # ---------------------------------------------------------- состояние

    @property
    def show_menus(self) -> bool:
        return bool(self.h.config.get("bridge_menus", True))

    def register_input(self, token: str, fn: Any, args: tuple) -> None:
        self._inputs[token] = (fn, tuple(args or ()))

    # ---------------------------------------------------------- рендер меню

    def render(self, msg: Any) -> str:
        """Хук транспорта: дописывает меню к тексту и регистрирует его."""
        chat_id = msg.chat_id
        by_msg = self._msg_no.setdefault(chat_id, {})
        no = by_msg.get(msg.message_id)
        if no is None:
            menus = self._menus.setdefault(chat_id, {})
            no = max(menus, default=0) + 1
            menus[no] = MenuRec(no=no, message_id=msg.message_id)
            by_msg[msg.message_id] = no
            if len(menus) > _MAX_MENUS:  # выкинуть самое старое
                oldest = min(menus)
                old = menus.pop(oldest)
                by_msg.pop(old.message_id, None)
        rec = self._menus[chat_id][no]

        prefix = self.h.prefix
        cb_tokens: List[str] = []
        in_tokens: List[str] = []
        rows_out: List[str] = []
        for row in msg.buttons or []:
            items: List[str] = []
            for btn in row if isinstance(row, (list, tuple)) else [row]:
                if not isinstance(btn, dict) or btn.get("data") is None:
                    if isinstance(btn, dict) and btn.get("url"):
                        items.append(f"↗ {html.escape(str(btn.get('text', '?')))}: {btn['url']}")
                    continue
                label = html.escape(str(btn.get("text", "?")))
                if btn.get("input"):
                    in_tokens.append(btn["data"])
                    items.append(f"<code>{prefix}it {len(in_tokens)} {no}</code> {label}")
                else:
                    cb_tokens.append(btn["data"])
                    items.append(f"<code>{prefix}cb {len(cb_tokens)} {no}</code> {label}")
            if items:
                rows_out.append(" ┃ ".join(items))

        rec.tokens, rec.inputs = cb_tokens, in_tokens
        rec.html = ""
        if rows_out:
            rec.html = f"<b>⚙️ Меню #{no}:</b>\n" + "\n".join(rows_out)
        if not self.show_menus or not rec.html:
            return msg.text
        return f"{msg.text}\n\n{rec.html}"

    def rebind(self, msg: Any, old_id: int) -> None:
        """Транспорт получил реальный message_id после отправки —
        переписываем учётку меню с временного id (0) на боевой."""
        by_msg = self._msg_no.get(msg.chat_id)
        if not by_msg or old_id not in by_msg:
            return
        no = by_msg.pop(old_id)
        by_msg[msg.message_id] = no
        rec = self._menus.get(msg.chat_id, {}).get(no)
        if rec is not None:
            rec.message_id = msg.message_id

    def _find(self, chat_id: int, no: Optional[int]) -> Optional[MenuRec]:
        menus = self._menus.get(chat_id) or {}
        if no is None:
            return menus.get(max(menus, default=0)) or None
        return menus.get(no)

    # ---------------------------------------------------------- .cb [N] [M]

    async def handle_cb(self, event: Any) -> None:
        parts = event.text.split()
        nums: List[int] = []
        for p in parts[1:3]:
            try:
                nums.append(int(p))
            except ValueError:
                break
        idx = nums[0] if nums else None
        no = nums[1] if len(nums) > 1 else None

        rec = self._find(event.chat_id, no)
        if rec is None:
            await event.reply("❌ <b>Нет активного меню кнопок</b>")
            return
        if idx is None:
            await event.reply(rec.html or "❌ <b>Меню пусто</b>")
            return
        if not 1 <= idx <= len(rec.tokens):
            await event.reply(
                f"❌ <b>Кнопка #{idx} не найдена</b> в меню #{rec.no} (всего {len(rec.tokens)})"
            )
            return
        if not self.h.permissions.check(event.sender_id, 1):
            return
        ok = await self.h._on_callback(
            rec.tokens[idx - 1], event.sender_id, event.chat_id, rec.message_id, None
        )
        if not ok:
            await event.reply("⏰ <b>Кнопка устарела</b> — вызови команду модуля заново")

    # ---------------------------------------------------------- .it N [M] текст

    async def handle_it(self, event: Any) -> None:
        toks = event.text.split(maxsplit=3)
        if len(toks) < 3:
            await event.reply(
                f"Использование: <code>{self.h.prefix}it N текст</code> или "
                f"<code>{self.h.prefix}it N M текст</code> (меню #M)"
            )
            return
        try:
            idx = int(toks[1])
        except ValueError:
            await event.reply("❌ <b>N должно быть числом</b>")
            return
        no: Optional[int] = None
        if len(toks) == 4 and toks[2].isdigit():
            no, text = int(toks[2]), toks[3]
        else:
            text = " ".join(toks[2:])
        rec = self._find(event.chat_id, no)
        if rec is None or not 1 <= idx <= len(rec.inputs):
            await event.reply("❌ <b>Кнопка ввода не найдена</b> (сначала открой форму)")
            return
        if not self.h.permissions.check(event.sender_id, 1):
            return
        token = rec.inputs[idx - 1]
        entry = self._inputs.get(token)
        if entry is None:
            await event.reply("⏰ <b>Кнопка ввода устарела</b>")
            return
        fn, args = entry
        call = CallbackQueryEvent(
            data=token,
            sender_id=event.sender_id,
            chat_id=event.chat_id,
            message_id=rec.message_id,
            transport=self.h.transport,
        )
        try:
            await fn(call, text, *args)
        except Exception as e:  # noqa: BLE001
            await event.reply(f"<b>Error:</b> <code>{str(e)[:100]}</code>")

    # ---------------------------------------------------------- .cbf

    async def handle_cbf(self, event: Any) -> None:
        if not self.h.permissions.check(event.sender_id, 1):
            return
        new = not self.show_menus
        self.h.config["bridge_menus"] = new
        self.h.save_config()
        state = "подсказки меню включены" if new else "подсказки меню скрыты (кнопки работают вслепую, .iq доступен)"
        await event.reply(f"🎛 <b>{state}</b>")

    # ---------------------------------------------------------- .iqs / .iq

    async def handle_iqs(self, event: Any) -> None:
        parts = event.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await event.reply(
                f"Использование: <code>{self.h.prefix}iqs имя_хендлера запрос</code>"
            )
            return
        query = parts[1].strip()
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:8]
        await self.h.db.set("iq", digest, query)
        # копия запроса улетает в «избранное» (чат с собой), а не в общий чат
        await self.h.transport.send(
            self.h.transport.me_id, f"🔐 сохранённый inline-запрос <code>{digest}</code>\n{query}"
        )
        await event.reply(
            f"🔐 Запрос сохранён в избранное. Запуск: <code>{self.h.prefix}iq {digest}</code>"
        )

    async def handle_iq(self, event: Any) -> None:
        parts = event.text.split(maxsplit=1)
        arg = parts[1].strip() if len(parts) > 1 else ""
        if not arg:
            await event.reply(
                f"Использование: <code>{self.h.prefix}iq имя_хендлера запрос</code> "
                f"или <code>{self.h.prefix}iq хэш</code>"
            )
            return
        source = ""
        if _HASH_RE.match(arg.split()[0]) and len(arg.split()) == 1:
            saved = await self.h.db.get("iq", arg)
            if saved is not None:
                query, source = saved, " (из избранного 🔐)"
            else:
                await event.reply("❌ <b>Хэш не найден</b> — сохрани запрос заново (.iqs)")
                return
        else:
            query = arg

        answers = getattr(self.h.transport, "inline_answers", [])
        before = len(answers)
        handled = await self.h._on_inline(query, event.sender_id, None)
        if not handled or len(answers) == before:
            name = html.escape(query.split()[0])
            await event.reply(f"❌ Инлайн-хендлер «{name}» не найден")
            return
        name, titles = answers[-1]
        lines = [f"<b>🔎 {html.escape(str(name))}</b>{source} — результатов: {len(titles)}"]
        lines += [f"{i}. {html.escape(str(t))}" for i, t in enumerate(titles, 1)]
        await event.reply("\n".join(lines))
