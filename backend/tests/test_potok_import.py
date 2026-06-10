"""Тесты для импорта кандидатов из Potok.io"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.integrations.potok.client import list_applicants
from app.services.integrations.potok.mapper import map_potok_applicant
from app.services.candidate_import import preview_potok_import, _classify_potok_rows
from app.models import Candidate
from app.core.errors import ValidationError, ConflictError


def _patch_potok_http(mock_cls, *, is_success=True, status_code=200, payload=None, content=b""):
    """Настраивает мок httpx.AsyncClient: async with + (await get) + СИНХРОННЫЙ json().

    httpx.Response.json() — синхронный, поэтому объект ответа = MagicMock (не AsyncMock),
    иначе .json() вернёт корутину и тест проверит не то. .get awaitable → AsyncMock.
    """
    resp = MagicMock()
    resp.is_success = is_success
    resp.status_code = status_code
    resp.content = content
    resp.json.return_value = payload if payload is not None else {}

    client_obj = MagicMock()
    client_obj.get = AsyncMock(return_value=resp)

    mock_cls.return_value.__aenter__ = AsyncMock(return_value=client_obj)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return resp


class TestPotokClient:
    """Тесты клиента Potok API (на моках HTTP)"""

    @pytest.mark.asyncio
    async def test_list_applicants_success(self):
        """Успешный запрос к API Potok"""
        mock_response = {
            "data": [
                {"id": 123, "first_name": "Иван", "last_name": "Петров"}
            ],
            "page": 1,
            "per_page": 100,
            "pages": 1
        }

        with patch("app.services.integrations.potok.client.httpx.AsyncClient") as mock_client:
            _patch_potok_http(mock_client, is_success=True, payload=mock_response)

            result = await list_applicants("valid_token", page=1, per_page=100)

            assert result == mock_response
            assert len(result["data"]) == 1
            assert result["data"][0]["id"] == 123

    @pytest.mark.asyncio
    async def test_list_applicants_auth_error(self):
        """Ошибка аутентификации (401)"""
        with patch("app.services.integrations.potok.client.httpx.AsyncClient") as mock_client:
            _patch_potok_http(mock_client, is_success=False, status_code=401,
                              content=b'{"error": "unauthorized"}', payload={"error": "unauthorized"})

            with pytest.raises(ValidationError) as exc_info:
                await list_applicants("invalid_token")

            assert "токен активен" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_list_applicants_subscription_error(self):
        """Ошибка подписки (402) → ConflictError"""
        with patch("app.services.integrations.potok.client.httpx.AsyncClient") as mock_client:
            _patch_potok_http(mock_client, is_success=False, status_code=402,
                              content=b'{"error": "subscription expired"}', payload={"error": "subscription expired"})

            with pytest.raises(ConflictError) as exc_info:
                await list_applicants("valid_token")

            assert "подписка" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_list_applicants_rate_limit(self):
        """Ошибка превышения rate limit (429) — после ретраев поднимается ValidationError"""
        with patch("app.services.integrations.potok.client.httpx.AsyncClient") as mock_client, \
             patch("app.services.integrations.potok.client.asyncio.sleep", new=AsyncMock()):
            _patch_potok_http(mock_client, is_success=False, status_code=429,
                              content=b'{"error": "too many requests"}', payload={"error": "too many requests"})

            with pytest.raises(ValidationError) as exc_info:
                await list_applicants("valid_token")

            assert "лимит запросов" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_list_applicants_empty_token(self):
        """Пустой токен"""
        with pytest.raises(ValidationError) as exc_info:
            await list_applicants("")

        assert "токен" in str(exc_info.value).lower()


class TestPotokMapper:
    """Тесты маппинга данных из Potok"""

    def test_map_potok_applicant_full_data(self):
        """Маппинг полных данных кандидата"""
        potok_data = {
            "id": 12345,
            "first_name": "Иван",
            "last_name": "Петров",
            "middle_name": "Владимирович",
            "email": "ivan@example.com",
            "phones": ["79991234567", "78885554433"],
            "born": "1990-05-15",
            "gender": "male",
            "title": "Python Developer",
            "salary": 150000,
            "city": {"name": "Москва", "text": "Москва"},
            "source_url": "https://potok.io/candidate/123",
            "resumes": [{
                "cv_params": {
                    "about_me": "Опытный разработчик Python",
                    "skills": "Дополнительные навыки",
                    "experience": [
                        {
                            "position": "Senior Developer",
                            "company": "ООО Рога и копыта",
                            "start": "2020-01-15",
                            "end": "2023-12-01",
                            "now": False,
                            "description": "Разработка веб-приложений"
                        }
                    ],
                    "skill_set": ["Python", "Django", "PostgreSQL"],
                    "education": {
                        "primary": [
                            {
                                "name": "МГУ",
                                "organization": "ВМК",
                                "result": "Прикладная математика",
                                "year": "2018"
                            }
                        ]
                    },
                    "languages": [
                        {"name": "Английский", "level": {"name": "B2"}},
                        {"name": "Немецкий", "level": {"name": "A1"}}
                    ]
                }
            }]
        }

        result = map_potok_applicant(potok_data)

        assert result["first_name"] == "Иван"
        assert result["last_name"] == "Петров"
        assert result["middle_name"] == "Владимирович"
        assert result["phone"] == "+79991234567"
        assert result["email"] == "ivan@example.com"
        assert result["city"] == "Москва"
        assert result["gender"] == "male"
        assert result["salary_expectation"] == 150000
        assert result["last_position"] == "Python Developer"
        assert result["external_id"] == "12345"

        # Проверяем опыт
        assert len(result["experience"]) == 1
        exp = result["experience"][0]
        assert exp["position"] == "Senior Developer"
        assert exp["company"] == "ООО Рога и копыта"
        assert "2020-01" in exp["period"]
        assert "2023-12" in exp["period"]

        # Проверяем навыки
        assert len(result["skills"]) == 3
        skills = [s["skill"] for s in result["skills"]]
        assert "Python" in skills
        assert "Django" in skills

        # Проверяем образование
        assert len(result["education"]) == 1
        edu = result["education"][0]
        assert edu["institution"] == "МГУ"
        # specialty маппится из result (специализация), не из organization (факультет) — см. mapper
        assert edu["specialty"] == "Прикладная математика"

        # Проверяем языки
        assert len(result["languages"]) == 2
        assert "Английский — B2" in result["languages"]

    def test_map_potok_applicant_minimal_data(self):
        """Маппинг минимальных данных (толерантность к пропускам)"""
        potok_data = {
            "id": 999,
            "first_name": "Анна"
            # Остальные поля отсутствуют
        }

        result = map_potok_applicant(potok_data)

        assert result["first_name"] == "Анна"
        assert result["last_name"] == ""
        assert result["phone"] is None
        assert result["email"] is None
        assert result["experience"] == []
        assert result["skills"] == []
        assert result["education"] == []
        assert result["external_id"] == "999"

    def test_map_potok_applicant_salary_object(self):
        """Маппинг зарплаты в формате объекта"""
        potok_data = {
            "id": 1,
            "first_name": "Тест",
            "salary": {"amount": "80000", "currency": "RUR"}
        }

        result = map_potok_applicant(potok_data)
        assert result["salary_expectation"] == 80000

    def test_map_potok_applicant_salary_number(self):
        """Маппинг зарплаты в формате числа"""
        potok_data = {
            "id": 1,
            "first_name": "Тест",
            "salary": 90000
        }

        result = map_potok_applicant(potok_data)
        assert result["salary_expectation"] == 90000

    def test_map_potok_applicant_invalid_salary(self):
        """Невалидная зарплата игнорируется"""
        potok_data = {
            "id": 1,
            "first_name": "Тест",
            "salary": "invalid"
        }

        result = map_potok_applicant(potok_data)
        assert result["salary_expectation"] is None


class TestPotokClassification:
    """Тесты классификации кандидатов Potok"""

    def test_classify_potok_rows_new_candidates(self):
        """Классификация новых кандидатов"""
        candidates = [
            {
                "first_name": "Иван",
                "last_name": "Петров",
                "phone": "+79991234567",
                "email": "ivan@example.com"
            },
            {
                "first_name": "Анна",
                "last_name": "Сидорова",
                "phone": "+79997654321",
                "email": "anna@example.com"
            }
        ]

        existing = []  # Пустая база

        result = _classify_potok_rows(candidates, existing)

        assert len(result) == 2
        assert all(row["status"] == "new" for row in result)
        assert result[0]["name"] == "Иван Петров"
        assert result[1]["name"] == "Анна Сидорова"

    def test_classify_potok_rows_duplicates(self):
        """Классификация дублей"""
        candidates = [
            {
                "first_name": "Иван",
                "last_name": "Петров",
                "phone": "+79991234567",
                "email": "ivan@example.com"
            }
        ]

        # Существующий кандидат с таким же телефоном
        existing = [
            Candidate(
                id=uuid4(),
                first_name="Иван",
                last_name="Петров",
                phone="+79991234567",
                email="other@example.com"
            )
        ]

        result = _classify_potok_rows(candidates, existing)

        assert len(result) == 1
        assert result[0]["status"] == "duplicate"

    def test_classify_potok_rows_errors(self):
        """Классификация ошибок (нет имени/контакта)"""
        candidates = [
            {
                "first_name": "",
                "last_name": "",
                "phone": "",
                "email": ""
            },
            {
                "first_name": "Иван",
                "last_name": "Петров",
                "phone": "",
                "email": ""
            }
        ]

        result = _classify_potok_rows(candidates, [])

        assert len(result) == 2
        assert all(row["status"] == "error" for row in result)
        assert result[0]["error"] == "нет имени"
        assert result[1]["error"] == "нет контакта"

    def test_classify_potok_rows_within_request_duplicates(self):
        """Внутренние дубли в одном запросе"""
        candidates = [
            {
                "first_name": "Иван",
                "last_name": "Петров",
                "phone": "+79991234567",
                "email": "ivan@example.com"
            },
            {
                "first_name": "Иван",
                "last_name": "Петров",
                "phone": "+79991234567",  # тот же телефон
                "email": "other@example.com"
            }
        ]

        result = _classify_potok_rows(candidates, [])

        assert len(result) == 2
        assert result[0]["status"] == "new"
        assert result[1]["status"] == "duplicate"  # внутренний дубль


class TestPotokIntegration:
    """Интеграционные тесты импорта Potok (на моках)"""

    @pytest.mark.asyncio
    async def test_preview_potok_import_success(self, db_session, admin_user):
        """
        ЧЕСТНО помечено: реальный API пинится заказчиком.
        Тест на моке HTTP показывает работу логики превью.
        """
        company_id = admin_user.company_id
        mock_response = {
            "data": [
                {
                    "id": 123,
                    "first_name": "Иван",
                    "last_name": "Петров",
                    "email": "ivan@potok.test",
                    "phones": ["79991234567"]
                }
            ],
            "page": 1,
            "pages": 1,
            "per_page": 100
        }

        with patch("app.services.candidate_import.list_applicants") as mock_api:
            mock_api.return_value = mock_response

            result = await preview_potok_import(db_session, company_id, "test_token", "skip")

            assert result["summary"]["total"] == 1
            assert result["summary"]["new"] == 1
            assert result["summary"]["duplicates"] == 0
            assert result["summary"]["errors"] == 0
            assert len(result["rows"]) == 1
            assert result["rows"][0]["name"] == "Иван Петров"
            assert result["rows"][0]["source"] == "potok"

    @pytest.mark.asyncio
    async def test_preview_potok_import_api_error(self, db_session, admin_user):
        """Ошибка API передается корректно"""
        company_id = admin_user.company_id
        with patch("app.services.candidate_import.list_applicants") as mock_api:
            mock_api.side_effect = ValidationError("Невалидный токен")

            with pytest.raises(ValidationError):
                await preview_potok_import(db_session, admin_user.company_id, "bad_token", "skip")