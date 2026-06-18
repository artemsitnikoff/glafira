"""Тесты для импорта кандидатов из Potok.io"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.integrations.potok.client import get_all_applicants, list_applicants, preview_applicants, iter_applicants
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
    async def test_preview_applicants_success(self):
        """Быстрый превью кандидатов"""
        with patch("app.services.integrations.potok.client.httpx.AsyncClient") as mock_client_class:
            # Mock для preview API
            mock_client = MagicMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            preview_response = MagicMock()
            preview_response.is_success = True
            preview_response.json.return_value = {
                "data": [
                    {
                        "id": 123,
                        "first_name": "Иван",
                        "last_name": "Петров",
                        "cv_params": {"about_me": "Тестовое резюме"}
                    }
                ],
                "pages": 157,  # ~15,700 кандидатов total
                "per_page": 100
            }

            mock_client.get = AsyncMock(return_value=preview_response)

            estimated_total, sample_data = await preview_applicants("valid_token", sample=50)

            assert estimated_total == 15700  # 157 * 100
            # preview_applicants делает репрезентативный сэмпл: стр.1 + середина + конец
            # (max_page=157, доп страницы: {78, 157}); мок отдаёт тот же ответ [id=123] трижды
            assert len(sample_data) == 3
            assert sample_data[0]["id"] == 123

    @pytest.mark.asyncio
    async def test_get_all_applicants_hybrid_success(self):
        """HYBRID запрос всех кандидатов: Phase 1 (список) + Phase 2 (jobs → detail)"""
        with patch("app.services.integrations.potok.client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Phase 1: /api/v3/applicants.json responses
            list_response_page1 = MagicMock()
            list_response_page1.is_success = True
            list_response_page1.status_code = 200
            list_response_page1.json.return_value = {
                "data": [
                    {"id": 100, "first_name": "Фаза1", "last_name": "Кандидат1"},
                    {"id": 101, "first_name": "Фаза1", "last_name": "Кандидат2"}
                ]
            }

            list_response_page2 = MagicMock()
            list_response_page2.is_success = True
            list_response_page2.status_code = 200
            list_response_page2.json.return_value = {"data": []}  # Пустая страница = конец Phase 1

            # Phase 2: jobs
            jobs_response = MagicMock()
            jobs_response.is_success = True
            jobs_response.json.return_value = {
                "objects": {"jobs": [{"id": 500}]},
                "has_next_page": False
            }

            # ajs_joins
            ajs_joins_response = MagicMock()
            ajs_joins_response.is_success = True
            ajs_joins_response.json.return_value = {
                "objects": [
                    {"applicant_id": 100},  # уже есть в Phase 1
                    {"applicant_id": 200}   # новый для Phase 2
                ],
                "has_next_page": False
            }

            # Detail fetch remainder
            applicant_detail_response = MagicMock()
            applicant_detail_response.is_success = True
            applicant_detail_response.status_code = 200
            applicant_detail_response.json.return_value = {
                "id": 200,
                "first_name": "Фаза2",
                "last_name": "Кандидат3"
            }

            # Настраиваем последовательность вызовов
            mock_client.get = AsyncMock()
            mock_client.get.side_effect = [
                # Phase 1: список
                list_response_page1,  # page=1
                list_response_page2,  # page=2, пустая → конец Phase 1
                # Phase 2: jobs
                jobs_response,  # active jobs
                jobs_response,  # archived jobs (тот же)
                ajs_joins_response,  # job 500 ajs_joins
                applicant_detail_response,  # detail fetch applicant_id=200
            ]

            result = await get_all_applicants("valid_token")

            assert len(result) == 3  # 2 из Phase 1 + 1 из Phase 2
            ids = [r["id"] for r in result]
            assert 100 in ids
            assert 101 in ids
            assert 200 in ids

    @pytest.mark.asyncio
    async def test_get_all_applicants_phase1_422_cap(self):
        """Test 422 page limit error в Phase 1 → переход к Phase 2"""
        with patch("app.services.integrations.potok.client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Page 1 успешная
            list_response_page1 = MagicMock()
            list_response_page1.is_success = True
            list_response_page1.status_code = 200
            list_response_page1.json.return_value = {
                "data": [{"id": 100, "first_name": "Тест"}]
            }

            # Page 100 → 422 page limit
            list_response_422 = MagicMock()
            list_response_422.is_success = False
            list_response_422.status_code = 422
            list_response_422.content = b'{"errors":{"page":["page limit exceeded"]}}'
            list_response_422.json.return_value = {
                "errors": {"page": ["page limit exceeded"]}
            }

            # Mock Phase 2 (пустой для простоты)
            empty_jobs_response = MagicMock()
            empty_jobs_response.is_success = True
            empty_jobs_response.json.return_value = {
                "objects": {"jobs": []},
                "has_next_page": False
            }

            mock_client.get = AsyncMock()
            mock_client.get.side_effect = [
                list_response_page1,  # page=1 успех
                list_response_422,    # page=2 → 422, должен graceful break
                empty_jobs_response,  # active jobs (пустой)
                empty_jobs_response,  # archived jobs (пустой)
            ]

            result = await get_all_applicants("valid_token")

            assert len(result) == 1  # только из Phase 1
            assert result[0]["id"] == 100

    @pytest.mark.asyncio
    async def test_list_applicants_legacy_compatibility(self):
        """Legacy list_applicants использует новый API под капотом"""
        with patch("app.services.integrations.potok.client.get_all_applicants") as mock_get_all:
            mock_get_all.return_value = [
                {"id": 123, "first_name": "Иван", "last_name": "Петров"}
            ]

            result = await list_applicants("valid_token", page=1, per_page=100)

            assert "data" in result
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

    @pytest.mark.asyncio
    async def test_iter_applicants_streaming(self):
        """Тест стримингового генератора кандидатов"""
        with patch("app.services.integrations.potok.client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Phase 1: две страницы
            list_response_page1 = MagicMock()
            list_response_page1.is_success = True
            list_response_page1.status_code = 200
            list_response_page1.json.return_value = {
                "data": [
                    {"id": 100, "first_name": "Batch1", "last_name": "User1"},
                    {"id": 101, "first_name": "Batch1", "last_name": "User2"}
                ],
                "pages": 2,
                "per_page": 2
            }

            list_response_page2 = MagicMock()
            list_response_page2.is_success = True
            list_response_page2.status_code = 200
            list_response_page2.json.return_value = {"data": []}  # Конец Phase 1

            # Phase 2: пустой для простоты
            empty_jobs_response = MagicMock()
            empty_jobs_response.is_success = True
            empty_jobs_response.json.return_value = {
                "objects": {"jobs": []},
                "has_next_page": False
            }

            mock_client.get = AsyncMock()
            mock_client.get.side_effect = [
                list_response_page1,  # page=1
                list_response_page2,  # page=2, empty
                empty_jobs_response,  # active jobs
                empty_jobs_response,  # archived jobs
            ]

            # Собираем все батчи
            all_batches = []
            async for batch in iter_applicants("valid_token"):
                all_batches.append(batch)

            assert len(all_batches) == 1  # Один батч из Phase 1
            assert len(all_batches[0]) == 2  # Два кандидата в батче
            assert all_batches[0][0]["id"] == 100
            assert all_batches[0][1]["id"] == 101

    @pytest.mark.asyncio
    async def test_iter_applicants_422_page_limit_graceful(self):
        """Тест graceful обработки 422 page limit"""
        with patch("app.services.integrations.potok.client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Page 1 успешная
            list_response_page1 = MagicMock()
            list_response_page1.is_success = True
            list_response_page1.status_code = 200
            list_response_page1.json.return_value = {
                "data": [{"id": 100, "first_name": "Success"}],
                "pages": 200,
                "per_page": 100
            }

            # Page 2 → 422 page limit
            list_response_422 = MagicMock()
            list_response_422.is_success = False
            list_response_422.status_code = 422
            list_response_422.content = b'{"errors":{"page":["page limit"]}}'
            list_response_422.json.return_value = {"errors": {"page": ["page limit"]}}

            # Empty Phase 2
            empty_jobs_response = MagicMock()
            empty_jobs_response.is_success = True
            empty_jobs_response.json.return_value = {
                "objects": {"jobs": []},
                "has_next_page": False
            }

            mock_client.get = AsyncMock()
            mock_client.get.side_effect = [
                list_response_page1,
                list_response_422,  # Должно graceful break, не raise
                empty_jobs_response,
                empty_jobs_response,
            ]

            batches = []
            async for batch in iter_applicants("valid_token"):
                batches.append(batch)

            # Должны получить только успешную страницу 1
            assert len(batches) == 1
            assert len(batches[0]) == 1
            assert batches[0][0]["id"] == 100

    @pytest.mark.asyncio
    async def test_iter_applicants_timeout_continue(self):
        """Тест продолжения работы при таймауте одной страницы"""
        with patch("app.services.integrations.potok.client.httpx.AsyncClient") as mock_client_class:
            import httpx

            mock_client = MagicMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Page 1 успешная
            success_response = MagicMock()
            success_response.is_success = True
            success_response.status_code = 200
            success_response.json.return_value = {
                "data": [{"id": 100, "first_name": "Success"}],
                "pages": 3,
                "per_page": 1
            }

            # Page 3 успешная после таймаута на page 2
            success_response2 = MagicMock()
            success_response2.is_success = True
            success_response2.status_code = 200
            success_response2.json.return_value = {
                "data": [{"id": 102, "first_name": "AfterTimeout"}]
            }

            # Empty end
            empty_response = MagicMock()
            empty_response.is_success = True
            empty_response.status_code = 200
            empty_response.json.return_value = {"data": []}

            # Empty Phase 2
            empty_jobs_response = MagicMock()
            empty_jobs_response.is_success = True
            empty_jobs_response.json.return_value = {
                "objects": {"jobs": []},
                "has_next_page": False
            }

            # Настраиваем side_effect с таймаутом на page 2
            mock_client.get = AsyncMock()
            mock_client.get.side_effect = [
                success_response,           # page=1 success
                httpx.TimeoutException("timeout on page 2"),  # page=2 timeout
                httpx.TimeoutException("timeout retry 1"),    # page=2 retry 1
                httpx.TimeoutException("timeout retry 2"),    # page=2 retry 2
                success_response2,          # page=3 success
                empty_response,             # page=4 empty
                empty_jobs_response,        # active jobs
                empty_jobs_response,        # archived jobs
            ]

            batches = []
            async for batch in iter_applicants("valid_token"):
                batches.append(batch)

            # Должны получить page 1 и page 3 (page 2 пропущена из-за таймаута)
            assert len(batches) == 2
            assert batches[0][0]["id"] == 100
            assert batches[1][0]["id"] == 102


class TestPotokMapper:
    """Тесты маппинга данных из Potok"""

    def test_map_potok_applicant_full_data(self):
        """Маппинг полных данных кандидата с cv_params на top level"""
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
            # cv_params теперь на TOP LEVEL
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
        }

        result = map_potok_applicant(potok_data)

        assert result["first_name"] == "Иван"
        assert result["last_name"] == "Петров"
        assert result["middle_name"] == "Владимирович"
        assert result["phone"] == "79991234567"
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

    def test_map_potok_applicant_legacy_resumes_fallback(self):
        """Фолбэк на legacy схему resumes[].cv_params если top-level пуст"""
        potok_data = {
            "id": 1,
            "first_name": "Тест",
            # cv_params отсутствует на top level
            "resumes": [{
                "cv_params": {
                    "about_me": "Тест из legacy резюме",
                    "skill_set": ["Legacy Skill"]
                }
            }]
        }

        result = map_potok_applicant(potok_data)
        assert result["resume_summary"] == "Тест из legacy резюме"
        assert len(result["skills"]) == 1
        assert result["skills"][0]["skill"] == "Legacy Skill"


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

        with patch("app.services.candidate_import.preview_applicants") as mock_api:
            mock_api.return_value = (15700, mock_response["data"])  # (estimated_total, sample)

            result = await preview_potok_import(db_session, company_id, "test_token", "skip")

            # estimated_total=15700, sample=1 → scale_factor=15700 → total/new экстраполированы
            assert result["summary"]["total"] == 15700
            assert result["summary"]["new"] == 15700
            assert result["summary"]["duplicates"] == 0
            assert result["summary"]["errors"] == 0
            assert len(result["rows"]) == 1
            assert result["rows"][0]["name"] == "Иван Петров"
            assert result["rows"][0]["source"] == "potok"

    @pytest.mark.asyncio
    async def test_preview_potok_import_api_error(self, db_session, admin_user):
        """Ошибка API передается корректно"""
        company_id = admin_user.company_id
        with patch("app.services.candidate_import.preview_applicants") as mock_api:
            mock_api.side_effect = ValidationError("Невалидный токен")

            with pytest.raises(ValidationError):
                await preview_potok_import(db_session, admin_user.company_id, "bad_token", "skip")