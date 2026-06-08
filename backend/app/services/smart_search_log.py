"""Текстовый журнал умного подбора (подробный лог каждого прогона).

Пишем построчно в settings.SMART_SEARCH_LOG_PATH (по умолчанию /app/storage/smart_search.log —
named-том backend_storage, общий для веб-контейнера и cron-контейнера `run --rm`,
переживает рестарт). Запись НИКОГДА не бросает: сбой журнала не должен ронять подбор.

Формат строки:
  2026-06-08 15:30:45 UTC  RUN d1e2f3 • Аналитик данных • страница 1/3 (42 резюме) • found=269
  2026-06-08 15:30:47 UTC  RUN d1e2f3 • резюме 12345 • Иванов И. • score 78 (good) • passed
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from ..config import settings

logger = logging.getLogger(__name__)


def log_smart_search(run_id: UUID, message: str) -> None:
    """Дописать одну строку в журнал умного подбора. Безопасно при любых ошибках ФС."""
    path = settings.SMART_SEARCH_LOG_PATH
    if not path:
        return
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        run_short = str(run_id)[:6]
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{ts} UTC  RUN {run_short} • {message}\n")
    except Exception as e:  # noqa: BLE001 — журнал не критичен, не валим подбор
        logger.warning("Не удалось записать журнал умного подбора: %s", e)


def log_and_append_to_run(run, run_id: UUID, message: str, max_log_size: int = 200) -> None:
    """
    Записывает сообщение в файл-лог И добавляет в run.log (с ограничением размера).

    Args:
        run: объект SmartSearchRun
        run_id: UUID прогона
        message: сообщение для логирования
        max_log_size: максимальное количество строк в run.log
    """
    # Записываем в файл
    log_smart_search(run_id, message)

    # Добавляем в run.log с ограничением размера
    if not isinstance(run.log, list):
        run.log = []

    run.log = run.log.copy()  # Создаём новый список чтобы SQLAlchemy увидел изменение
    run.log.append(message)

    # Обрезаем до последних max_log_size записей
    if len(run.log) > max_log_size:
        run.log = run.log[-max_log_size:]