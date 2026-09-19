# author: @Hairpin00
# version: 1.0.0
# description: скрытая привязка ссылки к превью сообщений
# requires: json

import json
import os
import re
from telethon.tl.types import MessageEntityTextUrl
from telethon import events

CONFIG_FILE = "link_preview_config.json"
ZERO_WIDTH_CHAR = "\u2060"

class LinkPreviewConfig:
    def __init__(self):
        self.enabled = False
        self.link = ""
        self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.enabled = data.get('enabled', False)
                    self.link = data.get('link', "")
            except:
                self.enabled = False
                self.link = ""

    def save_config(self):
        data = {
            'enabled': self.enabled,
            'link': self.link
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

def add_link_preview(text, entities, link):
    if not text or not link:
        return text, entities

    new_text = ZERO_WIDTH_CHAR + text

    new_entities = []

    if entities:
        for entity in entities:
            new_entity = entity
            if hasattr(entity, 'offset'):
                new_entity.offset += 1
            new_entities.append(new_entity)

    link_entity = MessageEntityTextUrl(
        offset=0,
        length=1,
        url=link
    )

    new_entities.append(link_entity)

    return new_text, new_entities

def register(kernel):
    client = kernel.client
    config = LinkPreviewConfig()

    @client.on(events.NewMessage(outgoing=True))
    async def message_handler(event):
        if not config.enabled or not config.link:
            return

        if event.text and (event.text.startswith('.lhe') or event.text.startswith('.setlhe')):
            return

        try:
            text = event.text
            entities = event.message.entities

            new_text, new_entities = add_link_preview(text, entities, config.link)

            if new_text != text:
                await event.edit(new_text, formatting_entities=new_entities, link_preview=True)
        except:
            pass

    @kernel.register.command('lhe')
    # управление скрытой привязкой ссылки (on/off/status)
    async def toggle_handler(event):
        args = event.text.split()
        if len(args) < 2:
            await event.edit('⛈️ Использование: .lhe [on|off|status]')
            return

        cmd = args[1].lower()
        if cmd == 'on':
            config.enabled = True
            await event.edit('✅ **Предпросмотр ссылки включен**')
        elif cmd == 'off':
            config.enabled = False
            await event.edit('⛈️ **Предпросмотр ссылки выключен**')
        elif cmd == 'status':
            status = 'включен ✅' if config.enabled else 'выключен ⛈️'
            link_display = f"`{config.link}`" if config.link else "не установлена"
            await event.edit(f'📊 **Статус:** {status}\n🔗 **Ссылка:** {link_display}')
        else:
            await event.edit('⛈️ Неизвестная команда')

        config.save_config()

    @kernel.register.command('setlhe')
    # установка ссылки для скрытой привязки
    async def setlink_handler(event):
        args = event.text.split(maxsplit=1)
        if len(args) < 2:
            await event.edit('⛈️ Использование: .setlhe ссылка')
            return

        link = args[1].strip()

        if not re.match(r'^https?://', link):
            link = 'https://' + link

        config.link = link
        config.save_config()

        await event.edit(f'✅ **Ссылка установлена:**\n`{link}`')
