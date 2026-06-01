"""SMTP-транспорт: реальная отправка письма через stdlib smtplib.

Без сторонних зависимостей (aiosmtplib не нужен). Синхронный smtplib крутится
в пуле потоков (asyncio.to_thread), чтобы не блокировать event loop.

Все сбои — честные: исключения smtplib/сети маппятся на AppError с понятным
кодом и причиной (status 400), а НЕ молча проглатываются. «Отправлено» = реально
сервер принял письмо без исключения.
"""

import asyncio
import smtplib
import socket
import ssl
from email.message import EmailMessage

from ....core.errors import AppError

# Таймаут на соединение/операции SMTP (сек). Не висим бесконечно на мёртвом хосте.
SMTP_TIMEOUT = 20


def _build_message(
    from_email: str,
    from_name: str,
    reply_to: str,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    return msg


def _send_sync(
    host: str,
    port: int,
    encryption: str,
    username: str,
    password: str,
    msg: EmailMessage,
) -> None:
    """Синхронная отправка (выполняется в отдельном потоке)."""
    context = ssl.create_default_context()

    if encryption == "ssl":
        with smtplib.SMTP_SSL(host, port, context=context, timeout=SMTP_TIMEOUT) as server:
            if username:
                server.login(username, password)
            server.send_message(msg)
    else:
        # tls (STARTTLS) или none (без шифрования)
        with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT) as server:
            server.ehlo()
            if encryption == "tls":
                server.starttls(context=context)
                server.ehlo()
            if username:
                server.login(username, password)
            server.send_message(msg)


async def send_via_smtp(
    *,
    host: str,
    port: int,
    encryption: str,
    username: str,
    password: str,
    from_email: str,
    from_name: str,
    reply_to: str,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> None:
    """Отправляет письмо. Бросает AppError с честным кодом/причиной при сбое.

    Возврат без исключения = сервер принял письмо.
    """
    msg = _build_message(from_email, from_name, reply_to, to, subject, body_text, body_html)

    try:
        await asyncio.to_thread(
            _send_sync, host, port, encryption, username, password, msg
        )
    except smtplib.SMTPAuthenticationError as e:
        raise AppError(
            code="SMTP_AUTH_ERROR",
            message="Не удалось авторизоваться на SMTP-сервере — проверьте логин и пароль",
            status_code=400,
            details={"reason": str(e)},
        )
    except smtplib.SMTPConnectError as e:
        raise AppError(
            code="SMTP_CONNECT_ERROR",
            message="Не удалось подключиться к SMTP-серверу",
            status_code=400,
            details={"reason": str(e)},
        )
    except smtplib.SMTPRecipientsRefused as e:
        raise AppError(
            code="SMTP_RECIPIENT_REFUSED",
            message="SMTP-сервер отклонил адрес получателя",
            status_code=400,
            details={"reason": str(e)},
        )
    except smtplib.SMTPException as e:
        # Любая прочая SMTP-ошибка (sender refused, data error, disconnect и т.п.)
        raise AppError(
            code="SMTP_SEND_ERROR",
            message="Ошибка SMTP при отправке письма",
            status_code=400,
            details={"reason": str(e)},
        )
    except ssl.SSLError as e:
        # SSLError — подкласс OSError, ловим до общего OSError
        raise AppError(
            code="SMTP_TLS_ERROR",
            message="Ошибка TLS/SSL при подключении к SMTP-серверу (проверьте порт и режим шифрования)",
            status_code=400,
            details={"reason": str(e)},
        )
    except (socket.timeout, TimeoutError) as e:
        raise AppError(
            code="SMTP_TIMEOUT",
            message="Таймаут подключения к SMTP-серверу (проверьте хост и порт)",
            status_code=400,
            details={"reason": str(e)},
        )
    except (socket.gaierror, ConnectionError, OSError) as e:
        raise AppError(
            code="SMTP_CONNECT_ERROR",
            message="Не удалось подключиться к SMTP-серверу (проверьте хост и порт)",
            status_code=400,
            details={"reason": str(e)},
        )
