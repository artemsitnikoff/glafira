"""Публичные Pydantic-схемы экзамен-API модуля «Тесты».

⚠️ БЕЗОПАСНОСТЬ — ГЛАВНОЕ ПРАВИЛО ЭТОГО ФАЙЛА:
    Ни одна схема НЕ содержит `correct_option_id` и НИКАКОГО признака правильности.
    Правильный ответ живёт ТОЛЬКО в TestItem.correct_option_id (server-only колонка) и
    сериализуется ИСКЛЮЧИТЕЛЬНО на сервере при проверке ответа. Клиент получает лишь
    тело задания (`body`) и варианты (`options` = {id, params|text}) — без пометок.

Это ОТДЕЛЬНЫЕ схемы (а не ORM-сериализация модели) именно затем, чтобы физически
исключить утечку правильного ответа: поля `correct_option_id` здесь просто нет.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PublicOption(BaseModel):
    """Вариант ответа, отдаваемый КЛИЕНТУ.

    Содержит только идентификатор варианта и его отображаемое наполнение
    (params — для матриц, text — для вербальных). ⚠️ НЕТ признака правильности.
    """
    id: str
    params: Optional[dict] = None   # matrix
    text: Optional[str] = None      # text


class PublicItem(BaseModel):
    """Одно задание для прохождения. Правильного ответа НЕ содержит."""
    id: str
    kind: str            # 'matrix' | 'text'
    body: dict           # тело задания (ячейка-вопрос пустая / термины) — без ответа
    options: list[PublicOption]


class PublicBlockInfo(BaseModel):
    index: int           # 0-based позиция блока
    key: str
    title: str
    item_count: int
    duration_min: int


class PublicTestInfo(BaseModel):
    """Инфо-экран (до старта). БЕЗ заданий/ответов/PII кандидата."""
    status: str          # 'sent' | 'started' | 'completed' | 'expired'
    company_name: str
    test_name: str
    kind: str            # 'single' | 'blocked'
    instruction: str
    item_count: int
    duration_min: Optional[int] = None   # single (весь тест); для blocked — None
    blocks: list[PublicBlockInfo] = Field(default_factory=list)


class PublicStartRequest(BaseModel):
    # ⚠️ Согласие ОБЯЗАТЕЛЬНО (152-ФЗ): без true старт невозможен.
    consent: bool = False


class PublicStartResponse(BaseModel):
    status: str          # 'started'
    kind: str            # 'single' | 'blocked'


class PublicCurrentBlock(BaseModel):
    index: int           # 0-based позиция текущего блока
    total: int           # всего блоков
    key: str
    title: str
    time_left_sec: int   # серверный остаток времени ТЕКУЩЕГО блока


class PublicCurrentResponse(BaseModel):
    """Текущее задание (ОДНО). Правильного ответа НЕ содержит.

    status:
      'in_progress'          — есть задание (item != None);
      'awaiting_next_block'  — блок завершён, нужно вызвать /block/next (blocked);
      'completed'            — тест завершён (item == None, баллов здесь нет);
      'not_started'          — прохождение ещё не начато (нужно /start).
    """
    status: str
    index: int = 0       # 0-based позиция задания в текущем потоке/блоке
    total: int = 0       # число заданий в текущем потоке/блоке
    time_left_sec: Optional[int] = None   # single: остаток на весь тест
    block: Optional[PublicCurrentBlock] = None
    item: Optional[PublicItem] = None
    next_block_title: Optional[str] = None  # для awaiting_next_block


class PublicAnswerRequest(BaseModel):
    item_id: str
    # Ровно один из двух: стабильный id варианта ИЛИ позиция в выданном (перемешанном) списке.
    chosen_option_id: Optional[str] = None
    chosen_index: Optional[int] = None
    time_ms: Optional[int] = None


class PublicAnswerResponse(BaseModel):
    """Подтверждение записи ответа.

    ⚠️ БЕЗ is_correct и любого признака правильности — верность ответа клиенту не
    раскрывается ни на одном шаге. Только сигнал о состоянии прохождения.
    """
    ok: bool = True
    status: str          # 'in_progress' | 'awaiting_next_block' | 'completed'


class PublicBlockNextResponse(BaseModel):
    status: str          # 'in_progress' (стартовал следующий блок) | 'completed'
    block: Optional[PublicCurrentBlock] = None
