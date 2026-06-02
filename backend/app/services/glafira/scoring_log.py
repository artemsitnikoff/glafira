"""Текстовый журнал оценок Глафиры (авто + по кнопке).

Пишем построчно в settings.SCORING_LOG_PATH (по умолчанию /app/storage/scoring.log —
named-том backend_storage, общий для веб-контейнера и cron-контейнера `run --rm`,
переживает рестарт). Запись НИКОГДА не бросает: сбой журнала не должен ронять скоринг.

Формат строки:
  2026-06-02 14:05:31 UTC  АВТО • Иванов Иван • Руководитель ОП • оценка 73 (good)
  2026-06-02 14:05:31 UTC  КНОПКА • Петров П. • без вакансии • оценки не было (уже была, балл 81)
"""

import logging
import os
from datetime import datetime, timezone

from ...config import settings

logger = logging.getLogger(__name__)


def log_scoring(message: str) -> None:
    """Дописать одну строку в журнал оценок. Безопасно при любых ошибках ФС."""
    path = settings.SCORING_LOG_PATH
    if not path:
        return
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{ts} UTC  {message}\n")
    except Exception as e:  # noqa: BLE001 — журнал не критичен, не валим скоринг
        logger.warning("Не удалось записать журнал оценок: %s", e)
