# github: https://github.com/hairpin01/repo-MCUB-fork/liber/
# Channel: https://t.me/LinuxGram2
# -------------------- Meta data ---------------------------
# requires: aiohttp
# author: @Hairpin00
# version: 1.4.0
# description: ru: Получает мудрые цитаты из API / en: Gets wise quotes from API
# ----------------------- End ------------------------------
import aiohttp
import random

def register(kernel):

    language = kernel.config.get('language', 'ru')

    strings = {
        'ru': {
            'searching': '<tg-emoji emoji-id="5116468787377341336">💬</tg-emoji> Ищу мудрые слова...',
            'api_error': '<tg-emoji emoji-id="5382224089295365367">🫡</tg-emoji> Ошибка при получении цитаты',
            'fetch_error': '<tg-emoji emoji-id="5382224089295365367">🫡</tg-emoji> Не удалось получить цитату. Проверьте логи.',
            'network_error': '<tg-emoji emoji-id="5382224089295365367">🫡</tg-emoji> Ошибка сети'
        },
        'en': {
            'searching': '<tg-emoji emoji-id="5116468787377341336">💬</tg-emoji> Searching for wise words...',
            'api_error': '<tg-emoji emoji-id="5382224089295365367">🫡</tg-emoji> Error getting quote',
            'fetch_error': '<tg-emoji emoji-id="5382224089295365367">🫡</tg-emoji> Failed to get quote. Check logs.',
            'network_error': '<tg-emoji emoji-id="5382224089295365367">🫡</tg-emoji> Network error'
        }
    }

    lang_strings = strings.get(language, strings['ru'])

    async def fetch_quote():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://zenquotes.io/api/random') as response:
                    if response.status == 200:
                        data = await response.json()
                        return f"<tg-emoji emoji-id='5465143921912846619'>💭</tg-emoji> {data[0]['q']}\n— {data[0]['a']}"
                    return lang_strings['api_error']
        except Exception as e:
            return f"{lang_strings['network_error']}: {str(e)}"

    @kernel.register.command('zquote')
    # Отправляет случайную мудрую цитату
    async def quote_handler(event):
        try:
            msg = await event.edit(lang_strings['searching'], parse_mode='html')
            quote = await fetch_quote()

            await msg.edit(quote, parse_mode='html')

        except Exception as e:
            await kernel.handle_error(e, source="quote_handler", event=event)
            await event.edit(
                f"<b>{lang_strings['fetch_error']}</b>",
                parse_mode='html'
            )
