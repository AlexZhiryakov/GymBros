import os
import sys
import django

# 1. Добавляем путь к корню проекта (/root/)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 2. Добавляем путь к папке gymbros_admin (где лежит botapp)
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gymbros_admin"))

# 3. Указываем правильный модуль настроек
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gymbros_admin.settings")

# 4. Инициализируем Django
django.setup()

# 5. Теперь можно импортировать бота
from bot.core import main

if __name__ == "__main__":
    main()