"""
Универсальный загрузчик модулей для Hydra Userbot
Нативная поддержка Hikka, HeroKu и Hydra модулей
"""

import importlib
import sys
import os
import asyncio
import re
import inspect
from pathlib import Path
from typing import Dict, List
import logging
import importlib.util

logger = logging.getLogger(__name__)

# Глобальное хранилище справки по модулям
modules_help: Dict[str, Dict[str, str]] = {}

# Глобальный клиент
global_client = None


class UniversalModuleLoader:
    """Универсальный загрузчик для всех типов модулей"""
    
    def __init__(self, client):
        global global_client
        global_client = client
        self.loaded_modules = {}
    
    def detect_module_type(self, module_code: str) -> str:
        """Определяет тип модуля с улучшенной логикой"""
        module_code_lower = module_code.lower()
        
        # Hikka модули
        if ('@loader.tds' in module_code or 
            'from hikka' in module_code_lower or 
            'hikkamods' in module_code_lower or
            'hikariatama' in module_code_lower or
            'scope: hikka_only' in module_code_lower):
            return 'hikka'
        
        # HeroKu модули  
        elif ('from heroku' in module_code_lower or 
              'heroku.module' in module_code_lower or
              'herokumods' in module_code_lower):
            return 'heroku'
        
        # Hydra модули (нативные)
        elif ('async def' in module_code and '_handler' in module_code and
              'modules_help' in module_code):
            return 'hydra'
        
        else:
            return 'unknown'

    async def load_hikka_module_with_relative_imports(self, module_name: str) -> bool:
        """Специальная загрузка Hikka модулей с относительными импортами"""
        try:
            # Читаем исходный код модуля
            file_path = f"modules/{module_name}.py"
            with open(file_path, 'r', encoding='utf-8') as f:
                module_code = f.read()
            
            # Заменяем относительные импорты на абсолютные
            fixed_code = module_code.replace('from .. import loader, utils', '')
            fixed_code = fixed_code.replace('from .. import loader', '')
            fixed_code = fixed_code.replace('from .. import utils', '')
            
            # Создаем временный файл с исправленным кодом
            temp_file = f"modules/_{module_name}_fixed.py"
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(fixed_code)
            
            # Загружаем исправленный модуль
            spec = importlib.util.spec_from_file_location(module_name, temp_file)
            module = importlib.util.module_from_spec(spec)
            
            # Добавляем необходимые атрибуты для совместимости
            module.__package__ = "modules"
            module.__name__ = module_name
            
            # Вручную добавляем loader и utils в модуль
            import hikka
            module.loader = hikka.loader
            module.utils = hikka.utils
            
            # Выполняем модуль
            spec.loader.exec_module(module)
            
            # Регистрируем модуль
            success = await self.register_hikka_module_v2(module, module_name)
            
            # Удаляем временный файл
            try:
                os.remove(temp_file)
            except:
                pass
                
            return success
            
        except Exception as e:
            logger.error(f"❌ Error loading Hikka module {module_name} with relative imports: {e}")
            # Удаляем временный файл при ошибке
            try:
                os.remove(f"modules/_{module_name}_fixed.py")
            except:
                pass
            return False
    
    async def load_and_register_module(self, module_path: str, module_name: str) -> bool:
        """Загружает и регистрирует модуль любого типа с улучшенной совместимостью"""
        try:
            # Определяем тип модуля
            file_path = f"modules/{module_name}.py"
            with open(file_path, 'r', encoding='utf-8') as f:
                module_code = f.read()
            
            module_type = self.detect_module_type(module_code)
            
            # Для Hikka модулей с относительными импортами используем специальную загрузку
            if module_type == 'hikka' and ('from .. import' in module_code or 'from ... import' in module_code):
                return await self.load_hikka_module_with_relative_imports(module_name)
            
            # Обычная загрузка для других типов модулей
            if module_path in sys.modules:
                module = importlib.reload(sys.modules[module_path])
            else:
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                
                # Устанавливаем атрибуты для совместимости
                module.__package__ = "modules"
                
                sys.modules[module_path] = module
                spec.loader.exec_module(module)
            
            # Регистрируем в зависимости от типа
            if module_type == 'hikka':
                success = await self.register_hikka_module_v2(module, module_name)
                if not success:
                    success = await self.register_hikka_module(module, module_name)
            elif module_type == 'heroku':
                success = await self.register_heroku_module(module, module_name)
            elif module_type == 'hydra':
                success = await self.register_hydra_module(module, module_name)
            else:
                success = await self.register_unknown_module(module, module_name)
            
            if success:
                self.loaded_modules[module_name] = {
                    'module': module,
                    'type': module_type
                }
                logger.info(f"✅ {module_name} ({module_type})")
                return True
            else:
                logger.error(f"❌ {module_name} ({module_type})")
                return False
                
        except Exception as e:
            logger.error(f"❌ {module_name}: {e}")
            import traceback
            logger.error(f"Detailed error: {traceback.format_exc()}")
            return False
    
    async def register_hikka_module_v2(self, module, module_name: str) -> bool:
        """Улучшенная регистрация Hikka модулей с поддержкой декораторов"""
        try:
            # Ищем класс модуля с декоратором @loader.tds
            module_class = None
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    hasattr(obj, '__module__') and 
                    obj.__module__ == module.__name__ and
                    (hasattr(obj, 'strings') or hasattr(obj, 'cmd_'))):
                    module_class = obj
                    break
            
            if not module_class:
                logger.error(f"❌ Hikka module class not found in {module_name}")
                return False
            
            # Создаем экземпляр модуля
            module_instance = module_class()
            module_instance.client = global_client
            
            # Инициализируем конфиг если есть
            if hasattr(module_instance, 'config'):
                module_instance.config = getattr(module_instance, 'config', {})
            
            # Регистрируем команды через декораторы
            await self.register_hikka_commands_v2(module_instance, module_name, module_class)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error registering Hikka module {module_name}: {e}")
            return False

    async def register_hikka_commands_v2(self, module_instance, module_name: str, module_class):
        """Регистрация команд Hikka с поддержкой декораторов"""
        from telethon import events
        from config import prefix
        
        command_count = 0
        
        # Ищем методы с командами
        for attr_name in dir(module_class):
            if not (attr_name.endswith('cmd') or hasattr(getattr(module_class, attr_name), '_hikka_command')):
                continue
                
            attr = getattr(module_class, attr_name)
            
            # Пропускаем не-функции
            if not inspect.isfunction(attr):
                continue
                
            # Определяем имя команды
            if attr_name.endswith('cmd'):
                cmd_name = attr_name[:-3]  # Убираем 'cmd'
            else:
                cmd_name = attr_name
                
            # Получаем документацию
            doc_string = getattr(attr, '__doc__', 'No description')
            
            # Создаем обертку для обработчика
            async def hikka_command_wrapper(event, cmd_func=attr, instance=module_instance, cmd_name=cmd_name):
                if event.out:
                    try:
                        # Создаем совместимый объект message
                        class HikkaMessage:
                            def __init__(self, event):
                                self.event = event
                                self.text = event.text
                                self.sender = event.sender
                                self.chat_id = event.chat_id
                                self.client = event.client
                                self.out = event.out
                                self.id = event.id
                                
                            async def get_reply_message(self):
                                return await self.event.get_reply_message()
                                
                            async def edit(self, text, **kwargs):
                                await self.event.edit(text, **kwargs)
                                
                            async def reply(self, text, **kwargs):
                                await self.event.reply(text, **kwargs)
                                
                            async def delete(self):
                                await self.event.delete()
                        
                        message = HikkaMessage(event)
                        
                        # Вызываем оригинальный обработчик
                        await cmd_func(instance, message)
                        
                    except Exception as e:
                        from utils.misc import edit_or_reply
                        await edit_or_reply(event, f"❌ Hikka Error in {cmd_name}: {e}")
            
            # Регистрируем команду
            pattern = rf'^{prefix}{cmd_name}$'
            
            @global_client.on(events.NewMessage(pattern=pattern, outgoing=True))
            async def wrapped_handler(event):
                await hikka_command_wrapper(event)
            
            # Добавляем в справку
            if module_name not in modules_help:
                modules_help[module_name] = {}
            
            modules_help[module_name][cmd_name] = doc_string if doc_string != 'No description' else f"Hikka: {cmd_name}"
            
            command_count += 1
            logger.info(f"📝 Registered Hikka command: {prefix}{cmd_name}")
        
        return command_count
    
    async def register_hikka_module(self, module, module_name: str) -> bool:
        """Регистрирует Hikka модуль"""
        try:
            # Ищем класс модуля
            module_class = None
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    (hasattr(obj, '__module__') and obj.__module__ == module.__name__) and
                    (hasattr(obj, 'strings') or 'cmd_' in str(obj.__dict__))):
                    module_class = obj
                    break
            
            if not module_class:
                logger.error(f"❌ Hikka module class not found in {module_name}")
                return False
            
            # Создаем экземпляр модуля
            module_instance = module_class()
            module_instance.client = global_client
            
            # Вызываем методы жизненного цикла
            if hasattr(module_instance, 'config_complete'):
                module_instance.config_complete()
            
            # Регистрируем команды
            await self.register_hikka_commands(module_instance, module_name)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error registering Hikka module {module_name}: {e}")
            return False
    
    async def register_heroku_module(self, module, module_name: str) -> bool:
        """Регистрирует HeroKu модуль"""
        try:
            # Ищем класс модуля
            module_class = None
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    (hasattr(obj, '__module__') and obj.__module__ == module.__name__) and
                    (hasattr(obj, 'strings') or '_cmd' in str(obj.__dict__))):
                    module_class = obj
                    break
            
            if not module_class:
                logger.error(f"❌ HeroKu module class not found in {module_name}")
                return False
            
            # Создаем экземпляр модуля
            module_instance = module_class()
            module_instance.client = global_client
            
            # Регистрируем команды
            await self.register_heroku_commands(module_instance, module_name)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error registering HeroKu module {module_name}: {e}")
            return False
    
    async def register_hydra_module(self, module, module_name: str) -> bool:
        """Регистрирует Hydra модуль"""
        try:
            # Передаем клиент в модуль
            module.client = global_client
            
            # Регистрируем команды
            await self.register_hydra_commands(module, module_name)
            
            # Добавляем справку
            if hasattr(module, 'modules_help'):
                if isinstance(module.modules_help, dict):
                    for mod_name, commands in module.modules_help.items():
                        if mod_name not in modules_help:
                            modules_help[mod_name] = {}
                        modules_help[mod_name].update(commands)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error registering Hydra module {module_name}: {e}")
            return False
    
    async def register_unknown_module(self, module, module_name: str) -> bool:
        """Регистрирует модуль неизвестного типа"""
        try:
            # Пробуем зарегистрировать как Hydra модуль
            module.client = global_client
            
            # Ищем обработчики команд
            command_count = await self.register_auto_commands(module, module_name)
            
            if command_count > 0:
                logger.info(f"🔍 Auto-registered {command_count} commands in {module_name}")
                return True
            else:
                logger.error(f"❌ No commands found in unknown module {module_name}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error registering unknown module {module_name}: {e}")
            return False
    
    async def register_hikka_commands(self, module_instance, module_name: str):
        """Регистрирует команды Hikka модуля"""
        from telethon import events
        from config import prefix
        
        command_count = 0
        for attr_name in dir(module_instance):
            if attr_name.startswith('cmd_'):
                cmd_name = attr_name[4:]  # Убираем 'cmd_'
                handler_func = getattr(module_instance, attr_name)
                
                # Создаем обертку
                async def command_wrapper(event, func=handler_func, instance=module_instance):
                    if event.out:
                        try:
                            # Создаем совместимый объект message
                            class CompatMessage:
                                def __init__(self, event):
                                    self.event = event
                                    self.text = event.text
                                    self.sender = event.sender
                                    self.chat_id = event.chat_id
                                    self.out = event.out
                                    self.client = event.client
                                
                                async def edit(self, text, **kwargs):
                                    await self.event.edit(text, **kwargs)
                                
                                async def reply(self, text, **kwargs):
                                    await self.event.reply(text, **kwargs)
                                
                                async def delete(self):
                                    await self.event.delete()
                            
                            message = CompatMessage(event)
                            await func(instance, message)
                            
                        except Exception as e:
                            from utils.misc import edit_or_reply
                            await edit_or_reply(event, f"❌ Hikka Error: {e}")
                
                # Регистрируем команду
                pattern = rf'^{prefix}{cmd_name}$'
                
                @global_client.on(events.NewMessage(pattern=pattern, outgoing=True))
                async def wrapped_handler(event):
                    await command_wrapper(event)
                
                # Добавляем в справку
                if module_name not in modules_help:
                    modules_help[module_name] = {}
                modules_help[module_name][cmd_name] = f"Hikka: {cmd_name}"
                
                command_count += 1
                logger.debug(f"📝 Registered Hikka command: {prefix}{cmd_name}")
        
        return command_count
    
    async def register_heroku_commands(self, module_instance, module_name: str):
        """Регистрирует команды HeroKu модуля"""
        from telethon import events
        from config import prefix
        
        command_count = 0
        for attr_name in dir(module_instance):
            if attr_name.endswith('_cmd'):
                cmd_name = attr_name[:-4]  # Убираем '_cmd'
                handler_func = getattr(module_instance, attr_name)
                
                # Создаем обертку
                async def command_wrapper(event, func=handler_func, instance=module_instance):
                    if event.out:
                        try:
                            # Создаем совместимый объект message
                            class CompatMessage:
                                def __init__(self, event):
                                    self.event = event
                                    self.text = event.text
                                    self.sender = event.sender
                                    self.chat_id = event.chat_id
                                    self.out = event.out
                                    self.client = event.client
                                
                                async def edit(self, text, **kwargs):
                                    await self.event.edit(text, **kwargs)
                                
                                async def reply(self, text, **kwargs):
                                    await self.event.reply(text, **kwargs)
                                
                                async def delete(self):
                                    await self.event.delete()
                            
                            message = CompatMessage(event)
                            await func(instance, message)
                            
                        except Exception as e:
                            from utils.misc import edit_or_reply
                            await edit_or_reply(event, f"❌ HeroKu Error: {e}")
                
                # Регистрируем команду
                pattern = rf'^{prefix}{cmd_name}$'
                
                @global_client.on(events.NewMessage(pattern=pattern, outgoing=True))
                async def wrapped_handler(event):
                    await command_wrapper(event)
                
                # Добавляем в справку
                if module_name not in modules_help:
                    modules_help[module_name] = {}
                modules_help[module_name][cmd_name] = f"HeroKu: {cmd_name}"
                
                command_count += 1
                logger.debug(f"📝 Registered HeroKu command: {prefix}{cmd_name}")
        
        return command_count
    
    async def register_hydra_commands(self, module, module_name: str):
        """Регистрирует команды Hydra модуля"""
        from telethon import events
        from config import prefix
        
        command_count = 0
        
        if hasattr(module, 'modules_help'):
            for mod_name, commands in module.modules_help.items():
                for cmd_name in commands.keys():
                    handler_name = f"{cmd_name}_handler"
                    
                    if hasattr(module, handler_name):
                        handler_func = getattr(module, handler_name)
                        
                        # Регистрируем команду
                        pattern = rf'^{prefix}{cmd_name}$'
                        
                        @global_client.on(events.NewMessage(pattern=pattern, outgoing=True))
                        async def command_wrapper(event):
                            if event.out:
                                await handler_func(event)
                        
                        command_count += 1
                        logger.debug(f"📝 Registered Hydra command: {prefix}{cmd_name}")
        
        return command_count
    
    async def register_auto_commands(self, module, module_name: str) -> int:
        """Автоматически регистрирует команды любого типа"""
        from telethon import events
        from config import prefix
        
        command_count = 0
        
        # Ищем функции-обработчики
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and asyncio.iscoroutinefunction(attr):
                # Пробуем разные паттерны имен
                cmd_name = None
                if attr_name.startswith('cmd_'):
                    cmd_name = attr_name[4:]
                elif attr_name.endswith('_cmd'):
                    cmd_name = attr_name[:-4]
                elif attr_name.endswith('_handler'):
                    cmd_name = attr_name[:-8]
                
                if cmd_name:
                    # Регистрируем команду
                    pattern = rf'^{prefix}{cmd_name}$'
                    
                    @global_client.on(events.NewMessage(pattern=pattern, outgoing=True))
                    async def command_wrapper(event):
                        if event.out:
                            await attr(event)
                    
                    # Добавляем в справку
                    if module_name not in modules_help:
                        modules_help[module_name] = {}
                    modules_help[module_name][cmd_name] = f"Auto: {cmd_name}"
                    
                    command_count += 1
                    logger.debug(f"📝 Auto-registered command: {prefix}{cmd_name}")
        
        return command_count


async def load_all_modules(directory: str, client) -> tuple:
    """
    Загружает все модули из директории
    
    Args:
        directory: Путь к директории с модулями
        client: Telethon клиент
        
    Returns:
        (успешно_загружено, всего_модулей)
    """
    modules_path = Path(directory)
    if not modules_path.exists():
        logger.warning(f"Directory {directory} not found")
        return 0, 0
    
    # Создаем загрузчик
    loader = UniversalModuleLoader(client)
    
    success = 0
    total = 0
    
    # Добавляем текущую директорию в sys.path для импорта
    if str(Path.cwd()) not in sys.path:
        sys.path.insert(0, str(Path.cwd()))
    
    for path in modules_path.rglob("*.py"):
        # Пропускаем файлы начинающиеся с _
        if path.stem.startswith("_"):
            continue
        
        # Пропускаем файлы с конфликтующими именами
        if path.stem in ['loader', 'config', 'main']:
            logger.warning(f"⚠️ Skipping conflicting module: {path.stem}")
            continue
        
        total += 1
        module_name = path.stem
        
        # Формируем путь для импорта
        module_path = f"{directory}.{module_name}"
        
        # Загружаем модуль
        if await loader.load_and_register_module(module_path, module_name):
            success += 1
    
    # Логируем загруженные модули для отладки
    logger.info(f"📚 Loaded modules: {list(modules_help.keys())}")
    
    return success, total