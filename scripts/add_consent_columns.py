"""Добавляет колонки согласия 152-ФЗ в таблицу users."""
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
    "sslmode": os.getenv("DB_SSLMODE", "require"),
}


def main() -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS consent_accepted_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS consent_version VARCHAR(32);
                """
            )
        conn.commit()
        print("OK: consent columns ensured")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
