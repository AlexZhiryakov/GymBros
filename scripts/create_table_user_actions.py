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
    """Создание таблицы users с правильной структурой"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Создаем таблицу user_actions
        cursor.execute("""
            DROP TABLE IF EXISTS user_actions;
            CREATE TABLE user_actions (
               id SERIAL PRIMARY KEY,
               user_id INTEGER NOT NULL,
               target_user_id INTEGER NOT NULL,
               action INTEGER NOT NULL,
               timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
               FOREIGN KEY (user_id) REFERENCES users(id),
               FOREIGN KEY (target_user_id) REFERENCES users(id),
               UNIQUE(user_id, target_user_id)
            );
        """)

        conn.commit()
        print("Таблица users успешно созданы")
        
    except Exception as e:
        print(f"Ошибка при создании таблиц: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()

create_tables()