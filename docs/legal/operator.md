# Сведения об операторе персональных данных

Заполните этот файл перед публичным заявлением о соответствии 152-ФЗ. После заполнения синхронизируйте плейсхолдеры в `privacy-policy.md` и `consent.md` (или держите единый источник правды здесь и ссылайтесь из бота через env).

| Поле | Значение |
|------|----------|
| ФИО / наименование | _указать_ |
| Статус | физлицо / ИП / ООО |
| ИНН | _указать или «не применяется»_ |
| ОГРН / ОГРНИП | _указать или «не применяется»_ |
| Адрес для корреспонденции | _указать_ |
| Контакт для запросов ПДн | e-mail: _…_ · Telegram: @gymbros_manager (или другой) |
| Публичная ссылка на Политику | после merge: `https://github.com/AlexZhiryakov/GymBros/blob/main/docs/legal/privacy-policy.md` |
| Регион / провайдер БД | сейчас: Neon PostgreSQL, `eu-central-1` (временно); цель: хостинг в РФ |
| Хостинг бота | _Railway / Render / Oracle / иное_ |
| Получатель платежей Premium/VIP | _реквизиты_ |

Env для бота (опционально):

```
OPERATOR_CONTACT=@gymbros_manager
PRIVACY_POLICY_URL=https://github.com/AlexZhiryakov/GymBros/blob/main/docs/legal/privacy-policy.md
CONSENT_VERSION=1.0
```
