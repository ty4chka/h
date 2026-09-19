import asyncio
import logging
import os
import time
from pathlib import Path
import sys
import importlib
import types

# Добавляем совместимость с Hikka и HeroKu
sys.path.insert(0, str(Path.cwd()))

# Эмуляция Hikka utils
class HikkaUtils:
    """Эмуляция Hikka utils"""
    
    @staticmethod
    def answer(message, text):
        """Эмуляция utils.answer"""
        from utils.misc import edit_or_reply
        return edit_or_reply(message.event if hasattr(message, 'event') else message, text)
    
    @staticmethod
    def escape_html(text: str) -> str:
        """Экранирование HTML"""
        if not text:
            return ""
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    @staticmethod
    def get_args(message):
        """Получение аргументов команды"""
        return message.text.split()[1:] if len(message.text.split()) > 1 else []
    
    @staticmethod 
    def get_args_raw(message):
        """Получение сырых аргументов"""
        return message.text.split(' ', 1)[1] if len(message.text.split(' ', 1)) > 1 else ""

# Имитируем Hikka окружение
class HikkaCompat:
    """Полная совместимость с Hikka модулями"""
    
    class loader:
        class Module:
            """Базовый класс модуля Hikka"""
            strings = {"name": "HikkaModule"}
            
            def __init__(self):
                self.client = None
                self._db = None
                self.inline = None
                self.allmodules = None
                self.config = {}
            
            def config_complete(self):
                """Вызывается после загрузки конфига"""
                pass
            
            async def client_ready(self, client, db):
                """Вызывается когда клиент готов"""
                self.client = client
                self._db = db
            
            async def on_unload(self):
                """Вызывается при выгрузке модуля"""
                pass

        class Library:
            """Библиотека Hikka"""
            pass

        class Validator:
            """Валидаторы конфига"""
            class Boolean:
                pass
            class String:
                pass
            class Integer:
                pass
            class Float:
                pass
            class Series:
                pass
            class Choice:
                pass

        @staticmethod
        def tds(cls):
            """Декоратор для модулей Hikka"""
            return cls

        @staticmethod  
        def module(name=None):
            """Декоратор для модулей Hikka"""
            def decorator(cls):
                return cls
            return decorator

        @staticmethod
        def command(name=None, aliases=None, ru_doc=None):
            """Декоратор для команд Hikka"""
            def decorator(func):
                # Сохраняем оригинальную функцию
                func._hikka_command = True
                func._ru_doc = ru_doc
                return func
            return decorator

        @staticmethod
        def loop(interval=None, autostart=False, wait_before=False):
            """Декоратор для циклов Hikka"""
            def decorator(func):
                return func
            return decorator

# Имитируем HeroKu окружение  
class HeroKuCompat:
    """Совместимость с HeroKu модулями"""
    class loader:
        class Module:
            """Базовый класс модуля HeroKu"""
            strings = {"name": "HeroKuModule"}
            
            def __init__(self):
                self.client = None
                self._db = None
                self.inline = None
                self.allmodules = None
            
            def config_complete(self):
                """Вызывается после загрузки конфига"""
                pass
            
            async def client_ready(self, client, db):
                """Вызывается когда клиент готов"""
                self.client = client
                self._db = db
            
            async def on_unload(self):
                """Вызывается при выгрузке модуля"""
                pass

        class Library:
            """Библиотека HeroKu"""
            pass

# Создаем глобальные объекты для совместимости
hikka = HikkaCompat()
heroku = HeroKuCompat()
utils_compat = HikkaUtils()

# Добавляем в sys.modules для импорта
sys.modules['hikka'] = hikka
sys.modules['heroku'] = heroku
sys.modules['hikka.loader'] = hikka.loader
sys.modules['heroku.loader'] = heroku.loader
sys.modules['hikka.utils'] = utils_compat

# СИСТЕМА ОТНОСИТЕЛЬНЫХ ИМПОРТОВ ДЛЯ HIKKA МОДУЛЕЙ
class RelativeImportFix:
    """Фикс для относительных импортов Hikka модулей"""
    
    def __init__(self):
        self.fake_parent = None
    
    def setup_relative_imports(self):
        """Настраивает систему для поддержки относительных импортов"""
        # Создаем фейковый родительский пакет для модулей
        self.fake_parent = types.ModuleType("hikka_modules")
        sys.modules["hikka_modules"] = self.fake_parent
        
        # Добавляем loader и utils в фейковый родительский пакет
        sys.modules["hikka_modules.loader"] = hikka.loader
        sys.modules["hikka_modules.utils"] = utils_compat
        
        print("    🔧 Relative import system initialized")

# Перехватчик импортов для обработки относительных импортов
class RelativeImportHandler:
    """Обработчик относительных импортов Hikka модулей"""
    
    def find_spec(self, fullname, path, target=None):
        # Обрабатываем относительные импорты from .. import
        if fullname in ["..loader", "...loader", "..utils", "...utils"]:
            # Создаем фейковый spec для обхода ошибок импорта
            return importlib.util.spec_from_loader(fullname, loader=None)
        return None

    def find_module(self, fullname, path=None):
        # Старый метод для обратной совместимости
        if fullname in ["..loader", "...loader", "..utils", "...utils"]:
            return self
        return None

    def load_module(self, fullname):
        # Загружаем фейковый модуль для относительных импортов
        if fullname == "..loader" or fullname == "...loader":
            return sys.modules['hikka.loader']
        elif fullname == "..utils" or fullname == "...utils":
            return sys.modules['hikka.utils']
        raise ImportError(f"Can't import {fullname}")

# Устанавливаем перехватчик импортов
sys.meta_path.insert(0, RelativeImportHandler())

# Инициализируем фикс относительных импортов
import_fix = RelativeImportFix()
import_fix.setup_relative_imports()

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

import config
from utils.loader import load_all_modules
from utils.misc import set_start_time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

# Время запуска бота
start_time = time.time()
set_start_time(start_time)


def clear_screen():
    """Очистка экрана терминала"""
    os.system('cls' if os.name == 'nt' else 'clear')


def fix_session_file():
    """Исправление поврежденного файла сессии"""
    session_file = "hydra_session.session"
    if os.path.exists(session_file):
        try:
            # Простая проверка - если файл меньше 100 байт, он вероятно поврежден
            if os.path.getsize(session_file) < 100:
                os.remove(session_file)
                print("    🔧 Fixed corrupted session file")
        except:
            # Если не можем проверить, просто удаляем
            os.remove(session_file)
            print("    🔧 Fixed corrupted session file")


async def init_compat_system(client):
    """Инициализирует систему совместимости"""
    # Создаем глобальные объекты для модулей
    class FakeDB:
        """Фейковая база данных для совместимости"""
        def get(self, *args, **kwargs):
            return None
        def set(self, *args, **kwargs):
            pass
        def save(self):
            pass

    class FakeInline:
        """Фейковый инлайн для совместимости"""
        def __init__(self):
            self.bot_username = "hydra_bot"
            self.init_complete = True

    class FakeAllModules:
        """Фейковый allmodules для совместимости"""
        def __init__(self):
            self.modules = []
            self.libraries = []

    # Глобальные объекты для совместимости
    global_db = FakeDB()
    global_inline = FakeInline()
    global_allmodules = FakeAllModules()

    # Обновляем объекты совместимости
    hikka.loader.Module.client = client
    hikka.loader.Module._db = global_db
    hikka.loader.Module.inline = global_inline
    hikka.loader.Module.allmodules = global_allmodules

    heroku.loader.Module.client = client
    heroku.loader.Module._db = global_db
    heroku.loader.Module.inline = global_inline
    heroku.loader.Module.allmodules = global_allmodules

    print("    🔄 Compatibility system initialized")


async def main():
    """Главная функция запуска"""
    clear_screen()
    
    print("""
    ╔══════════════════════════════╗
    ║         HYDRA USERBOT        ║
    ║     Hikka/HeroKu Compat      ║
    ║          Starting...         ║
    ╚══════════════════════════════╝
    """)
    
    # Исправляем файл сессии если нужно
    fix_session_file()
    
    # Создаем клиент
    client = TelegramClient(
        "hydra_session",
        config.api_id,
        config.api_hash
    )
    
    # Создаем директорию для модулей если не существует
    Path("modules").mkdir(exist_ok=True)
    
    try:
        await client.start()
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        print(f"    ✅ Logged in as @{me.username or me.first_name}")
        
        # Инициализируем систему совместимости
        await init_compat_system(client)
        
    except SessionPasswordNeededError:
        print("    🔐 Two-factor authentication required")
        password = input("    Enter password: ")
        await client.sign_in(password=password)
        me = await client.get_me()
        print(f"    ✅ Logged in as @{me.username or me.first_name}")
        
        # Инициализируем систему совместимости после входа
        await init_compat_system(client)
    except Exception as e:
        print(f"    ❌ Failed to start: {e}")
        logging.exception("Detailed error:")
        return
    
    # Загрузка модулей
    print("\n    📦 Loading modules...\n")
    success, total = await load_all_modules("modules", client)
    
    print(f"""
    ╔══════════════════════════════╗
    ║       HYDRA STARTED!         ║
    ║    Modules: {success:2d}/{total:2d} loaded       ║
    ║   Prefix: {config.prefix}                    ║
    ║   Type {config.prefix}help for commands    ║
    ║   Compat: Hikka/HeroKu ✅    ║
    ╚══════════════════════════════╝
    """)
    
    try:
        print("    🚀 Bot is running... Press Ctrl+C to stop")
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print("\n    🛑 Stopping...")
    finally:
        await client.disconnect()
        print("    👋 Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass