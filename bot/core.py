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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # /root/
sys.path.insert(0, "/root/gymbros_admin")  # Путь к Django-проекту

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gymbros_admin.settings")
django.setup()  # Инициализация Django

# Теперь можно импортировать модели
from botapp.models import UserAdStat, Ad


# Загрузка переменных окружения
load_dotenv()

# Токен бота
TOKEN = os.getenv("TOKEN")

# Данные для подключения к БД
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT")
}

# Состояния для ConversationHandler
(
    NAME, PHOTO, AGE, GENDER, PREFERRED_GENDER, CITY, EXPERIENCE, 
    DESCRIPTION, GYM_NAME, GYM_STREET
) = range(10)

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
        
        # Формируем динамический SQL запрос
        set_clauses = []
        values = []
        
        for field, value in update_data.items():
            if field == 'city_id':
                set_clauses.append("city_id = %s")
                values.append(value)
            elif field == 'photo':
                set_clauses.append("photo = %s")
                values.append(value)
            elif field == 'name':
                set_clauses.append("name = %s")
                values.append(value)
            elif field == 'age':
                set_clauses.append("age = %s")
                values.append(value)
            elif field == 'gender':
                set_clauses.append("gender = %s")
                values.append(value)
            elif field == 'preferred_gender':
                set_clauses.append("preferred_gender = %s")
                values.append(value)
            elif field == 'experience':
                set_clauses.append("experience = %s")
                values.append(value)
            elif field == 'description':
                set_clauses.append("description = %s")
                values.append(value)
            elif field == 'gym_name':
                set_clauses.append("gym_name = %s")
                values.append(value)
            elif field == 'gym_street':
                set_clauses.append("gym_street = %s")
                values.append(value)
        
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
            set_clauses=sql.SQL(', ').join(map(sql.SQL, set_clauses))
        )
        
        print(f"Выполняем запрос: {query.as_string(conn)} с параметрами: {values}")
        cursor.execute(query, values)
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
async def save_user_to_db(user_data, context, update: Update = None):
    """Исправленная функция сохранения пользователя с username"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем username из Telegram
        username = update.effective_user.username if update and update.effective_user else None
        
        # Проверяем обязательные поля
        required_fields = ['name', 'age', 'gender', 'preferred_gender', 'city_id']
        for field in required_fields:
            if field not in user_data:
                raise ValueError(f"Отсутствует обязательное поле: {field}")
        
        cursor.execute("""
            INSERT INTO users (
                telegram_id, username, name, photo, age, gender,
                preferred_gender, city_id, experience, description,
                gym_name, gym_street
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (telegram_id) 
            DO UPDATE SET
                username = EXCLUDED.username,
                name = EXCLUDED.name,
                photo = EXCLUDED.photo,
                age = EXCLUDED.age,
                gender = EXCLUDED.gender,
                preferred_gender = EXCLUDED.preferred_gender,
                city_id = EXCLUDED.city_id,
                experience = EXCLUDED.experience,
                description = EXCLUDED.description,
                gym_name = EXCLUDED.gym_name,
                gym_street = EXCLUDED.gym_street
            RETURNING id
        """, (
            context.user_data['user_id'],
            username,  # Теперь username точно сохраняется
            user_data['name'],
            user_data.get('photo'),
            user_data['age'],
            user_data.get('gender', 1),
            user_data.get('preferred_gender', 1),
            user_data['city_id'],
            user_data.get('experience'),
            user_data.get('description'),
            user_data.get('gym_name'),
            user_data.get('gym_street')
        ))
        
        result = cursor.fetchone()
        conn.commit()
        
        if result:
            print(f"Анкета сохранена, ID: {result[0]}")
            return result[0]
        return None
    except Exception as e:
        print(f"Ошибка при сохранении пользователя: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [["Создать анкету", "Использовать существующую"]], 
        resize_keyboard=True
    )

def get_edit_keyboard():
    return ReplyKeyboardMarkup([["Изменить анкету", "Смотреть анкеты"]], resize_keyboard=True)

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
    """Клавиатура для выбора стажа тренировок"""
    return ReplyKeyboardMarkup([
        ["Новичок (до 2 лет)", "Продвинутый (2-5 лет)"],
        ["Профессионал (5+ лет)", "Пропустить"]
    ], resize_keyboard=True)

def get_edit_choice_keyboard(user_data):
    keyboard = [
        ["1. Имя", "2. Фото"],
        ["3. Возраст", "4. Пол"],
        ["5. Предпочтения", "6. Город"],
        ["7. Стаж", "8. Описание"],
        ["9. Название зала", "10. Улица зала"],
        ["✅ Завершить редактирование"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Сохраняем telegram_id пользователя
    context.user_data['user_id'] = update.effective_user.id
    
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
            "GymBros – бот для поиска напарника для тренировок!\n\n" "🏋️‍♂️🤝 Создавай анкету, ищи GymBro или GymGirl рядом и качайся вместе.\n\n" "Давайте создадим вашу анкету.",
            reply_markup=ReplyKeyboardMarkup([["Создать анкету"]], resize_keyboard=True)
        )

# Добавляем обработчик для кнопки "Использовать существующую"
async def use_existing_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = await get_user_from_db(user_id, context)
    
    if not user_data:
        await update.message.reply_text(
            "У вас нет сохраненной анкеты. Сначала создайте её.",
            reply_markup=ReplyKeyboardMarkup([["Создать анкету"]], resize_keyboard=True)
        )
        return
    
    # Сохраняем данные в контексте
    context.user_data.update(user_data)
    
    # Показываем меню редактирования/просмотра
    await update.message.reply_text(
        "Ваша анкета успешно загружена. Что вы хотите сделать?",
        reply_markup=get_edit_keyboard()
    )


async def begin_questionnaire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинаем создание анкеты"""
    # Сохраняем telegram_id пользователя
    context.user_data['user_id'] = update.effective_user.id
    
    await update.message.reply_text(
        "Как вас зовут?",
        reply_markup=ReplyKeyboardRemove()
    )
    return NAME

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
    await update.message.reply_text("Теперь отправьте ваше фото:")
    return PHOTO

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото!")
        return PHOTO
    
    context.user_data['photo'] = update.message.photo[-1].file_id
    await update.message.reply_text("Сколько вам лет?")
    return AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        age = int(update.message.text)
        if age < 10 or age > 100:
            raise ValueError
        context.user_data['age'] = age
        await update.message.reply_text(
            "Укажите ваш пол:",
            reply_markup=get_gender_keyboard()
        )
        return GENDER
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректный возраст (число от 10 до 100)!")
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
    if update.message.text == "Пропустить":
        context.user_data['experience'] = None
        await update.message.reply_text(
            "Напишите краткое описание о себе (или нажмите «Пропустить»)",
            reply_markup=get_skip_or_text_keyboard()
        )
        return DESCRIPTION
    
    # Сохраняем выбранный стаж
    experience_text = update.message.text
    # Сохраняем только категорию без пояснения в скобках
    experience_category = experience_text.split(' ')[0]
    context.user_data['experience'] = experience_category
    
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
    await update.message.reply_text("На какой улице находится ваш зал?")
    return GYM_STREET

# Модифицируем формирование анкеты в get_gym_street и edit_gym_street
async def get_gym_street(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем улицу зала, сохраняем анкету и показываем результат"""
    context.user_data['gym_street'] = update.message.text
    
    # Сохраняем всю анкету в базу данных
    user_id = await save_user_to_db(context.user_data, context, update)
    
    if user_id:
        # Формируем текст анкеты для показа пользователю
        description_text = f"\n\n{context.user_data['description']}" if context.user_data.get('description') else ""
        experience_text = f"\n{context.user_data['experience']}" if context.user_data.get('experience') else ""

        profile_text = (
            f"{context.user_data['name']}, {context.user_data['age']}, {context.user_data['city']}\n"
            f"{context.user_data['gym_name']}, {context.user_data['gym_street']}"
            f"{experience_text}"
            f"{description_text}"
        )
        
        await update.message.reply_text(
            "✅ Ваша анкета успешно сохранена! Вот как она выглядит:"
        )
        
        # Отправляем анкету с фото или без
        if 'photo' in context.user_data:
            await update.message.reply_photo(
                photo=context.user_data['photo'],
                caption=profile_text,
                reply_markup=get_edit_keyboard()
            )
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
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# Добавляем функцию для обновления статистики просмотров
async def update_view_stats(user_id, context):
    """Обновляет статистику просмотров и показывает рекламу каждые 2 просмотра"""
    try:
        with transaction.atomic(using='neon'):
            stat, created = UserAdStat.objects.get_or_create(
                user_id=user_id,
                defaults={
                    'profiles_viewed': 1,
                    'ads_shown': 0
                }
            )
            
            if not created:
                stat.profiles_viewed += 1
                stat.save(using='neon')
            
            # Показываем рекламу каждые 2 просмотра
            if stat.profiles_viewed % 2 == 0:
                ad = Ad.objects.filter(
                    is_active=True
                ).order_by('?').first()
                
                if ad:
                    # Создаем клавиатуру с кнопкой "Пропустить"
                    skip_keyboard = ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
                    
                    try:
                        # Если есть file_id в базе, используем его
                        if ad.telegram_file_id:
                            await context.bot.send_photo(
                                chat_id=user_id,
                                photo=ad.telegram_file_id,
                                caption=ad.text,
                                reply_markup=skip_keyboard
                            )
                        else:
                            # Если file_id нет, но есть изображение, загружаем его
                            if ad.image:
                                with open(ad.image.path, 'rb') as photo_file:
                                    message = await context.bot.send_photo(
                                        chat_id=user_id,
                                        photo=photo_file,
                                        caption=ad.text,
                                        reply_markup=skip_keyboard
                                    )
                                    # Сохраняем file_id для будущего использования
                                    if message.photo:
                                        ad.telegram_file_id = message.photo[-1].file_id
                                        ad.save()
                        stat.ads_shown += 1
                        stat.save(using='neon')
                        return True  # Реклама была показана
                    except Exception as e:
                        print(f"Ошибка при отправке рекламы с фото: {e}")
                        # Если не удалось отправить с фото, отправляем текстовое сообщение
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=ad.text,
                            reply_markup=skip_keyboard
                        )
                        stat.ads_shown += 1
                        stat.save(using='neon')
                        return True  # Реклама была показана
    
        return False  # Реклама не была показана
        
    except Exception as e:
        print(f"Ошибка при обновлении статистики: {e}")
        return False
    

# ПРОСМОТР АНКЕТ ################################################################################

# Добавим новые состояния
VIEW_PROFILES, PROFILE_ACTION, EDIT_CHOICE, EDIT_SELECTED = range(10, 14)

# Модифицируем функцию get_potential_matches
async def get_potential_matches(user_id, context):
    """Получаем анкеты, которые подходят пользователю, с приоритетом для лайкнувших"""
    conn = None
    try:
        # Сначала получаем данные текущего пользователя
        user_data = await get_user_from_db(user_id, context)
        if not user_data:
            print("Данные текущего пользователя не найдены")
            return None
            
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Определяем предпочтения по полу
        preferred_gender = user_data.get('preferred_gender', 1)
        gender_condition = ""
        if preferred_gender == 1:  # Gym Bro
            gender_condition = "AND u.gender = 1"
        elif preferred_gender == 2:  # Gym Girl
            gender_condition = "AND u.gender = 2"
        
        # Сначала ищем анкеты пользователей, которые лайкнули текущего пользователя
        query = f"""
            WITH liked_me AS (
                SELECT ua.user_id 
                FROM user_actions ua
                JOIN users u ON ua.user_id = u.id
                WHERE ua.target_user_id = %s AND ua.action = 1
                AND u.telegram_id != %s
                AND u.city_id = %s
                {gender_condition}
            )
            
            SELECT u.*, c.name as city_name,
                   CASE WHEN lm.user_id IS NOT NULL THEN 1 ELSE 0 END as liked_me
            FROM users u
            LEFT JOIN cities c ON u.city_id = c.id
            LEFT JOIN liked_me lm ON u.id = lm.user_id
            WHERE u.city_id = %s
            {gender_condition}
            AND u.telegram_id != %s
            AND u.id NOT IN (
                SELECT target_user_id FROM user_actions 
                WHERE user_id = %s
            )
            ORDER BY liked_me DESC, RANDOM()
            LIMIT 1
        """
        
        print("Выполняемый запрос:", query)
        print("Параметры:", [user_data['id'], user_id, user_data['city_id'], 
              user_data['city_id'], user_id, user_data['id']])
        
        cursor.execute(query, [user_data['id'], user_id, user_data['city_id'], 
                       user_data['city_id'], user_id, user_data['id']])
        
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
def get_profile_action_keyboard():
    return ReplyKeyboardMarkup([
        ["💪", "👎"],
        ["⏹️ Закончить просмотр"]
    ], resize_keyboard=True)

async def view_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало просмотра анкет"""
    if 'user_id' not in context.user_data:
        await update.message.reply_text(
            "У вас нет анкеты. Сначала создайте её.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    print("Ищем анкеты для user_id:", context.user_data['user_id'])
    profile = await get_potential_matches(context.user_data['user_id'], context)
    print("Результат поиска анкет:", profile)

    if not profile:
        await update.message.reply_text(
            "Нет подходящих анкет для просмотра.",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    # Сохраняем текущую анкету в контексте
    context.user_data['current_profile'] = profile
    print("Текущий профиль сохранён:", profile)
    
    # Показываем анкету
    await show_profile(update, profile)
    
    return PROFILE_ACTION

# Модифицируем функцию handle_profile_action для учета просмотров
async def handle_profile_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий с анкетой с уведомлениями о лайках"""
    action = update.message.text
    current_profile = context.user_data.get('current_profile')
    user_id = context.user_data['user_id']  # telegram_id текущего пользователя

    # Если пользователь нажал "Пропустить" на рекламе, продолжаем показ анкет
    if action == "Пропустить":
        # Удаляем клавиатуру "Пропустить"
        await update.message.reply_text("Реклама пропущена. Продолжаем показ анкет...", 
                                     reply_markup=ReplyKeyboardRemove())
        # Продолжаем обычный процесс показа анкет
        return await continue_showing_profiles(update, context)
    
    if not current_profile:
        await update.message.reply_text(
            "Ошибка: анкета не найдена.",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    if action == "💪":
        # Сохраняем лайк
        success = await save_user_action(user_id, current_profile['telegram_id'], 1)
        
        if success != True:
            await update.message.reply_text("Не удалось сохранить ваш лайк. Попробуйте позже.")
        
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

    elif action == "👎":
        # Сохраняем дизлайк
        success = await save_user_action(user_id, current_profile['telegram_id'], 0)
        if success != True:
            await update.message.reply_text("Не удалось сохранить ваш дизлайк. Попробуйте позже.")
    
    elif action == "⏹️ Закончить просмотр":
        await update.message.reply_text(
            "Просмотр анкет завершен.",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    # Обновляем статистику просмотров и проверяем рекламу
    ad_shown = await update_view_stats(user_id, context)
    
    # Если была показана реклама, ждем нажатия кнопки "Пропустить"
    if ad_shown:
        return PROFILE_ACTION  # Остаемся в том же состоянии
    
    # Если реклама не была показана, продолжаем показ анкет
    return await continue_showing_profiles(update, context)

async def continue_showing_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Продолжает показ анкет после рекламы или если реклама не была показана"""
    # Получаем следующую анкету
    profile = await get_potential_matches(context.user_data['user_id'], context)
    
    if not profile:
        await update.message.reply_text(
            "Анкеты закончились! Попробуйте позже или измените критерии поиска.",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    # Проверяем, что это не та же самая анкета
    if 'current_profile' in context.user_data and context.user_data['current_profile']['id'] == profile['id']:
        await update.message.reply_text(
            "Больше нет новых анкет для просмотра. Попробуйте позже!",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    # Сохраняем текущую анкету в контексте
    context.user_data['current_profile'] = profile
    
    # Формируем и показываем анкету
    await show_profile(update, profile)
    
    return PROFILE_ACTION

async def show_profile(update: Update, profile):
    """Показывает анкету пользователя"""
    description_text = f"\n\n{profile['description']}" if profile.get('description') else ""
    experience_text = f"\n{profile['experience']}" if profile.get('experience') else ""

    profile_text = (
        f"{profile['name']}, {profile['age']}, {profile.get('city_name', 'Не указан')}\n"
        f"{profile['gym_name']}, {profile['gym_street']}"
        f"{experience_text}"
        f"{description_text}"
    )
    
    if profile.get('photo'):
        await update.message.reply_photo(
            photo=profile['photo'],
            caption=profile_text,
            reply_markup=get_profile_action_keyboard()
        )
    else:
        await update.message.reply_text(
            profile_text,
            reply_markup=get_profile_action_keyboard()
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
        await update.message.reply_text(
            "Отправьте новое фото:",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['editing_field'] = 'photo'
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
            "Напишите новое описание о себе:",
            reply_markup=ReplyKeyboardRemove()
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
    
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите вариант из меню.",
            reply_markup=get_edit_choice_keyboard(context.user_data['current_data'])
        )
        return EDIT_CHOICE

async def edit_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода нового значения для выбранного поля"""
    field = context.user_data['editing_field']
    value = update.message.text
    
    # Обработка специальных полей
    if field == 'photo':
        if not update.message.photo:
            await update.message.reply_text("Пожалуйста, отправьте фото!")
            return EDIT_SELECTED
        value = update.message.photo[-1].file_id
    
    elif field == 'gender':
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

    elif field == 'experience' and value != "Пропустить":
        # Сохраняем только категорию без пояснения в скобках
        value = value.split(' ')[0]

    # Сохраняем изменение
    context.user_data['changes'][field] = value

    await update.message.reply_text(
        "Изменения сохранены. Выберите что ещё хотите изменить:",
        reply_markup=get_edit_choice_keyboard(context.user_data['current_data'])
    )
    return EDIT_CHOICE

async def finish_editing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение редактирования и сохранение изменений"""
    if not context.user_data.get('changes'):
        await update.message.reply_text(
            "Вы не внесли никаких изменений.",
            reply_markup=get_edit_keyboard()
        )
        return ConversationHandler.END
    
    print(f"Пытаемся сохранить изменения: {context.user_data['changes']}")
    
    try:
        # Обновляем данные в БД
        success = await update_user_in_db(
            context.user_data['user_id'],
            context.user_data['changes']
        )
        
        print(f"Результат обновления: {success}")
        
        if success:
            # Получаем обновлённые данные
            user_data = await get_user_from_db(context.user_data['user_id'], context)
            if not user_data:
                await update.message.reply_text(
                    "Анкета не найдена после обновления.",
                    reply_markup=get_main_keyboard()
                )
                return ConversationHandler.END
            
            # Формируем текст анкеты
            description_text = f"\n\n{user_data['description']}" if user_data.get('description') else ""
            experience_text = f"\n{user_data['experience']}" if user_data.get('experience') else ""

            profile_text = (
                f"{user_data['name']}, {user_data['age']}, {user_data.get('city_name', 'Не указан')}\n"
                f"{user_data['gym_name']}, {user_data['gym_street']}"
                f"{experience_text}"
                f"{description_text}"
            )

            await update.message.reply_text("✅ Анкета успешно обновлена:")

            if user_data.get('photo'):
                await update.message.reply_photo(
                    photo=user_data['photo'],
                    caption=profile_text,
                    reply_markup=get_edit_keyboard()
                )
            else:
                await update.message.reply_text(
                    profile_text,
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
            "Введите username (без @) или нажмите 'Пропустить':",
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
    """Получаем стаж"""
    if update.message.text == "Пропустить":
        context.user_data['fake_profile']['experience'] = None
    else:
        context.user_data['fake_profile']['experience'] = update.message.text
    
    await update.message.reply_text(
        "Напишите описание о себе или нажмите 'Пропустить':",
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
    """Получаем фото или пропускаем"""
    if update.message.text == "Пропустить":
        context.user_data['fake_profile']['photo'] = None
    else:
        # Получаем file_id фотографии вместо самих бинарных данных
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

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Обработчик команды /start
    application.add_handler(CommandHandler("start", start))
    
    # Обработчик создания анкеты
    create_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Создать анкету$"), begin_questionnaire)],
        states={
           NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
           PHOTO: [MessageHandler(filters.PHOTO, get_photo)],
           AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
           GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gender)],
           PREFERRED_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_preferred_gender)],
           CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_city)],
           EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_experience)],
           DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_description)],
           GYM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gym_name)],
           GYM_STREET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gym_street)],
       },
       fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Обработчик использования существующей анкеты
    application.add_handler(MessageHandler(filters.Regex("^Использовать существующую$"), use_existing_profile))
    
    # Обновляем обработчик редактирования анкеты
    edit_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Изменить анкету$"), edit_questionnaire)],
        states={
            EDIT_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_choice)],
            EDIT_SELECTED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_selected),
                MessageHandler(filters.PHOTO, edit_selected)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Обработчик просмотра анкет
    view_profiles_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Смотреть анкеты$"), view_profiles)],
        states={
            PROFILE_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_profile_action)],
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
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(create_conv_handler)
    application.add_handler(edit_conv_handler)
    application.add_handler(view_profiles_conv)
    application.add_handler(generate_conv_handler)
    
    # Запуск бота
    application.run_polling()