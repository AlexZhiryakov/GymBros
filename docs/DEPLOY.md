# Деплой GymBros

Бот работает в режиме **long polling** (`application.run_polling()`), поэтому нужен процесс, который **не засыпает**.

База уже может жить на бесплатном Neon — это нормально. Платить нужно (или искать always-on) только за **рантайм бота**.

## Быстрый старт локально

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполните секреты и реквизиты оператора
python scripts/add_consent_columns.py
python main.py
```

## Docker

```bash
docker build -t gymbros .
docker run --env-file .env --restart unless-stopped gymbros
```

## Куда выложить бесплатно / дёшево

| Вариант | 24/7 для polling | Комментарий |
|---|---|---|
| Специализированный bot-hosting (FadeHost, Kerit, Inject Cloud и аналоги) | Обычно да | Удобно для pet-проекта: залить репозиторий, указать `python main.py` |
| Дешёвый VPS (~100–300 ₽/мес) | Да | Самый предсказуемый вариант |
| Render / Koyeb free web | Нет | Засыпают без HTTP — для polling плохо |
| Railway free credit | Коротко | Кредита хватает на несколько дней |

### Что указать на bot-hosting

1. Start command: `python main.py`
2. Переменные окружения из `.env.example`
3. После первого деплоя выполните один раз: `python scripts/add_consent_columns.py` (через one-off / console)

## GitHub Actions (старый сервер)

Workflow `.github/workflows/deploy.yml` рассчитан на VPS по SSH. Если сервер больше не оплачивается — отключите workflow или обновите secrets под новый хост.

## Ссылка для README и визитки

https://t.me/OfficialGymBrosBot
