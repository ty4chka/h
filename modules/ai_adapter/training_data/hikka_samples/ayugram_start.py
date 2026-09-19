import os
from utils.misc import edit_or_reply


async def start_handler(event):
    """Отправляет приветственное фото с информацией о боте"""
    try:
        # Получаем информацию о пользователе безопасно
        if event.sender:
            username = event.sender.username or "Не установлен"
            user_id = event.sender.id
        else:
            # Если sender None, используем информацию из сообщения
            username = "Неизвестно"
            user_id = "Неизвестно"
        
        # Путь к фото
        photo_path = "start.jpg"
        
        # Создаем папку assets если не существует
        os.makedirs("assets", exist_ok=True)
        
        # Если фото не существует, отправляем текстовое сообщение
        if not os.path.exists(photo_path):
            await send_text_start(username, user_id, event)
            return
        
        # Текст для сообщения
        caption = """🤖 **Hydra User Bot**

⚡️ **Версия:** 1.0.2
👤 **Пользователь:** @{username}
🆔 **ID:** {user_id}

💻 **Разработчик:** @global_050""".format(
            username=username,
            user_id=user_id
        )

        # Отправляем фото с использованием client.send_file
        await event.client.send_file(
            event.chat_id,
            photo_path,
            caption=caption
        )
        
        # Удаляем исходное сообщение команды
        await event.delete()
        
    except Exception as e:
        await edit_or_reply(event, f"❌ Error: {e}")


async def send_text_start(username, user_id, event):
    """Отправляет текстовое сообщение если фото не найдено"""
    text = """🤖 **Hydra User Bot**

⚡️ **Версия:** 1.0.2
👤 **Пользователь:** @{username}
🆔 **ID:** {user_id}

💻 **Разработчик:** @global_050

💡 *Для установки фото создайте папку assets и поместите туда start.jpg*""".format(
        username=username,
        user_id=user_id
    )
    
    await edit_or_reply(event, text)


modules_help = {
    "start": {
        "start": "Start the bot and show information"
    }
}