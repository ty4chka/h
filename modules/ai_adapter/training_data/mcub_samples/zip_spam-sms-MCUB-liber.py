# requires:
# author:
# version: 1.0.0
# description: Простой модуль для спама

import asyncio

def register(kernel):
    # Локализованные строки
    strings = {
        'en': {
            'name': 'Spammer',
            'description': 'Simple spam module',
            'spamming': '🚀 Spamming...',
            'done': '✅ Done! Sent {} messages',
            'usage': 'Usage: .spam <count> <text>',
            'max_limit': '❌ Max limit is 100 messages',
            'no_text': '❌ Please provide text',
            'invalid_count': '❌ Invalid count',
        },
        'ru': {
            'name': 'Спаммер',
            'description': 'Простой модуль для спама',
            'spamming': '🚀 Спамлю...',
            'done': '✅ Готово! Отправлено {} сообщений',
            'usage': 'Использование: .spam <кол-во> <текст>',
            'max_limit': '❌ Максимальный лимит - 100 сообщений',
            'no_text': '❌ Пожалуйста, укажите текст',
            'invalid_count': '❌ Неверное количество',
        }
    }

    # Получаем текущий язык
    language = kernel.config.get('language', 'en')
    s = strings.get(language, strings['en'])

    @kernel.register.command('spam')
    # spam <count> <sms>
    async def spam_handler(event):
        """Обработчик команды спама"""
        args = event.text.split(maxsplit=2)

        if len(args) < 3:
            await event.edit(s['usage'])
            return

        try:
            count = int(args[1])
            text = args[2]

            if count <= 0:
                await event.edit(s['invalid_count'])
                return

            if count > 100:
                await event.edit(s['max_limit'])
                return

            if not text.strip():
                await event.edit(s['no_text'])
                return

            await event.edit(s['spamming'])

            # Отправляем сообщения
            for i in range(count):
                await event.respond(text)
                await asyncio.sleep(0.1)  # Небольшая задержка

            await event.delete()

            # Отправляем подтверждение
            sms = await event.respond(s['done'].format(count))
            await sms.delete()

        except ValueError:
            await event.edit(s['invalid_count'])
        except Exception as e:
            await kernel.handle_error(e, source="spam_handler", event=event)
            await event.edit(f"❌ Error: {str(e)}")
