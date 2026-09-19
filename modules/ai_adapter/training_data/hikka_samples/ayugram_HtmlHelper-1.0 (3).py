# meta developer: @C00l9r
# meta name: HtmlHelper
# meta version: 3.0.0
# meta banner: https://yufic.ru/api/hc/?a=HtmlHelper&b=@C00l9r
# requires: requests beautifulsoup4

import io
import os
import zipfile
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from telethon.tl.types import Message

from .. import loader, utils


@loader.tds
class HtmlHelperMod(loader.Module):
    """Получает исходный код веб-страницы (HTML, CSS, JS)."""

    strings = {
        "name": "HtmlHelper",
        "processing": "<emoji document_id=5429411030960711866>💬</emoji> <b>Получаю HTML сайта...</b>",
        "processing_zip": "<emoji document_id=5257969839313526622>📂</emoji> <b>Анализирую и создаю ZIP-архив...</b>",
        "no_url": "<emoji document_id=5260342697075416641>❌</emoji> <b>Укажите URL сайта после команды.</b>\n<code>.html [--zip] https://example.com</code>",
        "fetch_error": "<emoji document_id=5260342697075416641>❌</emoji> <b>Не удалось получить код сайта.</b>\n<b>Ошибка:</b> <code>{}</code>",
        "caption_zip": "<emoji document_id=5258389041006518073>📂</emoji> <b>Исходный код (HTML, CSS, JS) для сайта</b> <code>{}</code>",
        "caption_html": "<emoji document_id=5257965810634202885>📁</emoji> <b>Исходный HTML-код для сайта</b> <code>{}</code>",
    }

    strings_ru = {
        "processing": "<emoji document_id=5429411030960711866>💬</emoji> <b>Получаю HTML сайта...</b>",
        "processing_zip": "<emoji document_id=5257969839313526622>📂</emoji> <b>Анализирую и создаю ZIP-архив...</b>",
        "no_url": "<emoji document_id=5260342697075416641>❌</emoji> <b>Укажите URL сайта после команды.</b>\n<code>.html [--zip] https://example.com</code>",
        "fetch_error": "<emoji document_id=5260342697075416641>❌</emoji> <b>Не удалось получить код сайта.</b>\n<b>Ошибка:</b> <code>{}</code>",
        "caption_zip": "<emoji document_id=5258389041006518073>📂</emoji> <b>Исходный код (HTML, CSS, JS) для сайта</b> <code>{}</code>",
        "caption_html": "<emoji document_id=5257965810634202885>📁</emoji> <b>Исходный HTML-код для сайта</b> <code>{}</code>",
        "_cls_doc": "Получает исходный код веб-страницы (HTML, CSS, JS).",
        "_cmd_doc_html": "[--zip] <ссылка> - Получить исходный код сайта. С флагом --zip - в виде ZIP-архива с CSS/JS."
    }

    @loader.command(ru_doc="[--zip] <ссылка> - Получить исходный код сайта. С флагом --zip - в виде ZIP-архива с CSS/JS.")
    async def html(self, message: Message):
        """[--zip] <url> - Get website source. With --zip flag, sends a ZIP with CSS/JS."""
        args = utils.get_args_raw(message)
        create_zip = "--zip" in args.lower()

        if create_zip:
            url = args.lower().replace("--zip", "").strip()
        else:
            url = args

        if not url:
            await utils.answer(message, self.strings("no_url"))
            return

        if not url.startswith("http"):
            url = "https://" + url

        message = await utils.answer(message, self.strings("processing"))

        try:
            response = await utils.run_sync(requests.get, url, timeout=15)
            response.raise_for_status()
            html_code = response.text
            base_url = response.url
        except requests.exceptions.RequestException as e:
            await utils.answer(message, self.strings("fetch_error").format(e))
            return

        if create_zip:
            await utils.answer(message, self.strings("processing_zip"))
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr("index.html", html_code)
                soup = BeautifulSoup(html_code, "html.parser")

                for link_tag in soup.find_all("link", rel="stylesheet"):
                    href = link_tag.get("href")
                    if not href: continue
                    css_url = urljoin(base_url, href)
                    css_filename = os.path.basename(urlparse(css_url).path) or "style.css"
                    try:
                        css_response = await utils.run_sync(requests.get, css_url, timeout=10)
                        if css_response.ok:
                            zip_file.writestr(f"css/{css_filename}", css_response.text)
                    except requests.exceptions.RequestException:
                        continue

                for script_tag in soup.find_all("script", src=True):
                    src = script_tag.get("src")
                    if not src: continue
                    js_url = urljoin(base_url, src)
                    js_filename = os.path.basename(urlparse(js_url).path) or "script.js"
                    try:
                        js_response = await utils.run_sync(requests.get, js_url, timeout=10)
                        if js_response.ok:
                            zip_file.writestr(f"js/{js_filename}", js_response.text)
                    except requests.exceptions.RequestException:
                        continue
            
            zip_buffer.seek(0)
            zip_buffer.name = "website_source.zip"
            file_to_send = zip_buffer
            caption = self.strings("caption_zip").format(url)
        else:
            file_to_send = io.BytesIO(html_code.encode("utf-8"))
            file_to_send.name = "source.html"
            caption = self.strings("caption_html").format(url)

        await self.client.send_file(
            message.to_id,
            file_to_send,
            caption=caption,
            reply_to=message.reply_to_msg_id,
        )
        if message.out:
            await message.delete()