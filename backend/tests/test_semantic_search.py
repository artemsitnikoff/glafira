"""Тесты семантического поиска кандидатов"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import threading

from app.services.base_search import (
    vector_retrieve,
    reindex_candidate,
    get_embeddings_index_status
)
from app.services.embeddings import (
    build_candidate_text,
    source_hash,
    embed_texts,
    embed_query,
    _get_embedding_model,
    warmup_embedding_model
)
from app.models import Candidate, CandidateSkill, CandidateExperience, CandidateEmbedding


class _FakeVec(list):
    """Имитация numpy-вектора fastembed: код делает embedding.tolist() — у обычного list его нет."""
    def tolist(self):
        return list(self)


# === Тесты сервиса эмбеддингов ===

@pytest.mark.asyncio
async def test_build_candidate_text(test_candidate, db_session):
    """Тест построения текста кандидата"""
    # Добавляем навыки
    skill1 = CandidateSkill(
        candidate_id=test_candidate.id,
        company_id=test_candidate.company_id,
        skill="Python",
        order_index=0
    )
    skill2 = CandidateSkill(
        candidate_id=test_candidate.id,
        company_id=test_candidate.company_id,
        skill="FastAPI",
        order_index=1
    )

    # Добавляем опыт
    exp = CandidateExperience(
        candidate_id=test_candidate.id,
        company_id=test_candidate.company_id,
        position="Senior Python Developer",
        company="Tech Corp",
        description="Разработка микросервисов",
        period="2020-2023",
        order_index=0
    )

    text = build_candidate_text(test_candidate, [skill1, skill2], [exp])

    assert "Python Developer" in text  # last_position кандидата
    assert "Python" in text
    assert "FastAPI" in text
    assert "Senior Python Developer" in text  # position из experience
    assert "микросервисов" in text


def test_source_hash():
    """Тест хеширования текста"""
    text1 = "test text"
    text2 = "test text"
    text3 = "different text"

    hash1 = source_hash(text1)
    hash2 = source_hash(text2)
    hash3 = source_hash(text3)

    assert hash1 == hash2  # Одинаковый текст → одинаковый хеш
    assert hash1 != hash3  # Разный текст → разный хеш
    assert len(hash1) == 64  # SHA256 hex = 64 символа
    assert source_hash("") == ""  # Пустой текст → пустой хеш


@pytest.mark.asyncio
@patch('app.services.embeddings._get_embedding_model')
async def test_embed_texts_success(mock_get_model):
    """Тест успешного создания эмбеддингов"""
    # Мокаем модель
    mock_model = MagicMock()
    mock_model.embed.return_value = [
        _FakeVec([0.1, 0.2, 0.3]),  # Эмбеддинг для "text1"
        _FakeVec([0.4, 0.5, 0.6])   # Эмбеддинг для "text2"
    ]
    mock_get_model.return_value = mock_model

    texts = ["text1", "text2"]
    embeddings = await embed_texts(texts)

    assert len(embeddings) == 2
    assert embeddings[0] == [0.1, 0.2, 0.3]
    assert embeddings[1] == [0.4, 0.5, 0.6]


@pytest.mark.asyncio
@patch('app.services.embeddings._get_embedding_model')
async def test_embed_texts_with_empty_texts(mock_get_model):
    """Тест обработки пустых текстов"""
    from app.services.embeddings import EMBED_DIM

    mock_model = MagicMock()
    # Модель получает ТОЛЬКО валидные тексты → один вектор
    mock_model.embed.return_value = [_FakeVec([0.1, 0.2] + [0.0] * (EMBED_DIM - 2))]
    mock_get_model.return_value = mock_model

    texts = ["", "valid text", "   "]  # Пустой, валидный, только пробелы
    embeddings = await embed_texts(texts)

    assert len(embeddings) == 3
    assert embeddings[0] is None  # Пустой текст → None (НЕ нулевой вектор — не грязним индекс)
    assert len(embeddings[1]) == EMBED_DIM  # Валидный текст → вектор
    assert embeddings[2] is None  # Только пробелы → None


@pytest.mark.asyncio
@patch('app.services.embeddings._get_embedding_model')
async def test_embed_query_success(mock_get_model):
    """Тест успешного создания эмбеддинга запроса"""
    mock_model = MagicMock()
    mock_model.embed.return_value = [_FakeVec([0.1, 0.2, 0.3])]
    mock_get_model.return_value = mock_model

    embedding = await embed_query("test query")

    assert embedding == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
@patch('app.services.embeddings._get_embedding_model')
async def test_embed_query_empty(mock_get_model):
    """Тест обработки пустого запроса"""
    embedding = await embed_query("")
    assert embedding is None

    embedding = await embed_query("   ")
    assert embedding is None


# === Тесты векторного поиска ===

@pytest.mark.asyncio
@patch('app.services.base_search.embed_query')
async def test_vector_retrieve_no_embedding(mock_embed_query, db_session, test_company):
    """Тест векторного поиска когда не удается создать эмбеддинг"""
    mock_embed_query.return_value = None

    result = await vector_retrieve(db_session, test_company.id, "test query")

    assert result == []
    mock_embed_query.assert_called_once_with("test query")


@pytest.mark.asyncio
@patch('app.services.base_search.embed_query')
async def test_vector_retrieve_no_embeddings_in_db(mock_embed_query, db_session, test_company):
    """Тест векторного поиска когда нет эмбеддингов в БД"""
    mock_embed_query.return_value = [0.1, 0.2, 0.3]

    result = await vector_retrieve(db_session, test_company.id, "test query")

    assert result == []


@pytest.mark.asyncio
@patch('app.services.base_search.embed_query')
async def test_vector_retrieve_with_embeddings(mock_embed_query, db_session, test_company, test_candidate):
    """Тест векторного поиска с эмбеддингами"""
    mock_embed_query.return_value = [0.1] * 384  # Правильная размерность

    # Создаём эмбеддинг в БД
    embedding = CandidateEmbedding(
        company_id=test_company.id,
        candidate_id=test_candidate.id,
        embedding=[0.1] * 384,
        source_hash="test_hash"
    )
    db_session.add(embedding)
    await db_session.flush()

    result = await vector_retrieve(db_session, test_company.id, "test query")

    assert len(result) == 1
    assert result[0] == test_candidate.id


# === Тесты изоляции компаний ===

@pytest.mark.asyncio
@patch('app.services.base_search.embed_query')
async def test_company_isolation_in_vector_search(mock_embed_query, db_session):
    """Тест изоляции компаний в векторном поиске"""
    from app.models import Company

    mock_embed_query.return_value = [0.1] * 384

    # Создаём две компании
    company1 = Company(id=uuid4(), name="Company 1")
    company2 = Company(id=uuid4(), name="Company 2")
    db_session.add_all([company1, company2])
    await db_session.flush()

    # Создаём кандидатов в разных компаниях
    candidate1 = Candidate(
        company_id=company1.id,
        first_name="John",
        last_name="Doe",
        source="manual"
    )
    candidate2 = Candidate(
        company_id=company2.id,
        first_name="Jane",
        last_name="Smith",
        source="manual"
    )
    db_session.add_all([candidate1, candidate2])
    await db_session.flush()

    # Создаём эмбеддинги для обоих кандидатов
    embedding1 = CandidateEmbedding(
        company_id=company1.id,
        candidate_id=candidate1.id,
        embedding=[0.1] * 384,
        source_hash="hash1"
    )
    embedding2 = CandidateEmbedding(
        company_id=company2.id,
        candidate_id=candidate2.id,
        embedding=[0.2] * 384,
        source_hash="hash2"
    )
    db_session.add_all([embedding1, embedding2])
    await db_session.flush()

    # Поиск в компании 1 должен вернуть только кандидата 1
    result1 = await vector_retrieve(db_session, company1.id, "test query")
    assert len(result1) == 1
    assert result1[0] == candidate1.id

    # Поиск в компании 2 должен вернуть только кандидата 2
    result2 = await vector_retrieve(db_session, company2.id, "test query")
    assert len(result2) == 1
    assert result2[0] == candidate2.id


# === Тесты индексации ===

@pytest.mark.asyncio
@patch('app.services.base_search.embed_texts')
async def test_reindex_candidate_new_embedding(mock_embed_texts, db_session, test_company, test_candidate):
    """Тест создания нового эмбеддинга при индексации"""
    mock_embed_texts.return_value = [[0.1] * 384]

    # Добавляем навык для построения текста
    skill = CandidateSkill(
        candidate_id=test_candidate.id,
        company_id=test_company.id,
        skill="Python",
        order_index=0
    )
    db_session.add(skill)
    await db_session.flush()

    await reindex_candidate(db_session, test_company.id, test_candidate.id)
    await db_session.flush()

    # Проверяем что эмбеддинг создан
    from sqlalchemy import select
    stmt = select(CandidateEmbedding).where(
        CandidateEmbedding.candidate_id == test_candidate.id
    )
    result = await db_session.execute(stmt)
    embedding = result.scalar_one_or_none()

    assert embedding is not None
    assert embedding.company_id == test_company.id
    assert embedding.candidate_id == test_candidate.id
    assert len(embedding.embedding) == 384


@pytest.mark.asyncio
@patch('app.services.base_search.embed_texts')
async def test_reindex_candidate_skip_unchanged(mock_embed_texts, db_session, test_company, test_candidate):
    """Тест пропуска переиндексации при неизменном хеше"""
    # Создаём существующий эмбеддинг
    existing_hash = "existing_hash"
    embedding = CandidateEmbedding(
        company_id=test_company.id,
        candidate_id=test_candidate.id,
        embedding=[0.5] * 384,
        source_hash=existing_hash
    )
    db_session.add(embedding)
    await db_session.flush()

    # Мокаем embed_texts так чтобы он не должен был вызваться
    mock_embed_texts.return_value = [[0.1] * 384]

    # Мокаем build_candidate_text чтобы вернуть текст с тем же хешом
    with patch('app.services.base_search.build_candidate_text') as mock_build_text, \
         patch('app.services.base_search.source_hash') as mock_hash:

        mock_build_text.return_value = "test text"
        mock_hash.return_value = existing_hash

        await reindex_candidate(db_session, test_company.id, test_candidate.id)

    # embed_texts не должен был вызываться
    mock_embed_texts.assert_not_called()


# === Тесты graceful деградации ===



# === Тест статуса индексации ===

@pytest.mark.asyncio
async def test_get_embeddings_index_status(db_session, test_company, test_candidate):
    """Тест получения статуса индексации"""
    # get_embeddings_index_status считает ТОЛЬКО кандидатов с resume_text → задаём его
    test_candidate.source = "manual"
    test_candidate.resume_text = "Резюме для индексации"
    db_session.add(test_candidate)
    await db_session.commit()

    # Изначально - один кандидат (с резюме), ноль эмбеддингов
    status = await get_embeddings_index_status(db_session, test_company.id)
    assert status["total_candidates"] == 1
    assert status["indexed_candidates"] == 0

    # Добавляем эмбеддинг
    embedding = CandidateEmbedding(
        company_id=test_company.id,
        candidate_id=test_candidate.id,
        embedding=[0.1] * 384,
        source_hash="test_hash"
    )
    db_session.add(embedding)
    await db_session.flush()

    # Теперь один кандидат, один эмбеддинг
    status = await get_embeddings_index_status(db_session, test_company.id)
    assert status["total_candidates"] == 1
    assert status["indexed_candidates"] == 1


# === Тесты single-flight и singleton модели ===

def test_embedding_model_singleton():
    """Тест singleton поведения модели: два последовательных вызова → один инстанс"""
    from app.services.embeddings import _model, _model_lock

    # Очистим глобальное состояние
    import app.services.embeddings
    app.services.embeddings._model = None

    call_count = 0

    def mock_text_embedding(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_instance = MagicMock()
        return mock_instance

    with patch('app.services.embeddings.TextEmbedding', side_effect=mock_text_embedding) as mock_te:
        # Первый вызов
        model1 = _get_embedding_model()
        # Второй вызов
        model2 = _get_embedding_model()

        # TextEmbedding должен быть создан РОВНО один раз
        assert call_count == 1
        assert mock_te.call_count == 1
        # Оба вызова возвращают одну модель
        assert model1 is model2

    # Очистим состояние для других тестов
    app.services.embeddings._model = None


def test_embedding_model_single_flight():
    """Тест single-flight: параллельные потоки грузят модель ОДИН раз"""
    from app.services.embeddings import _model, _model_lock

    # Очистим глобальное состояние
    import app.services.embeddings
    app.services.embeddings._model = None

    call_count = 0
    load_event = threading.Event()

    def slow_text_embedding(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Имитируем медленную загрузку
        load_event.wait()
        mock_instance = MagicMock()
        return mock_instance

    def call_get_model():
        return _get_embedding_model()

    with patch('app.services.embeddings.TextEmbedding', side_effect=slow_text_embedding):
        # Запускаем 3 потока параллельно
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(call_get_model) for _ in range(3)]

            # Разблокируем загрузку после того как все потоки запущены
            load_event.set()

            # Ждем завершения всех потоков
            models = [future.result() for future in futures]

        # TextEmbedding должен быть создан РОВНО один раз (single-flight)
        assert call_count == 1
        # Все потоки получили одну модель
        assert all(model is models[0] for model in models)

    # Очистим состояние для других тестов
    app.services.embeddings._model = None


@pytest.mark.asyncio
@patch('app.services.embeddings.TextEmbedding')
async def test_embed_texts_model_failure(mock_text_embedding):
    """Тест деградации: модель None (сбой загрузки) → возврат [None]*len"""
    # Модель бросает исключение при инициализации
    mock_text_embedding.side_effect = Exception("Model load failed")

    # Очистим глобальное состояние
    import app.services.embeddings
    app.services.embeddings._model = None

    texts = ["text1", "text2", "text3"]
    embeddings = await embed_texts(texts)

    # Должно вернуть [None] * len(texts)
    assert len(embeddings) == 3
    assert all(e is None for e in embeddings)

    # Очистим состояние для других тестов
    app.services.embeddings._model = None


@pytest.mark.asyncio
async def test_warmup_embedding_model():
    """Тест прогрева модели: не бросает при сбое"""
    import app.services.embeddings
    app.services.embeddings._model = None

    with patch('app.services.embeddings._get_embedding_model') as mock_get_model:
        # Успешный прогрев
        mock_get_model.return_value = MagicMock()
        await warmup_embedding_model()
        mock_get_model.assert_called_once()

        # Прогрев со сбоем - не должен бросать исключение
        mock_get_model.reset_mock()
        mock_get_model.side_effect = Exception("Load failed")
        await warmup_embedding_model()  # Не должно бросить исключение
        mock_get_model.assert_called_once()

    # Очистим состояние для других тестов
    app.services.embeddings._model = None


def test_embedding_model_retry_after_failure():
    """Тест повторной попытки после провала загрузки модели"""
    import app.services.embeddings
    app.services.embeddings._model = None

    call_count = 0

    def failing_then_success(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("First load failed")
        return MagicMock()

    with patch('app.services.embeddings.TextEmbedding', side_effect=failing_then_success):
        # Первый вызов - провал
        model1 = _get_embedding_model()
        assert model1 is None

        # Второй вызов - успех
        model2 = _get_embedding_model()
        assert model2 is not None

        # Должно быть 2 попытки загрузки (провал не кэшируется навсегда)
        assert call_count == 2

    # Очистим состояние для других тестов
    app.services.embeddings._model = None