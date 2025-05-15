import asyncio
from telegram import Update, Message, Chat, User
from telegram.ext import ContextTypes
from bot import edit_gym_street
from typing import Dict, Any

class MockBot:
    async def send_message(self, chat_id, text, reply_markup=None):
        print(f"Bot.send_message: {text}")
    
    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None):
        print(f"Bot.send_photo: {caption}")

class MockContext(ContextTypes.DEFAULT_TYPE):
    def __init__(self):
        self.bot = MockBot()
        self.user_data: Dict[str, Any] = {
            'user_id': 123456789,  # Пример telegram_id
            'changes': {
                'gym_street': 'Новая улица 123'
            },
            'current_data': {
                'name': 'Тестовый пользователь',
                'age': 25,
                'city_name': 'Москва',
                'gym_name': 'Фитнес клуб',
                'gym_street': 'Старая улица 456',
                'description': 'Тестовое описание',
                'experience': 'Продвинутый',
                'photo': None
            }
        }
    
    async def get_user_from_db(self, user_id, context):
        # Возвращаем тестовые данные пользователя
        return {
            'id': 60,
            'name': 'Тестовый пользователь',
            'age': 25,
            'city_name': 'Москва',
            'gym_name': 'Фитнес клуб',
            'gym_street': 'Новая улица 123',  # Обновленное значение
            'description': 'Тестовое описание',
            'experience': 'Продвинутый',
            'photo': None,
            'telegram_id': 123456789
        }
    
    async def update_user_in_db(self, user_id, changes):
        # Мок для успешного обновления
        print(f"Updating user {user_id} with changes: {changes}")
        return True

class MockUpdate(Update):
    def __init__(self, text="Оставить текущее"):
        self.message = Message(
            message_id=1,
            date=None,
            chat=Chat(id=1, type='private'),
            text=text,
            from_user=User(
                id=123456789,
                first_name='Test',
                is_bot=False
            )
        )

async def test_edit_gym_street():
    print("=== Тест 1: Изменение адреса зала ===")
    update = MockUpdate(text="Новая улица 123")
    context = MockContext()
    await edit_gym_street(update, context)
    
    print("\n=== Тест 2: Без изменений ===")
    update = MockUpdate(text="Оставить текущее")
    context = MockContext()
    context.user_data['changes'] = {}  # Нет изменений
    await edit_gym_street(update, context)
    
    print("\n=== Тест 3: Ошибка при обновлении ===")
    update = MockUpdate(text="Новая улица 123")
    context = MockContext()
    # Переопределяем метод для имитации ошибки
    async def mock_update_fail(*args, **kwargs):
        return False
    context.update_user_in_db = mock_update_fail
    await edit_gym_street(update, context)

if __name__ == "__main__":
    asyncio.run(test_edit_gym_street())