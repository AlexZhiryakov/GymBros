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
    """Создает таблицу для рекламы в БД"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                image_url TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_ad_stats (
                user_id INTEGER REFERENCES users(id),
                ads_shown INTEGER DEFAULT 0,
                profiles_viewed INTEGER DEFAULT 0,
                last_ad_shown_at TIMESTAMP,
                PRIMARY KEY (user_id)
            )
        """)
        
        conn.commit()
        print("Таблицы для рекламы успешно созданы")
    except Exception as e:
        print(f"Ошибка при создании таблиц для рекламы: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            cursor.close()
            conn.close()


create_tables()