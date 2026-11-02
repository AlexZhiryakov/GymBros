# GymBros

<p align="center">
  <strong>Telegram-бот для поиска напарника для тренировок</strong><br/>
  «Качковский Tinder» — анкеты, лайки, зал рядом и тренировки вдвоём.
</p>

<p align="center">
  <a href="https://t.me/OfficialGymBrosBot"><img src="https://img.shields.io/badge/Telegram-Открыть%20бота-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" alt="Open bot"></a>
  <a href="https://t.me/OfficialGymBrosBot"><img src="https://img.shields.io/badge/Demo-t.me%2FOfficialGymBrosBot-black?style=for-the-badge" alt="Demo"></a>
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/License-Portfolio-lightgrey?style=for-the-badge" alt="License">
</p>

<p align="center">
  <a href="https://t.me/OfficialGymBrosBot"><strong>🚀 Live demo → @OfficialGymBrosBot</strong></a>
</p>

---

## О проекте

**GymBros** — pet-проект / бывший продукт 2025 года: бот в Telegram, где можно создать анкету и найти GymBro или GymGirl для совместных тренировок.

Идея простая: меньше «кто сегодня свободен в зале?», больше совпадений по городу, залу и предпочтениям.

| | |
|---|---|
| **Статус** | Online (демо / портфолио) |
| **Платформа** | Telegram |
| **Возраст** | 18+ |
| **Демо** | [t.me/OfficialGymBrosBot](https://t.me/OfficialGymBrosBot) |

## Возможности

- Анкета: имя, фото/видео, возраст, пол, город, зал, описание, стаж
- Лента подходящих анкет — лайк / дизлайк / суперлайк
- Уведомления о взаимном интересе
- Реферальная система и лидерборд
- Premium / VIP-функции
- Согласие на обработку ПДн, политика и удаление данных (**152-ФЗ**)

## Стек технологий

| Слой | Технологии |
|---|---|
| Бот | Python, [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot), APScheduler |
| Данные | PostgreSQL (Neon), psycopg2 |
| Админка | Django (рекламные объявления) |
| Деплой | Docker / FadeHost (long polling) |

## Как пользоваться (демо)

1. Открой бота: [t.me/OfficialGymBrosBot](https://t.me/OfficialGymBrosBot)
2. Нажми **Start** / отправь `/start`
3. Прими согласие (18+ и обработка ПДн)
4. Создай анкету и листай ленту

Полезные команды: `/help`, `/privacy`, `/terms`, `/delete_my_data`

## Быстрый старт (локально)

```bash
git clone https://github.com/AlexZhiryakov/GymBros.git
cd GymBros

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
# source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # Windows: copy .env.example .env
```

Заполни `.env` (токен BotFather, PostgreSQL, `OPERATOR_NAME` / `OPERATOR_EMAIL`), затем:

```bash
python scripts/add_consent_columns.py
python main.py
```

Подробнее про выкладку: [docs/DEPLOY.md](docs/DEPLOY.md)

## Юридические документы

| Документ | Файл | В боте |
|---|---|---|
| Политика конфиденциальности | [docs/PRIVACY_POLICY.md](docs/PRIVACY_POLICY.md) | `/privacy` |
| Пользовательское соглашение | [docs/USER_AGREEMENT.md](docs/USER_AGREEMENT.md) | `/terms` |
| Удаление данных | — | `/delete_my_data` |

Перед созданием анкеты пользователь подтверждает возраст **18+** и согласие на обработку персональных данных.

## Структура репозитория

```text
├── main.py              # Точка входа
├── bot/
│   ├── core.py          # Логика бота
│   └── legal.py         # Тексты 152-ФЗ
├── gymbros_admin/       # Django admin (реклама)
├── scripts/             # Служебные / SQL-скрипты
├── docs/                # Политика, соглашение, деплой
├── Dockerfile
└── .env.example
```

## Переменные окружения

См. [.env.example](.env.example).

Секреты (`TOKEN`, пароль БД) храни только в `.env` / Environment Variables хостинга — **не коммить** в git.

## Roadmap / заметки

- Проект оформлен как портфолио-демо с живым ботом
- База пользователей сохранена с периода активного трафика
- Бесплатный always-on хостинг + Neon для PostgreSQL

## Автор

**Александр Жиряков**  
Telegram поддержки: [@gymbros_manager](https://t.me/gymbros_manager)  
Email: alexzhiryakov17@mail.ru

## Лицензия

Код публикуется для портфолио / pet-проекта. Использование — на свой страх и риск.
