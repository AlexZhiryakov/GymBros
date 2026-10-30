"""Идемпотентное создание таблицы журнала согласий (152-ФЗ). Безопасно для продакшена."""
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}


def create_table():
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_consents (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL UNIQUE,
                consented BOOLEAN NOT NULL DEFAULT FALSE,
                consent_version VARCHAR(32) NOT NULL,
                consented_at TIMESTAMPTZ,
                revoked_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_user_consents_telegram_id
                ON user_consents (telegram_id);
            """
        )
        conn.commit()
        print("Таблица user_consents готова")
    except Exception as e:
        print(f"Ошибка: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    create_table()
