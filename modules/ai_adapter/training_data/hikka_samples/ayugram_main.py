import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    JobQueue
)
from telegram.error import BadRequest
from telegram.request import HTTPXRequest
import sqlite3
import time
import asyncio
import itertools
from datetime import datetime
import random
import re

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
DATABASE_NAME = "love_bot.db"
HEART_ANIMATION_FRAMES = [
  # Полная анимация сердец
    # Кадр 1 - Чёрное сердце
    """
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
🤍🤍🖤🖤🤍🤍🖤🖤🤍🤍
🤍🖤🖤🖤🖤🖤🖤🖤🖤🤍
🤍🖤🖤🖤🖤🖤🖤🖤🖤🤍
🤍🤍🖤🖤🖤🖤🖤🖤🤍🤍
🤍🤍🤍🖤🖤🖤🖤🤍🤍🤍
🤍🤍🤍🤍🖤🖤🤍🤍🤍🤍
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
    """,
    
    # Кадр 2 - Красное сердце
    """
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
🤍🤍❤️❤️🤍🤍❤️❤️🤍🤍
🤍❤️❤️❤️❤️❤️❤️❤️❤️🤍
🤍❤️❤️❤️❤️❤️❤️❤️❤️🤍
🤍🤍❤️❤️❤️❤️❤️❤️🤍🤍
🤍🤍🤍❤️❤️❤️❤️🤍🤍🤍
🤍🤍🤍🤍❤️❤️🤍🤍🤍🤍
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
    """,
    
    # Кадр 3 - Оранжевое сердце
    """
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
🤍🤍🧡🧡🤍🤍🧡🧡🤍🤍
🤍🧡🧡🧡🧡🧡🧡🧡🧡🤍
🤍🧡🧡🧡🧡🧡🧡🧡🧡🤍
🤍🤍🧡🧡🧡🧡🧡🧡🤍🤍
🤍🤍🤍🧡🧡🧡🧡🤍🤍🤍
🤍🤍🤍🤍🧡🧡🤍🤍🤍🤍
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
    """,
    
    # Кадр 4 - Жёлтое сердце
    """
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
🤍🤍💛💛🤍🤍💛💛🤍🤍
🤍💛💛💛💛💛💛💛💛🤍
🤍💛💛💛💛💛💛💛💛🤍
🤍🤍💛💛💛💛💛💛🤍🤍
🤍🤍🤍💛💛💛💛🤍🤍🤍
🤍🤍🤍🤍💛💛🤍🤍🤍🤍
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
    """,
    
    # Кадр 5 - Зелёное сердце
    """
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
🤍🤍💚💚🤍🤍💚💚🤍🤍
🤍💚💚💚💚💚💚💚💚🤍
🤍💚💚💚💚💚💚💚💚🤍
🤍🤍💚💚💚💚💚💚🤍🤍
🤍🤍🤍💚💚💚💚🤍🤍🤍
🤍🤍🤍🤍💚💚🤍🤍🤍🤍
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
    """,
    
    # Кадр 6 - Синее сердце
    """
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
🤍🤍💙💙🤍🤍💙💙🤍🤍
🤍💙💙💙💙💙💙💙💙🤍
🤍💙💙💙💙💙💙💙💙🤍
🤍🤍💙💙💙💙💙💙🤍🤍
🤍🤍🤍💙💙💙💙🤍🤍🤍
🤍🤍🤍🤍💙💙🤍🤍🤍🤍
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
    """,
    
    # Кадр 7 - Фиолетовое сердце
    """
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
🤍🤍💜💜🤍🤍💜💜🤍🤍
🤍💜💜💜💜💜💜💜💜🤍
🤍💜💜💜💜💜💜💜💜🤍
🤍🤍💜💜💜💜💜💜🤍🤍
🤍🤍🤍💜💜💜💜🤍🤍🤍
🤍🤍🤍🤍💜💜🤍🤍🤍🤍
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
    """,
    
    # Кадр 8 - Розовое сердце
    """
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
🤍🤍💖💖🤍🤍💖💖🤍🤍
🤍💖💖💖💖💖💖💖💖🤍
🤍💖💖💖💖💖💖💖💖🤍
🤍🤍💖💖💖💖💖💖🤍🤍
🤍🤍🤍💖💖💖💖🤍🤍🤍
🤍🤍🤍🤍💖💖🤍🤍🤍🤍
🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍
    """
]

# Милые гифки с описаниями (ДОБАВЛЕНЫ НОВЫЕ ДЕЙСТВИЯ)
CUTE_ACTIONS = {
    "kiss": {
        "description": "💋 Послать нежный поцелуй",
        "gifs": [
            "https://media1.tenor.com/m/4j4UT0-4xTMAAAAC/peach-and-goma.gif",
            "https://media1.tenor.com/m/wXfUjrXrdY4AAAAC/h%C3%B4n.gif",
            "https://media1.tenor.com/m/PmrJ43cFiWEAAAAC/kiss.gif"
        ]
    },
    "hug": {
        "description": "🤗 Отправить теплые объятия",
        "gifs": [
            "https://media.tenor.com/A5VhCveZ_ygAAAAi/peach-and-goma-peach-goma.gif",
            "https://media.tenor.com/ieGsbU8n9J4AAAAi/peach-goma-peach-and-goma.gif",
            "https://media.tenor.com/m8vwQqfk0I4AAAAi/peach-and-goma-cuddle.gif"
        ]
    },
    "pat": {
        "description": "🖐️ Погладить по головке",
        "gifs": [
            "https://media1.tenor.com/m/IwRPwX9C3fEAAAAC/akira-blue-archive.gif",
            "https://media.tenor.com/lHCzlH_ez84AAAAi/cute-love.gif",
            "https://media.tenor.com/xFEinJ1BTosAAAAi/cartoon-patting.gif"
        ]
    },
    "cuddle": {
        "description": "🫂 Прижаться и обниматься",
        "gifs": [
            "https://media.tenor.com/R5hcw0c8l_sAAAAi/peachcat-peachcat-and-goma.gif",
            "https://media1.tenor.com/m/Iiv8C1J7cw4AAAAC/anime-couple.gif",
            "https://media1.tenor.com/m/Dzi6jfp-k0oAAAAd/cat-cuddle.gif"
        ]
    },
    "love": {
        "description": "💌 Признаться в любви",
        "gifs": [
            "https://media.tenor.com/Khzx2p5aGAsAAAAi/iu.gif",
            "https://media1.tenor.com/m/HER2_cj450wAAAAC/aaa-bbb.gif",
            "https://media.tenor.com/kDkh2cAMusgAAAAi/luv-heart.gif"
        ]
    },
    "blush": {
        "description": "😊 Вызвать милое смущение",
        "gifs": [
            "https://media.tenor.com/nNMCqrDsFhMAAAAi/cat-blush.gif",
            "https://media.tenor.com/9_Cuwoj-m5wAAAAi/cute-cat.gif",
            "https://media.tenor.com/6T4estiKG3gAAAAi/cat.gif"
        ]
    },
    "smile": {
        "description": "😄 Подарить улыбку",
        "gifs": [
            "https://media.tenor.com/K0Op-0SpsvkAAAAi/dudu-cute.gif",
            "https://media.tenor.com/Zjx4IpPncygAAAAi/yay-cute.gif",
            "https://media.tenor.com/V76AdqPJMQcAAAAi/okay-nod.gif"
        ]
    },
    # НОВЫЕ ДЕЙСТВИЯ
    "scratch": {
        "description": "🐾 Почесать за ушком",
        "gifs": [
            "https://media.tenor.com/OMFxCKUd7twAAAA1/anime-cute.gif",
            "https://media.tenor.com/61bEKACH460AAAA1/scratching-cat-head.gif",
            "https://media.tenor.com/oUgI-AR7_jcAAAA1/cats-ear-bite.gif"
        ]
    },
    "bite": {
        "description": "😋 Легкий укус",
        "gifs": [
            "https://media1.tenor.com/m/L8GrZ1X6ThsAAAAC/bite.gif",
            "https://media.tenor.com/xoSoxcmS8oUAAAA1/%D0%BA%D0%BE%D1%82-%D0%BA%D1%80%D0%BE%D0%BB%D0%B8%D0%BA.gif",
            "https://media.tenor.com/6qNDJDLq6m4AAAA1/bite.gif"
        ]
    },
    "hickey": {
        "description": "💋 Оставить засос",
        "gifs": [
            "https://media.tenor.com/yDyjMXf2GD4AAAA1/hoonistz-hoonistz-kiss.gif",
            "https://media.tenor.com/2yOmyJXTKM8AAAAm/peachcat-love.gif",
            "https://media.tenor.com/05lxIFAGoJkAAAA1/kiss-anime.gif"
        ]
    },
    "carry": {
        "description": "👑 Взять на ручки",
        "gifs": [
            "https://media.tenor.com/OF1m4shqAxAAAAAm/couple-ilu.gif",
            "https://media.tenor.com/UN9kT2Kusk8AAAAm/peach-goma-peach-and-goma.gif",
            "https://media.tenor.com/O5MMU45v6p4AAAAm/hasher-happy-sticker.gif"
        ]
    },
    "superhug": {
        "description": "🫂 Крепкие объятия",
        "gifs": [
            "https://media.tenor.com/fjuD9-g-vt0AAAAm/hug.gif",
            "https://media.tenor.com/epQeAT-abYgAAAA1/%E0%B8%81%E0%B8%AD%E0%B8%94.gif",
            "https://media.tenor.com/nK6OHJ8EOmEAAAAm/love-cwtch.gif"
        ]
    },
    "praise": {
        "description": "🌟 Похвалить",
        "gifs": [
            "https://media.tenor.com/UlIVJ8wmwbUAAAAm/clapping-applause.gif",
            "https://media.tenor.com/cBhiDLUgbewAAAAm/high-five-hands.gif",
            "https://media.tenor.com/796QBn4lcnoAAAAm/hands-in-the-air-johnny-rose.gif"
        ]
    },
    "lick": {
        "description": "👅 Лизнуть",
        "gifs": [
            "https://media.tenor.com/veV-DKw2IrEAAAA1/nyx-qis.gif",
            "https://media.tenor.com/O6qbA6WAcCYAAAA1/himemiya-rie-licking-screen.gif",
            "https://media.tenor.com/WlXWZBSE2EYAAAA1/anime-nozomi.gif"
        ]
    },
    "pinch": {
        "description": "🤏 Ущипнуть",
        "gifs": [
            "https://media.tenor.com/U4pZZGpeZJIAAAA1/meow-cute.gif",
            "https://media.tenor.com/M-yoCMWQWAMAAAAm/peach-and-goma-goma.gif",
            "https://media.tenor.com/MuHLNMVSuiAAAAA1/pinch-cheeks.gif"
        ]
    }
}

# Глобальные переменные
animation_jobs = {}

# ========================
#  БАЗА ДАННЫХ
# ========================
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        full_name TEXT,
        registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица сообщений
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        message_text TEXT NOT NULL,
        sent_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_read BOOLEAN DEFAULT 0,
        FOREIGN KEY (sender_id) REFERENCES users(user_id),
        FOREIGN KEY (receiver_id) REFERENCES users(user_id)
    )
    ''')
    
    # Таблица достижений
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS achievements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL
    )
    ''')
    
    # Таблица связей пользователей и достижений
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_achievements (
        user_id INTEGER,
        achievement_id INTEGER,
        unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, achievement_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (achievement_id) REFERENCES achievements(id)
    )
    ''')
    
    # Таблица для милых взаимодействий
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cute_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        action_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')
    
    # Предварительное заполнение достижений
    cursor.execute('''
    INSERT OR IGNORE INTO achievements (id, name, description) VALUES
        (1, 'Романтик', 'Запустил анимацию сердца'),
        (2, 'Отправитель', 'Отправил первое сообщение'),
        (3, 'Популярный', 'Получил первое сообщение'),
        (4, 'Социальная бабочка', 'Отправил 20 сообщений'),
        (5, 'Сердцеед', 'Получил 10 сообщений'),
        (6, 'Целовальник', 'Отправил 5 поцелуев'),
        (7, 'Обнимашка', 'Отправил 10 объятий'),
        (8, 'Ласкатель', 'Погладил 5 раз')
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Создает соединение с базой данных"""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def register_user(user):
    """Регистрирует пользователя в базе данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверяем, есть ли пользователь
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user.id,))
    existing_user = cursor.fetchone()
    
    if not existing_user:
        # Регистрируем нового пользователя
        cursor.execute('''
        INSERT INTO users (user_id, username, first_name, full_name)
        VALUES (?, ?, ?, ?)
        ''', (user.id, user.username, user.first_name, user.full_name))
        
        conn.commit()
        logger.info(f"Зарегистрирован новый пользователь: {user.id} ({user.username or user.first_name})")
    
    conn.close()

def find_user_id(username):
    """Находит ID пользователя по username (без @)"""
    username = username.lower().strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT user_id FROM users 
    WHERE LOWER(username) = ?
    ''', (username,))
    
    user = cursor.fetchone()
    conn.close()
    
    return user['user_id'] if user else None

def get_user_info(user_id):
    """Получает информацию о пользователе"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT * FROM users 
    WHERE user_id = ?
    ''', (user_id,))
    
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'user_id': user['user_id'],
            'username': user['username'],
            'first_name': user['first_name'],
            'full_name': user['full_name']
        }
    return None

def add_message(sender_id, receiver_id, message_text):
    """Добавляет сообщение в базу данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT INTO messages (sender_id, receiver_id, message_text)
        VALUES (?, ?, ?)
        ''', (sender_id, receiver_id, message_text))
        
        conn.commit()
        
        # Проверяем достижения для отправителя
        cursor.execute('''
        SELECT COUNT(*) as count FROM messages WHERE sender_id = ?
        ''', (sender_id,))
        sent_count = cursor.fetchone()['count']
        
        if sent_count == 1:
            # Присваиваем достижение "Отправитель"
            cursor.execute('''
            INSERT OR IGNORE INTO user_achievements (user_id, achievement_id) 
            VALUES (?, 2)
            ''', (sender_id,))
        
        # Проверяем достижения для получателя
        cursor.execute('''
        SELECT COUNT(*) as count FROM messages WHERE receiver_id = ?
        ''', (receiver_id,))
        received_count = cursor.fetchone()['count']
        
        if received_count == 1:
            # Присваиваем достижение "Популярный"
            cursor.execute('''
            INSERT OR IGNORE INTO user_achievements (user_id, achievement_id) 
            VALUES (?, 3)
            ''', (receiver_id,))
            
        # Проверяем достижение "Социальная бабочка"
        if sent_count >= 20:
            cursor.execute('''
            INSERT OR IGNORE INTO user_achievements (user_id, achievement_id) 
            VALUES (?, 4)
            ''', (sender_id,))
            
        # Проверяем достижение "Сердцеед"
        if received_count >= 10:
            cursor.execute('''
            INSERT OR IGNORE INTO user_achievements (user_id, achievement_id) 
            VALUES (?, 5)
            ''', (receiver_id,))
            
    except Exception as e:
        logger.error(f"Ошибка сохранения сообщения: {str(e)}")
    finally:
        conn.close()

def get_unread_messages(receiver_id):
    """Получает непрочитанные сообщения для пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT m.id, m.message_text, u.first_name, u.username 
    FROM messages m
    JOIN users u ON m.sender_id = u.user_id
    WHERE m.receiver_id = ? AND m.is_read = 0
    ORDER BY m.sent_time ASC
    ''', (receiver_id,))
    
    messages = cursor.fetchall()
    
    # Помечаем сообщения как прочитанные
    if messages:
        cursor.execute('''
        UPDATE messages SET is_read = 1 
        WHERE receiver_id = ? AND is_read = 0
        ''', (receiver_id,))
        conn.commit()
    
    conn.close()
    return [dict(msg) for msg in messages]

def add_romantic_achievement(user_id):
    """Добавляет достижение 'Романтик'"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем, есть ли уже это достижение
        cursor.execute('''
        SELECT 1 FROM user_achievements 
        WHERE user_id = ? AND achievement_id = 1
        ''', (user_id,))
        
        if not cursor.fetchone():
            # Присваиваем достижение
            cursor.execute('''
            INSERT INTO user_achievements (user_id, achievement_id) 
            VALUES (?, 1)
            ''', (user_id,))
            conn.commit()
            logger.info(f"Пользователь {user_id} получил достижение 'Романтик'")
            return True
        return False
    except Exception as e:
        logger.error(f"Ошибка добавления достижения: {str(e)}")
        return False
    finally:
        conn.close()

def add_cute_action(user_id, action_type):
    """Добавляет действие милого взаимодействия в базу данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем, есть ли уже это достижение
        cursor.execute('''
        SELECT COUNT(*) as count FROM cute_actions 
        WHERE user_id = ? AND action_type = ?
        ''', (user_id, action_type))
        count_row = cursor.fetchone()
        count = count_row['count'] if count_row else 0
        
        # Добавляем действие
        cursor.execute('''
        INSERT INTO cute_actions (user_id, action_type) 
        VALUES (?, ?)
        ''', (user_id, action_type))
        conn.commit()
        
        # Проверяем и добавляем достижения
        achievement_id = None
        if action_type == "kiss" and count + 1 >= 5:
            achievement_id = 6  # Целовальник
        elif action_type == "hug" and count + 1 >= 10:
            achievement_id = 7  # Обнимашка
        elif action_type == "pat" and count + 1 >= 5:
            achievement_id = 8  # Ласкатель
            
        if achievement_id:
            # Проверяем, есть ли уже это достижение
            cursor.execute('''
            SELECT 1 FROM user_achievements 
            WHERE user_id = ? AND achievement_id = ?
            ''', (user_id, achievement_id))
            
            if not cursor.fetchone():
                # Присваиваем достижение
                cursor.execute('''
                INSERT INTO user_achievements (user_id, achievement_id) 
                VALUES (?, ?)
                ''', (user_id, achievement_id))
                conn.commit()
                logger.info(f"Пользователь {user_id} получил достижение {achievement_id}")
        
        return True
    except sqlite3.OperationalError:
        # Если таблицы не существует, создаем ее
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS cute_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            action_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        conn.commit()
        return add_cute_action(user_id, action_type)
    except Exception as e:
        logger.error(f"Ошибка добавления действия: {str(e)}")
        return False
    finally:
        conn.close()

# ========================
#  АНИМАЦИЯ СЕРДЦА
# ========================
async def safe_edit_message(context, chat_id, message_id, text, reply_markup=None):
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Ошибка редактирования: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка редактирования: {str(e)}")

async def animate_hearts(context: ContextTypes.DEFAULT_TYPE):
    try:
        job = context.job
        frame = next(job.data['frame_iterator'])
        
        await safe_edit_message(
            context,
            job.data['chat_id'],
            job.data['message_id'],
            f"{frame}\nЯ тебя люблю <3",
            job.data['reply_markup']
        )
                
    except BadRequest as e:
        if "Message to edit not found" in str(e):
            logger.warning("Сообщение удалено, останавливаю анимацию")
            job.schedule_removal()
            chat_id = job.data['chat_id']
            if chat_id in animation_jobs:
                animation_jobs.pop(chat_id, None)
    except Exception as e:
        logger.error(f"Ошибка анимации: {str(e)}")
        job.schedule_removal()
        chat_id = job.data['chat_id']
        if chat_id in animation_jobs:
            animation_jobs.pop(chat_id, None)

async def send_heart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    register_user(user)  # Регистрируем пользователя
    
    # Останавливаем предыдущую анимацию, если есть
    if chat_id in animation_jobs:
        old_job = animation_jobs[chat_id]
        old_job.schedule_removal()
        animation_jobs.pop(chat_id, None)
        await asyncio.sleep(0.5)  # Даем время на остановку
    
    # Создаем клавиатуру для остановки
    keyboard = [[InlineKeyboardButton("🛑 Остановить анимацию", callback_data="stop_animation")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем начальное сообщение
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text="❤️\nЯ тебя люблю <3",
        reply_markup=reply_markup
    )
    
    # Создаем итератор кадров
    frame_iterator = itertools.cycle(HEART_ANIMATION_FRAMES)
    
    # Запускаем анимацию
    job = context.job_queue.run_repeating(
        animate_hearts,
        interval=0.8,
        first=0,
        data={
            'frame_iterator': frame_iterator,
            'chat_id': chat_id,
            'message_id': msg.message_id,
            'reply_markup': reply_markup
        },
        name=f"heart_anim_{chat_id}"
    )
    
    # Сохраняем ссылку на задание
    animation_jobs[chat_id] = job
    
    # Добавляем достижение "Романтик"
    achievement_added = add_romantic_achievement(user.id)
    if achievement_added:
        await context.bot.send_message(
            chat_id=chat_id,
            text="🏆 Вы получили новое достижение: 'Романтик'!\n"
                 "💖 За запуск анимации сердца"
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="💖 Анимация запущена! Нажмите кнопку, чтобы остановить."
        )

async def stop_animation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    
    if chat_id in animation_jobs:
        job = animation_jobs[chat_id]
        job.schedule_removal()
        animation_jobs.pop(chat_id, None)
        
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=query.message.message_id
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text="⏹️ Анимация остановлена"
            )
        except BadRequest:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⏹️ Анимация остановлена"
            )
    else:
        await query.edit_message_text("❌ Анимация уже остановлена")

# ========================
#  СОВМЕСТИМОСТЬ СЕРДЕЦ
# ========================
async def start_compatibility(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "💑 *Проверьте вашу совместимость с партнером!*\n\n"
            "Используйте: /compatibility @username\n"
            "Пример: /compatibility @username_любимого",
            parse_mode="Markdown"
        )
        return
        
    username = args[0].lstrip('@').strip().lower()
    if not username:
        await update.message.reply_text("Укажите username после команды: /compatibility @username")
        return
    
    partner_id = find_user_id(username)
    if not partner_id:
        await update.message.reply_text(
            f"Пользователь @{username} не найден.\n"
            "Он должен сначала отправить боту любое сообщение."
        )
        return
    
    if user.id == partner_id:
        await update.message.reply_text("Нельзя проверить совместимость с самим собой! 😉")
        return
        
    # Получаем информацию о пользователях
    user1_info = get_user_info(user.id)
    user2_info = get_user_info(partner_id)
    
    user1_name = user1_info['full_name'] or user1_info['first_name'] if user1_info else user.first_name
    user2_name = user2_info['full_name'] or user2_info['first_name'] if user2_info else f"Пользователь {partner_id}"
    
    # Создаем анимированный тест совместимости
    message = await update.message.reply_text(
        f"🔮 *Расчет совместимости*\n\n"
        f"{user1_name} ❤️ {user2_name}\n\n"
        "▰▰▰▰▰▰▰▰▰ 0%",
        parse_mode="Markdown"
    )
    
    # Запускаем анимацию расчета
    context.job_queue.run_once(
        calculate_compatibility, 
        3, 
        data={
            'chat_id': update.effective_chat.id,
            'message_id': message.message_id,
            'user1_id': user.id,
            'user2_id': partner_id,
            'user1_name': user1_name,
            'user2_name': user2_name
        }
    )

async def calculate_compatibility(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    
    # Генерируем "результат" совместимости (от 70% до 99% для положительного эффекта)
    compatibility = random.randint(70, 99)
    
    # Создаем прогресс бар
    progress = "🟥" * 10
    progress_bar = progress[:compatibility//10].replace("🟥", "🟩") + progress[compatibility//10:]
    
    # Генерируем романтичное описание
    descriptions = [
        "Ваши сердца бьются в унисон!",
        "Идеальное сочетание душ!",
        "Небеса предназначили вас друг для друга!",
        "Ваша связь особенная и уникальная!",
        "Настоящая любовь, которая преодолеет все преграды!"
    ]
    
    # Обновляем сообщение с результатом
    await context.bot.edit_message_text(
        chat_id=data['chat_id'],
        message_id=data['message_id'],
        text=(
            f"💖 *Результат совместимости!*\n\n"
            f"{data['user1_name']} ❤️ {data['user2_name']}\n\n"
            f"▰{progress_bar}▰ {compatibility}%\n\n"
            f"_{random.choice(descriptions)}_"
        ),
        parse_mode="Markdown"
    )
    
    # Отправляем партнеру уведомление (если это не бот)
    if data['user2_id'] != 'bot':
        try:
            await context.bot.send_message(
                chat_id=data['user2_id'],
                text=(
                    f"💌 {data['user1_name']} проверил(а) вашу совместимость!\n\n"
                    f"Результат: {compatibility}%!\n"
                    f"_{random.choice(descriptions)}_"
                ),
                parse_mode="Markdown"
            )
        except:
            pass

# ========================
#  СИСТЕМА СООБЩЕНИЙ
# ========================
async def send_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)  # Регистрируем пользователя
    
    # Проверяем формат команды
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "✉️ *Как отправить сообщение:*\n"
            "Используйте: /msg @username текст сообщения\n"
            "Пример: /msg @john Привет! Как дела?",
            parse_mode="Markdown"
        )
        return
        
    # Извлекаем username и текст сообщения
    username = context.args[0].lstrip('@').strip().lower()
    message_text = ' '.join(context.args[1:])
    
    # Находим пользователя
    receiver_id = find_user_id(username)
    if not receiver_id:
        await update.message.reply_text(f"Пользователь @{username} не найден.")
        return
        
    if user.id == receiver_id:
        await update.message.reply_text("Нельзя отправить сообщение самому себе!")
        return
        
    # Сохраняем сообщение в базе
    add_message(user.id, receiver_id, message_text)
    
    # Получаем информацию об отправителе
    sender_info = get_user_info(user.id)
    sender_name = sender_info['full_name'] or sender_info['first_name'] if sender_info else user.first_name
    
    # Отправляем уведомление получателю
    try:
        await context.bot.send_message(
            chat_id=receiver_id,
            text=f"💌 У вас новое сообщение от {sender_name}!\n"
                 f"Используйте /mymessages чтобы прочитать его."
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {str(e)}")
        await update.message.reply_text("❌ Не удалось отправить уведомление. Пользователь заблокировал бота?")
        return
        
    await update.message.reply_text("✅ Сообщение отправлено!")

async def show_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)  # Регистрируем пользователя
    
    # Получаем непрочитанные сообщения
    messages = get_unread_messages(user.id)
    
    if not messages:
        await update.message.reply_text("📭 У вас нет новых сообщений.")
        return
        
    # Формируем ответ
    response = "📬 *Ваши сообщения:*\n\n"
    for i, msg in enumerate(messages, 1):
        response += (
            f"{i}. От: {msg['first_name']} (@{msg['username']})\n"
            f"Сообщение: {msg['message_text']}\n\n"
        )
    
    await update.message.reply_text(response, parse_mode="Markdown")

# ========================
#  ДОСТИЖЕНИЯ
# ========================
async def show_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)  # Регистрируем пользователя
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT a.id, a.name, a.description, ua.unlocked_at 
    FROM user_achievements ua
    JOIN achievements a ON ua.achievement_id = a.id
    WHERE ua.user_id = ?
    ORDER BY ua.unlocked_at DESC
    ''', (user.id,))
    
    achievements = cursor.fetchall()
    conn.close()
    
    if not achievements:
        await update.message.reply_text("🎖️ У вас пока нет достижений.")
        return
        
    # Форматируем ответ
    response = "🏆 *Ваши достижения:*\n\n"
    for ach in achievements:
        unlocked_date = datetime.strptime(ach['unlocked_at'], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
        response += f"• *{ach['name']}* - {ach['description']} ({unlocked_date})\n\n"
    
    await update.message.reply_text(response, parse_mode="Markdown")

# ========================
#  МИЛЫЕ ВЗАИМОДЕЙСТВИЯ
# ========================
async def send_cute_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action_type):
    user = update.effective_user
    register_user(user)
    
    # Проверяем формат команды
    if not context.args:
        action_info = CUTE_ACTIONS.get(action_type, {})
        description = action_info.get('description', action_type)
        
        await update.message.reply_text(
            f"💞 *{description}*\n\n"
            f"Используйте: /{action_type} @username\n"
            f"Пример: /{action_type} @имя_любимого",
            parse_mode="Markdown"
        )
        return
        
    # Извлекаем username
    username = context.args[0].lstrip('@').strip().lower()
    if not username:
        await update.message.reply_text(f"Укажите username после команды: /{action_type} @username")
        return
    
    # Находим пользователя
    receiver_id = find_user_id(username)
    if not receiver_id:
        await update.message.reply_text(f"Пользователь @{username} не найден.")
        return
        
    if user.id == receiver_id:
        # Особое сообщение для себя
        messages = {
            "kiss": "💋 Вы послали поцелуй самому себе!",
            "hug": "🤗 Вы обняли себя!",
            "pat": "🥰 Вы погладили себя по головке!",
            "cuddle": "🫂 Вы прижались к себе!",
            "love": "💌 Вы признались в любви себе!",
            "blush": "😊 Вы смутились!",
            "smile": "😄 Вы улыбнулись себе!",
            # Новые действия для себя
            "scratch": "🐾 Вы почесали себя за ушком!",
            "bite": "😋 Вы укусили себя!",
            "hickey": "💋 Вы оставили себе засос!",
            "carry": "👑 Вы взяли себя на ручки!",
            "superhug": "🫂 Вы крепко обняли себя!",
            "praise": "🌟 Вы похвалили себя!",
            "lick": "👅 Вы лизнули себя!",
            "pinch": "🤏 Вы ущипнули себя!"
        }
        gif_url = random.choice(CUTE_ACTIONS.get(action_type, {}).get('gifs', []))
        
        try:
            if gif_url:
                await context.bot.send_animation(
                    chat_id=update.effective_chat.id,
                    animation=gif_url,
                    caption=messages.get(action_type, "Действие выполнено!")
                )
            else:
                await update.message.reply_text(messages.get(action_type, "Действие выполнено!"))
        except Exception as e:
            logger.error(f"Ошибка отправки гифки: {str(e)}")
            await update.message.reply_text(messages.get(action_type, "Действие выполнено!"))
        return
    
    # Получаем информацию об участниках
    sender_info = get_user_info(user.id)
    receiver_info = get_user_info(receiver_id)
    
    sender_name = sender_info['full_name'] if sender_info and sender_info['full_name'] else user.first_name
    receiver_name = receiver_info['full_name'] if receiver_info and receiver_info['full_name'] else f"Пользователь {receiver_id}"
    
    # Выбираем случайную гифку
    action_info = CUTE_ACTIONS.get(action_type, {})
    gif_url = random.choice(action_info.get('gifs', [])) if action_info else None
    
    # Сообщения для разных действий
    messages = {
        "kiss": f"💋 {sender_name} послал(а) поцелуй {receiver_name}!",
        "hug": f"🤗 {sender_name} обнял(а) {receiver_name}!",
        "pat": f"🥰 {sender_name} погладил(а) по головке {receiver_name}!",
        "cuddle": f"🫂 {sender_name} прижался(ась) к {receiver_name}!",
        "love": f"💌 {sender_name} признался(ась) в любви {receiver_name}!",
        "blush": f"😊 {sender_name} смутил(а) {receiver_name}!",
        "smile": f"😄 {sender_name} подарил(а) улыбку {receiver_name}!",
        # Новые действия
        "scratch": f"🐾 {sender_name} почесал(а) за ушком {receiver_name}!",
        "bite": f"😋 {sender_name} укусил(а) {receiver_name}!",
        "hickey": f"💋 {sender_name} оставил(а) засос {receiver_name}!",
        "carry": f"👑 {sender_name} взял(а) на ручки {receiver_name}!",
        "superhug": f"🫂 {sender_name} крепко обнял(а) {receiver_name}!",
        "praise": f"🌟 {sender_name} похвалил(а) {receiver_name}!",
        "lick": f"👅 {sender_name} лизнул(а) {receiver_name}!",
        "pinch": f"🤏 {sender_name} ущипнул(а) {receiver_name}!"
    }
    
    action_message = messages.get(action_type, f"{sender_name} отправил(а) действие {action_type} {receiver_name}")
    
    # Отправляем действие
    try:
        if gif_url:
            await context.bot.send_animation(
                chat_id=receiver_id,
                animation=gif_url,
                caption=action_message
            )
            
            # Отправляем подтверждение отправителю
            await context.bot.send_animation(
                chat_id=user.id,
                animation=gif_url,
                caption=f"Вы отправили: {action_message}"
            )
        else:
            await context.bot.send_message(
                chat_id=receiver_id,
                text=action_message
            )
            await update.message.reply_text(f"✅ Действие отправлено: {action_message}")
            
    except Exception as e:
        logger.error(f"Ошибка отправки действия: {str(e)}")
        await update.message.reply_text(f"❌ Не удалось отправить действие. Пользователь заблокировал бота?")
        return
        
    # Добавляем в статистику
    add_cute_action(user.id, action_type)

# ========================
#  ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ (ОБНОВЛЕНО)
# ========================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)  # Регистрируем пользователя при любом сообщении
    text = update.message.text.lower().strip()
    
    # Обработка текстовых команд
    if text in ["старт", "start"]:
        await start(update, context)
    elif text in ["помощь", "help"]:
        await help_command(update, context)
    elif text in ["сердце", "heart"]:
        await send_heart(update, context)
    elif text.startswith("совместимость "):
        username = text[14:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await start_compatibility(update, context)
    elif text.startswith("сообщение "):
        parts = text[10:].split(" ", 1)
        if len(parts) > 1:
            username = parts[0].strip()
            message_text = parts[1].strip()
            if username.startswith("@"):
                username = username[1:]
            context.args = [username, message_text]
            await send_message(update, context)
    # Обработка милых действий через текст
    elif text.startswith("поцелуй "):
        username = text[8:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "kiss")
    elif text.startswith("обнять "):
        username = text[7:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "hug")
    elif text.startswith("погладить "):
        username = text[10:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "pat")
    elif text.startswith("прижаться "):
        username = text[10:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "cuddle")
    elif text.startswith("люблю "):
        username = text[6:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "love")
    elif text.startswith("смутить "):
        username = text[8:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "blush")
    elif text.startswith("улыбнуться "):
        username = text[11:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "smile")
    # Новые текстовые команды
    elif text.startswith("почесать "):
        username = text[9:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "scratch")
    elif text.startswith("укусить "):
        username = text[8:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "bite")
    elif text.startswith("засос "):
        username = text[6:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "hickey")
    elif text.startswith("взять на руки "):
        username = text[14:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "carry")
    elif text.startswith("крепко обнять "):
        username = text[14:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "superhug")
    elif text.startswith("похвалить "):
        username = text[10:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "praise")
    elif text.startswith("лизнуть "):
        username = text[8:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "lick")
    elif text.startswith("ущипнуть "):
        username = text[9:].strip()
        if username.startswith("@"):
            username = username[1:]
        context.args = [username]
        await send_cute_action(update, context, "pinch")

# ========================
#  ОСНОВНЫЕ КОМАНДЫ (ОБНОВЛЕНО)
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)  # Регистрируем пользователя
    
    welcome_message = (
        "💖 *Добро пожаловать в Мини-сырка!*\n\n"
        "Я бот для романтического общения и выражения чувств! Вот что я умею:\n\n"
        "✨ *Основные команды:*\n"
        "/heart - Красивая анимация сердца ❤️\n"
        "/compatibility @username - Проверить совместимость 💑\n\n"
        "💌 *Сообщения:*\n"
        "/msg @username текст - Отправить анонимное сообщение ✉️\n"
        "/mymessages - Проверить свои сообщения 📬\n\n"
        "🏆 *Достижения:*\n"
        "/achievements - Ваши достижения\n\n"
        "💞 *Милые взаимодействия:*\n"
        "/kiss @username - Послать поцелуй 💋\n"
        "/hug @username - Обнять 🤗\n"
        "/pat @username - Погладить по головке 🥰\n"
        "/cuddle @username - Прижаться 🫂\n"
        "/love @username - Признаться в любви 💌\n"
        "/blush @username - Смутить 😊\n"
        "/smile @username - Улыбнуться 😄\n"
        # Новые команды
        "/scratch @username - Почесать за ушком 🐾\n"
        "/bite @username - Легкий укус 😋\n"
        "/hickey @username - Оставить засос 💋\n"
        "/carry @username - Взять на ручки 👑\n"
        "/superhug @username - Крепкие объятия 🫂\n"
        "/praise @username - Похвалить 🌟\n"
        "/lick @username - Лизнуть 👅\n"
        "/pinch @username - Ущипнуть 🤏\n\n"
        "Начните с /heart для красивой анимации!"
    )
    
    await update.message.reply_text(welcome_message, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)  # Регистрируем пользователя
    
    help_text = (
        "ℹ️ *Помощь по Мини-сырку*\n\n"
        "🔹 *Основные команды:*\n"
        "/start - Начало работы\n"
        "/help - Эта справка\n"
        "/heart - Анимация сердца\n\n"
        "🔹 *Совместимость:*\n"
        "/compatibility @username - Проверить совместимость\n\n"
        "🔹 *Сообщения:*\n"
        "/msg @username текст - Отправить сообщение\n"
        "/mymessages - Проверить входящие\n\n"
        "🔹 *Достижения:*\n"
        "/achievements - Показать ваши достижения\n\n"
        "🔹 *Милые взаимодействия:*\n"
        "/kiss @username - Послать поцелуй\n"
        "/hug @username - Отправить объятия\n"
        "/pat @username - Погладить по головке\n"
        "/cuddle @username - Прижаться\n"
        "/love @username - Признаться в любви\n"
        "/blush @username - Смутить\n"
        "/smile @username - Улыбнуться\n"
        # Новые команды
        "/scratch @username - Почесать за ушком\n"
        "/bite @username - Легкий укус\n"
        "/hickey @username - Оставить засос\n"
        "/carry @username - Взять на ручки\n"
        "/superhug @username - Крепкие объятия\n"
        "/praise @username - Похвалить\n"
        "/lick @username - Лизнуть\n"
        "/pinch @username - Ущипнуть\n\n"
        "По всем вопросам обращайтесь к Сырку"
    )
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ========================
#  ОСНОВНАЯ ФУНКЦИЯ
# ========================
def main() -> None:
    # Инициализация базы данных
    init_db()
    
    # Токен вашего бота
    TOKEN = "7964175947:AAFruKjz_ks7oyGhgw0iZ2bGtRBj1jwm0OE"
    
    # Настройка запросов с увеличенными таймаутами
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0
    )
    
    application = Application.builder().token(TOKEN).request(request).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("heart", send_heart))
    application.add_handler(CommandHandler("compatibility", start_compatibility))
    application.add_handler(CommandHandler("msg", send_message))
    application.add_handler(CommandHandler("mymessages", show_messages))
    application.add_handler(CommandHandler("achievements", show_achievements))
    
    # Обработчики милых взаимодействий (включая новые)
    for action in CUTE_ACTIONS.keys():
        application.add_handler(CommandHandler(action, lambda update, context, act=action: send_cute_action(update, context, act)))
    
    # Обработчики колбэков
    application.add_handler(CallbackQueryHandler(stop_animation_callback, pattern=r"^stop_animation$"))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()
