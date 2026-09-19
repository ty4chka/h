# meta: name=convert version=1.0.0 author=hydra-team framework=core
from utils.misc import edit_or_reply
import aiohttp
import json
import os
import re
import random
import asyncio
from datetime import datetime

class AIConverterUltimate:
    def __init__(self):
        self.supported_services = {
            "google": {
                "name": "🔮 Google Gemini",
                "url": "https://generativelanguage.googleapis.com/v1beta/models/",
                "key_required": True,
                "models": ["gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"],
                "limits": {"daily": 1000, "per_request": 8000}
            },
            "openrouter": {
                "name": "⚡ OpenRouter", 
                "url": "https://openrouter.ai/api/v1/chat/completions",
                "key_required": True,
                "models": ["google/gemini-2.0-flash-exp:free", "anthropic/claude-3.5-sonnet:beta"],
                "limits": {"daily": 500, "per_request": 16000}
            }
        }
        
        self.api_keys = {}
        self.usage_stats = {}
        self.conversion_history = []
        self.auto_optimize = True
        
        self.conversion_profiles = {
            "basic": {"name": "⚡ Базовая", "description": "Быстрая конвертация"},
            "advanced": {"name": "🔧 Продвинутая", "description": "Полная конвертация"}, 
            "premium": {"name": "💎 Премиум", "description": "Максимальная оптимизация"}
        }
        
        self.load_data()

    def load_data(self):
        try:
            if os.path.exists("ai_keys.json"):
                with open("ai_keys.json", "r", encoding='utf-8') as f:
                    self.api_keys = json.load(f)
            if os.path.exists("ai_stats.json"):
                with open("ai_stats.json", "r", encoding='utf-8') as f:
                    self.usage_stats = json.load(f)
            if os.path.exists("ai_history.json"):
                with open("ai_history.json", "r", encoding='utf-8') as f:
                    self.conversion_history = json.load(f)
        except Exception:
            pass

    def save_data(self):
        try:
            with open("ai_keys.json", "w", encoding='utf-8') as f:
                json.dump(self.api_keys, f, ensure_ascii=False, indent=2)
            with open("ai_stats.json", "w", encoding='utf-8') as f:
                json.dump(self.usage_stats, f, ensure_ascii=False, indent=2)
            with open("ai_history.json", "w", encoding='utf-8') as f:
                json.dump(self.conversion_history[-100:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def update_stats(self, service, tokens_used=0):
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.usage_stats:
            self.usage_stats[today] = {}
        if service not in self.usage_stats[today]:
            self.usage_stats[today][service] = {"requests": 0, "tokens": 0}
        self.usage_stats[today][service]["requests"] += 1
        self.usage_stats[today][service]["tokens"] += tokens_used
        self.save_data()

    def can_make_request(self, service):
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.usage_stats or service not in self.usage_stats[today]:
            return True
        daily_requests = self.usage_stats[today][service]["requests"]
        return daily_requests < self.supported_services[service]["limits"]["daily"]

    def get_smart_prompt(self, source_code, user_request="", profile="advanced"):
        base_prompts = {
            "basic": "КОНВЕРТАЦИЯ HIKKA → HYDRA\n1. ИМПОРТЫ: from .. import loader → from utils.misc import edit_or_reply\n2. КЛАССЫ: Убрать классы\n3. КОМАНДЫ: @loader.command → @command(pattern=\".cmd\")\nВЕРНИ ТОЛЬКО КОД!",
            
            "advanced": "🎯 ПРОДВИНУТАЯ КОНВЕРТАЦИЯ HIKKA → HYDRA\n📋 ТАБЛИЦА КОНВЕРСИИ:\n• from .. import loader → from utils.misc import edit_or_reply\n• @loader.tds → НЕТ ДЕКОРАТОРА\n• class Module() → ТОЛЬКО ФУНКЦИИ\n• @loader.command → @command(pattern=\".cmd\")\n• await utils.answer() → await edit_or_reply()\n• self._db.set() → db.set(\"module\", key, val)\n🚀 ВЕРНИ КОНВЕРТИРОВАННЫЙ КОД!",
            
            "premium": "💎 ПРЕМИУМ КОНВЕРТАЦИЯ HIKKA → HYDRA\n✨ ФИЧИ: Исправление ошибок + Оптимизация\n🔧 ПРАВИЛА:\n• Убрать ВСЕ классы\n• Добавить try/except в команды\n• Оптимизировать импорты\n• Правильная структура modules_help\n🚀 ВЕРНИ ИДЕАЛЬНЫЙ КОД!"
        }
        
        profile_prompt = base_prompts.get(profile, base_prompts["advanced"])
        
        if user_request:
            return f"{profile_prompt}\n🎯 ЗАПРОС: {user_request}\n💻 КОД HIKKA:\n```python\n{source_code}\n```"
        else:
            return f"{profile_prompt}\n💻 КОД HIKKA:\n```python\n{source_code}\n```"

    async def make_ai_request(self, service, source_code, user_request="", profile="advanced"):
        try:
            if service not in self.api_keys:
                return f"❌ API ключ для {self.supported_services[service]['name']} не установлен"

            if not self.can_make_request(service):
                return f"❌ Достигнут дневной лимит для {service}"

            api_key = self.api_keys[service]
            prompt = self.get_smart_prompt(source_code, user_request, profile)
            
            if service == "google":
                models = self.supported_services[service]["models"]
                for model in models:
                    url = f"{self.supported_services[service]['url']}{model}:generateContent?key={api_key}"
                    data = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"maxOutputTokens": 32000, "temperature": 0.1}
                    }
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.post(url, json=data, timeout=120) as response:
                                if response.status == 200:
                                    result = await response.json()
                                    text = result["candidates"][0]["content"]["parts"][0]["text"]
                                    self.update_stats(service, len(text.split()))
                                    return text
                    except Exception:
                        continue
                return "❌ Все модели Google недоступны"

            elif service == "openrouter":
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/hydra-userbot"
                }
                models = self.supported_services[service]["models"]
                for model in models:
                    data = {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 32000,
                        "temperature": 0.1
                    }
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.post(self.supported_services[service]["url"], headers=headers, json=data, timeout=90) as response:
                                if response.status == 200:
                                    result = await response.json()
                                    text = result["choices"][0]["message"]["content"]
                                    self.update_stats(service, result["usage"]["total_tokens"])
                                    return text
                    except Exception:
                        continue
                return "❌ Все модели OpenRouter недоступны"

        except Exception as e:
            return f"❌ Критическая ошибка: {str(e)}"

    def extract_code(self, response):
        try:
            code_blocks = re.findall(r'```python\s*(.*?)\s*```', response, re.DOTALL)
            if code_blocks:
                return code_blocks[0].strip()
            code_blocks = re.findall(r'```\s*(.*?)\s*```', response, re.DOTALL)
            if code_blocks:
                return code_blocks[0].strip()
            return response.strip()
        except Exception:
            return response

    def optimize_code(self, code):
        try:
            lines = code.split('\n')
            optimized = []
            imports_seen = set()
            
            for line in lines:
                line_stripped = line.strip()
                if line_stripped.startswith('import ') or line_stripped.startswith('from '):
                    if line_stripped not in imports_seen:
                        imports_seen.add(line_stripped)
                        optimized.append(line)
                else:
                    optimized.append(line)
            return '\n'.join(optimized)
        except Exception:
            return code

converter = AIConverterUltimate()

async def set_key_handler(event):
    try:
        if not event.out:
            return
        args = event.text.split(maxsplit=2)
        if len(args) < 3:
            await edit_or_reply(event, "❌ Использование: .set_key <сервис> <ключ>")
            return
        service = args[1].lower()
        api_key = args[2]
        if service not in converter.supported_services:
            services_list = "\n".join([f"• {s} - {info['name']}" for s, info in converter.supported_services.items()])
            await edit_or_reply(event, f"❌ Неизвестный сервис!\nДоступно:\n{services_list}")
            return
        converter.api_keys[service] = api_key
        converter.save_data()
        await edit_or_reply(event, f"✅ Ключ для {converter.supported_services[service]['name']} установлен!")
    except Exception as e:
        await edit_or_reply(event, f"❌ Ошибка: {str(e)}")

async def show_keys_handler(event):
    try:
        if not event.out:
            return
        if not converter.api_keys:
            await edit_or_reply(event, "🔑 Ключи не установлены")
            return
        text = "🔑 Установленные ключи:\n"
        for service, key in converter.api_keys.items():
            text += f"• {converter.supported_services[service]['name']}: {key[:12]}...\n"
        await edit_or_reply(event, text)
    except Exception as e:
        await edit_or_reply(event, f"❌ Ошибка: {str(e)}")

async def convert_handler(event):
    try:
        if not event.out:
            return
        reply = await event.get_reply_message()
        if not reply or not reply.media or not (reply.file and reply.file.name.endswith('.py')):
            await edit_or_reply(event, "❌ Ответьте на .py файл!\nИспользование: .convert [сервис] [профиль] [запрос]")
            return

        args = event.text.split(maxsplit=3)
        service = "google"
        profile = "advanced"
        user_request = "Конвертировать код из Hikka в Hydra"
        
        if len(args) > 1:
            service = args[1].lower()
        if len(args) > 2:
            profile = args[2].lower()
        if len(args) > 3:
            user_request = args[3]

        if service not in converter.supported_services:
            await edit_or_reply(event, f"❌ Неизвестный сервис: {service}")
            return
        if profile not in converter.conversion_profiles:
            await edit_or_reply(event, f"❌ Неизвестный профиль: {profile}")
            return
        if service not in converter.api_keys:
            await edit_or_reply(event, f"❌ Установи ключ: .set_key {service} <ключ>")
            return

        await edit_or_reply(event, "📥 Скачиваю файл...")
        file_path = await reply.download_media()
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        os.remove(file_path)

        await edit_or_reply(event, f"🔄 Конвертирую...\nСервис: {converter.supported_services[service]['name']}\nПрофиль: {converter.conversion_profiles[profile]['name']}")
        
        response = await converter.make_ai_request(service, source_code, user_request, profile)
        
        if response.startswith("❌"):
            await edit_or_reply(event, response)
            return

        converted_code = converter.extract_code(response)
        if converter.auto_optimize:
            converted_code = converter.optimize_code(converted_code)
            
        if not converted_code.strip():
            await edit_or_reply(event, "❌ Не удалось извлечь код")
            return

        original_filename = reply.file.name
        converted_filename = f"hydra_{profile}_{original_filename}"
        
        with open(converted_filename, 'w', encoding='utf-8') as f:
            f.write(converted_code)

        caption = (f"✅ УСПЕШНАЯ КОНВЕРТАЦИЯ!\n\n"
                  f"📁 Файл: {original_filename}\n"
                  f"🔮 Сервис: {converter.supported_services[service]['name']}\n"
                  f"🎯 Профиль: {converter.conversion_profiles[profile]['name']}")
        
        if user_request != "Конвертировать код из Hikka в Hydra":
            caption += f"\n🎯 Запрос: {user_request}"

        await event.client.send_file(event.chat_id, converted_filename, caption=caption, force_document=True)
        await event.delete()
        os.remove(converted_filename)
        
    except Exception as e:
        await edit_or_reply(event, f"❌ Ошибка: {str(e)}")

async def fix_handler(event):
    try:
        if not event.out:
            return
        reply = await event.get_reply_message()
        if not reply or not reply.media or not (reply.file and reply.file.name.endswith('.py')):
            await edit_or_reply(event, "❌ Ответьте на .py файл для исправления!")
            return

        args = event.text.split(maxsplit=1)
        user_request = "Исправь все ошибки и оптимизируй код"
        if len(args) > 1:
            user_request = args[1]

        service = "google"
        if service not in converter.api_keys:
            await edit_or_reply(event, f"❌ Установи ключ: .set_key {service} <ключ>")
            return

        await edit_or_reply(event, "📥 Скачиваю файл...")
        file_path = await reply.download_media()
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        os.remove(file_path)

        await edit_or_reply(event, "🔧 Исправляю...")
        response = await converter.make_ai_request(service, source_code, user_request, "premium")
        
        if response.startswith("❌"):
            await edit_or_reply(event, response)
            return

        fixed_code = converter.extract_code(response)
        original_filename = reply.file.name
        fixed_filename = f"fixed_{original_filename}"
        
        with open(fixed_filename, 'w', encoding='utf-8') as f:
            f.write(fixed_code)

        await event.client.send_file(event.chat_id, fixed_filename, caption=f"✅ КОД ИСПРАВЛЕН!\nФайл: {original_filename}", force_document=True)
        await event.delete()
        os.remove(fixed_filename)
        
    except Exception as e:
        await edit_or_reply(event, f"❌ Ошибка: {str(e)}")

async def stats_handler(event):
    try:
        if not event.out:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        text = "📊 СТАТИСТИКА:\n\n"
        
        if today in converter.usage_stats:
            for service, stats in converter.usage_stats[today].items():
                text += f"• {converter.supported_services[service]['name']}: {stats['requests']} запросов\n"
        
        text += f"\n📈 Всего конвертаций: {len(converter.conversion_history)}"
        await edit_or_reply(event, text)
    except Exception as e:
        await edit_or_reply(event, f"❌ Ошибка: {str(e)}")

async def services_handler(event):
    try:
        if not event.out:
            return
        text = "🤖 ДОСТУПНЫЕ СЕРВИСЫ:\n\n"
        for service_id, service_info in converter.supported_services.items():
            has_key = "✅" if service_id in converter.api_keys else "❌"
            text += f"• {service_info['name']} ({service_id}) {has_key}\n"
        
        text += "\n🎯 ПРОФИЛИ:\n"
        for profile_id, profile_info in converter.conversion_profiles.items():
            text += f"• {profile_info['name']} ({profile_id}) - {profile_info['description']}\n"
        
        text += "\n🚀 КОМАНДЫ:\n.set_key • .convert • .fix • .stats • .show_keys"
        await edit_or_reply(event, text)
    except Exception as e:
        await edit_or_reply(event, f"❌ Ошибка: {str(e)}")

modules_help = {
    "ai_converter": {
        "set_key": "<сервис> <ключ> - Установить API ключ",
        "show_keys": "Показать ключи", 
        "convert": "[сервис] [профиль] [запрос] - Конвертировать файл",
        "fix": "[запрос] - Исправить код",
        "stats": "Статистика использования",
        "services": "Список сервисов"
    }
}

print("✅ AI Converter Ultimate загружен!")
print("🚀 Сервисы: Google Gemini, OpenRouter")
print("🎯 Профили: basic, advanced, premium")