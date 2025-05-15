import csv
import requests
from io import StringIO
import psycopg2
from psycopg2 import extras
from dotenv import load_dotenv
import os

# Загрузка переменных окружения из .env
load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT")
}

def create_cities_table():
    """Создание таблицы cities с правильной структурой"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            DROP TABLE IF EXISTS cities;
            
            CREATE TABLE cities (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                secondName VARCHAR(100),
                thirdName VARCHAR(100),
                fourthName VARCHAR(100),
                CONSTRAINT cities_name_unique UNIQUE (name)
            )
        """)
        conn.commit()
        print("Таблица cities успешно создана")
        
    except Exception as e:
        print(f"Ошибка при создании таблицы: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()
create_cities_table()

def get_all_russian_cities_from_csv():
    """Загрузка городов России из CSV"""
    url = "https://raw.githubusercontent.com/epogrebnyak/ru-cities/main/assets/towns.csv"
    response = requests.get(url)
    response.raise_for_status()

    csvfile = StringIO(response.text)
    reader = csv.DictReader(csvfile)

    cities = set()
    for row in reader:
        city = row["city"].strip()  # Заменено с name -> city
        if city:
            cities.add(city)

    return sorted(cities)

def load_cities_to_db():
    """Загрузка городов в PostgreSQL"""
    conn = None
    try:
        cities = get_all_russian_cities_from_csv()
        if not cities:
            print("Список городов пуст.")
            return

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Вставка с защитой от дубликатов
        query = """
            INSERT INTO cities (name)
            VALUES %s
            ON CONFLICT ON CONSTRAINT cities_name_unique DO NOTHING
        """

        values = [(city,) for city in cities]

        extras.execute_values(cursor, query, values, template="(%s)")
        conn.commit()

        print(f"Успешно добавлено {cursor.rowcount} городов.")

    except Exception as e:
        print(f"Ошибка при загрузке городов: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()

if __name__ == "__main__":
    load_cities_to_db()
