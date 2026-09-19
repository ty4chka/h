# meta name: ASCIIArt
# meta developer: @bsod4ik_plugins
# meta version: 1.2.2
# scope: hikka_only
# requires: pillow

import asyncio
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from telethon.tl.types import Message

from .. import loader, utils


@loader.tds
class ASCIIArtMod(loader.Module):
    """Преобразует изображения в ASCII-арт с превью в виде картинки."""

    strings = {
        "name": "ASCIIArt",
        "no_reply": "<a href=\"tg://emoji?id=5274099962655816924\">❗️</a> <b>Ответь на изображение, GIF, видео, стикер или документ с изображением.</b>",
        "downloading": "<a href=\"tg://emoji?id=6039454987250044861\">🔊</a> <b>Загружаю медиа...</b>",
        "processing": "<a href=\"tg://emoji?id=5341715473882955310\">⚙️</a> <b>Конвертирую изображение в ASCII-арт...</b>",
        "processing_video": "<a href=\"tg://emoji?id=5341715473882955310\">⚙️</a> <b>Извлекаю кадры и собираю ASCII-анимацию...</b>",
        "bad_media": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Не удалось обработать это медиа как изображение или видео.</b>",
        "animated_not_supported": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Анимированные стикеры не поддерживаются.</b>",
        "ffmpeg_missing": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>На сервере не найден</b> <code>ffmpeg</code><b>, поэтому видео ASCII недоступно.</b>",
        "video_decode_error": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Не удалось извлечь кадры из видео или GIF.</b>",
        "video_empty": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Не удалось получить ни одного кадра из видео.</b>",
        "quality_set": "<a href=\"tg://emoji?id=5206607081334906820\">✔️</a> <b>Качество ASCII обновлено:</b> <code>{}</code>",
        "quality_current": "<a href=\"tg://emoji?id=5427168083074628963\">💎</a> <b>Текущее качество:</b> <code>{}</code>\n<i>Это ширина ASCII в символах.</i>",
        "quality_invalid": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Укажи целое число от</b> <code>{}</code> <b>до</b> <code>{}</code><b>.</b>",
        "done_caption": "<a href=\"tg://emoji?id=5461151367559141950\">🎉</a> <b>ASCII-арт готов</b>\n<b>Ширина:</b> <code>{width}</code>\n<b>Размер:</b> <code>{src_w}x{src_h}</code>\n<b>Размер ASCII:</b> <code>{width}x{lines}</code>\n<b>Тема превью:</b> <code>{theme}</code>",
        "done_video_caption": "<a href=\"tg://emoji?id=5461151367559141950\">🎉</a> <b>ASCII-анимация готова</b>\n<b>Ширина:</b> <code>{width}</code>\n<b>Кадров:</b> <code>{frames}</code>\n<b>FPS:</b> <code>{fps}</code>\n<b>Исходный размер:</b> <code>{src_w}x{src_h}</code>\n<b>Тема превью:</b> <code>{theme}</code>",
        "too_large_text": "<a href=\"tg://emoji?id=5395695537687123235\">🚨</a> <b>ASCII слишком длинный для подписи, отправляю TXT-файлом.</b>",
        "render_error": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Не удалось отрисовать ASCII-превью.</b>",
        "theme_set": "<a href=\"tg://emoji?id=5206607081334906820\">✔️</a> <b>Тема превью обновлена:</b> <code>{}</code>",
        "theme_current": "<a href=\"tg://emoji?id=5438496463044752972\">⭐️</a> <b>Текущая тема превью:</b> <code>{}</code>\n<i>Доступно: light, dark, toggle.</i>",
        "theme_invalid": "<a href=\"tg://emoji?id=5210952531676504517\">❌</a> <b>Укажи тему:</b> <code>light</code><b>,</b> <code>dark</code> <b>или</b> <code>toggle</code><b>.</b>",
        "description_ascii": "Преобразовать изображение, стикер, GIF или видео из реплая в ASCII и отправить превью.",
        "description_quality": "Показать или изменить качество ASCII-арта в символах по ширине.",
        "description_theme": "Показать или переключить тему превью ASCII между светлой и тёмной.",
    }

    strings_ru = strings

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "default_width",
                90,
                lambda: "Ширина ASCII в символах по умолчанию.",
                validator=loader.validators.Integer(minimum=50, maximum=4096),
            ),
            loader.ConfigValue(
                "invert",
                False,
                lambda: "Инвертировать палитру ASCII.",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "send_txt",
                True,
                lambda: "Отправлять TXT-файл с ASCII вместе с превью.",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "preview_theme",
                "light",
                lambda: "Тема превью ASCII: light или dark.",
                validator=loader.validators.Choice(["light", "dark"]),
            ),
            loader.ConfigValue(
                "video_fps",
                24,
                lambda: "FPS для ASCII-анимации из видео или GIF.",
                validator=loader.validators.Integer(minimum=1, maximum=24),
            ),
            loader.ConfigValue(
                "max_video_frames",
                120,
                lambda: "Максимум кадров для ASCII-анимации.",
                validator=loader.validators.Integer(minimum=1, maximum=240),
            ),
        )
        self._gradient = "@%#*+=-:. "
        self._gradient_invert = " .:-=+*#%@"

    async def client_ready(self, client, db):
        self.client = client
        self.db = db

    def _get_default_width(self):
        width = int(self.config["default_width"])
        if width < 50:
            return 50
        if width > 4096:
            return 4096
        return width

    def _normalize_theme_arg(self, raw: str):
        if not raw:
            return None
        raw = raw.strip().lower()
        mapping = {
            "light": "light",
            "white": "light",
            "l": "light",
            "светлая": "light",
            "светлый": "light",
            "белая": "light",
            "белый": "light",
            "dark": "dark",
            "black": "dark",
            "d": "dark",
            "темная": "dark",
            "тёмная": "dark",
            "темный": "dark",
            "тёмный": "dark",
            "черная": "dark",
            "чёрная": "dark",
            "черный": "dark",
            "чёрный": "dark",
            "toggle": "toggle",
            "switch": "toggle",
            "swap": "toggle",
            "переключить": "toggle",
            "сменить": "toggle",
            "инверт": "toggle",
        }
        return mapping.get(raw)

    def _get_preview_theme(self):
        theme = str(self.config["preview_theme"] or "light").lower()
        if theme not in {"light", "dark"}:
            theme = "light"
        return theme

    def _get_preview_colors(self):
        if self._get_preview_theme() == "dark":
            return (18, 18, 18), (255, 255, 255)
        return (255, 255, 255), (0, 0, 0)

    def _parse_width_arg(self, raw: str):
        if not raw:
            return None, None
        raw = raw.strip()
        if not raw:
            return None, None
        if not raw.isdigit():
            return False, (50, 4096)
        width = int(raw)
        if width < 50 or width > 4096:
            return False, (50, 4096)
        return width, None

    async def _extract_media_bytes(self, reply: Message):
        if not reply or not reply.media:
            return None, None, "no_reply"

        sticker = getattr(reply, "sticker", None)
        sticker_mime = (getattr(sticker, "mime_type", None) or "").lower()
        if sticker and sticker_mime == "application/x-tgsticker":
            return None, None, "animated_not_supported"

        media_type = "image"
        file = getattr(reply, "file", None)
        if getattr(reply, "video", None) or getattr(reply, "gif", None):
            media_type = "video"
        elif file:
            mime = (getattr(file, "mime_type", None) or "").lower()
            if mime.startswith("video/"):
                media_type = "video"
            elif mime and not mime.startswith("image/"):
                is_static_sticker = bool(sticker) and mime in {
                    "image/webp",
                    "image/png",
                    "application/webp",
                }
                if not is_static_sticker and not getattr(reply, "photo", None):
                    return None, None, "bad_media"

        data = await self.client.download_media(reply, bytes)
        if not data:
            return None, None, "bad_media"
        return data, media_type, None

    async def _extract_video_frames(self, data: bytes):
        fps = max(1, min(24, int(self.config["video_fps"])))
        max_frames = max(1, int(self.config["max_video_frames"]))
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-v",
                "error",
                "-i",
                "pipe:0",
                "-vf",
                f"fps={fps}",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return None, "ffmpeg_missing"

        stdout, stderr = await process.communicate(data)
        if process.returncode != 0 or not stdout:
            return None, "video_decode_error"

        frames = []
        signature = b"\x89PNG\r\n\x1a\n"
        offset = 0
        output_len = len(stdout)

        while len(frames) < max_frames:
            start = stdout.find(signature, offset)
            if start == -1:
                break
            next_start = stdout.find(signature, start + len(signature))
            chunk = stdout[start:] if next_start == -1 else stdout[start:next_start]
            offset = output_len if next_start == -1 else next_start
            try:
                frame = Image.open(BytesIO(chunk))
                frame.load()
                frames.append(ImageOps.exif_transpose(frame).convert("RGB"))
            except (UnidentifiedImageError, OSError, ValueError):
                continue

        if not frames:
            if stderr:
                return None, "video_decode_error"
            return None, "video_empty"

        return {"frames": frames, "fps": fps}, None

    def _open_image(self, data: bytes):
        try:
            image = Image.open(BytesIO(data))
            image = ImageOps.exif_transpose(image)
            if getattr(image, "is_animated", False):
                try:
                    image.seek(0)
                except Exception:
                    pass
            return image.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError):
            return None

    def _image_to_ascii(self, image: Image.Image, width: int):
        gradient = self._gradient_invert if self.config["invert"] else self._gradient
        gray = image.convert("L")
        src_w, src_h = gray.size
        if src_w <= 0 or src_h <= 0:
            raise ValueError("Invalid image size")

        crop_size = min(src_w, src_h)
        left = max(0, (src_w - crop_size) // 2)
        top = max(0, (src_h - crop_size) // 2)
        gray = gray.crop((left, top, left + crop_size, top + crop_size))

        resized = gray.resize((width, width))
        pixels = list(resized.getdata())

        lines = []
        scale = len(gradient) - 1
        for y in range(width):
            row = pixels[y * width : (y + 1) * width]
            line = "".join(gradient[p * scale // 255] for p in row)
            lines.append(line)

        ascii_text = "\n".join(lines)
        return ascii_text, src_w, src_h, len(lines)

    def _render_ascii_preview(self, ascii_text: str):
        if not ascii_text:
            return None

        font = ImageFont.load_default()
        lines = ascii_text.splitlines() or [""]
        max_line = max((len(line) for line in lines), default=1)
        line_count = max(len(lines), 1)

        dummy = Image.new("RGB", (32, 32), "white")
        draw = ImageDraw.Draw(dummy)
        sample_chars = "@MWA#.: "
        bboxes = [draw.textbbox((0, 0), char, font=font) for char in sample_chars]
        char_w = max(1, max(bbox[2] - bbox[0] for bbox in bboxes))
        char_h = max(1, max(bbox[3] - bbox[1] for bbox in bboxes))
        cell_w = max(1, char_w)
        cell_h = max(1, char_h + 1)
        padding = 12

        width = max(64, padding * 2 + cell_w * max_line)
        height = max(64, padding * 2 + cell_h * line_count)

        bg_color, text_color = self._get_preview_colors()
        canvas = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(canvas)

        for row_index, line in enumerate(lines):
            y = padding + row_index * cell_h
            for col_index, char in enumerate(line):
                x = padding + col_index * cell_w
                bbox = draw.textbbox((0, 0), char, font=font)
                glyph_w = max(1, bbox[2] - bbox[0])
                glyph_h = max(1, bbox[3] - bbox[1])
                glyph_x = x - bbox[0] + max(0, (cell_w - glyph_w) // 2)
                glyph_y = y - bbox[1] + max(0, (cell_h - glyph_h) // 2)
                draw.text((glyph_x, glyph_y), char, font=font, fill=text_color)

        output = BytesIO()
        output.name = "ascii_preview.png"
        canvas.save(output, format="PNG", optimize=True)
        output.seek(0)
        return output

    def _render_ascii_gif(self, ascii_frames, fps: int):
        if not ascii_frames:
            return None

        rendered_frames = []
        for ascii_text in ascii_frames:
            preview = self._render_ascii_preview(ascii_text)
            if not preview:
                continue
            try:
                frame = Image.open(preview)
                frame.load()
                rendered_frames.append(frame.convert("P", palette=Image.ADAPTIVE))
            except (UnidentifiedImageError, OSError, ValueError):
                continue

        if not rendered_frames:
            return None

        output = BytesIO()
        output.name = "ascii_animation.gif"
        duration = max(1, int(1000 / max(1, fps)))
        rendered_frames[0].save(
            output,
            format="GIF",
            save_all=True,
            append_images=rendered_frames[1:],
            duration=duration,
            loop=0,
            optimize=False,
            disposal=2,
        )
        output.seek(0)
        return output

    async def _video_to_ascii_frames(self, data: bytes, width: int):
        extracted, err_key = await self._extract_video_frames(data)
        if err_key:
            return None, err_key

        frames = extracted["frames"]
        ascii_frames = []
        src_w = 0
        src_h = 0

        for frame in frames:
            ascii_text, frame_w, frame_h, _ = self._image_to_ascii(frame, width)
            ascii_frames.append(ascii_text)
            if not src_w or not src_h:
                src_w, src_h = frame_w, frame_h

        if not ascii_frames:
            return None, "video_empty"

        return {
            "ascii_frames": ascii_frames,
            "fps": extracted["fps"],
            "src_w": src_w,
            "src_h": src_h,
            "frame_count": len(ascii_frames),
        }, None

    def _build_txt(self, ascii_text: str):
        data = BytesIO(ascii_text.encode("utf-8"))
        data.name = "ascii_art.txt"
        data.seek(0)
        return data

    @loader.command(
        ru_doc="Преобразовать изображение, стикер, GIF или видео из реплая в ASCII-арт. Аргумент: ширина ASCII в символах.",
        en_doc="Convert replied image, sticker, GIF or video to ASCII art. Argument: ASCII width in characters.",
    )
    async def ascii(self, message: Message):
        """Преобразовать изображение, стикер, GIF или видео из реплая в ASCII и отправить превью."""
        args = utils.get_args_raw(message)
        width_arg, error = self._parse_width_arg(args)
        if width_arg is False:
            await utils.answer(message, self.strings["quality_invalid"].format(50, 4096))
            return

        width = width_arg or self._get_default_width()
        reply = await message.get_reply_message()
        if not reply:
            await utils.answer(message, self.strings["no_reply"])
            return

        await utils.answer(message, self.strings["downloading"])
        data, media_type, err_key = await self._extract_media_bytes(reply)
        if err_key:
            await utils.answer(message, self.strings[err_key])
            return

        if media_type == "video":
            await utils.answer(message, self.strings["processing_video"])
            try:
                result, err_key = await self._video_to_ascii_frames(data, width)
            except Exception:
                result, err_key = None, "render_error"

            if err_key:
                await utils.answer(message, self.strings[err_key])
                return

            preview = self._render_ascii_gif(result["ascii_frames"], result["fps"])
            if not preview:
                await utils.answer(message, self.strings["render_error"])
                return

            caption = self.strings["done_video_caption"].format(
                width=width,
                frames=result["frame_count"],
                fps=result["fps"],
                src_w=result["src_w"],
                src_h=result["src_h"],
                theme=self._get_preview_theme(),
            )

            await self.client.send_file(
                message.peer_id,
                preview,
                caption=caption,
                reply_to=utils.get_topic(message) or reply.id,
                force_document=True,
            )
            await message.delete()
            return

        image = self._open_image(data)
        if not image:
            await utils.answer(message, self.strings["bad_media"])
            return

        await utils.answer(message, self.strings["processing"])
        try:
            ascii_text, src_w, src_h, line_count = self._image_to_ascii(image, width)
            preview = self._render_ascii_preview(ascii_text)
        except Exception:
            await utils.answer(message, self.strings["render_error"])
            return

        if not preview:
            await utils.answer(message, self.strings["render_error"])
            return

        caption = self.strings["done_caption"].format(
            width=width,
            src_w=src_w,
            src_h=src_h,
            lines=line_count,
            theme=self._get_preview_theme(),
        )

        files = [preview]
        if self.config["send_txt"]:
            files.append(self._build_txt(ascii_text))

        await self.client.send_file(
            message.peer_id,
            files,
            caption=caption,
            reply_to=utils.get_topic(message) or reply.id,
            force_document=True,
        )

        await message.delete()

    @loader.command(
        ru_doc="Показать или изменить качество ASCII-арта. Аргумент: ширина в символах.",
        en_doc="Show or change ASCII art quality. Argument: width in characters.",
    )
    async def asciiq(self, message: Message):
        """Показать или изменить качество ASCII-арта в символах по ширине."""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings["quality_current"].format(self._get_default_width()))
            return

        parsed, error = self._parse_width_arg(args)
        if parsed is False:
            await utils.answer(message, self.strings["quality_invalid"].format(50, 4096))
            return

        self.config["default_width"] = parsed
        await utils.answer(message, self.strings["quality_set"].format(parsed))

    @loader.command(
        ru_doc="Показать или переключить тему превью ASCII. Аргумент: light, dark или toggle.",
        en_doc="Show or switch ASCII preview theme. Argument: light, dark or toggle.",
    )
    async def asciitheme(self, message: Message):
        """Показать или переключить тему превью ASCII между светлой и тёмной."""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings["theme_current"].format(self._get_preview_theme()))
            return

        parsed = self._normalize_theme_arg(args)
        if not parsed:
            await utils.answer(message, self.strings["theme_invalid"])
            return

        if parsed == "toggle":
            parsed = "dark" if self._get_preview_theme() == "light" else "light"

        self.config["preview_theme"] = parsed
        await utils.answer(message, self.strings["theme_set"].format(parsed))