import time
from utils.misc import get_uptime, get_start_time, edit_or_reply


async def ping_handler(event):
    """Проверка задержки и uptime"""
    try:
        # Засекаем время
        start = time.time()
        msg = await edit_or_reply(event, "⚡")
        end = time.time()
        
        # Вычисляем задержку
        ping_ms = round((end - start) * 1000, 2)
        
        # Получаем uptime
        start_time = get_start_time()
        uptime = get_uptime(start_time)
        
        # Формируем ответ
        text = (
            f"⚡️ **Ping:** `{ping_ms}` ms\n"
            f"🕐 **Uptime:** `{uptime}`"
        )
        
        await msg.edit(text)
        
    except Exception as e:
        await edit_or_reply(event, f"❌ Error: {e}")


# Справка для модуля - исправленная структура
modules_help = {
    "ping": {
        "ping": "Check bot response time and uptime"
    }
}