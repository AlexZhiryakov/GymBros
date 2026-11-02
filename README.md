# 🏋️ GymBros — поиск напарника для тренировок

Telegram-бот для знакомств в зале: создаёшь анкету, листаешь ленту и находишь GymBro или GymGirl рядом.

![Python](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)
![Telegram Bot](https://img.shields.io/badge/telegram-bot-26A5E4?logo=telegram&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)
![Django](https://img.shields.io/badge/Django-admin-092E20?logo=django&logoColor=white)

---

## 🔗 Живое демо

- Бот в Telegram: **[t.me/OfficialGymBrosBot](https://t.me/OfficialGymBrosBot)**
- Канал проекта: [@gymbroshub](https://t.me/gymbroshub)

Открой бота → `/start` → согласие 18+ → анкета → лента.

---

## 📖 О проекте

**GymBros** — «качковский Tinder»: бот помогает найти человека для совместных тренировок по городу, залу и предпочтениям.

Пользователь собирает анкету (фото/видео, возраст, пол, город, зал, описание), смотрит подходящие профили, ставит лайки и получает уведомления о взаимном интересе. Есть рефералка, лидерборд и Premium/VIP-функции.

Проект оформлен как портфолио-демо с живым ботом. Добавлены согласие на обработку ПДн, политика конфиденциальности и удаление данных (**152-ФЗ**).

---

## 🛠️ Стек технологий

* **Python 3.12+** — язык проекта
* **python-telegram-bot** — Telegram Bot API, диалоги, клавиатуры, polling
* **PostgreSQL (Neon)** — анкеты, лайки, города, рефералы
* **psycopg2** — работа с базой
* **Django** — админка для рекламных объявлений
* **APScheduler** — ежедневные задачи (лимиты, подписки)
* **python-dotenv** — конфигурация через `.env`
* **Docker / FadeHost** — деплой always-on процесса бота

---

## 🚀 Как пользоваться ботом

1. Открой [живое демо](https://t.me/OfficialGymBrosBot).
2. Нажми **Start** или отправь `/start`.
3. Прими согласие на обработку персональных данных (18+).
4. Создай анкету:
   * имя, фото или видео;
   * возраст, пол, кого ищешь;
   * город, зал, описание.
5. Зайди в **«Смотреть анкеты»** и листай ленту:
   * лайк / дизлайк / суперлайк;
   * при взаимном лайке придёт уведомление.
6. В **«⚙️ Настройки»** можно открыть политику, соглашение или удалить свои данные.

Полезные команды: `/help`, `/privacy`, `/terms`, `/delete_my_data`, `/cancel`.

---

## 💻 Локальный запуск

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

Подробнее про деплой: [docs/DEPLOY.md](docs/DEPLOY.md)

---

## ⚖️ Документы (152-ФЗ)

* [Политика конфиденциальности](docs/PRIVACY_POLICY.md) — `/privacy`
* [Пользовательское соглашение](docs/USER_AGREEMENT.md) — `/terms`
* Удаление анкеты и данных — `/delete_my_data`

---

## 📁 Структура

```text
├── main.py              # Точка входа
├── bot/
│   ├── core.py          # Логика бота
│   └── legal.py         # Тексты 152-ФЗ
├── gymbros_admin/       # Django admin (реклама)
├── scripts/             # Служебные скрипты
├── docs/                # Политика, соглашение, деплой
├── Dockerfile
└── .env.example
```

---

## 👤 Автор

**Александр Жиряков**  
Поддержка: [@gymbros_manager](https://t.me/gymbros_manager)  
Email: alexzhiryakov17@mail.ru

Код публикуется для портфолио / pet-проекта.
