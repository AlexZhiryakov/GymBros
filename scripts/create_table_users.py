import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT")
}

def create_tables():
    """Создание таблицы users"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Удаляем таблицу с CASCADE, если она существует
        cursor.execute("""
            DROP TABLE IF EXISTS users CASCADE;
        """)

        # Создаем таблицу заново
        cursor.execute("""
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username VARCHAR(100),
                name VARCHAR(100) NOT NULL,
                photo TEXT,
                age INTEGER NOT NULL,
                gender INTEGER DEFAULT 1,
                preferred_gender INTEGER DEFAULT 1,
                city_id INTEGER REFERENCES cities(id),
                experience TEXT,
                description TEXT,
                gym_name TEXT,
                gym_street TEXT,
                language VARCHAR(5) DEFAULT 'ru',
                mode INTEGER DEFAULT 0
            );
        """)

        conn.commit()
        print("Таблица users успешно создана")
        
    except Exception as e:
        print(f"Ошибка при создании таблицы: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()

create_tables()