"""Тесты экспорта резюме умного подбора (hh) с AI-разбором Глафиры.

Проверяет:
- build_resume_pdf/docx с ai_analysis=None (обратная совместимость)
- build_resume_pdf/docx с ai_analysis (секция «Разбор Глафиры» добавляется)
- requirements_match как list[dict] не роняет рендер
- GET /smart/runs/{run_id}/candidates/{hh_resume_id}/resume — 200 + непустые bytes
- 404 на неизвестный hh_resume_id
- 404 на чужой run (company_id не совпадает)
- manager-доступ запрещён (403)
- неверный формат — 400
"""

import io
import pytest
import types
from uuid import uuid4

from app.services.resume_export import build_resume_pdf, build_resume_docx
from app.models.smart_search import SmartSearchRun
from app.models import Company


# ---------------------------------------------------------------------------
# Вспомогательная функция — минимальный shim-кандидат для рендера
# ---------------------------------------------------------------------------

def _make_shim(
    first_name="Иван",
    last_name="Тестов",
    city="Москва",
    skills=None,
    experience=None,
):
    return types.SimpleNamespace(
        first_name=first_name,
        last_name=last_name,
        middle_name=None,
        gender=None,
        phone=None,
        email=None,
        city=city,
        region=None,
        last_position="Python Developer",
        salary_expectation=None,
        currency="RUB",
        extra={},
        resume_summary=None,
        experience=experience or [
            types.SimpleNamespace(
                period="2020–2024",
                company="Tech Corp",
                position="Python Developer",
                description="Разработка API",
            )
        ],
        skills=[types.SimpleNamespace(skill=s) for s in (skills or ["Python", "FastAPI"])],
        education=[],
    )


_AI_ANALYSIS = {
    "score": 87,
    "verdict": "good",
    "summary": "Отличный кандидат с глубоким Python-опытом.",
    "strengths": ["Опыт FastAPI", "Умение работать в команде"],
    "risks": ["Нет опыта с Kubernetes"],
    "requirements_match": [
        "Python 5+ лет",
        {"requirement": "FastAPI", "matched": True, "comment": "Есть в резюме"},
    ],
    "forecast": "Высокая вероятность успешного найма.",
}


# ---------------------------------------------------------------------------
# Тесты build_resume_pdf / build_resume_docx (unit)
# ---------------------------------------------------------------------------

class TestBuildResumeWithAI:
    """Unit-тесты генераторов PDF/DOCX с ai_analysis."""

    def test_pdf_without_ai_analysis_backward_compat(self, test_company):
        """build_resume_pdf без ai_analysis работает как раньше."""
        shim = _make_shim()
        content = build_resume_pdf(shim)
        assert isinstance(content, bytes)
        assert len(content) > 0
        assert content.startswith(b"%PDF")

    def test_docx_without_ai_analysis_backward_compat(self, test_company):
        """build_resume_docx без ai_analysis работает как раньше."""
        shim = _make_shim()
        content = build_resume_docx(shim)
        assert isinstance(content, bytes)
        assert len(content) > 0
        assert content.startswith(b"PK")

    def test_pdf_with_ai_analysis_is_nonempty(self, test_company):
        """build_resume_pdf с ai_analysis — непустой PDF."""
        shim = _make_shim()
        content = build_resume_pdf(shim, ai_analysis=_AI_ANALYSIS)
        assert isinstance(content, bytes)
        assert len(content) > 0
        assert content.startswith(b"%PDF")

    def test_pdf_with_ai_analysis_larger_than_without(self, test_company):
        """PDF с AI-секцией должен быть больше PDF без неё."""
        shim = _make_shim()
        content_no_ai = build_resume_pdf(shim)
        content_with_ai = build_resume_pdf(shim, ai_analysis=_AI_ANALYSIS)
        assert len(content_with_ai) > len(content_no_ai)

    def test_docx_with_ai_analysis_contains_section_header(self, test_company):
        """DOCX с AI-секцией содержит слова «Разбор Глафиры»."""
        from docx import Document
        shim = _make_shim()
        content = build_resume_docx(shim, ai_analysis=_AI_ANALYSIS)
        assert isinstance(content, bytes)
        assert len(content) > 0
        # Парсим DOCX и ищем текст секции
        doc = Document(io.BytesIO(content))
        all_text = " ".join(p.text for p in doc.paragraphs)
        assert "Разбор Глафиры" in all_text
        assert "87/100" in all_text
        assert "рекомендуется" in all_text

    def test_docx_requirements_match_dict_does_not_crash(self, test_company):
        """requirements_match как list[dict] не роняет рендер DOCX."""
        shim = _make_shim()
        ai = {
            "score": 70,
            "verdict": "partial",
            "summary": "",
            "strengths": [],
            "risks": [],
            "requirements_match": [
                {"requirement": "Python", "matched": True, "comment": "Опыт 5 лет"},
                {"requirement": "Go", "matched": False, "comment": "Нет опыта"},
            ],
            "forecast": "",
        }
        content = build_resume_docx(shim, ai_analysis=ai)
        assert isinstance(content, bytes)
        assert len(content) > 0

    def test_pdf_requirements_match_dict_does_not_crash(self, test_company):
        """requirements_match как list[dict] не роняет рендер PDF."""
        shim = _make_shim()
        ai = {
            "score": 55,
            "verdict": "bad",
            "summary": "Слабый кандидат",
            "strengths": [],
            "risks": ["Нет нужного опыта"],
            "requirements_match": [
                {"requirement": "Java", "matched": False, "comment": ""},
            ],
            "forecast": "Мало шансов.",
        }
        content = build_resume_pdf(shim, ai_analysis=ai)
        assert isinstance(content, bytes)
        assert content.startswith(b"%PDF")

    def test_pdf_ai_analysis_none_fields_skipped(self, test_company):
        """Пустые поля ai_analysis не роняют рендер — просто пропускаются."""
        shim = _make_shim()
        ai = {
            "score": None,
            "verdict": "",
            "summary": "",
            "strengths": [],
            "risks": [],
            "requirements_match": [],
            "forecast": "",
        }
        content = build_resume_pdf(shim, ai_analysis=ai)
        assert isinstance(content, bytes)
        assert content.startswith(b"%PDF")


# ---------------------------------------------------------------------------
# Тесты эндпоинта GET /smart/runs/{run_id}/candidates/{hh_resume_id}/resume
# ---------------------------------------------------------------------------

class TestSmartResumeExportEndpoint:
    """Тесты HTTP-эндпоинта экспорта резюме умного подбора."""

    # Фикстура: SmartSearchRun со scored_candidates
    @pytest.fixture
    async def smart_run_with_candidates(self, db_session, test_company, test_vacancy):
        """Создаёт SmartSearchRun с двумя scored_candidates в БД."""
        run = SmartSearchRun(
            company_id=test_company.id,
            vacancy_id=test_vacancy.id,
            status="done",
            stage="done",
            params={"scan_n": 10},
            scored_candidates=[
                {
                    "hh_resume_id": "hh_abc123",
                    "name": "Иванов Иван Иванович",
                    "age": 30,
                    "city": "Москва",
                    "score": 87,
                    "verdict": "good",
                    "summary": "Отличный кандидат",
                    "strengths": ["Python", "FastAPI"],
                    "risks": ["Нет Docker"],
                    "requirements_match": [
                        "Python 5+ лет",
                        {"requirement": "FastAPI", "matched": True, "comment": "Есть"},
                    ],
                    "forecast": "Высокие шансы.",
                    "resume": {
                        "experience": [
                            {
                                "position": "Python Developer",
                                "company": "Tech Corp",
                                "period": "2020–2024",
                                "description": "Разработка API",
                            }
                        ],
                        "skills": ["Python", "FastAPI", "PostgreSQL"],
                        "salary": "200 000 ₽",
                    },
                },
                {
                    "hh_resume_id": "hh_xyz456",
                    "name": "Петрова",
                    "city": "Санкт-Петербург",
                    "score": 55,
                    "verdict": "partial",
                    "summary": "",
                    "strengths": [],
                    "risks": [],
                    "requirements_match": [],
                    "forecast": "",
                    "resume": {
                        "experience": [],
                        "skills": [],
                        "salary": "",
                    },
                },
            ],
        )
        db_session.add(run)
        await db_session.commit()
        return run

    async def test_export_smart_resume_pdf_200(
        self, async_client, auth_headers, smart_run_with_candidates
    ):
        """200 + непустые bytes PDF для известного hh_resume_id."""
        run = smart_run_with_candidates
        response = await async_client.get(
            f"/api/v1/smart/runs/{run.id}/candidates/hh_abc123/resume?format=pdf",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]
        assert len(response.content) > 0
        assert response.content.startswith(b"%PDF")

    async def test_export_smart_resume_docx_200(
        self, async_client, auth_headers, smart_run_with_candidates
    ):
        """200 + непустые bytes DOCX для известного hh_resume_id."""
        run = smart_run_with_candidates
        response = await async_client.get(
            f"/api/v1/smart/runs/{run.id}/candidates/hh_abc123/resume?format=docx",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert "wordprocessingml" in response.headers["content-type"]
        assert len(response.content) > 0
        assert response.content.startswith(b"PK")

    async def test_export_smart_resume_filename_has_glafira_suffix(
        self, async_client, auth_headers, smart_run_with_candidates
    ):
        """Content-Disposition содержит «Глафира» в имени файла."""
        run = smart_run_with_candidates
        response = await async_client.get(
            f"/api/v1/smart/runs/{run.id}/candidates/hh_abc123/resume?format=pdf",
            headers=auth_headers,
        )
        assert response.status_code == 200
        cd = response.headers.get("content-disposition", "")
        assert "filename*=UTF-8''" in cd
        # URL-encoded «Глафира» = %D0%93%D0%BB%D0%B0%D1%84%D0%B8%D1%80%D0%B0
        assert "%D0%93%D0%BB%D0%B0%D1%84%D0%B8%D1%80%D0%B0" in cd

    async def test_export_smart_resume_404_unknown_hh_resume_id(
        self, async_client, auth_headers, smart_run_with_candidates
    ):
        """404 при несуществующем hh_resume_id."""
        run = smart_run_with_candidates
        response = await async_client.get(
            f"/api/v1/smart/runs/{run.id}/candidates/NONEXISTENT/resume?format=pdf",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_export_smart_resume_404_unknown_run_id(
        self, async_client, auth_headers
    ):
        """404 при несуществующем run_id."""
        response = await async_client.get(
            f"/api/v1/smart/runs/{uuid4()}/candidates/hh_abc123/resume?format=pdf",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_export_smart_resume_404_wrong_company(
        self, async_client, auth_headers, test_vacancy, db_session
    ):
        """404 при run из другой компании (company_id не совпадает)."""
        other_company = Company(name="Чужая компания (smart export)")
        db_session.add(other_company)
        await db_session.flush()

        other_run = SmartSearchRun(
            company_id=other_company.id,
            vacancy_id=test_vacancy.id,
            status="done",
            stage="done",
            params={},
            scored_candidates=[
                {
                    "hh_resume_id": "hh_other",
                    "name": "Чужой Кандидат",
                    "city": "",
                    "score": 50,
                    "verdict": "partial",
                    "summary": "",
                    "strengths": [],
                    "risks": [],
                    "requirements_match": [],
                    "forecast": "",
                    "resume": {"experience": [], "skills": [], "salary": ""},
                }
            ],
        )
        db_session.add(other_run)
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/smart/runs/{other_run.id}/candidates/hh_other/resume?format=pdf",
            headers=auth_headers,
        )
        # Наш пользователь не видит чужой run → 404
        assert response.status_code == 404

    async def test_export_smart_resume_manager_forbidden(
        self, async_client, manager_headers, smart_run_with_candidates
    ):
        """403 для роли manager."""
        run = smart_run_with_candidates
        response = await async_client.get(
            f"/api/v1/smart/runs/{run.id}/candidates/hh_abc123/resume?format=pdf",
            headers=manager_headers,
        )
        assert response.status_code == 403

    async def test_export_smart_resume_invalid_format(
        self, async_client, auth_headers, smart_run_with_candidates
    ):
        """400 при неверном формате."""
        run = smart_run_with_candidates
        response = await async_client.get(
            f"/api/v1/smart/runs/{run.id}/candidates/hh_abc123/resume?format=txt",
            headers=auth_headers,
        )
        assert response.status_code == 400

    async def test_export_smart_resume_requirements_match_dict_no_crash(
        self, async_client, auth_headers, smart_run_with_candidates
    ):
        """requirements_match как list[dict] в scored_candidates не роняет эндпоинт."""
        run = smart_run_with_candidates
        # hh_abc123 уже имеет dict в requirements_match — проверяем 200
        response = await async_client.get(
            f"/api/v1/smart/runs/{run.id}/candidates/hh_abc123/resume?format=pdf",
            headers=auth_headers,
        )
        assert response.status_code == 200

    async def test_export_smart_resume_single_token_name(
        self, async_client, auth_headers, smart_run_with_candidates
    ):
        """Кандидат с однотокенным именем (Петрова) — 200, файл непуст."""
        run = smart_run_with_candidates
        response = await async_client.get(
            f"/api/v1/smart/runs/{run.id}/candidates/hh_xyz456/resume?format=docx",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert len(response.content) > 0
