# GymBros

Telegram-бот для поиска напарника в зал («качковский Tinder»): анкеты, города, лайки/мэтчи, рефералка, опции Premium/VIP.

## Открыть бота

**👉 [https://t.me/OfficialGymBrosBot](https://t.me/OfficialGymBrosBot)**

Канал: [@gymbroshub](https://t.me/gymbroshub) · менеджер: [@gymbros_manager](https://t.me/gymbros_manager)

> Если ссылка не открывается — бот ещё не задеплоен или токен отозван. См. раздел «Деплой».

## Стек

- Python, [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot) (long polling)
- PostgreSQL (`psycopg2`)
- Django admin (`gymbros_admin`) для рекламных объявлений

Точка входа: `python main.py`.

## Быстрый старт (локально)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# заполните TOKEN, DB_*, OWNER_ID, SECRET_KEY
python scripts/create_table_user_consents.py  # один раз на БД
python main.py
```

### Переменные окружения

См. [`.env.example`](.env.example). Обязательные: `TOKEN`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `OWNER_ID`.

Для юридических ссылок в боте: `PRIVACY_POLICY_URL`, `OPERATOR_CONTACT`, `CONSENT_VERSION`.

**Никогда не коммитьте `.env` и реальные токены.**

## Персональные данные (РФ)

До создания анкеты бот запрашивает **отдельное** согласие на обработку ПДн.

| Документ | Файл |
|----------|------|
| Политика | [`docs/legal/privacy-policy.md`](docs/legal/privacy-policy.md) |
| Текст согласия | [`docs/legal/consent.md`](docs/legal/consent.md) |
| Реквизиты оператора | [`docs/legal/operator.md`](docs/legal/operator.md) — заполняет владелец |

В боте: `/privacy`, `/delete_my_data`.

## Деплой (бесплатно / дёшево)

Рекомендуется **Railway** (worker: `python main.py`) или Oracle Cloud Always Free VM.  
Старый GitHub Actions workflow рассчитан на исчезнувший VPS — не используйте его без новых SSH secrets.

1. Создайте проект на Railway → подключите этот GitHub-репозиторий.  
2. Задайте Variables из `.env.example` (**новый** `TOKEN` после ротации).  
3. Start command: `python main.py` (или Dockerfile из репо).  
4. Проверьте [t.me/OfficialGymBrosBot](https://t.me/OfficialGymBrosBot).

Подробный план revival и compliance: у координатора проекта в Context (`docs/gymbros-revival-plan.md`).

## GitHub (оформление репозитория)

Предлагаемые настройки (вручную в Settings):

- **Description:** `Telegram-бот для поиска напарника в зал (GymBros) — анкеты, мэтчи, города РФ.`
- **Website:** `https://t.me/OfficialGymBrosBot`
- **Topics:** `telegram-bot`, `python`, `fitness`, `workout-partner`, `django`, `postgresql`, `russia`

## Безопасность

Если токен или пароль БД когда-либо попадали в git — **смените их** (BotFather → Revoke; Neon → reset password) и храните только в secrets хостинга.

## Структура

```
main.py                 # вход
bot/core.py             # логика бота
bot/legal.py            # согласие / политика / журнал
docs/legal/             # юридические тексты (RU)
gymbros_admin/          # Django admin
scripts/                # SQL-утилиты (осторожно: часть скриптов делает DROP)
```
