"""Тексты и хелперы 152-ФЗ: политика, согласие, журнал согласий."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import psycopg2

CONSENT_VERSION = os.getenv("CONSENT_VERSION", "1.0")

DEFAULT_PRIVACY_URL = (
    "https://github.com/AlexZhiryakov/GymBros/blob/main/docs/legal/privacy-policy.md"
)


def privacy_policy_url() -> str:
    return os.getenv("PRIVACY_POLICY_URL", DEFAULT_PRIVACY_URL)


def operator_contact() -> str:
    return os.getenv("OPERATOR_CONTACT", "@gymbros_manager")


def consent_message() -> str:
    contact = operator_contact()
    url = privacy_policy_url()
    return (
        "📋 <b>Согласие на обработку персональных данных</b>\n\n"
        "Чтобы пользоваться GymBros, нужно отдельное согласие на обработку "
        "персональных данных (152-ФЗ).\n\n"
        "<b>Цель:</b> создание анкеты и поиск напарника для тренировок "
        "(показ анкеты другим пользователям, мэтчи, уведомления).\n\n"
        "<b>Данные:</b> Telegram ID и username; имя, возраст, пол и предпочтения; "
        "город, опыт, описание, зал; фото/видео анкеты; лайки и служебные сведения; "
        "факт и время согласия.\n\n"
        "<b>Действия:</b> сбор, хранение, использование, показ в боте, передача "
        "инфраструктуре Telegram и хостинг-/БД-провайдеру, удаление по вашей просьбе.\n\n"
        f"<b>Оператор / контакты:</b> {contact}\n"
        f"<b>Политика:</b> {url}\n"
        f"<b>Полный текст согласия:</b> docs/legal/consent.md (версия {CONSENT_VERSION})\n\n"
        "Нажимая «✅ Согласен», вы даёте согласие отдельно от условий подписки. "
        "Отозвать можно командой /delete_my_data."
    )


def privacy_command_message() -> str:
    return (
        "🔒 <b>Персональные данные</b>\n\n"
        f"Политика обработки ПДн:\n{privacy_policy_url()}\n\n"
        f"Версия согласия: {CONSENT_VERSION}\n"
        f"Контакт оператора: {operator_contact()}\n\n"
        "Удалить анкету и связанные данные: /delete_my_data"
    )


def ensure_consents_table(db_config: dict) -> None:
    """Идемпотентно создаёт таблицу журнала согласий."""
    conn = None
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_consents (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL UNIQUE,
                consented BOOLEAN NOT NULL DEFAULT FALSE,
                consent_version VARCHAR(32) NOT NULL,
                consented_at TIMESTAMPTZ,
                revoked_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_user_consents_telegram_id
                ON user_consents (telegram_id);
            """
        )
        conn.commit()
    except Exception as e:
        print(f"ensure_consents_table: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def has_valid_consent(db_config: dict, telegram_id: int) -> bool:
    conn = None
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT consented, consent_version
            FROM user_consents
            WHERE telegram_id = %s AND consented = TRUE AND revoked_at IS NULL
            """,
            (telegram_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False
        # При смене мажорной версии политики можно форсировать повторное согласие
        return row[1] == CONSENT_VERSION
    except Exception as e:
        print(f"has_valid_consent: {e}")
        return False
    finally:
        if conn:
            conn.close()


def record_consent(db_config: dict, telegram_id: int, consented: bool) -> bool:
    conn = None
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc)
        if consented:
            cursor.execute(
                """
                INSERT INTO user_consents (
                    telegram_id, consented, consent_version, consented_at, revoked_at, updated_at
                ) VALUES (%s, TRUE, %s, %s, NULL, %s)
                ON CONFLICT (telegram_id) DO UPDATE SET
                    consented = TRUE,
                    consent_version = EXCLUDED.consent_version,
                    consented_at = EXCLUDED.consented_at,
                    revoked_at = NULL,
                    updated_at = EXCLUDED.updated_at
                """,
                (telegram_id, CONSENT_VERSION, now, now),
            )
        else:
            cursor.execute(
                """
                INSERT INTO user_consents (
                    telegram_id, consented, consent_version, consented_at, revoked_at, updated_at
                ) VALUES (%s, FALSE, %s, NULL, %s, %s)
                ON CONFLICT (telegram_id) DO UPDATE SET
                    consented = FALSE,
                    revoked_at = EXCLUDED.revoked_at,
                    updated_at = EXCLUDED.updated_at
                """,
                (telegram_id, CONSENT_VERSION, now, now),
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"record_consent: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()
