# GymBros

Telegram-бот для поиска напарника для тренировок — «качковский Tinder».

**Открыть бота:** [t.me/OfficialGymBrosBot](https://t.me/OfficialGymBrosBot)

---

## Что умеет

- Создание анкеты: имя, фото/видео, возраст, пол, город, зал, описание
- Лента совместимых анкет с лайками / дизлайками / суперлайками
- Уведомления о взаимном интересе
- Реферальная система и лидерборд
- Premium / VIP-функции
- Согласие на обработку ПДн, политика и удаление данных (152-ФЗ)

## Стек

- Python 3.12+, [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- PostgreSQL (в проде — Neon)
- Django admin для рекламных объявлений

## Быстрый старт

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
copy .env.example .env         # Windows
# cp .env.example .env         # Linux / macOS
```

Заполните `.env` (токен бота, БД, `OPERATOR_NAME` / `OPERATOR_EMAIL` для 152-ФЗ), затем:

```bash
python scripts/add_consent_columns.py
python main.py
```

Подробнее про выкладку: [docs/DEPLOY.md](docs/DEPLOY.md).

## Юридические документы

| Документ | Файл | В боте |
|---|---|---|
| Политика конфиденциальности | [docs/PRIVACY_POLICY.md](docs/PRIVACY_POLICY.md) | `/privacy` |
| Пользовательское соглашение | [docs/USER_AGREEMENT.md](docs/USER_AGREEMENT.md) | `/terms` |
| Удаление данных / отзыв согласия | — | `/delete_my_data` |

Перед созданием анкеты пользователь подтверждает возраст 18+ и согласие на обработку персональных данных.

> Для полноценного соответствия 152-ФЗ укажите в `.env` реальные `OPERATOR_NAME` и `OPERATOR_EMAIL`. При необходимости подайте уведомление в Роскомнадзор как оператор ПДн.

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Главное меню |
| `/help` | Справка |
| `/privacy` | Политика конфиденциальности |
| `/terms` | Пользовательское соглашение |
| `/delete_my_data` | Удалить анкету и ПДн |
| `/cancel` | Отменить текущий шаг |

## Структура

```
├── main.py                 # Точка входа
├── bot/
│   ├── core.py             # Логика бота
│   └── legal.py            # Тексты 152-ФЗ
├── gymbros_admin/          # Django admin (реклама)
├── scripts/                # SQL/миграционные скрипты
└── docs/                   # Политика, соглашение, деплой
```

## Переменные окружения

См. [.env.example](.env.example). Секреты (токен, пароль БД) **не коммитьте**.

## Лицензия

Код публикуется для портфолио / pet-проекта. Использование на свой страх и риск.
