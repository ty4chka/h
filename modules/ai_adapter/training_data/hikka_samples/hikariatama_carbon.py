# SOURCE: https://raw.githubusercontent.com/hikariatama/ftg/master/carbon.py
# DATE: 2026-04-13T20:47:04.495203

#             █ █ ▀ █▄▀ ▄▀█ █▀█ ▀
#             █▀█ █ █ █ █▀█ █▀▄ █
#              © Copyright 2022
#           https://t.me/hikariatama
#
# 🔒      Licensed under the GNU AGPLv3
# 🌐 https://www.gnu.org/licenses/agpl-3.0.html

# meta pic: https://img.icons8.com/stickers/500/000000/code.png
# meta banner: https://mods.hikariatama.ru/badges/carbon.jpg
# meta developer: @hikarimods
# scope: hikka_only
# scope: hikka_min 1.2.10
# requires: urllib requests

import io

import requests
from telethon.tl.types import Message

from .. import loader, utils


@loader.tds
class CarbonMod(loader.Module):
    """Create beautiful code images"""

    strings = {
        "name": "Carbon",
        "args": (
            "<emoji document_id=5312526098750252863>🚫</emoji> <b>No args specified</b>"
        ),
        "loading": (
            "<emoji document_id=5213452215527677338>⏳</emoji> <b>Loading...</b>"
        ),
    }

    strings_ru = {
        "args": (
            "<emoji document_id=5312526098750252863>🚫</emoji> <b>Не указаны"
            " аргументы</b>"
        ),
        "loading": (
            "<emoji document_id=5213452215527677338>⏳</emoji> <b>Обработка...</b>"
        ),
        "_cls_doc": "Создает симпатичные фотки кода",
        "_cmd_doc_carbon": "<код> - Сделать красивую фотку кода",
    }

    strings_de = {
        "args": (
            "<emoji document_id=5312526098750252863>🚫</emoji> <b>Keine Argumente"
            " angegeben</b>"
        ),
        "loading": "<emoji document_id=5213452215527677338>⏳</emoji> <b>Laden...</b>",
        "_cls_doc": "Erstellt schöne Code-Bilder",
        "_cmd_doc_carbon": "<code> - Erstelle ein schönes Code-Bild",
    }

    strings_hi = {
        "args": (
            "<emoji document_id=5312526098750252863>🚫</emoji> <b>कोई आर्ग्यूमेंट नहीं"
            " दिया गया</b>"
        ),
        "loading": (
            "<emoji document_id=5213452215527677338>⏳</emoji> <b>लोड हो रहा है...</b>"
        ),
        "_cls_doc": "सुंदर कोड छवियां बनाएं",
        "_cmd_doc_carbon": "<कोड> - सुंदर कोड छवि बनाएं",
    }

    strings_uz = {
        "args": (
            "<emoji document_id=5312526098750252863>🚫</emoji> <b>Hech qanday"
            " argumentlar ko'rsatilmadi</b>"
        ),
        "loading": (
            "<emoji document_id=5213452215527677338>⏳</emoji> <b>Yuklanmoqda...</b>"
        ),
        "_cls_doc": "G'ayratli kod rasmlarini yaratish",
        "_cmd_doc_carbon": "<kod> - G'ayratli kod rasmini yaratish",
    }

    strings_tr = {
        "args": (
            "<emoji document_id=5312526098750252863>🚫</emoji> <b>Argümanlar"
            " belirtilmedi</b>"
        ),
        "loading": (
            "<emoji document_id=5213452215527677338>⏳</emoji> <b>Yükleniyor...</b>"
        ),
        "_cls_doc": "Güzel kod resimleri oluşturur",
        "_cmd_doc_carbon": "<kod> - Güzel kod resmi oluşturur",
    }

    async def carboncmd(self, message: Message):
        """<code> - Create beautiful code image"""
        args = utils.get_args_raw(message)

        try:
            code_from_message = (
                await self._client.download_file(message.media, bytes)
            ).decode("utf-8")
        except Exception:
            code_from_message = ""

        try:
            reply = await message.get_reply_message()
            code_from_reply = (
                await self._client.download_file(reply.media, bytes)
            ).decode("utf-8")
        except Exception:
            code_from_reply = ""

        args = args or code_from_message or code_from_reply

        message = await utils.answer(message, self.strings("loading"))

        doc = io.BytesIO(
            (
                await utils.run_sync(
                    requests.post,
                    "https://carbonara-42.herokuapp.com/api/cook",
                    json={"code": args},
                )
            ).content
        )
        doc.name = "carbonized.jpg"

        await self._client.send_message(
            utils.get_chat_id(message),
            file=doc,
            force_document=(len(args.splitlines()) > 50),
            reply_to=getattr(message, "reply_to_msg_id", None),
        )
        await message.delete()
