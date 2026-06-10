"""Сервис эмбеддингов для семантического поиска"""

import logging
import hashlib
import asyncio
from typing import Optional
from functools import lru_cache

from ..config import settings
from ..models import Candidate, CandidateExperience, CandidateSkill

logger = logging.getLogger(__name__)

# Константы
EMBED_DIM = 384  # Размерность модели paraphrase-multilingual-MiniLM-L12-v2
GLAFIRA_EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache(maxsize=1)
def _get_embedding_model():
    """Ленивый синглтон TextEmbedding модели"""
    try:
        from fastembed import TextEmbedding
        model_name = getattr(settings, 'GLAFIRA_EMBED_MODEL', GLAFIRA_EMBED_MODEL)
        logger.info(f"Инициализация эмбеддинг-модели: {model_name}")
        return TextEmbedding(model_name)
    except Exception as e:
        logger.error(f"Ошибка инициализации эмбеддинг-модели: {e}")
        return None


def build_candidate_text(
    candidate: Candidate,
    skills: list[CandidateSkill],
    experiences: list[CandidateExperience]
) -> str:
    """
    Строит текстовое представление кандидата для эмбеддинга

    Args:
        candidate: Модель кандидата
        skills: Навыки кандидата
        experiences: Опыт работы кандидата

    Returns:
        str: Текстовое представление кандидата
    """
    parts = []

    # Должность
    if candidate.last_position:
        parts.append(f"Должность: {candidate.last_position}")

    # Компания
    if candidate.last_company:
        parts.append(f"Компания: {candidate.last_company}")

    # Навыки
    if skills:
        skills_text = ", ".join([skill.skill for skill in skills if skill.skill])
        if skills_text:
            parts.append(f"Навыки: {skills_text}")

    # Опыт работы
    if experiences:
        exp_parts = []
        for exp in experiences:
            exp_text = ""
            if exp.position:
                exp_text = exp.position
            if exp.description:
                exp_text += f" - {exp.description}"
            if exp_text:
                exp_parts.append(exp_text)

        if exp_parts:
            parts.append(f"Опыт: {' | '.join(exp_parts)}")

    # Резюме
    if candidate.resume_summary:
        parts.append(f"Резюме: {candidate.resume_summary}")
    elif candidate.resume_text:
        # Обрезаем очень длинные тексты резюме
        resume_text = candidate.resume_text[:2000] if len(candidate.resume_text) > 2000 else candidate.resume_text
        parts.append(f"Резюме: {resume_text}")

    text = " ".join(parts)
    return text.strip()


def source_hash(text: str) -> str:
    """
    Создаёт хеш от текста для отслеживания изменений

    Args:
        text: Текст для хеширования

    Returns:
        str: SHA256 хеш
    """
    if not text:
        return ""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


async def embed_texts(texts: list[str]) -> list[Optional[list[float]]]:
    """
    Создаёт эмбеддинги для списка текстов (батчевая обработка).

    Returns:
        list[Optional[list[float]]]: эмбеддинг на каждый текст; None — если текст пуст
        ИЛИ модель недоступна/сбой. ⚠️ НИКОГДА не нулевой вектор (нулевой вектор загрязнил бы
        индекс и сломал бы cosine-поиск). None → вызывающий код пропускает (индексация не
        хранит, retrieve деградирует на SQL).
    """
    if not texts:
        return []

    # Фильтруем пустые тексты (для них результат — None)
    valid_indices = []
    valid_texts = []
    for i, text in enumerate(texts):
        if text and text.strip():
            valid_indices.append(i)
            valid_texts.append(text.strip())

    if not valid_texts:
        return [None] * len(texts)

    try:
        model = _get_embedding_model()
        if model is None:
            logger.warning("Эмбеддинг-модель недоступна — возвращаем None (деградация, не нули)")
            return [None] * len(texts)

        # Выполняем в фоновом потоке (ONNX синхронный); сбой → пробрасываем в outer except
        def _embed_sync():
            embeddings_gen = model.embed(valid_texts)
            return [embedding.tolist() for embedding in embeddings_gen]

        embeddings = await asyncio.to_thread(_embed_sync)

        # Восстанавливаем порядок; пропущенные (пустые) тексты остаются None
        result: list[Optional[list[float]]] = [None] * len(texts)
        for pos, orig_i in enumerate(valid_indices):
            result[orig_i] = embeddings[pos]
        return result

    except Exception as e:
        logger.error(f"Ошибка embed_texts (деградация, возвращаем None): {e}")
        return [None] * len(texts)


async def embed_query(text: str) -> Optional[list[float]]:
    """
    Создаёт эмбеддинг для поискового запроса

    Args:
        text: Текст запроса

    Returns:
        Optional[list[float]]: Эмбеддинг или None при ошибке
    """
    if not text or not text.strip():
        return None

    try:
        embeddings = await embed_texts([text.strip()])
        return embeddings[0] if embeddings else None
    except Exception as e:
        logger.error(f"Ошибка создания эмбеддинга для запроса: {e}")
        return None