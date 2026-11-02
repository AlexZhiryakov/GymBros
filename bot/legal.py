"""
Тексты и хелперы по 152-ФЗ (персональные данные) для GymBros.
Реквизиты оператора задаются через переменные окружения.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone


CONSENT_VERSION = "2026-11-02"


def operator_name() -> str:
    return os.getenv("OPERATOR_NAME", "Жиряков Александр")


def operator_email() -> str:
    return os.getenv("OPERATOR_EMAIL", "alexzhiryakov17@mail.ru").strip()


def operator_telegram() -> str:
    tg = os.getenv("OPERATOR_TELEGRAM", "@gymbros_manager").strip()
    return tg if tg.startswith("@") else f"@{tg}"


def bot_username() -> str:
    return os.getenv("BOT_USERNAME", "OfficialGymBrosBot")


def privacy_policy_url() -> str:
    return os.getenv(
        "PRIVACY_POLICY_URL",
        "https://github.com/AlexZhiryakov/GymBros/blob/main/docs/PRIVACY_POLICY.md",
    )


def terms_url() -> str:
    return os.getenv(
        "TERMS_URL",
        "https://github.com/AlexZhiryakov/GymBros/blob/main/docs/USER_AGREEMENT.md",
    )


def consent_text() -> str:
    return (
        "📋 <b>Согласие на обработку персональных данных</b>\n\n"
        f"Оператор: <b>{operator_name()}</b>\n"
        f"Связь: {operator_email()}, {operator_telegram()}\n\n"
        "Продолжая, вы подтверждаете, что вам <b>есть 18 лет</b>, и даёте согласие "
        "на обработку персональных данных для работы сервиса GymBros "
        "(поиск напарника для тренировок), в том числе:\n"
        "• Telegram ID и username\n"
        "• имя, возраст, пол, город\n"
        "• фото/видео анкеты\n"
        "• описание, зал, предпочтения\n"
        "• действия в боте (лайки, просмотры)\n\n"
        f"Полный текст:\n"
        f"• Политика: {privacy_policy_url()}\n"
        f"• Соглашение: {terms_url()}\n\n"
        "Согласие можно отозвать командой /delete_my_data "
        "(анкета и связанные данные будут удалены).\n\n"
        f"Версия согласия: <code>{CONSENT_VERSION}</code>"
    )


def privacy_short_text() -> str:
    return (
        "🔒 <b>Политика конфиденциальности GymBros</b>\n\n"
        f"Оператор ПДн: {operator_name()}\n"
        f"Контакты: {operator_email()}, {operator_telegram()}\n\n"
        "Мы обрабатываем данные анкеты только для поиска напарника по залу, "
        "показа совместимых профилей и связи между пользователями внутри Telegram.\n\n"
        "Права пользователя (152-ФЗ):\n"
        "• получить информацию об обработке — /privacy\n"
        "• отозвать согласие и удалить данные — /delete_my_data\n\n"
        f"Полный текст: {privacy_policy_url()}"
    )


def terms_short_text() -> str:
    return (
        "📜 <b>Пользовательское соглашение GymBros</b>\n\n"
        "Сервис предназначен для лиц старше 18 лет.\n"
        "Запрещены оскорбления, спам, мошенничество, контент 18+ вне контекста "
        "знакомства для тренировок и публикация чужих персональных данных.\n"
        "Оператор может удалить анкету при нарушении правил.\n\n"
        f"Полный текст: {terms_url()}"
    )


def help_text() -> str:
    return (
        "🏋️‍♂️ <b>GymBros</b> — бот для поиска напарника для тренировок.\n\n"
        f"Открыть бота: https://t.me/{bot_username()}\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/help — справка\n"
        "/privacy — политика конфиденциальности\n"
        "/terms — пользовательское соглашение\n"
        "/delete_my_data — удалить анкету и персональные данные\n"
        "/cancel — отменить текущий шаг\n\n"
        f"Поддержка: {operator_telegram()}"
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
