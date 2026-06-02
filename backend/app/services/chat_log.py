"""Текстовый журнал чатов (исходящие сообщения по всем каналам + входящие hh).

Пишем построчно в settings.CHAT_LOG_PATH (по умолчанию /app/storage/chat.log —
том backend_storage, общий для веб- и cron-контейнера, переживает рестарт). Запись
НИКОГДА не бросает: сбой журнала не должен ронять отправку/приём сообщения.

Формат строки:
  2026-06-02 14:05:31 UTC  hh → Иванов Иван • отправлено
  2026-06-02 14:05:31 UTC  email → Петрова Анна • НЕ отправлено: SMTP не настроен
  2026-06-02 14:05:31 UTC  telegram → Сидоров П. • сохранено (канал без реальной отправки)
  2026-06-02 14:06:10 UTC  hh ← входящее (chat 3490): Здравствуйте, когда собеседование?
"""

import logging
import os
from datetime import datetime, timezone

from ..config import settings

logger = logging.getLogger(__name__)


def log_chat(message: str) -> None:
    """Дописать одну строку в журнал чатов. Безопасно при любых ошибках ФС."""
    path = settings.CHAT_LOG_PATH
    if not path:
        return
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{ts} UTC  {message}\n")
    except Exception as e:  # noqa: BLE001 — журнал не критичен, не валим чат
        logger.warning("Не удалось записать журнал чатов: %s", e)
