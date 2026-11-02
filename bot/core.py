from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes
)
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
from django.db import transaction
import django
import os
import sys
from asgiref.sync import sync_to_async
import asyncio
from telegram.error import Forbidden, BadRequest, TimedOut
from telegram import Bot
from telegram import InputMediaPhoto, InputMediaVideo
from botapp.models import UserAdStat, UserAdView, Ad
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot import legal as legal_texts

# Добавляем путь к корню проекта (/root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Добавляем путь к папке Django-проекта (/root/gymbros_admin)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gymbros_admin"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gymbros_admin.gymbros_admin.settings")
django.setup()  # Инициализация Django



# Загрузка переменных окружения
load_dotenv()

# Токен бота
TOKEN = os.getenv("TOKEN")

# Токен бота для уведомлений
NOTIFICATION_BOT_TOKEN = os.getenv("NOTIFICATION_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# Данные для подключения к БД
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "sslmode": os.getenv("DB_SSLMODE", "require"),
}

# Состояния для ConversationHandler
(
    NAME, PHOTO, AGE, GENDER, PREFERRED_GENDER, CITY, EXPERIENCE, 
    DESCRIPTION, GYM_NAME, GYM_STREET, TOGGLE_BADGE, CONSENT
) = range(12)

async def get_user_from_db(user_id, context):
    """Получаем данные пользователя из таблицы users"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT u.*, c.name as city_name 
            FROM users u
            LEFT JOIN cities c ON u.city_id = c.id
            WHERE u.telegram_id = %s
        """, [user_id])
        
        columns = [desc[0] for desc in cursor.description]
        result = cursor.fetchone()
        
        if result:
            user_data = dict(zip(columns, result))
            # Получаем фото из таблицы user_photos
            photos = await get_user_photos(user_id)
            if photos:
                user_data['photos'] = photos
                user_data['photo'] = photos[0]  # Первое фото для обратной совместимости (если нужно)
            # Используем сохраненное название города из context, если оно есть
            if 'city' in context.user_data:
                user_data['city_name'] = context.user_data['city']
                print('user_data:', user_data)
            return user_data
        return None
    except Exception as e:
        print(f"Ошибка при получении данных пользователя: {e}")
        return None
    finally:
        if conn:
            cursor.close()
            conn.close()

# Модифицируем функцию update_user_in_db
async def update_user_in_db(user_id, update_data):
    """Обновляем данные пользователя в таблице users"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Удаляем поле photo из update_data, так как оно теперь хранится в другой таблице
        if 'photo' in update_data:
            del update_data['photo']
        
        # Формируем динамический SQL запрос
        set_clauses = []
        values = []
        
        for field, value in update_data.items():
            if field == 'city_id':
                set_clauses.append(sql.SQL("city_id = {}").format(sql.Literal(value)))
            elif field == 'video':
                set_clauses.append(sql.SQL("video = {}").format(sql.Literal(value)))
            elif field == 'name':
                set_clauses.append(sql.SQL("name = {}").format(sql.Literal(value)))
            elif field == 'age':
                set_clauses.append(sql.SQL("age = {}").format(sql.Literal(value)))
            elif field == 'gender':
                set_clauses.append(sql.SQL("gender = {}").format(sql.Literal(value)))
            elif field == 'preferred_gender':
                set_clauses.append(sql.SQL("preferred_gender = {}").format(sql.Literal(value)))
            elif field == 'experience':
                set_clauses.append(sql.SQL("experience = {}").format(sql.Literal(value)))
            elif field == 'description':
                set_clauses.append(sql.SQL("description = {}").format(sql.Literal(value)))
            elif field == 'gym_name':
                set_clauses.append(sql.SQL("gym_name = {}").format(sql.Literal(value)))
            elif field == 'gym_street':
                set_clauses.append(sql.SQL("gym_street = {}").format(sql.Literal(value)))
            elif field == 'is_viewed':
                set_clauses.append(sql.SQL("is_viewed = {}").format(sql.Literal(value)))
        
        if not set_clauses:
            return False
            
        # Получаем ID пользователя из базы по telegram_id
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
        user_db_id = cursor.fetchone()
        if not user_db_id:
            print(f"Пользователь с telegram_id={user_id} не найден")
            return False
            
        user_db_id = user_db_id[0]
        values.append(user_db_id)
        
        query = sql.SQL("""
            UPDATE users 
            SET {set_clauses}
            WHERE id = %s
        """).format(
            set_clauses=sql.SQL(', ').join(set_clauses)
        )
        
        print(f"Выполняем запрос: {query.as_string(conn)} с параметрами: {user_db_id}")
        cursor.execute(query, [user_db_id])
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Ошибка при обновлении данных пользователя: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_city_id(city_name):
    """Получаем ID города по названию или альтернативным названиям (регистронезависимо)"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Проверяем все варианты названий из таблицы
        cursor.execute("""
            SELECT id FROM cities 
            WHERE LOWER(name) = LOWER(%s)
               OR LOWER(secondName) = LOWER(%s)
               OR LOWER(thirdName) = LOWER(%s)
               OR LOWER(fourthName) = LOWER(%s)
            LIMIT 1
        """, [city_name, city_name, city_name, city_name])
        
        result = cursor.fetchone()
        return result[0] if result else None
        
    except Exception as e:
        print(f"Ошибка при поиске города: {e}")
        return None
    finally:
        if conn:
            cursor.close()
            conn.close()

# Модифицируем функцию save_user_to_db
async def save_user_to_db(user_data, context, update: Update = None, referrer_id=None):
    """Функция сохранения пользователя с учетом реферала"""
    print("Сохраняемые данные:", user_data)
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        username = update.effective_user.username if update and update.effective_user else None
        
        if 'name' not in user_data:
            raise ValueError("Отсутствует обязательное поле: name")
        
        # Определяем значения для всех полей
        experience_value = user_data.get('experience')
        description_value = user_data.get('description')
        gym_street_value = user_data.get('gym_street')
        video_value = user_data.get('video')
        
        consent_at = user_data.get('consent_accepted_at') or legal_texts.utc_now()
        consent_version = user_data.get('consent_version') or legal_texts.CONSENT_VERSION

        cursor.execute("""
            INSERT INTO users (
                telegram_id, username, name, age, gender,
                preferred_gender, city_id, experience, description,
                gym_name, gym_street, video, is_viewed,
                consent_accepted_at, consent_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s)
            ON CONFLICT (telegram_id) 
            DO UPDATE SET
                username = EXCLUDED.username,
                name = EXCLUDED.name,
                age = EXCLUDED.age,
                gender = EXCLUDED.gender,
                preferred_gender = EXCLUDED.preferred_gender,
                city_id = EXCLUDED.city_id,
                experience = COALESCE(EXCLUDED.experience, NULL),
                description = COALESCE(EXCLUDED.description, NULL),
                gym_name = EXCLUDED.gym_name,
                gym_street = COALESCE(EXCLUDED.gym_street, NULL),
                video = COALESCE(EXCLUDED.video, NULL),
                is_viewed = FALSE,
                consent_accepted_at = COALESCE(EXCLUDED.consent_accepted_at, users.consent_accepted_at),
                consent_version = COALESCE(EXCLUDED.consent_version, users.consent_version)
            RETURNING id
        """, (
            context.user_data['user_id'],
            username,
            user_data['name'],
            user_data.get('age'),
            user_data.get('gender'),
            user_data.get('preferred_gender'),
            user_data.get('city_id'),
            experience_value,
            description_value,
            user_data.get('gym_name'),
            gym_street_value,
            video_value,
            consent_at,
            consent_version,
        ))
        
        result = cursor.fetchone()
        user_db_id = result[0] if result else None
        
        # Если есть реферер, сохраняем связь
        if referrer_id and user_db_id:
            cursor.execute("""
                INSERT INTO referrals (referrer_id, referred_id)
                VALUES (%s, %s)
                ON CONFLICT (referred_id) DO NOTHING
            """, (referrer_id, user_db_id))
        
        conn.commit()
        return user_db_id
    except Exception as e:
        print(f"Ошибка при сохранении пользователя: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

async def clear_user_video(user_id: int) -> bool:
    """Очищает видео пользователя из базы данных"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("UPDATE users SET video = NULL WHERE telegram_id = %s", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка при очистке видео: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [["Создать анкету", "Использовать существующую"]], 
        resize_keyboard=True
    )

def get_edit_keyboard():
    return ReplyKeyboardMarkup([
        ["Изменить анкету", "Смотреть анкеты"],
        ["«Кто меня лайкнул»", "⚙️ Настройки"]  # Новая кнопка для VIP
    ], resize_keyboard=True)

def get_skip_keyboard():
    return ReplyKeyboardMarkup([["Оставить текущее"]], resize_keyboard=True)

# Добавляем функцию для клавиатуры выбора пола
def get_gender_keyboard():
    return ReplyKeyboardMarkup([["Парень", "Девушка"]], resize_keyboard=True)

# Добавляем функцию для клавиатуры выбора предпочтений
def get_preferred_gender_keyboard():
    return ReplyKeyboardMarkup([["Gym Bro", "Gym Girl", "Без разницы"]], resize_keyboard=True)

# Добавляем новую клавиатуру для пропуска
def get_skip_or_text_keyboard():
    return ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)

def get_experience_keyboard():
    return ReplyKeyboardMarkup([
        ["Новичок", "Продвинутый"],
        ["Профессионал"]  # Убрали кнопку "Пропустить"
    ], resize_keyboard=True)

# В функции get_edit_choice_keyboard добавьте новый пункт меню для статуса
def get_edit_choice_keyboard(user_data):
    """Возвращает клавиатуру для редактирования с новым пунктом для значка"""
    keyboard = [
        ["1. Имя", "2. Фото"],
        ["3. Возраст", "4. Пол"],
        ["5. Предпочтения", "6. Город"],
        ["7. Стаж", "8. Описание"],
        ["9. Название зала", "10. Улица зала"],
        ["11. Значок подписки"],  # Новая строка для значка
        ["✅ Завершить редактирование"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_gym_street_keyboard():
    """Клавиатура для пропуска ввода улицы зала"""
    return ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)

def get_edit_description_keyboard():
    """Клавиатура для редактирования описания с кнопкой 'Стереть'"""
    return ReplyKeyboardMarkup([["Стереть"], ["Пропустить"]], resize_keyboard=True)

def get_admin_profile_action_keyboard():
    return ReplyKeyboardMarkup([
        ["Пропустить", "Удалить анкету"]
    ], resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, есть ли реферальный код в аргументах команды /start
    referrer_id = None
    if context.args and context.args[0].startswith('ref'):
        try:
            referrer_id = int(context.args[0][3:])  # Извлекаем ID после 'ref'
            context.user_data['referrer_id'] = referrer_id  # Сохраняем в контексте
        except ValueError:
            pass
    
    # Если пользователь уже в процессе создания или редактирования анкеты
    if context.user_data.get('is_creating_profile'):
        await update.message.reply_text(
            "Вы уже начали создание анкеты. Пожалуйста, завершите его, прежде чем снова использовать /start."
        )
        return
    
    if context.user_data.get('is_editing_profile'):
        await update.message.reply_text(
            "Вы редактируете анкету. Завершите редактирование, прежде чем использовать /start."
        )
        return
    
    # Сохраняем telegram_id пользователя
    context.user_data['user_id'] = update.effective_user.id
    
    # Если есть реферальный код, сохраняем его в контексте
    if referrer_id:
        context.user_data['referrer_id'] = referrer_id
    
    # Проверяем, есть ли у пользователя анкета
    user_data = await get_user_from_db(context.user_data['user_id'], context)
    
    if user_data:
        # Если анкета есть, предлагаем выбор
        await update.message.reply_text(
            "Добро пожаловать в GymBros!\n\n" "У вас уже есть анкета. Что вы хотите сделать?",
            reply_markup=get_main_keyboard()
        )
    else:
        # Если анкеты нет, предлагаем только создание
        await update.message.reply_text(
            "🏋️‍♂️ GymBros – бот для поиска напарника для тренировок!\n\n"
            "🤝 Создавай анкету, ищи GymBro или GymGirl рядом и качайся вместе.\n\n"
            "Сервис для лиц 18+.\n"
            "Перед созданием анкеты потребуется согласие на обработку персональных данных "
            "(152-ФЗ). Документы: /privacy и /terms.\n\n"
            "Давайте создадим вашу анкету.",
            reply_markup=ReplyKeyboardMarkup([["Создать анкету"]], resize_keyboard=True)
        )

# Добавляем обработчик для кнопки "Использовать существующую"
async def use_existing_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_username = update.effective_user.username  # Получаем текущий username
    
    # Получаем данные пользователя из базы
    user_data = await get_user_from_db(user_id, context)
    
    if not user_data:
        await update.message.reply_text(
            "У вас нет сохраненной анкеты. Сначала создайте её.",
            reply_markup=ReplyKeyboardMarkup([["Создать анкету"]], resize_keyboard=True)
        )
        return
    
    # Проверяем, совпадает ли username в базе с текущим
    if user_data.get('username') != current_username and current_username != 'gymbros_manager':

        # Обновляем username в базе данных
        conn = None
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE users 
                SET username = %s
                WHERE telegram_id = %s
            """, (current_username, user_id))
            
            conn.commit()
            
            # Обновляем username в полученных данных
            user_data['username'] = current_username
            print(f"Обновлен username для пользователя {user_id}: {current_username}")
        except Exception as e:
            print(f"Ошибка при обновлении username: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    
    # Сохраняем данные в контексте
    context.user_data.update(user_data)
    
    # Показываем меню редактирования/просмотра
    await update.message.reply_text(
        "Ваша анкета успешно загружена. Что вы хотите сделать?",
        reply_markup=get_edit_keyboard()
    )


def get_consent_keyboard():
    return ReplyKeyboardMarkup(
        [["✅ Согласен", "❌ Не согласен"]],
        resize_keyboard=True,
    )


async def begin_questionnaire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинаем создание анкеты с обязательного согласия (152-ФЗ)"""
    context.user_data['user_id'] = update.effective_user.id
    print('вызов begin_questionnaire')

    # Получаем текущее значение show_badge перед очисткой
    current_user_data = await get_user_from_db(context.user_data['user_id'], context)
    show_badge = current_user_data.get('show_badge', True) if current_user_data else True
    referrer_id = context.user_data.get('referrer_id')

    # Очищаем ВСЕ данные из предыдущей анкеты, кроме медиафайлов
    context.user_data.clear()
    context.user_data['user_id'] = update.effective_user.id  # Восстанавливаем user_id
    if referrer_id:
        context.user_data['referrer_id'] = referrer_id

    context.user_data['is_creating_profile'] = True

    # Явно инициализируем все поля, которые могут быть использованы
    context.user_data.update({
        'name': None,
        'age': None,
        'gender': None,
        'preferred_gender': None,
        'city_id': None,
        'city': None,
        'experience': None,
        'description': None,
        'gym_name': None,
        'gym_street': None,
        'video': None,
        'photos': [],
        'media': {'photos': [], 'video': None},
        'show_badge': show_badge  # Сохраняем текущее значение значка
    })

    await update.message.reply_text(
        legal_texts.consent_text(),
        parse_mode='HTML',
        reply_markup=get_consent_keyboard(),
        disable_web_page_preview=True,
    )
    return CONSENT


async def accept_consent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь принял согласие на обработку ПДн и подтвердил 18+"""
    context.user_data['consent_accepted_at'] = legal_texts.utc_now()
    context.user_data['consent_version'] = legal_texts.CONSENT_VERSION
    await update.message.reply_text(
        "Спасибо! Согласие принято.\n\nКак вас зовут?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NAME


async def decline_consent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отказ от согласия — анкету создать нельзя"""
    context.user_data.clear()
    await update.message.reply_text(
        "Без согласия на обработку персональных данных создать анкету нельзя.\n"
        "Вы всегда можете вернуться командой /start.\n\n"
        f"Документы: /privacy и /terms\nПоддержка: {legal_texts.operator_telegram()}",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END

async def get_city_canonical_name(city_id):
    """Получаем основное название города по ID"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM cities WHERE id = %s", [city_id])
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"Ошибка при получении названия города: {e}")
        return None
    finally:
        if conn:
            cursor.close()
            conn.close()

async def find_similar_cities(query):
    """Поиск похожих городов по любому из названий"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        query = f"%{query.lower()}%"
        cursor.execute("""
            SELECT name FROM cities 
            WHERE LOWER(name) LIKE LOWER(%s)
               OR LOWER(secondName) LIKE LOWER(%s)
               OR LOWER(thirdName) LIKE LOWER(%s)
               OR LOWER(fourthName) LIKE LOWER(%s)
            LIMIT 5
        """, [query, query, query, query])
        
        return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Ошибка при поиске похожих городов: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Теперь отправьте ваше фото/видео:")
    return PHOTO

async def get_user_photos(user_id):
    """Получает все фото пользователя из базы данных"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT photo FROM users WHERE telegram_id = %s
        """, (user_id,))
        
        result = cursor.fetchone()
        return [result[0]] if result and result[0] else []
    except Exception as e:
        print(f"Ошибка при получении фото пользователя: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            conn.close()

async def save_user_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает получение нового фото пользователя при редактировании"""
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото!")
        return False
    
    # Получаем file_id фото
    photo_file_id = update.message.photo[-1].file_id
    
    # Добавляем фото в список (не очищаем предыдущие)
    if 'photos' not in context.user_data:
        context.user_data['photos'] = []
    
    context.user_data['photos'].append(photo_file_id)
    
    # Проверяем, сколько фото уже добавлено
    if len(context.user_data['photos']) < 3:
        await update.message.reply_text(
            f"Фото {len(context.user_data['photos'])}/3 добавлено. "
            "Можно добавить еще фото или нажать «Далее» для продолжения.",
            reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
        )
    else:
        await update.message.reply_text(
            "Достигнут максимум (3 фото). Нажмите «Далее» для продолжения.",
            reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
        )
    
    return photo_file_id

async def save_user_photos(user_id: int, photo_file_ids: list) -> bool:
    """Сохраняет несколько фото пользователя в базу данных"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем ID пользователя из таблицы users
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
        user_db_id = cursor.fetchone()
        if not user_db_id:
            print(f"Пользователь с telegram_id={user_id} не найден")
            return False
            
        user_db_id = user_db_id[0]
        
        # Удаляем ВСЕ старые фото пользователя перед добавлением новых
        cursor.execute("DELETE FROM user_photos WHERE user_id = %s", (user_db_id,))
        
        # Вставляем новые фото с правильными позициями
        for position, photo_id in enumerate(photo_file_ids, 1):
            cursor.execute(
                "INSERT INTO user_photos (user_id, photo_id, position) VALUES (%s, %s, %s)",
                (user_db_id, photo_id, position)
            )
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка при сохранении фото пользователя: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_user_photos(user_id):
    """Получает все фото пользователя из базы данных"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT photo_id FROM user_photos 
            WHERE user_id = (
                SELECT id FROM users WHERE telegram_id = %s
            )
            ORDER BY position
        """, (user_id,))
        
        return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Ошибка при получении фото пользователя: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает получение фото или видео пользователя"""
    if 'media' not in context.user_data:
        context.user_data['media'] = {'photos': [], 'video': None}
    
    current_media = context.user_data['media']

    # Проверяем, были ли уже очищены старые медиафайлы
    if not context.user_data.get('media_cleared', False):
        await clear_user_photos(context.user_data['user_id'])
        await clear_user_video(context.user_data['user_id'])
        context.user_data['media_cleared'] = True
    
    if update.message.video:
        # Проверяем, есть ли уже видео
        if current_media['video']:
            await update.message.reply_text(
                "Вы уже добавили видео. Можно добавить только одно видео. ",
                reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
            )
            return PHOTO
        
        # Добавляем видео
        current_media['video'] = update.message.video.file_id
        total_media = len(current_media['photos']) + 1  # +1 за видео
        
        # Проверяем достигнут ли максимум (3 медиафайла)
        if total_media >= 3:
            await update.message.reply_text(
                "Достигнут максимум (3 медиафайла). Нажмите «Далее» для продолжения.",
                reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
            )
        else:
            await update.message.reply_text(
                f"Медиафайлов {total_media}/3 добавлено. Можно добавить еще фото или нажать «Далее» для продолжения.",
                reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
            )
        return PHOTO
    
    elif update.message.photo:
        # Проверяем общее количество медиафайлов (максимум 3)
        total_media = len(current_media['photos']) + (1 if current_media['video'] else 0)
        if total_media >= 3:
            await update.message.reply_text(
                "Медиафайлов 3/3 добавлено. Нажмите «Далее» для продолжения.",
                reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
            )
            return PHOTO
        
        # Добавляем фото
        photo_file_id = update.message.photo[-1].file_id
        current_media['photos'].append(photo_file_id)
        total_media = len(current_media['photos']) + (1 if current_media['video'] else 0)
        
        # Проверяем достигнут ли максимум
        if total_media >= 3:
            await update.message.reply_text(
                "Достигнут максимум (3 медиафайла). Нажмите «Далее» для продолжения.",
                reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
            )
        else:
            await update.message.reply_text(
                f"Медиафайлов {total_media}/3 добавлено. Можно добавить еще фото или нажать «Далее» для продолжения.",
                reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
            )
        return PHOTO
    
    elif update.message.text == "Далее":
        # Проверяем, есть ли хотя бы одно медиа
        if not current_media['photos'] and not current_media['video']:
            await update.message.reply_text(
                "Пожалуйста, добавьте хотя бы одно фото или видео перед продолжением."
            )
            return PHOTO
            
        await update.message.reply_text(
            "Сколько вам лет?",
            reply_markup=ReplyKeyboardRemove()
        )
        return AGE
    
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото или видео."
        )
        return PHOTO

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        age = int(update.message.text)
        if age < 18 or age > 100:
            raise ValueError
        context.user_data['age'] = age
        await update.message.reply_text(
            "Укажите ваш пол:",
            reply_markup=get_gender_keyboard()
        )
        return GENDER
    except ValueError:
        await update.message.reply_text(
            "Сервис доступен только с 18 лет. Введите возраст числом от 18 до 100."
        )
        return AGE
    
# Добавляем новую функцию для обработки пола
async def get_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем пол пользователя"""
    gender_text = update.message.text
    if gender_text == "Парень":
        context.user_data['gender'] = 1  # 1 для мужского
    elif gender_text == "Девушка":
        context.user_data['gender'] = 2  # 2 для женского
    else:
        await update.message.reply_text("Пожалуйста, выберите пол из предложенных вариантов")
        return GENDER
    
    await update.message.reply_text(
        "Кого вы предпочитаете в качестве напарника?",
        reply_markup=get_preferred_gender_keyboard()
    )
    return PREFERRED_GENDER

# Модифицируем функцию get_preferred_gender
async def get_preferred_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    preferred = update.message.text
    if preferred == "Gym Bro":
        context.user_data['preferred_gender'] = 1  # Сохраняем значение 1 для Gym Bro
    elif preferred == "Gym Girl":
        context.user_data['preferred_gender'] = 2  # Сохраняем значение 2 для Gym Girl
    elif preferred == "Без разницы":
        context.user_data['preferred_gender'] = 0  # Сохраняем значение 0 для "Без разницы"
    else:
        await update.message.reply_text("Пожалуйста, выберите вариант из предложенных")
        return PREFERRED_GENDER
    
    await update.message.reply_text(
        "В каком городе вы проживаете?",
        reply_markup=ReplyKeyboardRemove()
    )
    return CITY

# Модифицируем функцию get_city
async def get_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city_name = update.message.text
    city_id = await get_city_id(city_name)
    
    if city_id is None:
        await update.message.reply_text("Город не найден. Пожалуйста, введите корректное название города:")
        return CITY
    
    context.user_data['city'] = city_name
    context.user_data['city_id'] = city_id
    
    await update.message.reply_text(
        "Какой у вас стаж тренировок?",
        reply_markup=get_experience_keyboard()
    )
    return EXPERIENCE

# Модифицируем функцию get_experience
async def get_experience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем стаж тренировок с проверкой на соответствие предложенным вариантам"""
    user_input = update.message.text
    
    # Список допустимых вариантов ответа
    valid_options = [
        "Новичок",
        "Продвинутый",
        "Профессионал",
        "Пропустить"
    ]
    
    if user_input not in valid_options:
        await update.message.reply_text(
            "Пожалуйста, выберите вариант из предложенных",
            reply_markup=get_experience_keyboard()
        )
        return EXPERIENCE
    
    if user_input == "Пропустить":
        context.user_data['experience'] = None
    else:
        context.user_data['experience'] = user_input
    
    await update.message.reply_text(
        "Напишите краткое описание о себе (или нажмите «Пропустить»)",
        reply_markup=get_skip_or_text_keyboard()
    )
    return DESCRIPTION

# Модифицируем функцию get_description
async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Пропустить":
        context.user_data['description'] = None
    else:
        context.user_data['description'] = update.message.text
    
    await update.message.reply_text(
        "Введите название вашего зала:",
        reply_markup=ReplyKeyboardRemove()
    )
    return GYM_NAME

async def get_gym_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gym_name'] = update.message.text
    await update.message.reply_text(
        "На какой улице находится ваш зал? (или нажмите «Пропустить»)",
        reply_markup=get_gym_street_keyboard()  # Добавляем клавиатуру с кнопкой "Пропустить"
    )
    return GYM_STREET

# Модифицируем формирование анкеты в get_gym_street и edit_gym_street
async def get_gym_street(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем улицу зала или пропускаем"""
    if update.message.text == "Пропустить":
        context.user_data['gym_street'] = None
    else:
        context.user_data['gym_street'] = update.message.text

    # Всегда очищаем старые медиафайлы перед сохранением новых
    await clear_user_photos(context.user_data['user_id'])
    await clear_user_video(context.user_data['user_id'])

    if 'media' in context.user_data:
        # Сохраняем медиафайлы из временного хранилища
        context.user_data['video'] = context.user_data['media'].get('video')
        context.user_data['photos'] = context.user_data['media'].get('photos', [])[:3]

    # Получаем тип подписки пользователя и настройку значка
    subscription_type = await get_user_subscription(context.user_data['user_id'])
    show_badge = context.user_data.get('show_badge', True)  # Используем значение из контекста
    
    # Сначала сохраняем анкету в БД
    user_id = await save_user_to_db(context.user_data, context, update)
    
    if user_id:
        # Сохраняем новые фото, если они есть
        if 'photos' in context.user_data and context.user_data['photos']:
            await save_user_photos(context.user_data['user_id'], context.user_data['photos'])
        
        # Формируем текст анкеты с учетом подписки и настройки значка
        profile_text = ""
        
        if subscription_type == 1 and show_badge:  # Premium
            profile_text += " 🏆\n"
        elif subscription_type == 2 and show_badge:  # VIP
            profile_text += " 👑\n"
        else:
            profile_text += "\n"
            
        description_text = f"\n\n{context.user_data['description']}" if context.user_data.get('description') else ""
        experience_text = f"\n{context.user_data['experience']}" if context.user_data.get('experience') else ""
        gym_street_text = f", {context.user_data['gym_street']}" if context.user_data.get('gym_street') else ""

        profile_text += (
            f"{context.user_data['name']}, {context.user_data['age']}, {context.user_data['city']}\n"
            f"{context.user_data['gym_name']}{gym_street_text}"
            f"{experience_text}"
            f"{description_text}"
        )
        
        await update.message.reply_text(
            "✅ Ваша анкета успешно сохранена! Вот как она выглядит:",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Создаем медиагруппу
        media_group = []
        
        # Добавляем видео (если есть)
        if 'video' in context.user_data and context.user_data['video']:
            media_group.append(InputMediaVideo(context.user_data['video'], caption=profile_text))
        
        # Добавляем фото (если есть)
        if 'photos' in context.user_data and context.user_data['photos']:
            for photo in context.user_data['photos']:
                # Добавляем подпись только к первому элементу
                if not media_group:
                    media_group.append(InputMediaPhoto(photo, caption=profile_text))
                else:
                    media_group.append(InputMediaPhoto(photo))
        
        if media_group:
            try:
                await update.message.reply_media_group(media=media_group)
                await update.message.reply_text(
                    "Что вы хотите сделать дальше?",
                    reply_markup=get_edit_keyboard()
                )
            except Exception as e:
                print(f"Ошибка при отправке медиагруппы: {e}")
                await update.message.reply_text(
                    profile_text,
                    reply_markup=get_edit_keyboard()
                )

            # После показа анкеты спрашиваем про реферальный код
            return await ask_for_referral(update, context)
        else:
            await update.message.reply_text(
                profile_text,
                reply_markup=get_edit_keyboard()
            )
    else:
        await update.message.reply_text(
            "❌ Произошла ошибка при сохранении анкеты. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

    context.user_data.pop('is_creating_profile', None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.pop('is_creating_profile', None)
    context.user_data.pop('is_editing_profile', None)

    """Отмена создания/редактирования анкеты"""
    # Не очищаем медиафайлы при отмене
    await update.message.reply_text(
        "Создание анкеты отменено.",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

async def edit_questionnaire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса редактирования анкеты"""
    if 'user_id' not in context.user_data:
        await update.message.reply_text(
            "У вас нет анкеты. Сначала создайте её.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    
    context.user_data['is_editing_profile'] = True
    
    # Получаем данные из БД
    user_data = await get_user_from_db(context.user_data['user_id'], context)
    if not user_data:
        await update.message.reply_text(
            "Анкета не найдена. Создайте новую анкету.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    
    # Сохраняем текущие данные
    context.user_data.update({
        'current_data': user_data,
        'changes': {},
        'city': user_data.get('city_name')
    })
    
    await update.message.reply_text(
        "Выберите, что хотите изменить:",
        reply_markup=get_edit_choice_keyboard(user_data)
    )
    return EDIT_CHOICE

# Добавляем функцию для получения случайной рекламы
async def get_random_ad():
    """Получает случайную активную рекламу из БД"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT text, image_url FROM ads 
            WHERE is_active = TRUE
            ORDER BY RANDOM()
            LIMIT 1
        """)
        
        return cursor.fetchone()
    except Exception as e:
        print(f"Ошибка при получении рекламы: {e}")
        return None
    finally:
        if conn:
            cursor.close()
            conn.close()

# HTML-код рекламы
async def update_view_stats(user_id, context):
    """Обновляет статистику просмотров и показывает рекламу, которую пользователь еще не видел"""
    try:
        @sync_to_async
        def update_stats():
            from django.db import transaction
            from botapp.models import UserAdStat, UserAdView, Ad

            with transaction.atomic():
                try:
                    # Создаём или получаем статистику пользователя
                    stat, created = UserAdStat.objects.get_or_create(
                        user_id=user_id,
                        defaults={
                            'profiles_viewed': 0,
                            'ads_shown': 0
                        }
                    )

                    # Инициализируем счётчики, если они None
                    if stat.profiles_viewed is None:
                        stat.profiles_viewed = 0
                    if stat.ads_shown is None:
                        stat.ads_shown = 0

                    # Увеличиваем счётчик просмотров
                    stat.profiles_viewed += 1
                    stat.save()

                    # Показываем рекламу каждые N просмотров
                    if stat.profiles_viewed % 1 != 0:  # Можно изменить частоту показа
                        return None, stat

                    # Получаем ID всех рекламных объявлений, которые пользователь уже видел
                    viewed_ad_ids = set(UserAdView.objects.filter(
                        user_id=user_id
                    ).values_list('ad_id', flat=True))

                    # Получаем случайное рекламное объявление, которое пользователь еще не видел
                    ad = Ad.objects.filter(
                        is_active=True
                    ).exclude(
                        id__in=viewed_ad_ids
                    ).order_by('?').first()

                    if ad:
                        # Записываем факт просмотра
                        UserAdView.objects.create(
                            user_id=user_id,
                            ad=ad
                        )
                        stat.ads_shown = (stat.ads_shown or 0) + 1
                        stat.save()
                        return ad, stat
                    return None, stat

                except Exception as e:
                    print(f"Ошибка в update_stats: {e}")
                    return None, None

        ad, stat = await update_stats()

        if ad:
            try:
                skip_keyboard = ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
                
                if ad.telegram_file_id:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=ad.telegram_file_id,
                        caption=ad.text,
                        reply_markup=skip_keyboard,
                        parse_mode='HTML'
                    )
                elif ad.image:
                    with open(ad.image.path, 'rb') as photo_file:
                        message = await context.bot.send_photo(
                            chat_id=user_id,
                            photo=photo_file,
                            caption=ad.text,
                            reply_markup=skip_keyboard,
                            parse_mode='HTML'
                        )
                        if message.photo:
                            ad.telegram_file_id = message.photo[-1].file_id
                            await sync_to_async(ad.save)()
                return True
            except Exception as e:
                print(f"Ошибка при отправке рекламы с фото: {e}")
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=ad.text,
                        reply_markup=skip_keyboard,
                        parse_mode='HTML',
                    )
                    return True
                except Exception as e:
                    print(f"Ошибка при отправке текстовой рекламы: {e}")
                    return False

        return False
    except Exception as e:
        print(f"Ошибка при обновлении статистики: {e}")
        return False
    


# ПРОСМОТР АНКЕТ ################################################################################

# Добавим новые состояния
VIEW_PROFILES, PROFILE_ACTION, EDIT_CHOICE, EDIT_SELECTED = range(11, 15)

# Модифицируем функцию get_potential_matches
async def get_potential_matches(user_id, context):
    """Получаем анкеты, которые подходят пользователю, с приоритетом для VIP и лайкнувших"""
    conn = None
    try:
        # Сначала получаем данные текущего пользователя
        user_data = await get_user_from_db(user_id, context)
        if not user_data:
            print("Данные текущего пользователя не найдены")
            return None
            
        # Проверяем лимит просмотров для пользователей без подписки
        subscription_type = await get_user_subscription(user_id)
        if subscription_type == 0:  # Без подписки
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            # Проверяем, нужно ли сбросить счетчик
            cursor.execute("""
                SELECT profile_views_today, last_profile_views_reset 
                FROM users 
                WHERE telegram_id = %s
            """, (user_id,))
            result = cursor.fetchone()
            
            if result:
                views_today, last_reset = result
                # Если прошло больше 24 часов или это первый просмотр
                if last_reset is None or (datetime.now() - last_reset).total_seconds() >= 86400:
                    # Сбрасываем счетчик
                    cursor.execute("""
                        UPDATE users 
                        SET profile_views_today = 0,
                            last_profile_views_reset = CURRENT_TIMESTAMP
                        WHERE telegram_id = %s
                    """, (user_id,))
                    conn.commit()
                    views_today = 0
                
                # Проверяем лимит (10 просмотров)
                if views_today >= 10:
                    return None
                
                # Увеличиваем счетчик просмотров
                cursor.execute("""
                    UPDATE users 
                    SET profile_views_today = profile_views_today + 1
                    WHERE telegram_id = %s
                """, (user_id,))
                conn.commit()
            
        # Остальной код функции остается без изменений
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Определяем предпочтения по полу
        preferred_gender = user_data.get('preferred_gender', 1)
        gender_condition = ""
        if preferred_gender == 1:  # Gym Bro
            gender_condition = "AND u.gender = 1"
        elif preferred_gender == 2:  # Gym Girl
            gender_condition = "AND u.gender = 2"
        
        # Получаем ID текущего пользователя в базе
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
        current_user_db_id = cursor.fetchone()
        if not current_user_db_id:
            print("Не удалось найти ID текущего пользователя в базе")
            return None
            
        current_user_db_id = current_user_db_id[0]
        
        # Новый запрос с правильным приоритетом:
        # 1. Пользователи, которые лайкнули текущего (взаимные лайки)
        # 2. VIP пользователи
        # 3. Остальные подходящие пользователи
        query = """
            WITH 
            -- Пользователи, которые лайкнули текущего пользователя
            liked_me AS (
                SELECT ua.user_id 
                FROM user_actions ua
                JOIN users u ON ua.user_id = u.id
                WHERE ua.target_user_id = %s AND ua.action = 1
                AND u.telegram_id != %s
                AND u.city_id = %s
                {gender_condition}
            ),
            
            -- Пользователи, которых текущий пользователь еще не лайкал/дизлайкал
            not_viewed AS (
                SELECT u.id
                FROM users u
                WHERE u.city_id = %s
                {gender_condition}
                AND u.telegram_id != %s
                AND u.id NOT IN (
                    SELECT target_user_id FROM user_actions 
                    WHERE user_id = %s
                )
            )
            
            SELECT 
                u.*, 
                c.name as city_name,
                CASE WHEN u.subscription_type = 2 THEN 1 ELSE 0 END as is_vip,
                CASE WHEN lm.user_id IS NOT NULL THEN 1 ELSE 0 END as liked_me
            FROM users u
            LEFT JOIN cities c ON u.city_id = c.id
            LEFT JOIN liked_me lm ON u.id = lm.user_id
            WHERE u.id IN (SELECT id FROM not_viewed)
            ORDER BY 
                liked_me DESC,  -- Сначала те, кто лайкнул
                is_vip DESC,    -- Затем VIP
                RANDOM()        -- Затем случайный порядок
            LIMIT 1
        """.format(gender_condition=gender_condition)
        
        cursor.execute(query, [
            current_user_db_id, user_id, user_data['city_id'],
            user_data['city_id'], user_id, current_user_db_id
        ])
        
        columns = [desc[0] for desc in cursor.description]
        result = cursor.fetchone()
        
        if result:
            profile_data = dict(zip(columns, result))
            print("Найден профиль:", profile_data)
            return profile_data
        else:
            print("Подходящих анкет не найдено")
            return None
    except Exception as e:
        print(f"Ошибка при поиске анкет: {e}")
        return None
    finally:
        if conn:
            cursor.close()
            conn.close()

# Начало создания

async def save_user_action(user_telegram_id, target_user_telegram_id, action):
    """Сохраняем действие пользователя (лайк/дизлайк)"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем ID пользователей из таблицы users по их telegram_id
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_telegram_id,))
        user_id = cursor.fetchone()
        if not user_id:
            print(f"Пользователь с telegram_id={user_telegram_id} не найден")
            return False
        
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (target_user_telegram_id,))
        target_user_id = cursor.fetchone()
        if not target_user_id:
            print(f"Пользователь с telegram_id={target_user_telegram_id} не найден")
            return False
        
        user_id = user_id[0]
        target_user_id = target_user_id[0]
        
        # Сначала проверяем, есть ли уже такое действие
        cursor.execute("""
            SELECT 1 FROM user_actions 
            WHERE user_id = %s AND target_user_id = %s
        """, (user_id, target_user_id))
        
        if cursor.fetchone():
            # Если действие уже есть, обновляем его
            cursor.execute("""
                UPDATE user_actions SET action = %s, timestamp = CURRENT_TIMESTAMP
                WHERE user_id = %s AND target_user_id = %s
            """, (action, user_id, target_user_id))
        else:
            # Если действия нет, создаем новое
            cursor.execute("""
                INSERT INTO user_actions (user_id, target_user_id, action)
                VALUES (%s, %s, %s)
            """, (user_id, target_user_id, action))
        
        conn.commit()
        print(f"Действие сохранено: user_id={user_id}, target_user_id={target_user_id}, action={action}")
        return True
    except Exception as e:
        print(f"Ошибка при сохранении действия: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

# Добавим клавиатуру для действий с анкетой
def get_profile_action_keyboard(user_id=None, is_super_like_possible=False):
    """Возвращает клавиатуру с суперлайком и кнопкой возврата"""
    keyboard = [
        ["💪", "🔥 Суперлайк", "👎"],
        ["Вернуться назад", "Закончить просмотр"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def view_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало просмотра анкет"""
    if 'user_id' not in context.user_data:
        await update.message.reply_text(
            "У вас нет анкеты. Сначала создайте её.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    user_id = context.user_data['user_id']
    subscription_type = await get_user_subscription(user_id)
    
    # Проверяем лимит только для пользователей без подписки
    if subscription_type == 0:
        conn = None
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            # Проверяем количество просмотров за сегодня
            cursor.execute("""
                SELECT profile_views_today, last_profile_views_reset 
                FROM users 
                WHERE telegram_id = %s
            """, (user_id,))
            result = cursor.fetchone()
            
            if result:
                views_today, last_reset = result
                # Если прошло больше 24 часов или это первый просмотр
                if last_reset is None or (datetime.now() - last_reset).total_seconds() >= 86400:
                    # Сбрасываем счетчик
                    cursor.execute("""
                        UPDATE users 
                        SET profile_views_today = 0,
                            last_profile_views_reset = CURRENT_TIMESTAMP
                        WHERE telegram_id = %s
                    """, (user_id,))
                    conn.commit()
                    views_today = 0
                
                # Проверяем лимит (10 просмотров)
                if views_today >= 10:
                    await update.message.reply_text(
                        "🚫 Вы достигли дневного лимита просмотров (10 анкет в день).\n\n"
                        "Оформите Premium или VIP подписку, чтобы снять ограничения:\n"
                        "Нажмите «⚙️ Настройки» → «Условия подписки»",
                        reply_markup=get_edit_keyboard()
                    )
                    return ConversationHandler.END
                
                # Увеличиваем счетчик просмотров
                cursor.execute("""
                    UPDATE users 
                    SET profile_views_today = profile_views_today + 1
                    WHERE telegram_id = %s
                """, (user_id,))
                conn.commit()
            
        except Exception as e:
            print(f"Ошибка при проверке лимита просмотров: {e}")
        finally:
            if conn:
                conn.close()

    print("Ищем анкеты для user_id:", context.user_data['user_id'])
    profile = await get_potential_matches(context.user_data['user_id'], context)
    print("Результат поиска анкет:", profile)

    if not profile:
        await update.message.reply_text(
            "Нет подходящих анкет для просмотра.",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    # При начале просмотра анкет проверяем и обновляем суперлайки
    await can_use_super_like(context.user_data['user_id'])
    
    # Сохраняем текущую анкету в контексте
    context.user_data['current_profile'] = profile
    print("Текущий профиль сохранён:", profile)
    
    # Сохраняем анкету в историю просмотров
    await save_viewed_profile(context, profile)
    
    # Проверяем, может ли пользователь использовать суперлайк
    can_super_like = await can_use_super_like(context.user_data['user_id'])
    
    # Показываем анкету с соответствующей клавиатурой
    await show_profile(update, profile, can_super_like)
    
    return PROFILE_ACTION

# Модифицируем функцию handle_profile_action для учета просмотров
async def handle_profile_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий с анкетой с уведомлениями о лайках"""
    action = update.message.text
    current_profile = context.user_data.get('current_profile')
    user_id = context.user_data['user_id']  # telegram_id текущего пользователя

    # Если пользователь нажал "Пропустить" на рекламе, продолжаем показ анкет
    if action == "Пропустить":
        await update.message.reply_text("Реклама пропущена. Продолжаем показ анкет...", 
            reply_markup=ReplyKeyboardRemove())
        return await continue_showing_profiles(update, context)
    
    if not current_profile:
        await update.message.reply_text(
            "Ошибка: анкета не найдена.",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END

    # Обработка "Закончить просмотр"
    if action == "Закончить просмотр":
        await update.message.reply_text(
            "Просмотр анкет завершён.",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    # Обработка "Вернуться назад"
    if action == "Вернуться назад":
        subscription_type = await get_user_subscription(user_id)
        
        if subscription_type == 0:  # Нет подписки
            await update.message.reply_text(
                "🔙 Возврат к предыдущей анкете доступен только для Premium и VIP пользователей!\n\n"
                "Для оформления подписки нажмите «Закончить просмотр» → «⚙️ Настройки» → «Условия подписки».",
                reply_markup=get_profile_action_keyboard()
            )
            return PROFILE_ACTION
        
        # Проверяем историю просмотров
        if 'viewed_history' not in context.user_data or len(context.user_data['viewed_history']) < 2:
            await update.message.reply_text(
                "Нет предыдущих анкет для возврата.",
                reply_markup=get_profile_action_keyboard()
            )
            return PROFILE_ACTION
        
        # Удаляем текущую анкету из истории
        context.user_data['viewed_history'].pop()
        
        # Получаем предыдущую анкету
        previous_profile = context.user_data['viewed_history'][-1]
        context.user_data['current_profile'] = previous_profile
        
        # Показываем предыдущую анкету
        await show_profile(update, previous_profile, await can_use_super_like(user_id))
        return PROFILE_ACTION
    
    if action == "💪":
        # Обычный лайк
        success = await save_user_action(user_id, current_profile['telegram_id'], 1)
        
        if success:
            # Проверяем взаимный лайк
            conn = None
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                cursor = conn.cursor()
                
                cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
                current_user_id = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT 1 FROM user_actions
                    WHERE user_id = %s AND target_user_id = %s AND action = 1
                """, (current_profile['id'], current_user_id))
                
                if cursor.fetchone():
                    await send_match_notification(context.bot, user_id, current_profile['telegram_id'])
                    await send_match_notification(context.bot, current_profile['telegram_id'], user_id)

            except Exception as e:
                print(f"Ошибка при проверке взаимного лайка: {e}")
            finally:
                if conn:
                    cursor.close()
                    conn.close()
        
        # Продолжаем показ анкет после лайка
        return await continue_showing_profiles(update, context)
    
    elif action == "👎":
        # Дизлайк
        success = await save_user_action(user_id, current_profile['telegram_id'], 0)
        
        if success:
            # Продолжаем показ анкет после дизлайка
            return await continue_showing_profiles(update, context)
    
    elif action == "🔥 Суперлайк":
        # Проверяем подписку пользователя
        subscription_type = await get_user_subscription(user_id)
        
        if subscription_type == 0:  # Нет подписки
            await update.message.reply_text(
                "🔥 Суперлайки доступны только для пользователей с Premium или VIP подпиской.\n\n"
                "Неограниченные суперлайки + отправка сообщения (VIP)\n"
                "5 суперлайков в день (Premium)\n\n"
                "Для оформления подписки нажмите «Закончить просмотр» → «⚙️ Настройки» → «Условия подписки»",
                reply_markup=get_profile_action_keyboard()
            )
            return PROFILE_ACTION
        
        # Проверяем и обновляем лимит суперлайков
        can_super_like = await can_use_super_like(user_id)
        if not can_super_like:
            await update.message.reply_text(
                "❌ У вас закончились суперлайки на сегодня!\n\n"
                "Лимит: 5 суперлайков в день (обновляется каждые 24 часа).\n\n"
                "Для неограниченных суперлайков оформите подписку VIP.",
                reply_markup=get_profile_action_keyboard()
            )
            return PROFILE_ACTION
            
        # Сохраняем информацию о суперлайке
        context.user_data['superlike_target'] = current_profile['telegram_id']
        
        if subscription_type == 2:  # VIP - предлагаем отправить сообщение
            await update.message.reply_text(
                "💬 Хотите отправить сообщение вместе с суперлайком? Напишите текст или нажмите «Пропустить»:",
                reply_markup=ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
            )
            return SUPERLIKE_MESSAGE
        else:  # Premium - сразу отправляем суперлайк без сообщения
            # Сохраняем суперлайк
            success = await save_user_action(user_id, current_profile['telegram_id'], 2)
            
            if success:
                # Используем суперлайк
                await use_super_like(user_id)
                await send_superlike_notification(context.bot, user_id, current_profile['telegram_id'])
                
            # Обновляем статистику просмотров и проверяем рекламу
            ad_shown = await update_view_stats(user_id, context)
            
            # Если была показана реклама, ждем нажатия кнопки "Пропустить"
            if ad_shown:
                return PROFILE_ACTION
            
            # Если реклама не была показана, продолжаем показ анкет
            return await continue_showing_profiles(update, context)

async def continue_showing_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Продолжает показ анкет после рекламы или если реклама не была показана"""
    user_id = context.user_data['user_id']
    subscription_type = await get_user_subscription(user_id)
    
    # Для бесплатных пользователей проверяем лимит
    if subscription_type == 0:
        conn = None
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT profile_views_today FROM users 
                WHERE telegram_id = %s
            """, (user_id,))
            result = cursor.fetchone()
            
            if result and result[0] >= 10:
                await update.message.reply_text(
                    "🚫 Вы достигли дневного лимита просмотров (10 анкет в день).\n\n"
                    "Оформите Premium или VIP подписку, чтобы снять ограничения:\n"
                    "Нажмите «Закончить просмотр» → «⚙️ Настройки» → «Условия подписки»",
                    reply_markup=get_edit_keyboard()
                )
                return ConversationHandler.END
                
        except Exception as e:
            print(f"Ошибка при проверке лимита просмотров: {e}")
        finally:
            if conn:
                conn.close()
    
    # Получаем следующую анкету
    profile = await get_potential_matches(context.user_data['user_id'], context)
    
    if not profile:
        await update.message.reply_text(
            "В данный момент нет новых анкет для просмотра. Попробуйте позже!",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    # Проверяем, что это не та же самая анкета
    if 'current_profile' in context.user_data and context.user_data['current_profile']['id'] == profile['id']:
        await update.message.reply_text(
            "В данный момент нет новых анкет для просмотра. Попробуйте позже!",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    # Сохраняем текущую анкету в контексте
    context.user_data['current_profile'] = profile
    
    # Сохраняем анкету в историю просмотров
    await save_viewed_profile(context, profile)
    
    # Формируем и показываем анкету
    await show_profile(update, profile)
    
    return PROFILE_ACTION

async def show_profile(update: Update, profile, can_super_like=False):
    """Показывает анкету пользователя с фото/видео и текстом"""
    # Получаем тип подписки пользователя и настройку значка
    subscription_type = await get_user_subscription(profile['telegram_id'])
    show_badge = profile.get('show_badge', True)  # Получаем текущее значение

    if subscription_type == 1 and show_badge:  # Premium
        subscription_emoji = " 🏆"
    elif subscription_type == 2 and show_badge:  # VIP
        subscription_emoji = " 👑"
    else:
        subscription_emoji = ""
    
    # Формируем текст анкеты
    profile_text = f"{subscription_emoji}\n" if subscription_emoji else ""
    
    description_text = f"\n\n{profile['description']}" if profile.get('description') else ""
    experience_text = f"\n{profile['experience']}" if profile.get('experience') else ""
    gym_street_text = f", {profile['gym_street']}" if profile.get('gym_street') else ""

    profile_text += (
        f"{profile['name']}, {profile['age']}, {profile.get('city_name', 'Не указан')}\n"
        f"{profile['gym_name']}{gym_street_text}"
        f"{experience_text}"
        f"{description_text}"
    )
    
    # Получаем все фото пользователя из user_photos (основное фото уже включено в этот список)
    photos = await get_user_photos(profile['telegram_id'])
    
    # Создаем медиагруппу
    media_group = []
    
    # Добавляем видео (если есть) как первый элемент с подписью
    if profile.get('video'):
        media_group.append(InputMediaVideo(profile['video'], caption=profile_text))
    
    # Добавляем фото (если есть)
    if photos:
        # Если видео нет, добавляем подпись к первому фото
        if not media_group:
            media_group.append(InputMediaPhoto(photos[0], caption=profile_text))
            # Остальные фото без подписи
            for photo in photos[1:]:
                media_group.append(InputMediaPhoto(photo))
        else:
            # Если есть видео, фото добавляем без подписи
            for photo in photos:
                media_group.append(InputMediaPhoto(photo))
    
    if media_group:
        try:
            # Отправляем медиагруппу
            await update.message.reply_media_group(media=media_group)
            
            # Отправляем клавиатуру отдельным сообщением с учетом суперлайков
            await update.message.reply_text(
                "Выберите действие:",
                reply_markup=get_profile_action_keyboard(update.effective_user.id, can_super_like)
            )
        except Exception as e:
            print(f"Ошибка при отправке медиагруппы: {e}")
            # Если не удалось отправить медиагруппу, отправляем текст
            await update.message.reply_text(
                profile_text,
                reply_markup=get_profile_action_keyboard(update.effective_user.id, can_super_like)
            )
    else:
        # Если нет ни фото, ни видео, отправляем только текст
        await update.message.reply_text(
            profile_text,
            reply_markup=get_profile_action_keyboard(update.effective_user.id, can_super_like)
        )

async def send_match_notification(bot, user_telegram_id, matched_user_telegram_id):
    """Отправляет уведомление о взаимном лайке"""
    print(f"Отправка уведомления: user_telegram_id={user_telegram_id}, matched_user_telegram_id={matched_user_telegram_id}")
    
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем данные обоих пользователей
        cursor.execute("""
            SELECT name, username FROM users WHERE telegram_id = %s
        """, (matched_user_telegram_id,))
        matched_user_data = cursor.fetchone()
        
        if not matched_user_data:
            print(f"Пользователь с telegram_id={matched_user_telegram_id} не найден")
            return
        
        matched_name, matched_username = matched_user_data
        
        # Формируем сообщение
        message = f"💪 С вами хочет познакомиться {matched_name}!\n\n"
        if matched_username:
            message += f"Напиши: @{matched_username}\n"
            message += f"Или перейди в чат: https://t.me/{matched_username}"
        else:
            message += "К сожалению, у пользователя не указан username в Telegram."
        
        # Отправляем уведомление
        try:
            await bot.send_message(chat_id=user_telegram_id, text=message)
            print("Уведомление о взаимном лайке успешно отправлено")
        except Exception as e:
            print(f"Ошибка при отправке уведомления: {e}")
        
    except Exception as e:
        print(f"Ошибка при получении данных пользователя: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()

async def edit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора поля для редактирования"""
    choice = update.message.text
    
    if choice == "✅ Завершить редактирование":
        return await finish_editing(update, context)
    
    # Определяем какое поле выбрано
    if choice.startswith("1."):
        await update.message.reply_text(
            "Введите новое имя:",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['editing_field'] = 'name'
        return EDIT_SELECTED
    
    elif choice.startswith("2."):
        # Инициализируем новый объект для медиа
        context.user_data['media'] = {'photos': [], 'video': None}
        context.user_data['changes'] = {'photos_updated': True}  # Флаг, что фото обновляются

        await update.message.reply_text(
            "Теперь отправьте ваше фото/видео:",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['editing_field'] = 'photo'
        context.user_data['media_cleared'] = False  # Флаг, что медиа еще не очищены
        return EDIT_SELECTED

    elif choice.startswith("3."):
        await update.message.reply_text(
            "Введите новый возраст:",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['editing_field'] = 'age'
        return EDIT_SELECTED
    
    elif choice.startswith("4."):
        await update.message.reply_text(
            "Укажите ваш пол:",
            reply_markup=get_gender_keyboard()
        )
        context.user_data['editing_field'] = 'gender'
        return EDIT_SELECTED
    
    elif choice.startswith("5."):
        await update.message.reply_text(
            "Кого вы предпочитаете в качестве напарника?",
            reply_markup=get_preferred_gender_keyboard()
        )
        context.user_data['editing_field'] = 'preferred_gender'
        return EDIT_SELECTED
    
    elif choice.startswith("6."):
        await update.message.reply_text(
            "Введите новый город:",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['editing_field'] = 'city'
        return EDIT_SELECTED
    
    elif choice.startswith("7."):
        await update.message.reply_text(
            "Какой у вас стаж тренировок?",
            reply_markup=get_experience_keyboard()
        )
        context.user_data['editing_field'] = 'experience'
        return EDIT_SELECTED
    
    elif choice.startswith("8."):
        await update.message.reply_text(
            "Напишите новое описание о себе или нажмите «Стереть»:",
            reply_markup=get_edit_description_keyboard()
        )
        context.user_data['editing_field'] = 'description'
        return EDIT_SELECTED
    
    elif choice.startswith("9."):
        await update.message.reply_text(
            "Введите новое название зала:",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['editing_field'] = 'gym_name'
        return EDIT_SELECTED
    
    elif choice.startswith("10."):
        await update.message.reply_text(
            "Введите новую улицу зала:",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['editing_field'] = 'gym_street'
        return EDIT_SELECTED
    
    # Добавим обработку нового пункта для значка
    elif choice.startswith("11.") or choice == "11. Значок подписки":
        subscription_type = await get_user_subscription(context.user_data['user_id'])
        if subscription_type == 0:
            await update.message.reply_text(
                "Эксклюзивные значки доступны только для пользователей с Premium или VIP подпиской.\n\n"
                "Для оформления подписки нажмите «✅ Завершить редактирование» → «⚙️ Настройки» → «Условия подписки»",
                reply_markup=get_edit_choice_keyboard(context.user_data['current_data'])
            )
            return EDIT_CHOICE
        
        await update.message.reply_text(
            "Выберите действие со значком подписки:",
            reply_markup=get_badge_toggle_keyboard()
        )
        return TOGGLE_BADGE
    
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите вариант из меню.",
            reply_markup=get_edit_choice_keyboard(context.user_data['current_data'])
        )
        return EDIT_CHOICE

async def edit_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода нового значения для выбранного поля"""
    field = context.user_data['editing_field']
    
    if field == 'photo':
        # Инициализируем media, если его нет
        if 'media' not in context.user_data:
            context.user_data['media'] = {'photos': [], 'video': None}
        
        current_media = context.user_data['media']
        
        # Очищаем старые медиафайлы только при первом добавлении нового
        if not context.user_data.get('media_cleared', False) and (update.message.photo or update.message.video):
            await clear_user_photos(context.user_data['user_id'])
            await clear_user_video(context.user_data['user_id'])
            context.user_data['media_cleared'] = True
        
        if update.message.video:
            # Проверяем, есть ли уже видео
            if current_media['video']:
                await update.message.reply_text(
                    "Вы уже добавили видео. Можно добавить только одно видео. ",
                    reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
                )
                return EDIT_SELECTED
            
            # Добавляем видео
            current_media['video'] = update.message.video.file_id
            total_media = len(current_media['photos']) + 1  # +1 за видео
            
            # Проверяем достигнут ли максимум (3 медиафайла)
            if total_media >= 3:
                await update.message.reply_text(
                    "Достигнут максимум (3 медиафайла). Нажмите «Далее» для продолжения.",
                    reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
                )
            else:
                await update.message.reply_text(
                    f"Медиафайлов {total_media}/3 добавлено. Можно добавить еще фото или нажать «Далее» для продолжения.",
                    reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
                )
            return EDIT_SELECTED
        
        elif update.message.photo:
            # Проверяем общее количество медиафайлов (максимум 3)
            total_media = len(current_media['photos']) + (1 if current_media['video'] else 0)
            if total_media >= 3:
                await update.message.reply_text(
                    "Медиафайлов 3/3 добавлено. Нажмите «Далее» для продолжения.",
                    reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
                )
                return EDIT_SELECTED
            
            # Добавляем фото
            photo_file_id = update.message.photo[-1].file_id
            current_media['photos'].append(photo_file_id)
            total_media = len(current_media['photos']) + (1 if current_media['video'] else 0)
            
            # Проверяем достигнут ли максимум
            if total_media >= 3:
                await update.message.reply_text(
                    "Достигнут максимум (3 медиафайла). Нажмите «Далее» для продолжения.",
                    reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
                )
            else:
                await update.message.reply_text(
                    f"Медиафайлов {total_media}/3 добавлено. Можно добавить еще фото или нажать «Далее» для продолжения.",
                    reply_markup=ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True)
                )
            return EDIT_SELECTED
        
        elif update.message.text == "Далее":
            # Проверяем, есть ли хотя бы одно медиа
            if not current_media['photos'] and not current_media['video']:
                await update.message.reply_text(
                    "Пожалуйста, добавьте хотя бы одно фото или видео перед продолжением.",
                    reply_markup=ReplyKeyboardRemove()  # Убрали кнопку "Далее"
                )
                return EDIT_SELECTED
                
            # Сохраняем изменения
            context.user_data['changes']['media'] = current_media
            context.user_data['changes']['photos'] = current_media['photos']
            context.user_data['changes']['video'] = current_media['video']
            
            await update.message.reply_text(
                "Изменения сохранены. Выберите что ещё хотите изменить:",
                reply_markup=get_edit_choice_keyboard(context.user_data['current_data'])
            )
            return EDIT_CHOICE
        
        else:
            # Если пользователь отправил текст (не фото/видео и не "Далее")
            await update.message.reply_text(
                "Пожалуйста, отправьте фото или видео.",
                reply_markup=ReplyKeyboardRemove()  # Убрали кнопку "Далее"
            )
            return EDIT_SELECTED
    
    # Обработка специальных полей
    if field == 'description':
        if update.message.text == "Стереть":
            context.user_data['changes']['description'] = None
        elif update.message.text == "Пропустить":
            # Не сохраняем изменение, если пользователь нажал "Пропустить"
            pass
        else:
            context.user_data['changes']['description'] = update.message.text
        
        await update.message.reply_text(
            "Изменения сохранены. Выберите что ещё хотите изменить:",
            reply_markup=get_edit_choice_keyboard(context.user_data['current_data'])
        )
        return EDIT_CHOICE
    
    # Обработка поля experience (стаж)
    if field == 'experience':
        user_input = update.message.text
        valid_options = ["Новичок", "Продвинутый", "Профессионал"]  # Убрали "Пропустить"
        
        if user_input not in valid_options:
            await update.message.reply_text(
                "Пожалуйста, выберите вариант из предложенных",
                reply_markup=get_experience_keyboard()
            )
            return EDIT_SELECTED
        
        # Сохраняем выбранный стаж (теперь нельзя пропустить)
        context.user_data['changes']['experience'] = user_input
        
        await update.message.reply_text(
            "Изменения сохранены. Выберите что ещё хотите изменить:",
            reply_markup=get_edit_choice_keyboard(context.user_data['current_data'])
        )
        return EDIT_CHOICE
    
    # Для всех остальных полей (включая gym_street)
    value = update.message.text
    
    if field == 'gender':
        if value == "Парень":
            value = 1
        elif value == "Девушка":
            value = 2
        else:
            await update.message.reply_text(
                "Пожалуйста, выберите пол из предложенных вариантов",
                reply_markup=get_gender_keyboard()
            )
            return EDIT_SELECTED
    
    elif field == 'preferred_gender':
        if value == "Gym Bro":
            value = 1
        elif value == "Gym Girl":
            value = 2
        elif value == "Без разницы":
            value = 0
        else:
            await update.message.reply_text(
                "Пожалуйста, выберите вариант из предложенных",
                reply_markup=get_preferred_gender_keyboard()
            )
            return EDIT_SELECTED
    
    elif field == 'city':
        city_id = await get_city_id(value)
        if city_id is None:
            await update.message.reply_text("Город не найден. Пожалуйста, введите корректное название города:")
            return EDIT_SELECTED
        context.user_data['city'] = value
        value = city_id  # Сохраняем ID города вместо названия
        field = 'city_id'  # Меняем поле на city_id для базы данных
    
    elif field == 'age':
        try:
            value = int(value)
            if value < 10 or value > 100:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите корректный возраст (число от 10 до 100)!")
            return EDIT_SELECTED

    # Сохраняем изменение
    context.user_data['changes'][field] = value

    await update.message.reply_text(
        "Изменения сохранены. Выберите что ещё хотите изменить:",
        reply_markup=get_edit_choice_keyboard(context.user_data['current_data'])
    )
    return EDIT_CHOICE

async def clear_user_photos(user_id: int) -> bool:
    """Очищает все фото пользователя из базы данных"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем ID пользователя из таблицы users
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
        user_db_id = cursor.fetchone()
        if not user_db_id:
            print(f"Пользователь с telegram_id={user_id} не найден")
            return False
            
        user_db_id = user_db_id[0]
        
        # Удаляем все фото пользователя
        cursor.execute("DELETE FROM user_photos WHERE user_id = %s", (user_db_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка при очистке фото пользователя: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()


async def finish_editing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение редактирования и сохранение изменений"""
    context.user_data.pop('is_editing_profile', None)

    # Проверяем изменения
    if not context.user_data.get('changes'):
        await update.message.reply_text(
            "Вы не внесли никаких изменений.",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    try:
        # Получаем текущие данные пользователя
        user_data = await get_user_from_db(context.user_data['user_id'], context)
        
        # Создаем копию текущих данных
        updated_data = user_data.copy()
        
        # Применяем все изменения из context.user_data['changes']
        if 'changes' in context.user_data:
            for field, value in context.user_data['changes'].items():
                updated_data[field] = value
        
        # Убедимся, что gym_street сохранен, даже если он None
        if 'gym_street' in context.user_data['changes']:
            updated_data['gym_street'] = context.user_data['changes']['gym_street']
        elif 'gym_street' not in updated_data:
            updated_data['gym_street'] = None
        
        # Устанавливаем is_viewed в False
        updated_data['is_viewed'] = False
        
        # Получаем тип подписки и настройку значка
        subscription_type = await get_user_subscription(context.user_data['user_id'])
        show_badge = updated_data.get('show_badge', True)  # Получаем текущее значение

        if subscription_type == 1 and show_badge:  # Premium
            subscription_emoji = " 🏆"
        elif subscription_type == 2 and show_badge:  # VIP
            subscription_emoji = " 👑"
        else:
            subscription_emoji = ""
        
        # Обновляем данные в БД
        success = await update_user_in_db(
            context.user_data['user_id'],
            updated_data
        )
        
        if success:
            # Сохраняем новые фото, если они есть
            if 'photos' in context.user_data.get('changes', {}):
                await save_user_photos(context.user_data['user_id'], context.user_data['changes']['photos'])
            
            # Получаем обновлённые данные
            user_data = await get_user_from_db(context.user_data['user_id'], context)
            if not user_data:
                await update.message.reply_text(
                    "Анкета не найдена после обновления.",
                    reply_markup=get_main_keyboard()
                )
                return ConversationHandler.END
            
            # Формируем текст анкеты с новым форматом
            description_text = f"\n\n{user_data['description']}" if user_data.get('description') else ""
            experience_text = f"\n{user_data['experience']}" if user_data.get('experience') else ""
            gym_street_text = f", {user_data['gym_street']}" if user_data.get('gym_street') else ""

            profile_text = (
                f"{subscription_emoji}\n"
                f"{user_data['name']}, {user_data['age']}, {user_data.get('city_name', 'Не указан')}\n"
                f"{user_data['gym_name']}{gym_street_text}"
                f"{experience_text}"
                f"{description_text}"
            )

            await update.message.reply_text("✅ Анкета успешно обновлена:")

            # Получаем все фото пользователя
            photos = await get_user_photos(context.user_data['user_id'])
            
            # Создаем медиагруппу
            media_group = []
            
            # Добавляем видео (если есть) как первый элемент с подписью
            if 'video' in user_data and user_data['video']:
                media_group.append(InputMediaVideo(user_data['video'], caption=profile_text))
            
            # Добавляем фото (если есть)
            if photos:
                for i, photo in enumerate(photos):
                    # Добавляем подпись только к первому фото, если нет видео
                    if not media_group:  # Если видео нет
                        media_group.append(InputMediaPhoto(photo, caption=profile_text))
                    else:
                        media_group.append(InputMediaPhoto(photo))
            
            if media_group:
                try:
                    await update.message.reply_media_group(media=media_group)
                except Exception as e:
                    print(f"Ошибка при отправке медиагруппы: {e}")
                    await update.message.reply_text(profile_text)
            else:
                await update.message.reply_text(profile_text)
            
            # Отправляем клавиатуру для редактирования
            await update.message.reply_text(
                "Что вы хотите сделать дальше?",
                reply_markup=get_edit_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка при обновлении анкеты. Попробуйте позже.",
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        print(f"Ошибка при завершении редактирования: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обновлении анкеты. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
    
    return ConversationHandler.END



# Создание фейковых анкет

# Новые состояния для генерации анкет
GENERATE_PROFILE, GET_TELEGRAM_ID, GET_USERNAME, GET_NAME, GET_AGE, GET_GENDER, GET_PREFERRED_GENDER, GET_CITY, GET_EXPERIENCE, GET_DESCRIPTION, GET_GYM_NAME, GET_GYM_STREET, GET_PHOTO = range(13)

async def start_generate_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для рассылки уведомлений (только для владельца)"""
    owner_id = int(os.getenv("OWNER_ID", 0))  # Получаем ID владельца из .env
    
    if update.effective_user.id != owner_id:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    """Начало процесса создания фейковой анкеты"""
    # Завершаем все текущие диалоги
    if context.user_data.get('current_profile'):
        del context.user_data['current_profile']
    
    # Очищаем возможные предыдущие данные
    context.user_data.clear()
    
    await update.message.reply_text(
        "Введите Telegram ID для фейковой анкеты:",
        reply_markup=ReplyKeyboardRemove()
    )
    return GET_TELEGRAM_ID

async def get_telegram_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем Telegram ID"""
    try:
        telegram_id = int(update.message.text)
        context.user_data['fake_profile'] = {'telegram_id': telegram_id}
        await update.message.reply_text(
            "Введите username (без @) или нажмите «Пропустить»:",
            reply_markup=ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
        )
        return GET_USERNAME
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректный Telegram ID (число):")
        return GET_TELEGRAM_ID

async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем username или пропускаем"""
    if update.message.text == "Пропустить":
        context.user_data['fake_profile']['username'] = None
    else:
        context.user_data['fake_profile']['username'] = update.message.text
    
    await update.message.reply_text(
        "Введите имя:",
        reply_markup=ReplyKeyboardRemove()
    )
    return GET_NAME

async def get_fake_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем имя"""
    context.user_data['fake_profile']['name'] = update.message.text
    await update.message.reply_text("Введите возраст:")
    return GET_AGE

async def get_fake_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем возраст"""
    try:
        age = int(update.message.text)
        if age < 10 or age > 100:
            raise ValueError
        context.user_data['fake_profile']['age'] = age
        await update.message.reply_text(
            "Укажите пол:",
            reply_markup=ReplyKeyboardMarkup([["Парень", "Девушка"]], resize_keyboard=True)
        )
        return GET_GENDER
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректный возраст (число от 10 до 100)!")
        return GET_AGE

async def get_fake_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем пол"""
    gender_text = update.message.text
    if gender_text == "Парень":
        context.user_data['fake_profile']['gender'] = 1
    elif gender_text == "Девушка":
        context.user_data['fake_profile']['gender'] = 2
    else:
        await update.message.reply_text("Пожалуйста, выберите пол из предложенных вариантов")
        return GET_GENDER
    
    await update.message.reply_text(
        "Кого предпочитаете в качестве напарника?",
        reply_markup=ReplyKeyboardMarkup([["Gym Bro", "Gym Girl", "Без разницы"]], resize_keyboard=True)
    )
    return GET_PREFERRED_GENDER

async def get_fake_preferred_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем предпочтения по полу"""
    preferred = update.message.text
    if preferred == "Gym Bro":
        context.user_data['fake_profile']['preferred_gender'] = 1
    elif preferred == "Gym Girl":
        context.user_data['fake_profile']['preferred_gender'] = 2
    elif preferred == "Без разницы":
        context.user_data['fake_profile']['preferred_gender'] = 0
    else:
        await update.message.reply_text("Пожалуйста, выберите вариант из предложенных")
        return GET_PREFERRED_GENDER
    
    await update.message.reply_text(
        "Введите город:",
        reply_markup=ReplyKeyboardRemove()
    )
    return GET_CITY

async def get_fake_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем город"""
    city_name = update.message.text
    city_id = await get_city_id(city_name)
    
    if city_id is None:
        await update.message.reply_text("Город не найден. Пожалуйста, введите корректное название города:")
        return GET_CITY
    
    context.user_data['fake_profile']['city_id'] = city_id
    context.user_data['fake_profile']['city'] = city_name
    
    await update.message.reply_text(
        "Какой стаж тренировок?",
        reply_markup=ReplyKeyboardMarkup([
            ["Новичок", "Продвинутый"],
            ["Профессионал", "Пропустить"]
        ], resize_keyboard=True)
    )
    return GET_EXPERIENCE

async def get_fake_experience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем стаж для фейковой анкеты с проверкой на соответствие предложенным вариантам"""
    user_input = update.message.text
    
    # Список допустимых вариантов ответа
    valid_options = [
        "Новичок",
        "Продвинутый",
        "Профессионал",
        "Пропустить"
    ]
    
    if user_input not in valid_options:
        await update.message.reply_text(
            "Пожалуйста, выберите вариант из предложенных",
            reply_markup=get_experience_keyboard()
        )
        return GET_EXPERIENCE
    
    if user_input == "Пропустить":
        context.user_data['fake_profile']['experience'] = None
    else:
        context.user_data['fake_profile']['experience'] = user_input
    
    await update.message.reply_text(
        "Напишите описание о себе или нажмите «Пропустить»:",
        reply_markup=ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
    )
    return GET_DESCRIPTION

async def get_fake_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем описание или пропускаем"""
    if update.message.text == "Пропустить":
        context.user_data['fake_profile']['description'] = None
    else:
        context.user_data['fake_profile']['description'] = update.message.text
    
    await update.message.reply_text(
        "Отправьте фото для анкеты (необязательно):",
        reply_markup=ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
    )
    return GET_PHOTO

async def get_fake_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем фото или пропускаем для фейковой анкеты"""
    if update.message.text == "Пропустить":
        context.user_data['fake_profile']['photo'] = None
    else:
        if not update.message.photo:
            await update.message.reply_text("Пожалуйста, отправьте фото!")
            return GET_PHOTO
            
        photo_file_id = update.message.photo[-1].file_id
        context.user_data['fake_profile']['photo'] = photo_file_id
    
    await update.message.reply_text(
        "Введите название зала:",
        reply_markup=ReplyKeyboardRemove()
    )
    return GET_GYM_NAME

async def get_fake_gym_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем название зала"""
    context.user_data['fake_profile']['gym_name'] = update.message.text
    await update.message.reply_text("Введите улицу зала:")
    return GET_GYM_STREET

async def get_fake_gym_street(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем улицу зала и сохраняем анкету"""
    context.user_data['fake_profile']['gym_street'] = update.message.text
    
    # Сохраняем анкету в БД
    fake_data = context.user_data['fake_profile']
    profile_id = await save_fake_profile_to_db(
        fake_data['telegram_id'],
        fake_data.get('username'),
        fake_data
    )
    
    if profile_id:
        # Добавляем вызов уведомления админу
        # Формируем текст анкеты
        profile_text = (
            f"✅ Фейковая анкета создана (ID: {profile_id}):\n\n"
            f"Telegram ID: {fake_data['telegram_id']}\n"
            f"Username: @{fake_data.get('username', 'Не указан')}\n"
            f"Имя: {fake_data['name']}\n"
            f"Возраст: {fake_data['age']}\n"
            f"Пол: {'Парень' if fake_data['gender'] == 1 else 'Девушка'}\n"
            f"Предпочтения: {get_preferred_gender_text(fake_data['preferred_gender'])}\n"
            f"Город: {fake_data['city']}\n"
            f"Зал: {fake_data['gym_name']}, {fake_data['gym_street']}\n"
            f"Стаж: {fake_data.get('experience', 'Не указан')}\n"
            f"Описание: {fake_data.get('description', 'Не указано')}\n"
            f"Фото: {'Есть' if fake_data.get('photo') else 'Нет'}"
        )
        
        await update.message.reply_text(profile_text)
        
        # Если есть фото, отправляем его
        if fake_data.get('photo'):
            await update.message.reply_photo(photo=fake_data['photo'])
    else:
        await update.message.reply_text("❌ Не удалось создать фейковую анкету")
    
    return ConversationHandler.END

def get_preferred_gender_text(value):
    """Возвращает текстовое описание предпочтений"""
    if value == 1:
        return "Gym Bro"
    elif value == 2:
        return "Gym Girl"
    return "Без разницы"

async def save_fake_profile_to_db(telegram_id, username, fake_data):
    """Сохраняет фейковую анкету в БД"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO users (
                telegram_id, username, name, age, gender,
                preferred_gender, city_id, experience, description,
                gym_name, gym_street, photo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (telegram_id) 
            DO UPDATE SET
                username = EXCLUDED.username,
                name = EXCLUDED.name,
                age = EXCLUDED.age,
                gender = EXCLUDED.gender,
                preferred_gender = EXCLUDED.preferred_gender,
                city_id = EXCLUDED.city_id,
                experience = EXCLUDED.experience,
                description = EXCLUDED.description,
                gym_name = EXCLUDED.gym_name,
                gym_street = EXCLUDED.gym_street,
                photo = EXCLUDED.photo
            RETURNING id
        """, (
            telegram_id,
            username,
            fake_data['name'],
            fake_data['age'],
            fake_data['gender'],
            fake_data['preferred_gender'],
            fake_data['city_id'],
            fake_data.get('experience'),
            fake_data.get('description'),
            fake_data['gym_name'],
            fake_data['gym_street'],
            fake_data.get('photo')  # Теперь сохраняем file_id вместо бинарных данных
        ))
        
        result = cursor.fetchone()
        conn.commit()
        return result[0] if result else None
    except Exception as e:
        print(f"Ошибка при сохранении фейковой анкеты: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()



# Обновление бота
async def notify_all_users(bot):
    """Рассылает уведомления всем пользователям"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM users")
        users = cursor.fetchall()

        print(f"📢 Рассылка {len(users)} пользователям...")

        for user_id, in users:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text = (
                        "🔄 ОБНОВЛЕНИЕ В БОТЕ! Нажмите /start, чтобы продолжить.\n\n"
                        
                        "🔥 НОВЫЕ ФИЧИ:\n"
                        "🎁 Реферальная система - получай +3 дня Premium за каждого приглашенного друга\n"
                        "🏆 Лидерборд - соревнуйся за звание лучшего реферала\n\n"
                        
                        "🔹 Как получить Premium за рефералов?\n"
                        "1. Приглашай друзей по своей реферальной ссылке\n"
                        "2. За каждого друга, создавшего анкету, ты получаешь +3 дня Premium, а он +7 дней Premium функций подписки\n"
                        "3. Приглашай пользователей в своем телеграм канале, чтобы Premium статус держался еще дольше!\n\n"
                        
                        "💡 Все подробности:\n"
                        "Нажмите /start → «Использовать существующую» → «⚙️ Настройки» → «Реферальная система»\n\n"
                        
                        "📢 Подписывайтесь на наш Telegram-канал @gymbroshub - там анонсы новых фич и много различных рубрик!"
                    )
                )
                await asyncio.sleep(0.5)  # Задержка между сообщениями
            except Exception as e:
                print(f"❌ Ошибка при отправке {user_id}: {e}")

    except Exception as e:
        print(f"🔥 Ошибка в рассылке: {e}")
    finally:
        if conn:
            conn.close()

# Обработчик команды /notify_about_update
async def notify_all_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для рассылки уведомлений (только для владельца)"""
    owner_id = int(os.getenv("OWNER_ID", 0))  # Получаем ID владельца из .env
    
    if update.effective_user.id != owner_id:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    await update.message.reply_text("⏳ Рассылка уведомлений начата...")
    await notify_all_users(context.bot)
    await update.message.reply_text("✅ Рассылка завершена!")

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Ошибка: {context.error}")

            

# Просмотр новых анкет пользователей

# Добавьте новые состояния в начало файла, где определены другие состояния
CHECK_NEW_USERS, VIEW_NEW_PROFILE, SELECT_CITY_FOR_NOTIFICATION = range(20, 23)

async def save_admin_action(admin_telegram_id, target_user_telegram_id):
    """Сохраняет действие администратора (просмотр анкеты)"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем ID целевого пользователя
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (target_user_telegram_id,))
        target_user_id = cursor.fetchone()
        if not target_user_id:
            print(f"Пользователь с telegram_id={target_user_telegram_id} не найден")
            return False
            
        target_user_id = target_user_id[0]
        
        # Обновляем поле is_viewed
        cursor.execute("""
            UPDATE users 
            SET is_viewed = TRUE
            WHERE id = %s
        """, (target_user_id,))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка при сохранении действия администратора: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

async def get_new_profiles(admin_id):
    """Получает список новых анкет, которые администратор еще не просматривал"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем анкеты, которые еще не просмотрены (is_viewed = FALSE)
        cursor.execute("""
            SELECT u.*, c.name as city_name 
            FROM users u
            LEFT JOIN cities c ON u.city_id = c.id
            WHERE u.is_viewed = false
            AND u.telegram_id != %s  -- Исключаем самого администратора
            ORDER BY u.created_at DESC  -- Сортировка только по дате создания
            LIMIT 100  -- Ограничиваем количество, чтобы не перегружать
        """, (admin_id,))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Ошибка при получении новых анкет: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            conn.close()

async def check_new_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды для просмотра новых анкет"""
    owner_id = int(os.getenv("OWNER_ID", 0))
    
    if update.effective_user.id != owner_id:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return ConversationHandler.END
    
    # Получаем все анкеты, отсортированные по дате создания (новые сначала)
    new_profiles = await get_new_profiles(update.effective_user.id)
    
    if not new_profiles:
        await update.message.reply_text("Анкет не найдено.")
        return ConversationHandler.END
    
    # Сохраняем анкеты в контексте
    context.user_data['new_profiles'] = new_profiles
    context.user_data['current_profile_index'] = 0
    
    # Показываем первую анкету
    await show_new_profile(update, context)
    
    return VIEW_NEW_PROFILE

async def show_new_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает одну новую анкету с медиафайлами"""
    profiles = context.user_data['new_profiles']
    index = context.user_data['current_profile_index']
    
    if index >= len(profiles):
        await update.message.reply_text("Вы просмотрели все новые анкеты.")
        return ConversationHandler.END
    
    profile = profiles[index]
    
    # Получаем тип подписки пользователя
    subscription_type = await get_user_subscription(profile['telegram_id'])
    
    # Добавляем соответствующий эмоджи в зависимости от подписки
    subscription_emoji = ""
    if subscription_type == 1:  # Premium
        subscription_emoji = " 🏆"
    elif subscription_type == 2:  # VIP
        subscription_emoji = " 👑"
    
    # Получаем все фото пользователя
    photos = await get_user_photos(profile['telegram_id'])
    
    # Формируем текст анкеты
    description_text = f"\n\n{profile['description']}" if profile.get('description') else ""
    experience_text = f"\n{profile['experience']}" if profile.get('experience') else ""
    gym_street_text = f", {profile['gym_street']}" if profile.get('gym_street') else ""

    profile_text = (
        f"Анкета #{index + 1} из {len(profiles)}\n\n"
        f"ID: {profile.get('id', 'N/A')} {subscription_emoji}\n"
        f"Telegram ID: {profile.get('telegram_id', 'N/A')}\n"
        f"Username: @{profile.get('username', 'нет')}\n"
        f"Имя: {profile['name']}, {profile['age']}\n"
        f"Город: {profile.get('city_name', 'Не указан')}\n"
        f"Зал: {profile['gym_name']}{gym_street_text}"
        f"{experience_text}"
        f"{description_text}"
    )
    
    # Создаем медиагруппу
    media_group = []
    
    # Добавляем видео (если есть) как первый элемент с подписью
    if profile.get('video'):
        media_group.append(InputMediaVideo(profile['video'], caption=profile_text))
    
    # Добавляем фото (если есть)
    if photos:
        for i, photo in enumerate(photos):
            # Добавляем подпись только к первому фото, если нет видео
            if not media_group:  # Если видео нет
                media_group.append(InputMediaPhoto(photo, caption=profile_text))
            else:
                media_group.append(InputMediaPhoto(photo))
    
    if media_group:
        try:
            # Отправляем медиагруппу
            await update.message.reply_media_group(media=media_group)
            
            # Отправляем клавиатуру отдельным сообщением
            await update.message.reply_text(
                "Выберите действие:",
                reply_markup=get_admin_profile_action_keyboard()
            )
        except Exception as e:
            print(f"Ошибка при отправке медиагруппы: {e}")
            # Если не удалось отправить медиагруппу, отправляем текст
            await update.message.reply_text(
                profile_text,
                reply_markup=get_admin_profile_action_keyboard()
            )
    else:
        # Если нет ни фото, ни видео, отправляем только текст
        await update.message.reply_text(
            profile_text,
            reply_markup=get_admin_profile_action_keyboard()
        )

async def delete_user_profile(user_id):
    """Удаляет анкету пользователя из базы данных"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем ID пользователя из таблицы users
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
        user_db_id = cursor.fetchone()
        if not user_db_id:
            print(f"Пользователь с telegram_id={user_id} не найден")
            return False
            
        user_db_id = user_db_id[0]
        
        # Удаляем все связанные данные (отзыв согласия / удаление ПДн)
        cursor.execute("DELETE FROM user_photos WHERE user_id = %s", (user_db_id,))
        cursor.execute(
            "DELETE FROM user_actions WHERE user_id = %s OR target_user_id = %s",
            (user_db_id, user_db_id),
        )
        try:
            cursor.execute(
                "DELETE FROM referrals WHERE referrer_id = %s OR referred_id = %s",
                (user_db_id, user_db_id),
            )
        except Exception:
            pass
        try:
            cursor.execute(
                'DELETE FROM "botapp_useradview" WHERE user_id = %s',
                (user_id,),
            )
            cursor.execute(
                'DELETE FROM "botapp_useradstat" WHERE user_id = %s',
                (user_id,),
            )
        except Exception:
            pass
        cursor.execute("DELETE FROM users WHERE id = %s", (user_db_id,))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка при удалении анкеты пользователя: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

async def handle_new_profile_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик действий при просмотре новых анкет"""
    profiles = context.user_data['new_profiles']
    index = context.user_data['current_profile_index']
    
    if index >= len(profiles):
        await update.message.reply_text("Вы просмотрели все новые анкеты.")
        return ConversationHandler.END
    
    current_profile = profiles[index]
    
    # Сохраняем действие администратора (просмотр анкеты)
    await save_admin_action(
        update.effective_user.id,
        current_profile['telegram_id']
    )
    
    if update.message.text == "Пропустить":
        # Увеличиваем индекс и показываем следующую анкету
        context.user_data['current_profile_index'] += 1
        return await show_new_profile(update, context)
    elif update.message.text == "Удалить анкету":
        # Удаляем анкету
        success = await delete_user_profile(current_profile['telegram_id'])
        if success:
            await update.message.reply_text("✅ Анкета успешно удалена.")
        else:
            await update.message.reply_text("❌ Не удалось удалить анкету.")
        
        # Увеличиваем индекс и показываем следующую анкету
        context.user_data['current_profile_index'] += 1
        return await show_new_profile(update, context)
    
    return VIEW_NEW_PROFILE



#  Рассылка уведомлений пользователям из одного города

# Добавим новые состояния в начало файла, где определены другие состояния
SELECT_CITY_FOR_NOTIFICATION = 30

# Добавим функцию для получения списка городов
async def get_cities_list():
    """Получает список всех городов из базы"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM cities ORDER BY name")
        return cursor.fetchall()
    except Exception as e:
        print(f"Ошибка при получении списка городов: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            conn.close()

# Добавим клавиатуру для выбора города
def get_cities_keyboard(cities):
    """Создает клавиатуру с кнопками городов"""
    keyboard = []
    row = []
    for city_id, city_name in cities:
        row.append(city_name)
        if len(row) == 2:  # 2 кнопки в ряд
            keyboard.append(row)
            row = []
    if row:  # Добавляем оставшиеся кнопки
        keyboard.append(row)
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Обработчик команды для рассылки уведомлений по городу
async def notify_city_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса рассылки уведомлений по всем городам"""
    owner_id = int(os.getenv("OWNER_ID", 0))
    
    if update.effective_user.id != owner_id:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    # Отправляем сообщение о начале рассылки
    msg = await update.message.reply_text(
        "⏳ Начинаю рассылку уведомлений по всем городам...",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Создаем задачу для рассылки, чтобы не блокировать основной поток
    asyncio.create_task(process_city_notifications(context.bot, msg))

async def process_city_notifications(bot, status_message):
    """Асинхронная обработка рассылки по городам"""
    # Получаем список всех городов
    cities = await get_cities_list()
    if not cities:
        await bot.edit_message_text(
            "В базе нет городов.",
            chat_id=status_message.chat_id,
            message_id=status_message.message_id
        )
        return
    
    total_notified = 0
    processed_cities = 0
    total_cities = len(cities)
    
    for city_id, city_name in cities:
        processed_cities += 1
        try:
            # Обновляем статус
            if processed_cities % 10 == 0:  # Обновляем статус каждые 10 городов
                await bot.edit_message_text(
                    f"⏳ Обрабатываю город {processed_cities}/{total_cities} ({city_name})...",
                    chat_id=status_message.chat_id,
                    message_id=status_message.message_id
                )
            
            # Получаем пользователей для этого города
            conn = None
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT u.telegram_id 
                    FROM users u
                    WHERE u.city_id = %s
                    AND EXISTS (
                        SELECT 1 
                        FROM users potential_matches
                        WHERE potential_matches.city_id = %s
                        AND potential_matches.telegram_id != u.telegram_id
                        AND potential_matches.id NOT IN (
                            SELECT target_user_id 
                            FROM user_actions 
                            WHERE user_id = u.id
                        )
                        HAVING COUNT(*) >= 3
                    )
                """, (city_id, city_id))
                
                users = cursor.fetchall()
                
                if not users:
                    print(f"В городе {city_name} нет пользователей с 3+ непросмотренными анкетами")
                    continue
                
                # Рассылаем уведомления с небольшими паузами
                city_notified = 0
                for (user_id,) in users:
                    try:
                        keyboard = ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
                        await bot.send_message(
                            chat_id=user_id,
                            text=f"🏙️ В вашем городе появились новые анкеты!\n\nНажмите кнопку ниже, чтобы продолжить:",
                            reply_markup=keyboard
                        )
                        city_notified += 1
                        total_notified += 1
                        await asyncio.sleep(0.3)  # Пауза между сообщениями
                    except Exception as e:
                        print(f"Не удалось отправить уведомление пользователю {user_id} в городе {city_name}: {e}")
                        await asyncio.sleep(1)  # Пауза при ошибке
                
                print(f"Уведомления отправлены {city_notified} пользователям в городе {city_name}")
                
            except Exception as e:
                print(f"Ошибка при обработке города {city_name}: {e}")
            finally:
                if conn:
                    conn.close()
            
            await asyncio.sleep(0.1)  # Небольшая пауза между городами
            
        except Exception as e:
            print(f"Критическая ошибка при обработке города {city_name}: {e}")
    
    # Финальное сообщение о завершении
    await bot.edit_message_text(
        f"✅ Рассылка завершена! Всего уведомлений отправлено: {total_notified}",
        chat_id=status_message.chat_id,
        message_id=status_message.message_id
    )



# Premium/VIP подписки

# Добавим новые состояния в начало файла, где определены другие состояния
SETTINGS, SUBSCRIPTION_INFO, GET_USER_ID = range(50, 53)

# Добавим функцию для клавиатуры настроек
def get_settings_keyboard():
    return ReplyKeyboardMarkup([
        ["Условия подписки", "Узнать мой ID"],
        ["Реферальная система", "Лидерборд"],
        ["Политика конфиденциальности", "Соглашение"],
        ["🗑 Удалить мои данные"],
        ["Назад"]
    ], resize_keyboard=True)

# Добавим функцию для клавиатуры подписок
def get_subscription_keyboard():
    return ReplyKeyboardMarkup([
        ["Premium (99₽/мес)", "VIP (199₽/мес)"],
        ["Назад"]
    ], resize_keyboard=True)

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('in_referral_menu', None)  # Очищаем флаг меню реферальной системы
    
    await update.message.reply_text(
        "⚙️ Настройки:",
        reply_markup=get_settings_keyboard()
    )
    return SETTINGS

async def subscription_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о подписках"""
    subscription_text = (
        "🔥 <b>Подписки в GymBros</b> 🔥\n\n"
        
        "💎 <b>Premium (99 рублей в месяц)</b>\n"
        "☑️ Неограниченные просмотры анкет\n"
        "☑️ 5 суперлайков в день\n"
        "☑️ Возможность вернуться к анкете\n"
        "☑️ Эксклюзивный значок 🏆 в профиле\n"
        "☑️ Опция скрытия значка, для сохранения анонимности статуса пользователя\n\n"
        
        
        "💎 <b>VIP (199 рублей в месяц)</b>\n"
        "☑️ + Premium\n"
        "✅ Неограниченное количество суперлайков в день\n"
        "✅ Возможность отправки сообщения при суперлайке\n"
        "✅ Просмотр «Кто меня лайкнул»\n"
        "✅ Приоритет в показе\n"
        "✅ Эксклюзивный значок 👑 в профиле\n\n"
        
        "❗ <b>Важно:</b> Подписка <b>не продлевается автоматически</b> и действует ровно 1 месяц с момента активации.\n\n"
        
        "<b>Для оформления подписки напишите менеджеру</b> @gymbros_manager\n"
        "После оплаты вам будет предоставлен доступ к премиум-функциям."
    )
    
    await update.message.reply_text(
        subscription_text,
        parse_mode='HTML',
        reply_markup=get_subscription_keyboard()
    )
    return SUBSCRIPTION_INFO

async def get_user_id_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает ID пользователя"""
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"🆔 Ваш ID: <code>{user_id}</code>\n\n"
        "Этот идентификатор может понадобиться для оформления подписки.",
        parse_mode='HTML',
        reply_markup=get_settings_keyboard()
    )
    return SETTINGS

async def back_to_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в меню настроек"""
    await update.message.reply_text(
        "⚙️ Настройки:",
        reply_markup=get_settings_keyboard()
    )
    return SETTINGS

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Что вы хотите сделать?",
        reply_markup=get_edit_keyboard()
    )
    return ConversationHandler.END


async def show_privacy_policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    in_consent = bool(
        context.user_data.get('is_creating_profile')
        and not context.user_data.get('consent_accepted_at')
    )
    await update.message.reply_text(
        legal_texts.privacy_short_text(),
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=get_consent_keyboard() if in_consent else get_settings_keyboard(),
    )
    return CONSENT if in_consent else SETTINGS


async def show_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    in_consent = bool(
        context.user_data.get('is_creating_profile')
        and not context.user_data.get('consent_accepted_at')
    )
    await update.message.reply_text(
        legal_texts.terms_short_text(),
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=get_consent_keyboard() if in_consent else get_settings_keyboard(),
    )
    return CONSENT if in_consent else SETTINGS


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        legal_texts.help_text(),
        parse_mode='HTML',
        disable_web_page_preview=True,
    )


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        legal_texts.privacy_short_text(),
        parse_mode='HTML',
        disable_web_page_preview=True,
    )


async def terms_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        legal_texts.terms_short_text(),
        parse_mode='HTML',
        disable_web_page_preview=True,
    )


async def delete_my_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отзыв согласия и удаление персональных данных пользователя"""
    user_id = update.effective_user.id
    existing = await get_user_from_db(user_id, context)
    if not existing:
        await update.message.reply_text(
            "У вас нет сохранённых данных анкеты.\n"
            "Если появятся новые данные — удалить их можно этой же командой.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    success = await delete_user_profile(user_id)
    context.user_data.clear()
    if success:
        await update.message.reply_text(
            "✅ Ваша анкета и связанные персональные данные удалены.\n"
            "Согласие на обработку отозвано.\n\n"
            "Чтобы пользоваться сервисом снова — /start",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await update.message.reply_text(
            "❌ Не удалось удалить данные автоматически. "
            f"Напишите в поддержку: {legal_texts.operator_telegram()}",
            reply_markup=ReplyKeyboardRemove(),
        )
    return ConversationHandler.END


async def contact_manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ссылка на менеджера для подписки с шаблонными сообщениями"""
    user_id = update.effective_user.id
    subscription_type = "Premium" if "Premium" in update.message.text else "VIP"
    
    template_message = (
        f"Здравствуйте! Я хочу оформить подписку {subscription_type}.\n"
        f"Мой ID: {user_id}\n"
        "Какие есть способы оплаты?"
    )
    
    await update.message.reply_text(
        "📩 <b>Для оформления подписки напишите менеджеру</b> @gymbros_manager\n\n"
        "После подтверждения оплаты вам будут доступны все функции выбранной подписки.\n\n"
        "Вы можете отправить это сообщение или написать своё:",
        parse_mode='HTML',
        reply_markup=get_subscription_keyboard()
    )
    await update.message.reply_text(
        f"<code>{template_message}</code>",
        parse_mode='HTML',
        reply_markup=get_subscription_keyboard()
    )
    return SUBSCRIPTION_INFO



# Cуперлайки и отправка сообщения

SUPERLIKE_MESSAGE, = range(62, 63)

async def get_user_subscription(user_id):
    """Получает тип подписки пользователя (0 - нет подписки, 1 - Premium, 2 - VIP)"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT subscription_type FROM users WHERE telegram_id = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0
    except Exception as e:
        print(f"Ошибка при получении подписки пользователя: {e}")
        return 0
    finally:
        if conn:
            conn.close()

async def can_use_super_like(user_id):
    subscription_type = await get_user_subscription(user_id)
    
    # VIP — неограниченно
    if subscription_type == 2:
        return True
    
    # Premium — проверяем остаток
    if subscription_type == 1:
        conn = None
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            # Сначала проверяем, нужно ли обновить суперлайки
            cursor.execute("""
                SELECT last_super_likes_reset, super_likes_remaining 
                FROM users 
                WHERE telegram_id = %s
            """, (user_id,))
            result = cursor.fetchone()
            
            if not result:
                return False
                
            last_reset, remaining = result
            
            # Проверяем, прошло ли 24 часа с последнего сброса
            if last_reset is None or (datetime.now() - last_reset).total_seconds() >= 86400:  # 86400 секунд = 24 часа
                # Обновляем лимит
                cursor.execute("""
                    UPDATE users 
                    SET super_likes_remaining = 5, 
                        last_super_likes_reset = CURRENT_TIMESTAMP
                    WHERE telegram_id = %s
                    RETURNING super_likes_remaining
                """, (user_id,))
                conn.commit()
                new_remaining = cursor.fetchone()[0]
                return new_remaining > 0
            else:
                return remaining > 0
                
        except Exception as e:
            print(f"Ошибка при проверке суперлайков: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    # Без подписки — нельзя
    return False

async def use_super_like(user_id):
    """Уменьшает счетчик суперлайков на 1 (для Premium)"""
    if await get_user_subscription(user_id) == 1:  # Premium
        conn = None
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET super_likes_remaining = super_likes_remaining - 1
                WHERE telegram_id = %s
            """, (user_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка при использовании суперлайка: {e}")
            return False
        finally:
            if conn:
                conn.close()
    return True

async def send_superlike_notification(bot, sender_id, recipient_id, message_text=None):
    """Отправляет уведомление о суперлайке с возможным сообщением и показывает анкету отправителя"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем данные отправителя
        cursor.execute("""
            SELECT u.*, c.name as city_name 
            FROM users u
            LEFT JOIN cities c ON u.city_id = c.id
            WHERE u.telegram_id = %s
        """, (sender_id,))
        
        columns = [desc[0] for desc in cursor.description]
        sender_data = cursor.fetchone()
        
        if not sender_data:
            print(f"Отправитель с telegram_id={sender_id} не найден")
            return
        
        sender_profile = dict(zip(columns, sender_data))
        
        # Получаем фото отправителя
        sender_profile['photos'] = await get_user_photos(sender_id)
        
        # Формируем основное сообщение
        message = (
            "🔥 Вам поставили Суперлайк!\n\n"
            f"{sender_profile['name']} хочет с вами познакомиться!\n\n"
        )
        
        if message_text and message_text != "Пропустить":
            message += f"📩 Сообщение: {message_text}\n\n"
        
        if sender_profile.get('username'):
            message += f"Напишите: @{sender_profile['username']}\n"
            message += f"Или перейдите в чат: https://t.me/{sender_profile['username']}"
        else:
            message += "К сожалению, у пользователя не указан username в Telegram."
        
        # Отправляем уведомление
        try:
            # Сначала отправляем текстовое сообщение
            await bot.send_message(chat_id=recipient_id, text=message)
            
            # Затем отправляем заголовок перед анкетой
            await bot.send_message(chat_id=recipient_id, text="Анкета пользователя, который поставил вам суперлайк:")
            
            # Затем отправляем анкету отправителя
            subscription_type = await get_user_subscription(sender_id)
            show_badge = sender_profile.get('show_badge', True)
            
            if subscription_type == 1 and show_badge:  # Premium
                subscription_emoji = "🏆"
            elif subscription_type == 2 and show_badge:  # VIP
                subscription_emoji = "👑"
            else:
                subscription_emoji = ""
            
            description_text = f"\n\n{sender_profile['description']}" if sender_profile.get('description') else ""
            experience_text = f"\n{sender_profile['experience']}" if sender_profile.get('experience') else ""
            gym_street_text = f", {sender_profile['gym_street']}" if sender_profile.get('gym_street') else ""

            profile_text = (
                f"{subscription_emoji}\n"
                f"{sender_profile['name']}, {sender_profile['age']}, {sender_profile.get('city_name', 'Не указан')}\n"
                f"{sender_profile['gym_name']}{gym_street_text}"
                f"{experience_text}"
                f"{description_text}"
            )
            
            # Создаем медиагруппу
            media_group = []
            
            # Добавляем видео (если есть) как первый элемент с подписью
            if sender_profile.get('video'):
                media_group.append(InputMediaVideo(sender_profile['video'], caption=profile_text))
            
            # Добавляем фото (если есть)
            if sender_profile.get('photos'):
                for i, photo in enumerate(sender_profile['photos']):
                    # Добавляем подпись только к первому фото, если нет видео
                    if not media_group:  # Если видео нет
                        media_group.append(InputMediaPhoto(photo, caption=profile_text))
                    else:
                        media_group.append(InputMediaPhoto(photo))
            
            if media_group:
                try:
                    await bot.send_media_group(chat_id=recipient_id, media=media_group)
                except Exception as e:
                    print(f"Ошибка при отправке медиагруппы: {e}")
                    await bot.send_message(chat_id=recipient_id, text=profile_text)
            else:
                await bot.send_message(chat_id=recipient_id, text=profile_text)
                
            print("Уведомление о суперлайке успешно отправлено")
            
        except Exception as e:
            print(f"Ошибка при отправке уведомления о суперлайке: {e}")
        
    except Exception as e:
        print(f"Ошибка при получении данных пользователя: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()

async def handle_superlike_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает сообщение для суперлайка"""
    user_id = update.effective_user.id
    target_user_id = context.user_data['superlike_target']
    message_text = update.message.text
    
    # Проверяем подписку пользователя
    subscription_type = await get_user_subscription(user_id)
    
    # Сохраняем суперлайк
    success = await save_user_action(user_id, target_user_id, 2)  # 2 - код для суперлайка
    
    if success:
        # Используем суперлайк
        await use_super_like(user_id)
        
        # Отправляем уведомление с сообщением только для VIP
        if subscription_type == 2 and message_text != "Пропустить":
            await send_superlike_notification(context.bot, user_id, target_user_id, message_text)
        else:
            await send_superlike_notification(context.bot, user_id, target_user_id)
    
    # Обновляем статистику просмотров и проверяем рекламу
    ad_shown = await update_view_stats(user_id, context)
    
    # Если была показана реклама, ждем нажатия кнопки "Пропустить"
    if ad_shown:
        return PROFILE_ACTION
    
    # Если реклама не была показана, продолжаем показ анкет
    return await continue_showing_profiles(update, context)



# Добавление подписки пользователю

(ADD_PREMIUM, SELECT_SUBSCRIPTION_TYPE) = range(60, 62)

def get_subscription_type_keyboard():
    return ReplyKeyboardMarkup([
        ["Premium", "VIP"],
        ["Отмена"]
    ], resize_keyboard=True)

async def set_user_subscription(user_id, subscription_type):
    """Устанавливает подписку пользователю и обновляет дату окончания"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Проверяем, есть ли у пользователя рефералы
        cursor.execute("""
            SELECT COUNT(*) FROM referrals 
            WHERE referrer_id = (SELECT id FROM users WHERE telegram_id = %s)
            AND bonus_applied = FALSE
        """, (user_id,))
        referral_count = cursor.fetchone()[0]
        
        # Базовый срок подписки
        interval = '30 days'
        
        # Если есть непримененные рефералы, добавляем бонусные дни
        if referral_count > 0:
            bonus_days = referral_count * 3  # +3 дня за каждого реферала
            interval = f'{30 + bonus_days} days'
            
            # Помечаем рефералов как обработанные
            cursor.execute("""
                UPDATE referrals 
                SET bonus_applied = TRUE
                WHERE referrer_id = (SELECT id FROM users WHERE telegram_id = %s)
            """, (user_id,))
        
        cursor.execute(f"""
            UPDATE users 
            SET subscription_type = %s,
                subscription_end_date = CURRENT_DATE + INTERVAL '{interval}',
                super_likes_remaining = CASE 
                    WHEN %s = 1 THEN 5 
                    WHEN %s = 2 THEN 10
                    ELSE 0 
                END
            WHERE telegram_id = %s
        """, (subscription_type, subscription_type, subscription_type, user_id))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка при установке подписки: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

async def add_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса назначения подписки"""
    owner_id = int(os.getenv("OWNER_ID", 0))
    
    if update.effective_user.id != owner_id:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Введите Telegram ID пользователя:",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADD_PREMIUM

async def get_user_id_for_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем Telegram ID пользователя для назначения подписки"""
    try:
        user_id = int(update.message.text)
        context.user_data['premium_user_id'] = user_id
        
        await update.message.reply_text(
            "Выберите тип подписки:",
            reply_markup=get_subscription_type_keyboard()
        )
        return SELECT_SUBSCRIPTION_TYPE
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректный Telegram ID (число):")
        return ADD_PREMIUM

async def select_subscription_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает выбор типа подписки"""
    subscription_type = update.message.text
    user_id = context.user_data['premium_user_id']
    
    if subscription_type == "Отмена":
        await update.message.reply_text(
            "Действие отменено.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    # Определяем числовое значение подписки
    if subscription_type == "Premium":
        sub_type = 1
    elif subscription_type == "VIP":
        sub_type = 2
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите тип подписки из предложенных вариантов.",
            reply_markup=get_subscription_type_keyboard()
        )
        return SELECT_SUBSCRIPTION_TYPE
    
    # Устанавливаем подписку
    success = await set_user_subscription(user_id, sub_type)
    
    if success:
        await update.message.reply_text(
            f"✅ Пользователю {user_id} успешно назначена подписка {subscription_type} на 30 дней!",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text(
            "❌ Не удалось назначить подписку. Пользователь с таким ID может не существовать.",
            reply_markup=ReplyKeyboardRemove()
        )
    
    return ConversationHandler.END

async def check_expired_subscriptions():
    """Проверяет и отменяет истекшие подписки, сбрасывая все связанные поля"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Находим пользователей с истекшей подпиской
        cursor.execute("""
            SELECT telegram_id FROM users 
            WHERE subscription_type > 0 
            AND subscription_end_date < CURRENT_DATE
        """)
        
        expired_users = cursor.fetchall()
        
        if not expired_users:
            print("Нет подписок для отмены.")
            return
        
        # Отменяем подписки и сбрасываем все связанные поля
        cursor.execute("""
            UPDATE users 
            SET 
                subscription_type = 0,
                subscription_end_date = NULL,
                super_likes_remaining = 0,
                last_super_likes_reset = NULL,
                show_badge = FALSE
            WHERE subscription_type > 0 
            AND subscription_end_date < CURRENT_DATE
        """)
        
        conn.commit()
        print(f"Отменено {len(expired_users)} подписок. Все связанные поля сброшены.")
        
    except Exception as e:
        print(f"Ошибка при проверке подписок: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()



# "Кто меня лайкнул"

# Добавим новое состояние
VIEW_LIKED_PROFILES = 70

async def view_who_liked_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает кто лайкнул пользователя"""
    user_id = update.effective_user.id
    
    # Проверяем VIP статус
    subscription_type = await get_user_subscription(user_id)
    if subscription_type != 2:  # Не VIP
        await update.message.reply_text(
            "Эта функция доступна только для VIP пользователей.\n\n"
            "Оформите подписку VIP в настройках, чтобы увидеть кто вас лайкнул.",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    # Проверяем, когда в последний раз пользователь смотрел лайки
    last_viewed = context.user_data.get('last_likes_viewed')
    if last_viewed:
        time_since_last_view = datetime.now() - last_viewed
        hours_since_last_view = time_since_last_view.total_seconds() / 3600
        
        if hours_since_last_view < 24:
            hours_remaining = 24 - hours_since_last_view
            await update.message.reply_text(
                f"Вы уже просматривали лайки сегодня. Следующий просмотр будет доступен через {int(hours_remaining)} часа.",
                reply_markup=get_edit_keyboard()
            )
            return ConversationHandler.END
    
    # Получаем список лайкнувших
    likers = await get_users_who_liked_me(user_id)
    if not likers:
        await update.message.reply_text(
            "Вас пока что никто не лайкнул 😢\n"
            "Продолжайте активно использовать бот, и у вас появятся лайки!",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    # Сохраняем время просмотра
    context.user_data['last_likes_viewed'] = datetime.now()
    context.user_data['likers'] = likers
    context.user_data['current_liker_index'] = 0
    
    # Показываем первого лайкнувшего
    await show_liker_profile(update, context)
    
    return VIEW_LIKED_PROFILES

async def get_users_who_liked_me(user_id):
    """Получает список пользователей, которые лайкнули текущего пользователя"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем ID текущего пользователя в базе
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
        current_user_id = cursor.fetchone()
        if not current_user_id:
            return []
        
        current_user_id = current_user_id[0]
        
        # Получаем пользователей, которые лайкнули текущего
        cursor.execute("""
            SELECT u.*, c.name as city_name 
            FROM users u
            LEFT JOIN cities c ON u.city_id = c.id
            WHERE u.id IN (
                SELECT user_id FROM user_actions 
                WHERE target_user_id = %s AND action = 1
            )
            ORDER BY RANDOM()
        """, (current_user_id,))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Ошибка при получении лайкнувших: {e}")
        return []
    finally:
        if conn:
            cursor.close()
            conn.close()

async def show_liker_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает профиль пользователя, который лайкнул с поддержкой видео и стандартных кнопок"""
    likers = context.user_data['likers']
    index = context.user_data['current_liker_index']
    
    if index >= len(likers):
        await update.message.reply_text(
            "Вы просмотрели всех, кто вас лайкнул!",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    profile = likers[index]
    
    # Получаем тип подписки пользователя
    subscription_type = await get_user_subscription(profile['telegram_id'])
    
    # Добавляем соответствующий эмоджи в зависимости от подписки
    subscription_emoji = ""
    if subscription_type == 1:  # Premium
        subscription_emoji = "🏆"
    elif subscription_type == 2:  # VIP
        subscription_emoji = "👑"
    
    # Формируем текст анкеты
    description_text = f"\n\n{profile['description']}" if profile.get('description') else ""
    experience_text = f"\n{profile['experience']}" if profile.get('experience') else ""
    gym_street_text = f", {profile['gym_street']}" if profile.get('gym_street') else ""

    profile_text = (
        f"💪 Этот пользователь лайкнул вас!\n\n"
        f"{subscription_emoji}\n"
        f"{profile['name']}, {profile['age']}, {profile.get('city_name', 'Не указан')}\n"
        f"{profile['gym_name']}{gym_street_text}"
        f"{experience_text}"
        f"{description_text}"
    )
    
    # Получаем все медиа пользователя (фото и видео)
    photos = await get_user_photos(profile['telegram_id'])
    video = profile.get('video')
    
    # Создаем медиагруппу
    media_group = []
    
    # Добавляем видео (если есть) как первый элемент с подписью
    if video:
        media_group.append(InputMediaVideo(video, caption=profile_text))
    
    # Добавляем фото (если есть)
    if photos:
        for i, photo in enumerate(photos):
            # Добавляем подпись только к первому фото, если нет видео
            if not media_group:  # Если видео нет
                media_group.append(InputMediaPhoto(photo, caption=profile_text))
            else:
                media_group.append(InputMediaPhoto(photo))
    
    if media_group:
        try:
            # Отправляем медиагруппу
            await update.message.reply_media_group(media=media_group)
            
            # Проверяем, может ли пользователь использовать суперлайк
            can_super_like = await can_use_super_like(update.effective_user.id)
            
            # Отправляем стандартные кнопки действий
            await update.message.reply_text(
                "Выберите действие:",
                reply_markup=get_profile_action_keyboard(update.effective_user.id, can_super_like)
            )
        except Exception as e:
            print(f"Ошибка при отправке медиагруппы: {e}")
            # Если не удалось отправить медиагруппу, отправляем текст
            await update.message.reply_text(
                profile_text,
                reply_markup=get_profile_action_keyboard(update.effective_user.id, can_super_like)
            )
    else:
        # Если нет ни фото, ни видео, отправляем только текст
        await update.message.reply_text(
            profile_text,
            reply_markup=get_profile_action_keyboard(update.effective_user.id, await can_use_super_like(update.effective_user.id))
        )

async def handle_liker_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает действия при просмотре лайкнувших с поддержкой стандартных кнопок"""
    action = update.message.text
    likers = context.user_data['likers']
    index = context.user_data['current_liker_index']
    current_profile = likers[index]
    user_id = update.effective_user.id
    
    # Обработка "Закончить просмотр"
    if action == "Закончить просмотр":
        await update.message.reply_text(
            "Просмотр анкет завершён.",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    # Обработка обычного лайка
    if action == "💪":
        success = await save_user_action(user_id, current_profile['telegram_id'], 1)
        
        if success:
            # Проверяем взаимный лайк
            conn = None
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                cursor = conn.cursor()
                
                cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
                current_user_id = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT 1 FROM user_actions
                    WHERE user_id = %s AND target_user_id = %s AND action = 1
                """, (current_profile['id'], current_user_id))
                
                if cursor.fetchone():
                    await send_match_notification(context.bot, user_id, current_profile['telegram_id'])
                    await send_match_notification(context.bot, current_profile['telegram_id'], user_id)

            except Exception as e:
                print(f"Ошибка при проверке взаимного лайка: {e}")
            finally:
                if conn:
                    cursor.close()
                    conn.close()
        
        # Удаляем этого пользователя из списка (чтобы не показывать снова)
        del likers[index]
        if not likers:
            await update.message.reply_text(
                "Вы просмотрели всех, кто вас лайкнул!",
                reply_markup=get_edit_keyboard()
            )
            return ConversationHandler.END
        
        # Показываем следующего пользователя
        if context.user_data['current_liker_index'] >= len(likers):
            await update.message.reply_text(
                "Вы просмотрели всех, кто вас лайкнул!",
                reply_markup=get_edit_keyboard()
            )
            return ConversationHandler.END
        
        await show_liker_profile(update, context)
        return VIEW_LIKED_PROFILES
    
    # Обработка дизлайка
    elif action == "👎":
        await save_user_action(user_id, current_profile['telegram_id'], 0)
        
        # Переходим к следующей анкете
        context.user_data['current_liker_index'] += 1
        
        if context.user_data['current_liker_index'] >= len(likers):
            await update.message.reply_text(
                "Вы просмотрели всех, кто вас лайкнул!",
                reply_markup=get_edit_keyboard()
            )
            return ConversationHandler.END
        
        await show_liker_profile(update, context)
        return VIEW_LIKED_PROFILES
    
    # Обработка суперлайка
    elif action == "🔥 Суперлайк":
        # Проверяем подписку пользователя
        subscription_type = await get_user_subscription(user_id)
        
        if subscription_type == 0:  # Нет подписки
            await update.message.reply_text(
                "🔥 Суперлайки доступны только для пользователей с Premium или VIP подпиской.\n\n"
                "Неограниченные суперлайки + отправка сообщения (VIP)\n"
                "5 суперлайков в день (Premium)\n\n"
                "Для оформления подписки нажмите «Закончить просмотр» → «⚙️ Настройки» → «Условия подписки»",
                reply_markup=get_profile_action_keyboard()
            )
            return VIEW_LIKED_PROFILES
        
        # Для подписчиков проверяем остаток суперлайков
        conn = None
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT super_likes_remaining FROM users 
                WHERE telegram_id = %s
            """, (user_id,))
            result = cursor.fetchone()
            
            if result and result[0] <= 0:
                if subscription_type == 1:  # Premium
                    await update.message.reply_text(
                        "❌ У вас закончились суперлайки на сегодня!\n\n"
                        "Лимит: 5 суперлайков в день (обновляется каждые 24 часа).\n\n"
                        "Для неограниченных суперлайков оформите подписку VIP.",
                        reply_markup=get_profile_action_keyboard()
                    )
                return VIEW_LIKED_PROFILES
                
        except Exception as e:
            print(f"Ошибка при проверке суперлайков: {e}")
        finally:
            if conn:
                conn.close()

        # Сохраняем информацию о суперлайке
        context.user_data['superlike_target'] = current_profile['telegram_id']
        
        if subscription_type == 2:  # VIP - предлагаем отправить сообщение
            await update.message.reply_text(
                "💬 Хотите отправить сообщение вместе с суперлайком? Напишите текст или нажмите «Пропустить»:",
                reply_markup=ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
            )
            return SUPERLIKE_MESSAGE
        else:  # Premium - сразу отправляем суперлайк без сообщения
            # Сохраняем суперлайк
            success = await save_user_action(user_id, current_profile['telegram_id'], 2)
            
            if success:
                # Используем суперлайк
                await use_super_like(user_id)
                await send_superlike_notification(context.bot, user_id, current_profile['telegram_id'])
                
            # Переходим к следующей анкете
            context.user_data['current_liker_index'] += 1
            
            if context.user_data['current_liker_index'] >= len(likers):
                await update.message.reply_text(
                    "Вы просмотрели всех, кто вас лайкнул!",
                    reply_markup=get_edit_keyboard()
                )
                return ConversationHandler.END
            
            await show_liker_profile(update, context)
            return VIEW_LIKED_PROFILES
    
    # Обработка пропуска рекламы
    elif action == "Пропустить":
        return await continue_showing_likers(update, context)
    
    return VIEW_LIKED_PROFILES

async def continue_showing_likers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Продолжает показ лайкнувших профилей"""
    # Переходим к следующей анкете
    context.user_data['current_liker_index'] += 1
    
    if context.user_data['current_liker_index'] >= len(context.user_data['likers']):
        await update.message.reply_text(
            "Вы просмотрели всех, кто вас лайкнул!",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    await show_liker_profile(update, context)
    return VIEW_LIKED_PROFILES



# Возвращение назад при просмотре

async def save_viewed_profile(context: ContextTypes.DEFAULT_TYPE, profile_data):
    """Сохраняет просмотренную анкету в историю"""
    if 'viewed_history' not in context.user_data:
        context.user_data['viewed_history'] = []
    
    # Добавляем анкету в историю (но не более 5 последних)
    context.user_data['viewed_history'].append(profile_data)
    if len(context.user_data['viewed_history']) > 5:
        context.user_data['viewed_history'].pop(0)



# Подобрать анкету за 3 минуты

# Добавим новую функцию для поиска неактивных пользователей
async def get_inactive_users(min_days_inactive=2, min_profiles_in_city=3):
    """Получает список неактивных пользователей, у которых в городе есть минимум min_profiles_in_city анкет, которые они не просматривали"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем пользователей, которые не ставили реакции более min_days_inactive дней
        # и у которых в городе есть минимум min_profiles_in_city анкет, с которыми они не взаимодействовали
        cursor.execute("""
            SELECT u.telegram_id, u.city_id, c.name as city_name
            FROM users u
            JOIN cities c ON u.city_id = c.id
            WHERE u.telegram_id NOT IN (
                SELECT DISTINCT user_id 
                FROM user_actions 
                WHERE timestamp > CURRENT_DATE - INTERVAL '%s days'
            )
            AND u.city_id IN (
                -- Города, где есть минимум min_profiles_in_city анкет
                SELECT city_id 
                FROM users 
                GROUP BY city_id 
                HAVING COUNT(*) >= %s
            )
            AND u.telegram_id NOT IN (
                SELECT telegram_id 
                FROM users 
                WHERE subscription_type = 2  -- Исключаем VIP пользователей
            )
            -- Проверяем, что у пользователя есть непросмотренные анкеты в его городе
            AND EXISTS (
                SELECT 1 
                FROM users potential_matches
                WHERE potential_matches.city_id = u.city_id
                AND potential_matches.telegram_id != u.telegram_id
                AND potential_matches.id NOT IN (
                    SELECT target_user_id 
                    FROM user_actions 
                    WHERE user_id = u.id
                )
                LIMIT %s
            )
        """, (min_days_inactive, min_profiles_in_city, min_profiles_in_city))
        
        return [dict(zip(('telegram_id', 'city_id', 'city_name'), row)) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Ошибка при получении неактивных пользователей: {e}")
        return []
    finally:
        if conn:
            conn.close()

# Добавим обработчик команды /select_users
async def select_inactive_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для рассылки уведомлений неактивным пользователям"""
    owner_id = int(os.getenv("OWNER_ID", 0))
    
    if update.effective_user.id != owner_id:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    await update.message.reply_text("⏳ Ищу неактивных пользователей...")
    
    # Получаем неактивных пользователей
    inactive_users = await get_inactive_users()
    
    if not inactive_users:
        await update.message.reply_text("Нет неактивных пользователей для рассылки.")
        return
    
    await update.message.reply_text(f"🔍 Найдено {len(inactive_users)} неактивных пользователей. Начинаю рассылку...")
    
    success_count = 0
    for user in inactive_users:
        try:
            # Создаем клавиатуру с кнопкой
            keyboard = ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
            
            await context.bot.send_message(
                chat_id=user['telegram_id'],
                text="Хочешь мы подберем тебе GymBro за 3 минуты? Нажимай кнопку ниже чтобы продолжить.",
                reply_markup=keyboard
            )
            success_count += 1
            await asyncio.sleep(0.3)  # Задержка между сообщениями
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {user['telegram_id']}: {e}")
    
    await update.message.reply_text(f"✅ Рассылка завершена! Уведомления отправлены {success_count} пользователям.")

# Добавим обработчик для кнопки "Подобрать"
async def handle_suggest_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки для просмотра анкет после предложения"""
    return await view_profiles(update, context)



# Эксклюзивный значок

# Добавим клавиатуру для управления значком
def get_badge_toggle_keyboard():
    return ReplyKeyboardMarkup([
        ["Показать значок", "Скрыть значок"],
        ["Назад"]
    ], resize_keyboard=True)

# Добавим новый обработчик для управления значком
async def toggle_badge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает выбор показа/скрытия значка"""
    action = update.message.text
    user_id = context.user_data['user_id']
    
    if action == "Назад":
        await update.message.reply_text(
            "Выберите что хотите изменить:",
            reply_markup=get_edit_choice_keyboard(context.user_data['current_data'])
        )
        return EDIT_CHOICE
    
    # Определяем новое значение для show_badge
    show_badge = True if action == "Показать значок" else False
    
    # Обновляем данные пользователя
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE users 
            SET show_badge = %s
            WHERE telegram_id = %s
        """, (show_badge, user_id))
        
        conn.commit()
        
        # Обновляем данные в context.user_data
        if 'current_data' in context.user_data:
            context.user_data['current_data']['show_badge'] = show_badge
        if 'changes' in context.user_data:
            context.user_data['changes']['show_badge'] = show_badge
        
        badge_status = "включен" if show_badge else "выключен"
        await update.message.reply_text(
            f"Значок подписки успешно {badge_status}!",
            reply_markup=get_edit_choice_keyboard(context.user_data['current_data'])
        )
        return EDIT_CHOICE
    except Exception as e:
        print(f"Ошибка при обновлении значка: {e}")
        await update.message.reply_text(
            "Произошла ошибка при изменении значка.",
            reply_markup=get_edit_choice_keyboard(context.user_data['current_data'])
        )
        return EDIT_CHOICE
    finally:
        if conn:
            conn.close()



# Ограниченное количество просмотров анкет

async def reset_daily_views():
    """Сбрасывает дневные счетчики просмотров для всех пользователей"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET profile_views_today = 0,
                last_profile_views_reset = CURRENT_TIMESTAMP
            WHERE subscription_type = 0
        """)
        conn.commit()
        print("Дневные счетчики просмотров сброшены")
    except Exception as e:
        print(f"Ошибка при сбросе счетчиков просмотров: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()



# Добавление реферальной системы

REFERRAL_INPUT = 101
SHARE_REFERRAL = 102

async def ask_for_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Спрашиваем реферальный код после создания анкеты (только если ещё не вводили)"""
    user_id = context.user_data['user_id']  # telegram_id пользователя

    # Проверяем, есть ли уже запись, что этот пользователь вводил рефкод
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 1
            FROM referrals r
            JOIN users u ON r.referred_id = u.id
            WHERE u.telegram_id = %s
            LIMIT 1
        """, (user_id,))
        
        if cursor.fetchone():
            # Уже вводил рефкод — пропускаем этот шаг
            return ConversationHandler.END

    except Exception as e:
        print(f"Ошибка при проверке реферала: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()

    # Если код ещё не вводился — спрашиваем
    await update.message.reply_text(
        f"<b>Есть ли у вас реферальный код?</b>\n\n"
        "Если да - введите его ниже.\n"
        "Если нет - нажмите «Пропустить».\n\n"
        f"<b>🔗 По реферальной системе вы получите 7 дней функций Premium пользователя!</b>",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
    )
    return REFERRAL_INPUT

async def process_referral_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Пропустить":
        await update.message.reply_text(
            "Регистрация завершена! Что вы хотите сделать?",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    try:
        referrer_id = int(update.message.text)
        user_id = context.user_data['user_id']
        
        if referrer_id == user_id:
            await update.message.reply_text(
                "Вы не можете использовать свой ID как реферальный код.",
                reply_markup=ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
            )
            return REFERRAL_INPUT
        
        # Проверяем существование реферера
        conn = None
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (referrer_id,))
            referrer_db_id = cursor.fetchone()
            
            if not referrer_db_id:
                await update.message.reply_text(
                    "Пользователь с таким ID не найден.",
                    reply_markup=ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
                )
                return REFERRAL_INPUT
                
            referrer_db_id = referrer_db_id[0]
            
            # Получаем ID текущего пользователя
            cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
            user_db_id = cursor.fetchone()[0]
            
            # Проверяем, есть ли уже реферальная связь
            cursor.execute("""
                SELECT 1 FROM referrals WHERE referred_id = %s
            """, (user_db_id,))
            
            if cursor.fetchone():
                await update.message.reply_text(
                    "Регистрация завершена! Что вы хотите сделать?",
                    reply_markup=get_edit_keyboard()
                )
                return ConversationHandler.END
            
            # Сохраняем реферальную связь
            cursor.execute("""
                INSERT INTO referrals (referrer_id, referred_id)
                VALUES (%s, %s)
                RETURNING id
            """, (referrer_db_id, user_db_id))
            
            if cursor.fetchone():
                # Применяем бонусы
                await apply_referral_bonus(user_id, is_referrer=False)
                await apply_referral_bonus(referrer_id, is_referrer=True)
                
                await update.message.reply_text(
                    "🎉 Вы получили 7 дней функций Premium пользователя!",
                    reply_markup=get_edit_keyboard()
                )
            else:
                await update.message.reply_text(
                    "Регистрация завершена! Что вы хотите сделать?",
                    reply_markup=get_edit_keyboard()
                )
            
            conn.commit()
        except Exception as e:
            print(f"Ошибка при обработке реферала: {e}")
            if conn:
                conn.rollback()
            await update.message.reply_text(
                "Произошла ошибка. Попробуйте позже.",
                reply_markup=get_edit_keyboard()
            )
        finally:
            if conn:
                conn.close()
    except ValueError:
        await update.message.reply_text(
            "Введите корректный Telegram ID (число).",
            reply_markup=ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
        )
        return REFERRAL_INPUT
    
    return ConversationHandler.END

async def apply_referral_bonus(user_id, is_referrer):
    """Применяет бонус за реферала с учетом текущего типа подписки"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем текущий тип подписки и дату окончания
        cursor.execute("""
            SELECT subscription_type, subscription_end_date 
            FROM users 
            WHERE telegram_id = %s
        """, (user_id,))
        result = cursor.fetchone()
        
        if not result:
            return False
            
        current_type, current_end = result
        
        # Для приведенного пользователя - 7 дней Premium (если у него нет подписки)
        if not is_referrer:
            if current_type == 0:  # Нет подписки
                cursor.execute("""
                    UPDATE users 
                    SET subscription_type = 1,
                        subscription_end_date = CURRENT_DATE + INTERVAL '7 days'
                    WHERE telegram_id = %s
                """, (user_id,))
            # Если уже есть подписка - ничего не делаем
        # Для реферера - +3 дня в зависимости от текущего статуса
        else:
            # Обновляем счетчик рефералов
            cursor.execute("""
                INSERT INTO referral_stats (referrer_id, invited_count)
                VALUES (
                    (SELECT id FROM users WHERE telegram_id = %s),
                    1
                )
                ON CONFLICT (referrer_id) 
                DO UPDATE SET invited_count = referral_stats.invited_count + 1
            """, (user_id,))
            
            bonus_days = 3
            if current_type == 2:  # VIP - не меняем тип, просто добавляем дни
                cursor.execute("""
                    UPDATE users 
                    SET subscription_end_date = GREATEST(
                        COALESCE(subscription_end_date, CURRENT_DATE), 
                        CURRENT_DATE + INTERVAL '%s days'
                    )
                    WHERE telegram_id = %s
                """, (bonus_days, user_id))
            elif current_type == 1:  # Premium - добавляем дни
                cursor.execute("""
                    UPDATE users 
                    SET subscription_end_date = GREATEST(
                        COALESCE(subscription_end_date, CURRENT_DATE), 
                        CURRENT_DATE + INTERVAL '%s days'
                    )
                    WHERE telegram_id = %s
                """, (bonus_days, user_id))
            else:  # Нет подписки - даем Premium + дни
                cursor.execute("""
                    UPDATE users 
                    SET subscription_type = 1,
                        subscription_end_date = CURRENT_DATE + INTERVAL '%s days'
                    WHERE telegram_id = %s
                """, (bonus_days, user_id))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка при применении реферального бонуса: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

async def share_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает реферальную ссылку и кнопки"""
    user_id = update.effective_user.id
    context.user_data['in_referral_menu'] = True  # Устанавливаем флаг, что мы в меню реферальной системы
    
    # Создаем клавиатуру с кнопками
    keyboard = ReplyKeyboardMarkup([
        ["Поделиться с другом", "Опубликовать в канале"],
        ["Назад"]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        f"🔗 Ваш реферальный код: <code>{user_id}</code>\n\n"
        f"<b>Приглашайте друзей и получайте +3 дня Premium за каждого!</b>\n\n"
        "<b>Как это работает:</b>\n"
        "1. Друг регистрируется по вашему коду → получает 7 дней Premium\n"
        "2. Вы получаете +3 дня Premium за каждого приведенного друга\n\n"
        "Выберите действие:",
        parse_mode='HTML',
        reply_markup=keyboard
    )
    return SHARE_REFERRAL

async def handle_share_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает выбор способа поделиться"""
    action = update.message.text
    user_id = update.effective_user.id
    
    if action == "Назад":
        # Удаляем флаг меню реферальной системы
        context.user_data.pop('in_referral_menu', None)
        await update.message.reply_text(
            "⚙️ Настройки:",
            reply_markup=get_settings_keyboard()
        )
        return SETTINGS
    
    referral_text_1 = (
        "💥 Привет, нашёл бота — GymBros!\n\n"
        "Это первый в России бот, где знакомятся качки, фитоняшки и все, кто живёт железом 🏋️‍♂️🔥\n\n"
        "🔗 <b>Зарегистрируйся по моей ссылке и получи 7 дней функций Premium пользователя:</b>\n\n"
        "👇 Попробуй сам:\n"
        f"<a href='https://t.me/OfficialGymBrosBot?start=ref{user_id}'>@OfficialGymBrosBot</a>\n\n"
        f"<b>Мой реферальный код:</b> <code>{user_id}</code>"
    )

    referral_text_2 = (
        f"🏆 <b>GymBros — революция в мире спортивных знакомств!</b>\n\n"
        "Первый в России Telegram-бот для тех, кто живёт тренировками и железом 💪\n\n"
        "💬 Знакомься, тренируйся, достигай целей вместе!\n\n"
        "🔗 <b>Зарегистрируйся по моей ссылке и получи 7 дней функций Premium пользователя:</b>\n\n"
        "👇 Попробуй сам:\n"
        f"<a href='https://t.me/OfficialGymBrosBot?start=ref{user_id}'>@OfficialGymBrosBot</a>\n\n"
        f"<b>Мой реферальный код:</b> <code>{user_id}</code>"
    )
    
    if action == "Поделиться с другом":
        await update.message.reply_text(
            "Скопируй это сообщение и отправь другу:",
            parse_mode='HTML'
        )
        await update.message.reply_text(
            f"{referral_text_1}",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
        )
    elif action == "Опубликовать в канале":
        await update.message.reply_text(
            "Скопируй это сообщение и опубликуй в своем канале:",
            parse_mode='HTML'
        )
        await update.message.reply_text(
            f"{referral_text_2}",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
        )
    
    return SHARE_REFERRAL


# Лидерборд

LEADERBOARD = 103

# Добавим функцию для получения лидерборда
async def get_referral_leaderboard(limit=5):
    """Получает топ-5 пользователей по количеству приглашенных"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT u.telegram_id, u.name, rs.invited_count
            FROM referral_stats rs
            JOIN users u ON rs.referrer_id = u.id
            ORDER BY rs.invited_count DESC
            LIMIT %s
        """, (limit,))
        
        return cursor.fetchall()
    except Exception as e:
        print(f"Ошибка при получении лидерборда: {e}")
        return []
    finally:
        if conn:
            conn.close()

# Добавим обработчик для кнопки "Лидерборд"
async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает топ-5 пользователей по количеству приглашенных друзей"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем топ-5 рефералов
        cursor.execute("""
            SELECT 
                u.telegram_id, 
                u.username,
                u.name,
                rs.invited_count
            FROM referral_stats rs
            JOIN users u ON rs.referrer_id = u.id
            ORDER BY rs.invited_count DESC
            LIMIT 5
        """)
        
        top_referrers = cursor.fetchall()
        
        if not top_referrers:
            await update.message.reply_text(
                "Пока никто не пригласил друзей. Будьте первыми!",
                reply_markup=get_settings_keyboard()
            )
            return SETTINGS
        
        # Формируем текст лидерборда
        leaderboard_text = "🏆 <b>Топ-5 по приглашениям:</b>\n\n"
        
        for i, (telegram_id, username, name, count) in enumerate(top_referrers, 1):
            # Определяем правильную форму слова "приглашённый"
            if count % 10 == 1 and count % 100 != 11:
                word = "приглашённый"
            elif 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20):
                word = "приглашённых"
            else:
                word = "приглашённых"
            
            # Используем username если есть, иначе имя
            display_name = f"@{username}" if username else name
            
            leaderboard_text += f"{i}. {display_name} - {count} {word}\n"
        
        leaderboard_text += "\nПриглашайте друзей и поднимайтесь в рейтинге!"
        
        await update.message.reply_text(
            leaderboard_text,
            parse_mode='HTML',
            reply_markup=get_settings_keyboard()
        )
        
    except Exception as e:
        print(f"Ошибка при получении лидерборда: {e}")
        await update.message.reply_text(
            "Произошла ошибка при загрузке рейтинга. Попробуйте позже.",
            reply_markup=get_settings_keyboard()
        )
    finally:
        if conn:
            conn.close()
    
    return SETTINGS




def main():
    application = Application.builder().token(TOKEN).build()
    
    # Обработчик команды /start
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("privacy", privacy_command))
    application.add_handler(CommandHandler("terms", terms_command))
    application.add_handler(CommandHandler("delete_my_data", delete_my_data_command))

    # Обработчик создания анкеты
    create_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Создать анкету$"), begin_questionnaire)],
        states={
            CONSENT: [
                MessageHandler(filters.Regex("^✅ Согласен$"), accept_consent),
                MessageHandler(filters.Regex("^❌ Не согласен$"), decline_consent),
                MessageHandler(filters.Regex("^Политика конфиденциальности$"), show_privacy_policy),
                MessageHandler(filters.Regex("^Соглашение$"), show_terms),
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            PHOTO: [
                MessageHandler(filters.PHOTO | filters.VIDEO | filters.TEXT, get_media)
            ],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gender)],
            PREFERRED_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_preferred_gender)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_city)],
            EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_experience)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_description)],
            GYM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gym_name)],
            GYM_STREET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gym_street)],
            REFERRAL_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_referral_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Обработчик использования существующей анкеты
    application.add_handler(MessageHandler(filters.Regex("^Использовать существующую$"), use_existing_profile))

    # Обновим ConversationHandler для редактирования
    edit_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Изменить анкету$"), edit_questionnaire)],
        states={
            EDIT_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_choice)],
            EDIT_SELECTED: [
                MessageHandler(filters.PHOTO | filters.VIDEO, edit_selected),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_selected)
            ],
            TOGGLE_BADGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, toggle_badge)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )   

    # Обработчик просмотра анкет
    view_profiles_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Смотреть анкеты$"), view_profiles)],
        states={
            PROFILE_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_profile_action)],
            SUPERLIKE_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_superlike_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Обработчик генерации фейковых анкет
    generate_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("generate_fake", start_generate_profile)],
        states={
            GET_TELEGRAM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_telegram_id)],
            GET_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_username)],
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fake_name)],
            GET_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fake_age)],
            GET_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fake_gender)],
            GET_PREFERRED_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fake_preferred_gender)],
            GET_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fake_city)],
            GET_EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fake_experience)],
            GET_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fake_description)],
            GET_PHOTO: [
                MessageHandler(filters.PHOTO, get_fake_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_fake_photo)
            ],
            GET_GYM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fake_gym_name)],
            GET_GYM_STREET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fake_gym_street)],
            REFERRAL_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_referral_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Обработчик просмотра новых анкет
    check_new_users_conv = ConversationHandler(
        entry_points=[CommandHandler("check_new_users", check_new_users)],
        states={
            VIEW_NEW_PROFILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_profile_action)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Добавляем новый обработчик для рассылки уведомлений по городу
    notify_city_conv = ConversationHandler(
        entry_points=[CommandHandler("notify_city", notify_city_start)],
        states={},  # Больше нет состояний, так как город не выбирается
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Добавляем обработчик настроек
    settings_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^⚙️ Настройки$"), settings)],
        states={
            SETTINGS: [
                MessageHandler(filters.Regex("^Условия подписки$"), subscription_info),
                MessageHandler(filters.Regex("^Узнать мой ID$"), get_user_id_info),
                MessageHandler(filters.Regex("^Реферальная система$"), share_referral),
                MessageHandler(filters.Regex("^Лидерборд$"), show_leaderboard),
                MessageHandler(filters.Regex("^Политика конфиденциальности$"), show_privacy_policy),
                MessageHandler(filters.Regex("^Соглашение$"), show_terms),
                MessageHandler(filters.Regex("^🗑 Удалить мои данные$"), delete_my_data_command),
                MessageHandler(filters.Regex("^Назад$"), back_to_menu)
            ],
            SUBSCRIPTION_INFO: [
                MessageHandler(filters.Regex("^Premium"), contact_manager),
                MessageHandler(filters.Regex("^VIP"), contact_manager),
                MessageHandler(filters.Regex("^Назад$"), back_to_settings)
            ],
            SHARE_REFERRAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_share_action)
            ],
            LEADERBOARD: [
                MessageHandler(filters.Regex("^Назад$"), back_to_settings)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Обработчик назначения подписки
    add_premium_conv = ConversationHandler(
        entry_points=[CommandHandler("add_premium", add_premium_start)],
        states={
            ADD_PREMIUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_id_for_premium)],
            SELECT_SUBSCRIPTION_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_subscription_type)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Обработчик просмотра лайкнувших
    view_liked_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^«Кто меня лайкнул»$"), view_who_liked_me)],
        states={
            VIEW_LIKED_PROFILES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_liker_action)
            ],
            SUPERLIKE_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_superlike_message)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Обработчик реферальной системы
    referral_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Реферальная система$"), share_referral)],
        states={
            SHARE_REFERRAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_share_action)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(create_conv_handler)
    application.add_handler(edit_conv_handler)
    application.add_handler(view_profiles_conv)
    application.add_handler(generate_conv_handler)
    application.add_handler(CommandHandler("notify_about_update", notify_all_users_command))
    application.add_handler(check_new_users_conv)
    application.add_handler(notify_city_conv)
    application.add_handler(settings_conv)
    application.add_handler(add_premium_conv)
    application.add_error_handler(error_handler)
    application.add_handler(view_liked_conv)
    application.add_handler(CommandHandler("select_users", select_inactive_users))
    application.add_handler(referral_conv)

    # Настройка планировщика
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_expired_subscriptions, 'cron', hour=0, minute=0)
    scheduler.add_job(reset_daily_views, 'cron', hour=0, minute=0)
    
    # Запускаем планировщик в обработчике запуска приложения
    async def post_init(application):
        scheduler.start()
    
    application.post_init = post_init

    try:
        # Запускаем бота
        print("🤖 Бот запущен!")
        application.run_polling()
    finally:
        # Останавливаем планировщик при завершении работы бота
        scheduler.shutdown()