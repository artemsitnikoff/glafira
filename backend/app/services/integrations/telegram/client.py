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

import base64
import logging
import time

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.auth import ResendCodeRequest, ExportLoginTokenRequest, ImportLoginTokenRequest
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
    FloodWaitError,
    ApiIdInvalidError,
    AuthTokenExpiredError,
    AuthTokenAlreadyAcceptedError,
)
from telethon.tl import types as tl_types

from ....config import settings
from ....core.errors import AppError, ValidationError

logger = logging.getLogger(__name__)


def _mask_phone(p: str) -> str:
    p = p or ""
    return (p[:5] + "***" + p[-2:]) if len(p) > 8 else "***"


def _api_creds() -> tuple[int, str]:
    """Возвращает (api_id, api_hash). TELETHON_* имеют приоритет над TELEGRAM_*."""
    api_id = settings.TELETHON_API_ID or settings.TELEGRAM_API_ID
    api_hash = settings.TELETHON_API_HASH or settings.TELEGRAM_API_HASH
    if not api_id or not api_hash:
        raise ValidationError(
            "Telegram не настроен на сервере: задайте TELETHON_API_ID и "
            "TELETHON_API_HASH (или TELEGRAM_API_ID / TELEGRAM_API_HASH) в .env "
            "(получить на my.telegram.org)"
        )
    return int(api_id), api_hash


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
        code_type = type(sent.type).__name__
        next_type = type(sent.next_type).__name__ if sent.next_type else None
        logger.info(
            "[tg] send_code phone=%s -> type=%s next_type=%s timeout=%s hash=%s",
            _mask_phone(phone), code_type, next_type,
            getattr(sent, "timeout", None), bool(sent.phone_code_hash),
        )
        return {
            "session": client.session.save(),
            "phone_code_hash": sent.phone_code_hash,
            "code_type": code_type,
        }
    except PhoneNumberInvalidError:
        logger.warning("[tg] send_code phone=%s -> PhoneNumberInvalid", _mask_phone(phone))
        raise AppError(code="TG_PHONE_INVALID", message="Неверный номер телефона", status_code=400)
    except ApiIdInvalidError:
        logger.warning("[tg] send_code phone=%s -> ApiIdInvalid", _mask_phone(phone))
        raise AppError(code="TG_API_INVALID", message="Неверные api_id/api_hash (проверьте .env)", status_code=400)
    except FloodWaitError as e:
        logger.warning("[tg] send_code phone=%s -> FloodWait %ss", _mask_phone(phone), e.seconds)
        raise AppError(code="TG_FLOOD", message=f"Слишком частые запросы, подождите {e.seconds} сек", status_code=400, details={"seconds": e.seconds})
    except AppError:
        raise
    except Exception as e:
        logger.exception("[tg] send_code phone=%s -> %s: %s", _mask_phone(phone), type(e).__name__, e)
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
        code_type = type(sent.type).__name__
        next_type = type(sent.next_type).__name__ if sent.next_type else None
        logger.info(
            "[tg] resend_code phone=%s -> type=%s next_type=%s timeout=%s",
            _mask_phone(phone), code_type, next_type, getattr(sent, "timeout", None),
        )
        return {
            "session": client.session.save(),
            "phone_code_hash": sent.phone_code_hash,
            "code_type": code_type,
        }
    except FloodWaitError as e:
        logger.warning("[tg] resend_code phone=%s -> FloodWait %ss", _mask_phone(phone), e.seconds)
        raise AppError(code="TG_FLOOD", message=f"Слишком частые запросы, подождите {e.seconds} сек", status_code=400, details={"seconds": e.seconds})
    except AppError:
        raise
    except Exception as e:
        logger.exception("[tg] resend_code phone=%s -> %s: %s", _mask_phone(phone), type(e).__name__, e)
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


async def connect_with_session(session_str: str) -> dict:
    """Подключение по ГОТОВОЙ StringSession (минуя номер/код).

    Проверяет, что сессия авторизована, и возвращает данные аккаунта. Строку сессии
    НЕ логируем (это полный доступ к аккаунту).
    """
    api_id, api_hash = _api_creds()
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise AppError(code="TG_SESSION_INVALID", message="Строка сессии недействительна или не авторизована", status_code=400)
        me = await client.get_me()
        logger.info("[tg] connect_with_session -> authorized id=%s username=%s", getattr(me, "id", None), getattr(me, "username", None))
        return {"status": "connected", "session": client.session.save(), "user": _me_dict(me)}
    except AppError:
        raise
    except Exception as e:
        logger.exception("[tg] connect_with_session -> %s: %s", type(e).__name__, e)
        raise AppError(code="TG_SESSION_ERROR", message="Не удалось подключиться по строке сессии", status_code=400, details={"reason": str(e)})
    finally:
        await client.disconnect()


def _token_b64(token_bytes: bytes) -> str:
    """bytes → base64url without padding (для безопасной передачи в JSON)."""
    return base64.urlsafe_b64encode(token_bytes).decode().rstrip("=")


def _token_bytes(token_b64: str) -> bytes:
    """base64url without padding → bytes (реpadding)."""
    pad = 4 - len(token_b64) % 4
    if pad != 4:
        token_b64 += "=" * pad
    return base64.urlsafe_b64decode(token_b64)


async def qr_export() -> dict:
    """STATELESS QR-старт: ExportLoginToken → {qr_url, token, session, expires}.

    Создаёт пустой клиент, экспортирует QR-токен, сохраняет сессию (с auth-ключом DC)
    и дисконнектируется. Результат хранится в БД (сессия зашифрована).

    Возвращает:
      qr_url  — tg:// ссылка для кодирования в QR-код
      token   — base64url-строка токена (сохранить, передать в qr_poll)
      session — StringSession строка (сохранить зашифрованной)
      expires — unix epoch seconds (когда токен протухнет, обычно +60с)
    """
    api_id, api_hash = _api_creds()
    client = TelegramClient(StringSession(), api_id, api_hash)
    try:
        await client.connect()
        r = await client(ExportLoginTokenRequest(api_id=api_id, api_hash=api_hash, except_ids=[]))
        token_bytes = r.token
        token_b64 = _token_b64(token_bytes)
        qr_url = "tg://login?token=" + token_b64
        expires = getattr(r, "expires", None)
        if expires is None:
            expires = int(time.time()) + 60
        elif hasattr(expires, "timestamp"):
            expires = int(expires.timestamp())
        else:
            expires = int(expires)
        logger.info("[tg_qr] qr_export ok, expires=%s", expires)
        return {
            "qr_url": qr_url,
            "token": token_b64,
            "session": client.session.save(),
            "expires": expires,
        }
    except ApiIdInvalidError:
        raise AppError(code="TG_API_INVALID", message="Неверные api_id/api_hash (проверьте .env)", status_code=400)
    except FloodWaitError as e:
        raise AppError(code="TG_FLOOD", message=f"Слишком частые запросы, подождите {e.seconds} сек", status_code=400, details={"seconds": e.seconds})
    except AppError:
        raise
    except Exception as e:
        logger.exception("[tg_qr] qr_export -> %s: %s", type(e).__name__, e)
        raise AppError(code="TG_QR_EXPORT_ERROR", message="Не удалось создать QR-код Telegram", status_code=400, details={"reason": str(e)})
    finally:
        await client.disconnect()


async def qr_poll(session_str: str, token_b64: str) -> dict:
    """STATELESS QR-поллинг: ImportLoginToken → {status, ...}.

    Принимает сохранённую сессию и токен (из qr_export или предыдущего qr_poll).
    Возможные статусы в результате:
      'connected'      — QR отсканирован и авторизован; {'session', 'user'}
      'waiting'        — ещё не отсканирован
      'expired'        — токен протух, новый QR: {'qr_url', 'token', 'session', 'expires'}
      'password_needed'— 2FA: {'session'} (частичная сессия, нужен confirm_password)
    """
    api_id, api_hash = _api_creds()
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    try:
        await client.connect()
        token_bytes = _token_bytes(token_b64)

        try:
            r = await client(ImportLoginTokenRequest(token=token_bytes))

            if isinstance(r, tl_types.auth.LoginTokenSuccess):
                me = await client.get_me()
                logger.info("[tg_qr] qr_poll -> connected id=%s", getattr(me, "id", None))
                return {
                    "status": "connected",
                    "session": client.session.save(),
                    "user": _me_dict(me),
                }

            if isinstance(r, tl_types.auth.LoginTokenMigrateTo):
                # DC migration: переключаемся на другой DC и повторяем import
                logger.info("[tg_qr] qr_poll -> LoginTokenMigrateTo dc=%s", r.dc_id)
                await client._switch_dc(r.dc_id)
                r2 = await client(ImportLoginTokenRequest(token=r.token))
                if isinstance(r2, tl_types.auth.LoginTokenSuccess):
                    me = await client.get_me()
                    logger.info("[tg_qr] qr_poll -> connected (after dc migrate) id=%s", getattr(me, "id", None))
                    return {
                        "status": "connected",
                        "session": client.session.save(),
                        "user": _me_dict(me),
                    }
                # После DC migrate пришло что-то другое — не отсканировано
                logger.info("[tg_qr] qr_poll -> after dc migrate, still waiting")
                return {"status": "waiting"}

            # LoginToken — токен живой, ещё не отсканирован
            logger.info("[tg_qr] qr_poll -> waiting (LoginToken)")
            return {"status": "waiting"}

        except AuthTokenExpiredError:
            # Токен протух — перевыпускаем QR на той же сессии (auth-ключ уже есть)
            logger.info("[tg_qr] qr_poll -> AuthTokenExpiredError, re-exporting")
            r_new = await client(ExportLoginTokenRequest(api_id=api_id, api_hash=api_hash, except_ids=[]))
            new_token_bytes = r_new.token
            new_token_b64 = _token_b64(new_token_bytes)
            new_qr_url = "tg://login?token=" + new_token_b64
            new_expires = getattr(r_new, "expires", None)
            if new_expires is None:
                new_expires = int(time.time()) + 60
            elif hasattr(new_expires, "timestamp"):
                new_expires = int(new_expires.timestamp())
            else:
                new_expires = int(new_expires)
            return {
                "status": "expired",
                "qr_url": new_qr_url,
                "token": new_token_b64,
                "session": client.session.save(),
                "expires": new_expires,
            }

        except AuthTokenAlreadyAcceptedError:
            # Уже принят — проверим авторизацию
            logger.info("[tg_qr] qr_poll -> AuthTokenAlreadyAcceptedError")
            if await client.is_user_authorized():
                me = await client.get_me()
                return {
                    "status": "connected",
                    "session": client.session.save(),
                    "user": _me_dict(me),
                }
            return {"status": "waiting"}

        except SessionPasswordNeededError:
            # 2FA включена — возвращаем частичную сессию для confirm_password
            logger.info("[tg_qr] qr_poll -> SessionPasswordNeededError (2FA)")
            return {
                "status": "password_needed",
                "session": client.session.save(),
            }

    except ApiIdInvalidError:
        raise AppError(code="TG_API_INVALID", message="Неверные api_id/api_hash (проверьте .env)", status_code=400)
    except FloodWaitError as e:
        raise AppError(code="TG_FLOOD", message=f"Слишком частые запросы, подождите {e.seconds} сек", status_code=400, details={"seconds": e.seconds})
    except AppError:
        raise
    except Exception as e:
        logger.exception("[tg_qr] qr_poll -> %s: %s", type(e).__name__, e)
        raise AppError(code="TG_QR_POLL_ERROR", message="Ошибка поллинга QR-статуса Telegram", status_code=400, details={"reason": str(e)})
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
