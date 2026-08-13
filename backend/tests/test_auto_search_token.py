"""Проброс user_id инициатора в денежные/квотные пути Автоподбора + смежный smart-путь.

Фаза 2/3 персональных hh-токенов: интерактивные операции рекрутёра идут под ЕГО
токеном (личная квота просмотров / атрибуция). Здесь проверяем, что user_id реально
доходит до селектора/каскада токена в:
- get_auto_candidate_detail (просмотр резюме → каскад квоты),
- score_auto_candidate (точечная оценка, тоже просмотр → каскад),
- take_auto_contact (ПЛАТНОЕ открытие контакта → get_hh_token_for_user, БЕЗ каскада),
- smart_search.check_access (общий гейт умного подбора).

Всё offline — сеть/LLM замоканы; проверяем ТОЛЬКО маршрутизацию user_id.
"""

from contextlib import asynccontextmanager

import pytest
from unittest.mock import AsyncMock, patch

from app.models import AutoSearch
from app.services.auto_search import (
    get_auto_candidate_detail,
    score_auto_candidate,
    take_auto_contact,
)

_AUTO = "app.services.auto_search"
_HHSVC = "app.services.integrations.hh.service"


def _session_local_returning(db_session):
    """Фабрика-заглушка вместо AsyncSessionLocal(): отдаёт тестовый db_session
    (паттерн из test_smart_take — не открываем реальное соединение к прод-БД)."""
    @asynccontextmanager
    async def _factory():
        yield db_session
    return _factory


async def _make_auto_search(db_session, company_id, *, basis=None) -> AutoSearch:
    row = AutoSearch(
        company_id=company_id,
        hh_saved_search_id="ss_1",
        name="Автопоиск №1",
        basis=basis,
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# 1. get_auto_candidate_detail → каскад получает user_id инициатора
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detail_passes_user_id_to_cascade(db_session, admin_user):
    resume = {"id": "r1", "title": "Разработчик"}  # .get()/or-safe маппинг

    with patch(f"{_AUTO}.check_access", new_callable=AsyncMock, return_value=(True, True, None)), \
         patch(f"{_HHSVC}.view_resume_with_cascade", new_callable=AsyncMock, return_value=resume) as m_casc:
        await get_auto_candidate_detail(
            db_session, admin_user.company_id, "r1", user_id=admin_user.id
        )

    assert m_casc.await_count == 1
    assert m_casc.await_args.kwargs["user_id"] == admin_user.id
    assert m_casc.await_args.kwargs["company_id"] == admin_user.company_id
    assert m_casc.await_args.kwargs["resume_id"] == "r1"


# ---------------------------------------------------------------------------
# 2. score_auto_candidate → каскад получает user_id инициатора
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_passes_user_id_to_cascade(db_session, admin_user):
    auto = await _make_auto_search(
        db_session, admin_user.company_id, basis={"kind": "prompt", "text": "dev"}
    )
    resume = {"id": "r7", "title": "Дев"}
    score = {"score": 80, "verdict": "yes", "summary": "ок"}

    with patch(f"{_AUTO}.check_access", new_callable=AsyncMock, return_value=(True, True, None)), \
         patch(f"{_AUTO}.get_company_openrouter_key", new_callable=AsyncMock, return_value="k"), \
         patch(f"{_AUTO}.get_company_llm_model", new_callable=AsyncMock, return_value="m"), \
         patch(f"{_AUTO}._basis_to_vacancy_proxy", new_callable=AsyncMock, return_value=object()), \
         patch(f"{_AUTO}.score_resume_dict", new_callable=AsyncMock, return_value=score), \
         patch(f"{_HHSVC}.view_resume_with_cascade", new_callable=AsyncMock, return_value=resume) as m_casc:
        await score_auto_candidate(
            db_session, admin_user.company_id, auto.id, "r7", user_id=admin_user.id
        )

    assert m_casc.await_count == 1
    assert m_casc.await_args.kwargs["user_id"] == admin_user.id
    assert m_casc.await_args.kwargs["company_id"] == admin_user.company_id
    assert m_casc.await_args.kwargs["resume_id"] == "r7"


# ---------------------------------------------------------------------------
# 3. take_auto_contact (ПЛАТНО) → селектор токена получает actor_user_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_take_passes_user_id_to_selector(db_session, admin_user):
    auto = await _make_auto_search(db_session, admin_user.company_id)

    with patch(f"{_AUTO}.check_access", new_callable=AsyncMock, return_value=(True, True, None)), \
         patch(f"{_AUTO}._auto_pool_left", new_callable=AsyncMock, return_value=None), \
         patch(f"{_AUTO}.AsyncSessionLocal", _session_local_returning(db_session)), \
         patch(f"{_HHSVC}.get_hh_token_for_user", new_callable=AsyncMock, return_value="tok") as m_tok:
        # resume_ids=[] — сетевой цикл не выполняется; нам важна только маршрутизация токена.
        await take_auto_contact(
            db_session, admin_user.company_id, admin_user.id, auto.id, [], target="pool"
        )

    assert m_tok.await_count == 1
    assert m_tok.await_args.kwargs["user_id"] == admin_user.id
    assert m_tok.await_args.kwargs["company_id"] == admin_user.company_id


# ---------------------------------------------------------------------------
# 4. smart_search.check_access → селектор токена получает user_id (смежный smart-путь)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_access_forwards_user_id_to_selector(db_session, admin_user):
    from app.services.smart_search import check_access

    with patch(f"{_HHSVC}.get_hh_token_for_user", new_callable=AsyncMock, return_value="tok") as m_tok, \
         patch("app.services.smart_search.hh_client.get_me", new_callable=AsyncMock,
               return_value={"employer": {"id": "555"}}), \
         patch("app.services.smart_search.hh_client.get_payable_api_actions", new_callable=AsyncMock,
               return_value={}):
        await check_access(db_session, admin_user.company_id, admin_user.id)

    assert m_tok.await_count == 1
    assert m_tok.await_args.kwargs["user_id"] == admin_user.id
    assert m_tok.await_args.kwargs["company_id"] == admin_user.company_id
