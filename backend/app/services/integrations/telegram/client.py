"""Telethon-клиент для Telegram user-аккаунта (MTProto).

Поток входа STATELESS: каждая операция поднимает TelegramClient из StringSession,
коннектится, делает шаг, сериализует сессию обратно (client.session.save()) и
дисконнектится. Между шагами строка-сессия (с auth-ключом) переносится через БД.

⚠️ Сессия = ПОЛНЫЙ доступ к аккаунту Telegram (шифруется на уровне сервиса).
⚠️ Автоматизация user-аккаунта против ToS Telegram (риск бана) — осознанное решение
   заказчика.

api_id/api_hash — из .env (TELEGRAM_API_ID / TELEGRAM_API_HASH), одно приложение
на инстанс.
"""

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.auth import ResendCodeRequest
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
    FloodWaitError,
    ApiIdInvalidError,
)

from ....config import settings
from ....core.errors import AppError, ValidationError


def _api_creds() -> tuple[int, str]:
    if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
        raise ValidationError(
            "Telegram не настроен на сервере: задайте TELEGRAM_API_ID и "
            "TELEGRAM_API_HASH в .env (с my.telegram.org)"
        )
    return int(settings.TELEGRAM_API_ID), settings.TELEGRAM_API_HASH


def _me_dict(me) -> dict:
    return {
        "id": str(me.id),
        "username": getattr(me, "username", None),
        "first_name": getattr(me, "first_name", None),
        "phone": getattr(me, "phone", None),
    }


async def send_code(phone: str) -> dict:
    """Шаг 1: запросить код на номер. Возвращает {session, phone_code_hash, code_type}.

    code_type — КАК Telegram доставил код (SentCodeTypeApp/Sms/Call/...). При наличии
    активной сессии Telegram код уходит В ПРИЛОЖЕНИЕ (чат «Telegram»), а не по SMS.
    """
    api_id, api_hash = _api_creds()
    client = TelegramClient(StringSession(), api_id, api_hash)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        return {
            "session": client.session.save(),
            "phone_code_hash": sent.phone_code_hash,
            "code_type": type(sent.type).__name__,
        }
    except PhoneNumberInvalidError:
        raise AppError(code="TG_PHONE_INVALID", message="Неверный номер телефона", status_code=400)
    except ApiIdInvalidError:
        raise AppError(code="TG_API_INVALID", message="Неверные api_id/api_hash (проверьте .env)", status_code=400)
    except FloodWaitError as e:
        raise AppError(code="TG_FLOOD", message=f"Слишком частые запросы, подождите {e.seconds} сек", status_code=400, details={"seconds": e.seconds})
    except AppError:
        raise
    except Exception as e:
        raise AppError(code="TG_SEND_CODE_ERROR", message="Не удалось отправить код Telegram", status_code=400, details={"reason": str(e)})
    finally:
        await client.disconnect()


async def resend_code(session_str: str, phone: str, phone_code_hash: str) -> dict:
    """Повторная отправка кода по СЛЕДУЮЩЕМУ каналу (next_type): обычно App → SMS.

    Помогает, когда первый код (в приложение) не дошёл — Telegram переключает на SMS.
    """
    api_id, api_hash = _api_creds()
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    try:
        await client.connect()
        sent = await client(ResendCodeRequest(phone=phone, phone_code_hash=phone_code_hash))
        return {
            "session": client.session.save(),
            "phone_code_hash": sent.phone_code_hash,
            "code_type": type(sent.type).__name__,
        }
    except FloodWaitError as e:
        raise AppError(code="TG_FLOOD", message=f"Слишком частые запросы, подождите {e.seconds} сек", status_code=400, details={"seconds": e.seconds})
    except AppError:
        raise
    except Exception as e:
        raise AppError(code="TG_RESEND_ERROR", message="Не удалось переотправить код", status_code=400, details={"reason": str(e)})
    finally:
        await client.disconnect()


async def sign_in_code(session_str: str, phone: str, code: str, phone_code_hash: str) -> dict:
    """Шаг 2: ввод кода. Возвращает {status: 'connected'|'need_password', session, user?}."""
    api_id, api_hash = _api_creds()
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    try:
        await client.connect()
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            # Включена 2FA — нужен облачный пароль (шаг 2б)
            return {"status": "need_password", "session": client.session.save()}

        me = await client.get_me()
        return {"status": "connected", "session": client.session.save(), "user": _me_dict(me)}
    except (PhoneCodeInvalidError, PhoneCodeExpiredError):
        raise AppError(code="TG_CODE_INVALID", message="Неверный или истёкший код", status_code=400)
    except FloodWaitError as e:
        raise AppError(code="TG_FLOOD", message=f"Слишком частые запросы, подождите {e.seconds} сек", status_code=400, details={"seconds": e.seconds})
    except AppError:
        raise
    except Exception as e:
        raise AppError(code="TG_SIGNIN_ERROR", message="Ошибка входа в Telegram", status_code=400, details={"reason": str(e)})
    finally:
        await client.disconnect()


async def sign_in_password(session_str: str, password: str) -> dict:
    """Шаг 2б: облачный пароль 2FA. Возвращает {status:'connected', session, user}."""
    api_id, api_hash = _api_creds()
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    try:
        await client.connect()
        await client.sign_in(password=password)
        me = await client.get_me()
        return {"status": "connected", "session": client.session.save(), "user": _me_dict(me)}
    except FloodWaitError as e:
        raise AppError(code="TG_FLOOD", message=f"Слишком частые запросы, подождите {e.seconds} сек", status_code=400, details={"seconds": e.seconds})
    except AppError:
        raise
    except Exception as e:
        raise AppError(code="TG_PASSWORD_ERROR", message="Неверный пароль 2FA или ошибка входа", status_code=400, details={"reason": str(e)})
    finally:
        await client.disconnect()


async def send_to_self(session_str: str, text: str) -> None:
    """Тест: отправить сообщение себе («Избранное»)."""
    api_id, api_hash = _api_creds()
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise AppError(code="TG_NOT_AUTHORIZED", message="Сессия Telegram недействительна — подключитесь заново", status_code=400)
        await client.send_message("me", text)
    except AppError:
        raise
    except Exception as e:
        raise AppError(code="TG_SEND_ERROR", message="Не удалось отправить сообщение через Telegram", status_code=400, details={"reason": str(e)})
    finally:
        await client.disconnect()
