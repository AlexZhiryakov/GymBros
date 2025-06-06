from flask import Flask
from flask_admin import Admin
from flask_sqlalchemy import SQLAlchemy
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Конфигурация для PostgreSQL в Neon.tech
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    "?sslmode=require"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')  # Не забудьте добавить в .env

db = SQLAlchemy(app)
admin = Admin(app, name='GymBros Admin', template_mode='bootstrap3')

# Импорт моделей и представлений после инициализации
from admin import models, views