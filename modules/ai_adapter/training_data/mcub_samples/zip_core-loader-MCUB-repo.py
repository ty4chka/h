# requires: aiohttp
# author: @Hairpin00
# version: 1.0.2
# description: load new kernel
# banner_url: https://x0.at/WelF.mp4

import ast
import os
import sys
from pathlib import Path

import aiohttp
from telethon import events
from telethon.tl.types import DocumentAttributeFilename

from utils import restart_kernel, get_args, answer
from utils.strings import Strings


def register(kernel):

    lang = Strings(kernel, {
        'ru': {
            'usage': 'Использование: {prefix}core_load <имя> <источник> [--force]\n'
                     '  имя: название ядра (буквы, цифры, подчёркивание, дефис)\n'
                     '  источник: локальный путь или URL (http/https)\n'
                     '  --force: перезаписать существующий файл ядра без подтверждения\n\n'
                     'Или ответьте на файл (.py) командой, указав имя ядра (необязательно).',
            'invalid_name': 'Недопустимое имя ядра. Используйте только буквы, цифры, подчёркивание и дефис.',
            'exists': 'Ядро <b>{name}</b> уже существует. Используйте --force для перезаписи.',
            'download_failed': 'Не удалось загрузить: HTTP {status}',
            'read_error': 'Ошибка чтения источника: {error}',
            'empty_content': 'Пустое содержимое',
            'no_kernel_class': 'Файл не содержит класса с именем <b>Kernel</b>',
            'syntax_error': 'Синтаксическая ошибка: {error}',
            'save_failed': 'Не удалось сохранить ядро: {error}',
            'set_default_failed': 'Не удалось установить ядро по умолчанию: {error}',
            'installed': 'Ядро <b>{name}</b> установлено. Перезапуск с --core {name}...',
            'no_reply_file': 'Ответьте на сообщение с файлом .py или укажите источник.',
            'download_file_error': 'Ошибка загрузки файла: {error}',
            'no_filename': 'Не удалось определить имя файла. Укажите имя ядра в аргументах.',
        },
        'en': {
            'usage': 'Usage: {prefix}core_load <name> <source> [--force]\n'
                     '  name: kernel name (letters, digits, underscore, dash)\n'
                     '  source: local file path or URL (http/https)\n'
                     '  --force: overwrite existing kernel file without confirmation\n\n'
                     'Or reply to a .py file with the command, optionally specifying the kernel name.',
            'invalid_name': 'Invalid kernel name. Use only letters, digits, underscore and dash.',
            'exists': 'Kernel <b>{name}</b> already exists. Use --force to overwrite.',
            'download_failed': 'Failed to download: HTTP {status}',
            'read_error': 'Error reading source: {error}',
            'empty_content': 'Empty content',
            'no_kernel_class': 'The file does not contain a class named <b>Kernel</b>',
            'syntax_error': 'Syntax error: {error}',
            'save_failed': 'Failed to save kernel: {error}',
            'set_default_failed': 'Failed to set default kernel: {error}',
            'installed': 'Kernel <b>{name}</b> installed. Restarting with --core {name}...',
            'no_reply_file': 'Reply to a .py file or provide a source.',
            'download_file_error': 'Error downloading file: {error}',
            'no_filename': 'Could not determine filename. Specify kernel name as an argument.',
        },
    })

    @kernel.register.command("core_load")
    async def core_load(event):
        """[reply to file/URL] [--force] load new kernel"""
        args = get_args(event)
        reply = await event.get_reply_message()

        if reply and reply.document:
            filename = None
            for attr in reply.document.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break

            if args and args[0] and not args[0].startswith('--'):
                name = args[0].strip()
                args = args[1:]
            else:
                if filename:
                    name = Path(filename).stem
                else:
                    await answer(event, lang['no_filename'], as_html=True)
                    return

            force = "--force" in args

            if not name or not all(c.isalnum() or c in "_-" for c in name):
                await answer(event, lang['invalid_name'], as_html=True)
                return

            try:
                content_bytes = await reply.download_media(file=bytes)
                content = content_bytes.decode('utf-8')
            except Exception as e:
                await answer(event, lang('download_file_error', error=str(e)), as_html=True)
                return

            await _install_kernel(kernel, event, name, content, force, lang)

        else:
            if len(args) < 2:
                await answer(event, lang('usage', prefix=kernel.custom_prefix), as_html=True)
                return

            name = args[0].strip()
            source = args[1].strip()
            force = "--force" in args

            if not name or not all(c.isalnum() or c in "_-" for c in name):
                await answer(event, lang['invalid_name'], as_html=True)
                return

            kernel_dir = Path("core/kernel")
            kernel_dir.mkdir(parents=True, exist_ok=True)
            target_path = kernel_dir / f"{name}.py"

            if target_path.exists() and not force:
                await answer(event, lang('exists', name=name), as_html=True)
                return

            content = None
            try:
                if source.startswith(("http://", "https://")):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(source) as resp:
                            if resp.status != 200:
                                await answer(event, lang('download_failed', status=resp.status), as_html=True)
                                return
                            content = await resp.text()
                else:
                    with open(source, "r", encoding="utf-8") as f:
                        content = f.read()
            except Exception as e:
                await answer(event, lang('read_error', error=str(e)), as_html=True)
                return

            if not content:
                await answer(event, lang['empty_content'], as_html=True)
                return

            await _install_kernel(kernel, event, name, content, force, lang)


async def _install_kernel(kernel, event, name, content, force, lang):
    kernel_dir = Path("core/kernel")
    kernel_dir.mkdir(parents=True, exist_ok=True)
    target_path = kernel_dir / f"{name}.py"

    if target_path.exists() and not force:
        await answer(event, lang('exists', name=name), as_html=True)
        return

    try:
        tree = ast.parse(content)
        has_kernel_class = any(
            isinstance(node, ast.ClassDef) and node.name == "Kernel"
            for node in ast.walk(tree)
        )
        if not has_kernel_class:
            await answer(event, lang['no_kernel_class'], as_html=True)
            return
    except SyntaxError as e:
        await answer(event, lang('syntax_error', error=str(e)), as_html=True)
        return

    try:
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        await answer(event, lang('save_failed', error=str(e)), as_html=True)
        return

    default_core_path = Path("core/.default_core")
    try:
        with open(default_core_path, "w") as f:
            f.write(name)
    except Exception as e:

        await answer(event, lang('set_default_failed', error=str(e)), as_html=True)

    await answer(event, lang('installed', name=name), as_html=True)

    new_argv = []
    skip_next = False
    for i, arg in enumerate(sys.argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--core":
            skip_next = True
            continue
        new_argv.append(arg)

    new_argv.extend(["--core", name])

    sys.argv = new_argv
    await restart_kernel(kernel, event.chat_id, event.id)
