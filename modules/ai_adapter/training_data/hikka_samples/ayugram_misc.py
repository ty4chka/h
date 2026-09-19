"""
Вспомогательные функции для модулей
"""

import time
from datetime import datetime

# Импортируем из config
from config import prefix

# Глобальное время старта бота
bot_start_time = None

def set_start_time(start_time: float):
    """Установка времени старта бота"""
    global bot_start_time
    bot_start_time = start_time

def get_start_time() -> float:
    """Получение времени старта бота"""
    return bot_start_time

def get_uptime(start_time: float = None) -> str:
    """
    Форматирование uptime в читаемый вид
    
    Args:
        start_time: Время запуска (time.time()), если None - используется глобальное
        
    Returns:
        Строка вида "HH:MM:SS"
    """
    if start_time is None:
        start_time = get_start_time()
        if start_time is None:
            return "00:00:00"
    
    uptime_seconds = int(time.time() - start_time)
    return datetime.utcfromtimestamp(uptime_seconds).strftime("%H:%M:%S")


async def edit_or_reply(event, text: str, **kwargs):
    """
    Редактирует сообщение если оно исходящее, иначе отвечает на него
    
    Args:
        event: Событие Telethon
        text: Текст для отправки
        **kwargs: Дополнительные параметры
        
    Returns:
        Отправленное сообщение
    """
    try:
        if event.out:
            return await event.edit(text, **kwargs)
        else:
            return await event.reply(text, **kwargs)
    except Exception:
        return await event.reply(text, **kwargs)