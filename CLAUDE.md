# CLAUDE.md — ATS «Глафира Рекрутёр»

> Этот файл читается первым. Прежде чем что-то делать — прочитай его целиком.
> Продукт: ATS (система рекрутинга) с AI-агентом «Глафира» для российского рынка.
> Факты ниже сверены с реальным кодом (`grep`/`git`), а не взяты из отчётов.

---

## 0. КАК ЗДЕСЬ РАБОТАЮТ (прочитай обязательно)

Разработку ведут субагенты (`fastapi-expert` — бэкенд/миграции/seed; `react-expert` — фронт/CSS; `code-reviewer`) через одну консоль, **последовательно**. Архитектор/аналитик даёт планы и проверяет, агенты пишут код.

**ГЛАВНЫЙ УРОК ПРОЕКТА — агенты систематически выдают желаемое за действительное:**
- заглушки выдают за готовый функционал;
- пишут тесты «мимо поля» (тест проходит, а реальность не проверена) — и даже дёргают НЕсуществующие эндпоинты;
- галлюцинируют (выдуманные данные, кнопки с `console.log`, фейк-числа, несуществующие сущности);
- нарушают явные инструкции (например, добавляют запрещённые токены в `tokens.css`, лепят `alert()` вместо паттерна проекта);
- отчёты РЕГУЛЯРНО расходятся с реальным кодом.

**Рабочий принцип: ВЕРИТЬ `git diff` / `grep` / тестам, НЕ верить отчётам агента.**
Любое «функционал сохранён / всё работает» в отчёте проверять руками: `grep` по ключевым словам, чтение диффа, запуск тестов, ручная проверка в браузере на VPS. За проект это спасало на каждом шаге (последний пример: агент написал тесты против несуществующего `POST /applications`; другой повесил rename-PATCH на каждый keystroke и насовал `alert()`).

**Субагентам РАЗРЕШЕНО коммитить/пушить (с 2026-06-18, явное указание заказчика: «делай субагентами, пусть пушат»).** Реализацию вести СУБАГЕНТАМИ (fastapi-expert/react-expert), они сами ведут полный цикл (правка→коммит→`git push`→автодеплой). Запрет git-операций в промптах НЕ ставить. Защита смещена на **ПОСТ-ФАКТУМ проверку оркестратором** после КАЖДОГО субагента (раньше она была подстраховкой к запрету — теперь это основной контроль): `git log`/`git diff` против последнего своего коммита (что реально ушло?), `gh run list` (деплой зелёный?), одна alembic-голова?, `grep` фейков/`console`/выдуманных токенов/локальных импортов, прогон `tsc`/`build`/`py_compile`, чтение диффа на утечку `company_id`/PII, финальный `code-reviewer` → **фикс-форвард новым коммитом**, если что-то не так. ⚠️ Миграции данных на проде всё равно сверять (идемпотентность/NULL), но пуш субагента не блокировать. Память `subagents-no-git-operations`.

**Принцип «никаких фейк-заглушек»:** функционал либо работает по-настоящему, либо честно помечен «в разработке/скоро» (disabled-контролы, видно что неактивно). Недопустимо: кнопка выглядит рабочей, но ничего не делает; UI редактируется, но изменения не сохраняются; поле принимается схемой, но молча теряется. Молчаливый обман в HR-решениях (скоринг, отказы, верификация) — особенно критичен.

**Токены CSS:** использовать ТОЛЬКО реально существующие переменные из `frontend/src/styles/tokens.css`. НЕ выдумывать «семантические» имена (`--bg-hover`, `--accent-danger`, `--fg-link`, `--border-strong` — таких НЕТ, проверено). Если нужного токена нет — СТОП, спросить, не добавлять самовольно. Известные подмены: `--bg-hover`→`--bg-3-hover`, `--border-strong`→`--ark-gray-400`, `--fg-link`→`--accent`, `--dur-base`→`--dur-normal`, `--shadow-2`→`--shadow-lg`, `--rad-pill`/`--rad-md`→`--radius-full`/`--radius-md`, `--accent-soft`→`--ark-blue-100`. (⚠️ react-expert не раз «галлюцинировал» `--dur-base` как существующий — проверять КАЖДЫЙ `var(--…)` из диффа грепом по tokens.css.)

---

## 1. СТЕК

**Бэкенд:** FastAPI + PostgreSQL 16 + SQLAlchemy 2.0 (async) + Alembic + Pydantic v2 + asyncpg + JWT (python-jose) + pytest (+pytest-asyncio).

**Фронтенд:** React 18.3 + TypeScript 5.7 (strict) + Vite 5 + React Router v6 + TanStack Query v5 + Zustand 4 + axios + recharts + lucide-react + **голый CSS (токены, НЕ Tailwind)**.

**Монорепо:** `/backend` + `/frontend` + `/contracts` (+ `/docs`, `/project`).

**LLM:** через **OpenRouter** (httpx → `{OPENROUTER_BASE_URL}/chat/completions`, OpenAI-формат), модель `anthropic/claude-sonnet-4-6` (`settings.GLAFIRA_MODEL`). Клиент `backend/app/services/glafira/client.py` (методы `call_json` / `call_text`; пустой `OPENROUTER_API_KEY` → не делает живых вызовов). НЕ прямой Anthropic SDK — именно OpenRouter. (Переменная `ANTHROPIC_API_KEY` в конфиге ещё есть, но путь скоринга идёт через OpenRouter.)

> **ИСКЛЮЧЕНИЕ — интернет-разведка верификации (OSINT)** идёт НЕ через OpenRouter, а через **claude CLI с WebSearch/WebFetch** (subprocess, `services/glafira/claude_cli.py`, по образцу ArkadyJarvis). Образ бека (`backend/Dockerfile`) ставит Node 20 + `@anthropic-ai/claude-code`. Токен — из общего файла `CLAUDE_TOKEN_FILE` (формат `{access_token,…}`, держит свежим ArkadyJarvis; мы только читаем, НЕ рефрешим) или из `CLAUDE_CODE_OAUTH_TOKEN`. Подробно — память `verification-osint-claude-cli`.

**VPS:** домен `glafira.dclouds.ru`, Docker compose (postgres + бек + фронт), HTTPS (certbot), nginx **общий** (на сервере много чужих сервисов — их не трогать). Путь `/var/www/glafira`. **Push в `main` = автодеплой** (см. §6).

**Доступы:** demo-админ создаётся в `app/seed.py`; секреты — в `.env` на VPS (НЕ в git). Конкретные значения в доках НЕ хранить.

---

## 2. АРХИТЕКТУРНЫЕ ИНВАРИАНТЫ (не нарушать)

1. **Верификация без подписанного согласия (ПдН/152-ФЗ) → 403 `CONSENT_REQUIRED`.** Доступ к проверке только после подписи. Согласие даёт либо кандидат (online-подписание), либо рекрутёр под свою ответственность кнопкой **«ПдН подписан»** (`POST /consent/confirm-signed`, бумага и т.п.) — обе кнопки в блоке согласия таба Верификация.
2. **Каждое изменяющее действие → запись в `audit_log`.** Действия AI — с `actor_type='ai'`. (Отдельно: лента «Все действия» на карточке читает таблицу `Event`, не `audit_log` — новый тип события требует расширения CHECK `Event.type` + рендера.)
3. **Все записи с `company_id`** (мультитенантность).
4. **Скоринг / AI → строгий JSON.** При сбое парсинга — 502 `GLAFIRA_PARSE_ERROR`, НЕ молчаливый фейк (НЕ хардкод score=50, НЕ поддельная реплика).
5. **Переход `application → hired` идемпотентно создаёт `Employee` + план адаптации** (передача в раздел Пульс). Инвариант проверяется в seed реальным `move_application`.
6. **Единый формат ошибок** `{error: {code, message, details}}`. Бизнес-ошибки — через `core/errors.py` (`AppError` + наследники), НЕ сырой `HTTPException`.
7. **Правило 400 vs 422:** бизнес-ошибки → 400 (`ValidationError`/`ConflictError`=409/`NotFoundError`=404 и т.д.); ошибки валидации формы (Pydantic) → 422.
8. **Верификация — частично РЕАЛЬНАЯ** (с ~2026-06-04, `services/glafira/verify.py`): блоки — **контакты** (телефон/email/ФИО через DaData Clean API — реально), **госреестры** (ФССП/ФНС/банкротство/санкции/алименты — честные заглушки «Не подключено», 152-ФЗ, БЕЗ фейк-вердиктов), **OSINT** («Публичная экспертиза» + «Упоминания» — реальный веб-поиск через claude CLI, идёт В ФОНЕ `fill_candidate_osint` + поллинг на фронте). `is_mock=False`. Реальной интеграции с госреестрами НЕТ — заглушки НЕ включать как вердикты до неё (мина 152-ФЗ). `GLAFIRA_VERIFY_MODE` — legacy (verify_candidate на него не смотрит). В поиск идут ФИО+город+должность+компания+год+email+телефон (по согласию); плашка под блоками описывает это честно — НЕ менять текст плашки, не сверив с тем, что реально шлётся.
9. **Биллинг (с v0.9.48):** компания с `paid_until` в прошлом ИЛИ NULL → все аутентифицированные запросы её юзеров отбиваются **402 `SUBSCRIPTION_EXPIRED`** (гейт в `app/deps.py::get_current_user` через `company_subscription_active`, scoped по `user.company_id` — тариф А не влияет на Б). NULL = заблокирована (fail-closed). Логин и `/auth/refresh` НЕ гейтятся (фронт ловит 402 и показывает экран). **Суперадмин-сервис НЕ гейтится** — владелец заходит всегда. Дата `paid_until` правится руками в суперадминке. Память `billing-paid-until-state`.

---

## 3. БЕКЕНД (состояние)

Завершён по основной функциональности. **~194 эндпоинта** в 23 роутерах (`app/api/v1/`), тесты в `tests/` (offline — LLM-ключ пуст, живые вызовы не идут). (Числа растут с каждой фичей — при сомнении пересчитать `grep`, не верить цифре вслепую. Последнее обновление CLAUDE.md — 2026-06-17, версия 0.9.65.)

> ✅ **Полный pytest зелёный: 713/713** (67 файлов, прогон на VPS 2026-06-13). Достигнуто разгребанием тест-долга, вскрытого ПЕРВЫМ полным прогоном (90 падений → 0; попутно найдено 9 реальных прод-багов). **Урок: гонять ВЕСЬ suite, не только тронутые файлы** (кросс-файловые регрессы) + при починке падающего теста сверять ВЕСЬ его body (демаскирование: фикс одного ассерта вскрывает следующий). Память `full-suite-test-debt`.
> ✅ **Глубокий бэкенд-аудит пройден** (эра 0.9.1x): 0 Critical, все High/Medium закрыты, остался только Low (defense-in-depth `company_id`). Память `backend-deep-audit-0-9`.

> ⚠️ **`contracts/openapi.json` НЕ полностью актуален.** Последние правки (CRUD этапов воронки `/vacancies/{id}/stages`, источник `superjob`, поле `messengers`) подключены на фронте через **локальные TS-типы + `as`-cast**, openapi под них НЕ регенерён (нет живого сервера в рабочем окружении). Регенерировать против поднятого бэка, когда появится возможность, и тогда убрать cast.

**Модели/таблицы (43, `grep __tablename__`):** companies (+ `paid_until` Date nullable — биллинг, v0.9.48, см. инв. §2.9), users, clients, vacancies, vacancy_stages, vacancy_team, candidates, candidate_experience, candidate_skills, candidate_education, applications, stage_history, ai_evaluations, consents, documents, messages, comments, employees, pulse_surveys, pulse_plan_items, pulse_alerts, survey_templates, audit_log, events, email_templates, verifications, reject_reasons, tags, candidate_tags, glafira_settings, integrations, hh_integrations, hh_oauth_states, smart_search_runs, funnel_templates, funnel_template_stages, company_default_stages, candidate_import_jobs (импорт из Excel), base_search_runs (история поиска по своей базе), candidate_embeddings (pgvector-эмбеддинги резюме, заход B), **message_templates** (шаблоны быстрых сообщений для чата, v0.9.30 — общие на компанию, см. память `message-templates-state`), **calls** + **call_sync_jobs** (звонки Mango Office + джоб выгрузки истории, v0.9.34 — см. память `mango-calls-integration-state`).

**Источник кандидата (`Candidate.source` CHECK):** hh, avito, superjob, telegram, referral, direct, agency, import, manual, linkedin, **potok**, other. `'potok'` добавлен миграцией `j1k2l3m4n5o6` (импорт из Поток) — при добавлении нового источника обновлять И CHECK в модели, И миграцию, И `CandidateSource` Literal в `schemas/candidate.py`, И `lib/source-colors.ts`/фильтры на фронте. Текущая голова alembic — `u2v3w4x5y6z7` (add_paid_until_to_companies, биллинг); всего 54 ревизии, ОДНА голова. Перед новой миграцией найти НАСТОЯЩУЮ голову регексом (память `alembic-find-true-head`).

**Этапы воронки (`STAGES`, 9 шт., hex-цвета — источник правды на беке** `core/stages.py`, цвет вычисляется, НЕ хранится в БД):
- `response` Отклик, `added` Добавлен (system), `selected` Отобран, `recruiter` Контакт с рекрутером, `interview` Интервью, `manager` Контакт с менеджером, `offer` Оффер, `hired` Нанят (terminal), `rejected` Отказ (terminal).

**Защищённые этапы (`PROTECTED_STAGE_KEYS` в `core/stages.py`):** `hired`, `rejected`, `added`, `response` — нельзя удалять/менять `stage_key` (завязаны на найм, отказ, старт, fallback). Защита **серверная** (UI-защиты недостаточно).

**Связь этап↔кандидат — строковая** (`Application.stage == VacancyStage.stage_key`, без FK; `stage_history.from/to_stage` — тоже по строке). Поэтому:
- переименование этапа меняет ТОЛЬКО `label`, НИКОГДА `stage_key` (иначе осиротит applications + stage_history);
- смена порядка этапов = только `order_index` (история переходов по `stage_key` остаётся, аналитика не ломается);
- CRUD этапов живой вакансии — гранулярные эндпоинты (`POST/PATCH/DELETE/PUT /vacancies/{id}/stages[...]`), `update_vacancy` этапы НЕ трогает. Каждое действие = свой запрос (массив целиком слать нельзя — rename станет неотличим от delete+add).

**Описание этапа (`description`, с ~2026-06-04):** свободный текст-инструкция для команды (что делать на этапе, суть тестового, чек-лист). Колонка `description` (Text, nullable) в `vacancy_stages` + `company_default_stages` + `funnel_template_stages` (миграция `f3a4b5c6d7e8`). Редактируется в форме вакансии (FunnelStep, по blur PATCH) и в Настройках → «Воронка по умолчанию». PATCH этапа теперь меняет `label` И/ИЛИ `description` (через `model_fields_set` — label-only PATCH не затирает описание). На `stage_key`/порядок/аналитику не влияет.

**LLM-сервисы:** `services/glafira/` — scoring (скоринг резюме, взвешенная 100-балльная рубрика; в промпт `description` вакансии идёт со снятыми HTML-тегами `_strip_html`), screening (диалог-скрининг), resume_parse (парсинг PDF/TXT — DOC/DOCX/RTF НЕ парсятся), verify (см. инв. §2.8 — контакты DaData + госреестр-заглушки + OSINT через claude CLI, consent-gated, OSINT в фоне), employee_summary (AI-сводка сотрудника). Все с anti-hallucination guards в промптах и строгим JSON-контрактом. Ретрай-backoff на 403/429/5xx в `client.py` (OpenRouter); claude CLI (`claude_cli.py`) — graceful→None при любом сбое.

**Умный подбор — ДВЕ ветки (развилка источника, см. память `smart-search-state`):**
- **Ветка А — hh** (`services/smart_search.py` + `api/v1/smart.py`): активный сорсинг резюме hh — фоновая `asyncio`-задача search→eval→invite (паттерн OSINT). Модель `SmartSearchRun` (`smart_search_runs`). Оценка — `scoring.score_resume_dict` (рубрика, БЕЗ персиста). Эндпоинты `/smart/access|vacancies|search|runs[/{id}]|vacancy-filters/{id}`. **Денежные предохранители FAIL-CLOSED:** приглашения только при `has_paid_access && vacancy.hh_vacancy_id`; квота hh не определена/мала → 400; капы scan/invite. ⚠️ ВРЕМЕННЫЕ диаг-логи `[smart] payable_api_actions raw=`/`search_params=`. Тесты на моках. ПЛАТНЫЙ цикл подтверждён заказчиком.
- **Ветка Б — по СВОЕЙ базе** (`services/base_search.py`; заход A с v0.7.0, заход B/семантика с v0.8.0, гибрид с v0.9.0): **ГИБРИД retrieve→rerank**.
  - **Retrieve (мгновенно): семантический косинус по ВСЕЙ базе** через **pgvector HNSW** (`candidate_embeddings`, `SET LOCAL hnsw.ef_search`). Эмбеддинги — **локальная ONNX-модель fastembed** `paraphrase-multilingual-MiniLM-L12-v2` (384-dim), `services/embeddings.py` (single-flight синглтон `threading.Lock`, прогрев в lifespan, build внутри `to_thread`; fastembed-импорт на модуле с graceful-фолбэком). Переиндексация `reindex_all_embeddings` — фоновая задача (возвращает task), запуск из **Настройки→AI**. `match_percent` семантики = cosine→percent. Фолбэк, если эмбеддингов нет/вектор недоступен — SQL top-N (заход A не ломаем).
  - **Заход A (SQL, оставлен как фолбэк/основа фильтров):** `parse_query_to_criteria` (call_json → {role,skills,city,salary} + фолбэк на ключевые слова, НЕ 500); `search_base` (ILIKE last_position/city + EXISTS candidate_skills scoped-company + ЗП BETWEEN NULL-инклюзив; `match_percent` = РЕАЛЬНЫЙ overlap навыков; **фильтр `tags`/`vacancy_id` FAIL-CLOSED** на полностью невалидных UUID → `false()`, не вся база); `search_by_vacancy` (переиспользует `derive_vacancy_filters`, принимает override-критерии от фронта).
  - **Rerank (по кнопке, тратит AI-токены):** `_run_base_evaluate` — AI-оценка топ-N (`score_resume_dict`) кандидатов из retrieve, фоновая `asyncio`-задача. Запуск через `POST /smart/base/runs/{id}/evaluate` с **TOCTOU-предохранителем** (атомарный conditional UPDATE на сессии запроса → 409 `ConflictError` при `status='running'`; ValidationError для прочих невалидных статусов).
  - Эндпоинты `/smart/base/{search,runs,count,runs/{id}/evaluate,runs/{id}/mark-added}` (RBAC manager-forbidden). История `base_search_runs`. Опыт хранится строками → мягкий фильтр. «+ В вакансию» переиспользует `assign_candidate_to_vacancy` (невалидный/чужой этап → мягкий фолбэк на 1-й реальный этап, garbage не в `STAGES` → 400). Первый реальный поиск на живой базе — заказчик.

**Импорт кандидатов (бек, `services/candidate_import.py` + `api/v1/candidate_import.py`, см. память `candidate-import-excel-state`):** два источника в ОБЩУЮ базу (БЕЗ вакансии/этапа). (1) **Из файла Excel** (.xlsx/.xls): `/candidates/import/{parse,preview,execute,jobs/{id}}` — openpyxl через `to_thread`, авто-распознавание колонок, очистка (ФИО-коды/телефоны→+7), дедуп company-scoped (телефон-варианты + lower(email)), async-джоб `CandidateImportJob` (`candidate_import_jobs`: батчи 500, короткие сессии, GC-защита `_active_tasks`+add_done_callback, наивный finished_at). (2) **Из Поток (potok.io) по API** (с v0.6.8, `services/integrations/potok/`): офиц. API v3 (`https://app.potok.io/api/v3`, Bearer-токен компании), `/candidates/import/potok/{preview,execute}` → `GET /applicants.json` пагинацией → маппинг резюме (resume под `resumes[].cv_params`: experience→candidate_experience, skill_set→candidate_skills, education→candidate_education, languages→`extra.languages`, about→resume_summary), source='potok'. **Токен НЕ персистится** (только в памяти задачи, не в БД/логах/ответах). RBAC manager-forbidden, company_id из контекста, каждая строка в savepoint (сбой одной не валит батч). ⚠️ Живой API Поток из dev-среды НЕ проверен (гео/IP) — маппер по OpenAPI-спеке, пинит заказчик.

**Email «Доступ к аккаунту» (credentials, реален с v0.2.49):** `services/integrations/smtp/templates.py::render_credentials_email` (HTML из кода, не из БД/файла) → `service.py::send_credentials_email` → `send_email` (stdlib `smtplib`, SMTP компании). Триггеры: создание юзера (`POST /users`) и импорт из Б24 — оба шлют письмо с логином/паролем, если SMTP настроен. Фронт (`CreateUserModal`/`BitrixImportModal`) обрабатывает и успех, и fallback. Прототип письма — `project/Письмо - Доступ к аккаунту.html`.

**Снятые CHECK-констрейнты (миграции):** `check_stage_key` на `vacancy_stages` (`a1b2c3d4e5f7`) и `check_application_stage` на `applications.stage` (`c8d9e0f1a2b3`) сняты — чтобы воронка могла иметь кастомные этапы и кандидаты могли на них перемещаться. Downgrade восстанавливает прежний список.

**seed:**
- `python -m app.seed` — базовый (компания, админ, справочник причин отказа, дефолтные настройки). Для чистого прода. Идемпотентен (exists-guard).
- `python -m app.seed_demo` — демо-данные. **НЕ мягко-идемпотентен:** в начале `cleanup_demo` УДАЛЯЕТ свои demo-сущности (кандидаты с `extra->>'demo'='true'`; вакансии/клиенты ПО ИМЕНИ из списков + каскад) и пересоздаёт. Реальные данные целы, ПОКА имена не пересекаются с demo. Всё в одной транзакции. Создаёт клиентов, вакансии + vacancy_stages, кандидатов по этапам, employee (через реальный `move→hired`), pulse-опросы, consent, документы, сообщения, AI-оценки. `ai_score` проставляется напрямую (LLM НЕ вызывается). `stage_history` монотонный с реалистичными интервалами.
- `python -m app.jobs.regenerate_employee_summaries` — батч AI-сводок сотрудников (cron на VPS).

---

## 4. ФРОНТЕНД — ЭКРАНЫ

12 экранов (компоненты в `frontend/src/`). Подробные ТЗ по экранам — в `docs/tz/` + `project/docs/` (экран 11 — `project/docs/11 - Умный подбор.md`, экран 12 — `project/docs/12 - Импорт кандидатов.md`).

1. **Главная** (Home/Dashboard) — KPI-сетка, «Требуют внимания», «Лента событий» (polling, live-dot), блок «Адаптация/Пульс», «Топ-источники».
2. **Вакансии** — список в сайдбаре (inline), форма создания (4 шага, кастомные этапы), форма добавления кандидата (full-screen), архив.
3. **Воронка** (`/vacancies/:id`) — таблица кандидатов (закреплённый профиль-рельс 378px + скролл-часть), чипы этапов, сортировка, фильтры (drawer), bulk-действия, выезд карточки (detailMode — оверлей `left:378px`).
4. **Карточка соискателя** — right-side панель (оверлей в воронке), 8 табов: Резюме, Оценка AI, Верификация (ПдН-gated), Чат, **Звонки** (Mango, v0.9.34), Документы, Комментарии, Все действия. Тулбар — строго 5 кнопок: Перевести / Отклонить / Комментарий / ПдН / ✕.
5. **Кандидаты — общая база** (CandidatesPool) — сетка карточек всех кандидатов + карточка-пул (та же карточка, режим `fromPool`).
6. **Аналитика** — 7 отчётов (Обзор, Скорость, Воронка, Источники, Отказы, Текучка, Рекрутёры).
7. **Пульс — главный** — пост-найм-модуль, таблица сотрудников в адаптации, алерты, риск ухода.
8. **Пульс — карточка сотрудника** — профиль адаптации, план, опросы, AI-сводка.
9. **Настройки** — профиль, команда, интеграции, голос Глафиры, шаблоны, «Воронка по умолчанию» (шаблон для новых вакансий), биллинг.
10. **Сайдбар** — постоянная навигация, раскрытие подменю (Вакансии/Аналитика inline), бейдж Пульса, user-card. **Список вакансий в сайдбаре — эталонный, НЕ трогать.** Пункт ✨ «Умный подбор» (beta) — сразу после «Кандидаты».
11. **Умный подбор** (`/smart`, beta, RoleGuard admin/recruiter) — **развилка источника** (`SSFork`): ветка А «на hh.ru» (активный сорсинг, конструктор 5 шагов, поллинг `GET /smart/runs/{id}`, ⚠️ тратит деньги клиента) ИЛИ ветка Б «по своей базе» (промт / по открытой вакансии → **мгновенный семантический косинус (pgvector)** + пилюли «N% совпадение» + кнопка **AI-оценки топ-N** [тратит токены, поллинг `GET /smart/base/runs/{id}`], история, «+ В вакансию» — см. §3). В обеих ветках сверху `‹ Выбор источника`. Эталон — `project/components/SmartSearch.jsx` (развилка+hh) + `project/components/SmartSearchBase.jsx` (ветка Б) + `project/styles/smart-search.css`. Хуки `useSmartSearch.ts`. Автофильтры vacancy-метода ветки Б — в стиле фильтров кандидатов (Должность/Город/Опыт/ЗП/Навыки, правки реально влияют на поиск). Индексация эмбеддингов — в **Настройки→AI**.
12. **Импорт кандидатов** (полноэкранный визард из шапки «Кандидаты», кнопка «Импорт кандидатов») — **развилка источника** (4 карточки 2×2): «Из файла» (Excel: загрузка → маппинг колонок → превью → импорт) и «Из Потока» (токен API → превью → импорт, без маппинга) — рабочие; «Talantix»/«Хантфлоу» — заглушки «Скоро» (`.imp-source-card.soon`, некликабельны, только вёрстка). Превью/результат/попап резюме общие. Эталон — `project/components/ImportCandidates.jsx` + `project/styles/import.css` + ТЗ `docs 12`. Бек — §3.

---

## 5. КОНВЕЙЕР ПЕРЕСБОРКИ ФРОНТА ПО ЭТАЛОНУ (текущая фаза)

**Зачем:** первый фронт визуально разошёлся с дизайн-эталоном. Эталон — хэндофф из Claude Design в папке `project/` (HTML/CSS/JS-прототипы: `project/components/*.jsx`, `project/styles/*.css`, `project/Глафира Рекрутер (standalone).html`). Источник правды по визуалу: `project/styles/` + `frontend/src/styles/tokens.css` (ark-палитра + `--bg-*`/`--fg-*` через ark; шкала `--fs-11..32`; `--font-sans`=Inter, `--font-mono`=JetBrains Mono).

**Метод (Вариант 3):** пересобирать каждый экран 1:1 по эталону **КОНВЕЙЕРОМ — по одному экрану, с проверкой функционала после каждого.** НЕ всё разом (агент растеряет функционал/нагаллюцинирует).

**Жёсткие правила пересборки (на каждый экран):**
- Структура DOM + CSS — **буквально из эталона** `project/`.
- Функционал — **буквально из нашего текущего компонента** (хуки, мутации, состояния сохранить, ничего не выдумывать).
- НЕ переносить служебные артефакты прототипа: `data-screen-label`, фейковые данные, метки инструмента.
- CSS — только реальные токены (см. §0); эталонные hex смапить на токены, не вставлять как есть (иначе откат палитры).
- CSS **scoped** к корню экрана, НЕ глобально. **Исключение:** `.submenu-search` — глобальный примитив, его делит Архив; скоупить нельзя.
- Эталон местами хардкодит `font-size` в px — приводить КОНКРЕТНЫЕ значения к эталонным, не переводить массово на токены.
- НИКАКИХ `console.log` / mock / выдуманных данных / `alert()`.
- **Новый элемент, которого в эталоне нет** (эталон — create-only прототип без бэка; напр. счётчик кандидатов в редакторе этапов, инлайн-баннер серверной ошибки): точного 1:1 неоткуда — но СНАЧАЛА найти ближайший идиом в эталоне/проекте и повторить его, а не лепить своё. Счётчик этапа → идиом `.fc-count` (моно-число, без фона); ошибка формы → `.error-banner`.

**Иконки:** оставлены lucide-react (НЕ портируем из эталона — решение принято).

**Пересобраны и задеплоены:** Главная, Сайдбар (со списком вакансий), Layout, Воронка (каркас + карточка соискателя/7 табов + позиционирование detailMode), Перевести/Отклонить (карточка + bulk), форма создания вакансии (4 шага, кастомные этапы), форма добавления кандидата, редактирование воронки живой вакансии (CRUD этапов с защитой непустого/системного).

**Конвейер пересборки фронта по эталону — в основном ЗАВЕРШЁН** (последний релиз цикла `0.1.80`). С эры **0.2/0.3** идёт фаза интеграций и фич (hh/Avito/SMTP/Telegram/Bitrix/теги/пользователи/RBAC/Пульс — детали в памяти проекта) + точечные фичи поверх эталона. Правила пересборки выше остаются в силе для любого нового/трогаемого экрана.

**Свежие фичи (0.3.x):** верификация частично реальная (DaData + OSINT claude-cli + «ПдН подписан», см. §2.8); рич-текст редактор описания вакансии (`RichTextField`, contentEditable+execCommand — `description` хранит HTML, в скоринг идёт со снятыми тегами); редактируемое «Описание этапа» воронки.

**Свежие фичи (0.4.x) — АВТОМАТИЗАЦИЯ ВОРОНКИ (⚠️ действует с живыми людьми, дефолт OFF, opt-in на вакансии):** см. память `funnel-automation-state`. П.1 автоперевод по скорингу + П.4 настраиваемый текст отказа — РЕАЛЬНЫ. П.2 (вопросы+автоперевод по ответам) и П.3 (автоотказ) — реализованы, тумблеры рабочие, дефолт OFF. **NB:** полный автоотказ+письмо (П.3) требует `glafira_mode='B'`, а селектора режима в UI НЕТ (`glafira_mode` зашит в 'A') → штатно сейчас П.3 = только подсказка `auto_reject_suggested_at`. Адверс-ревью v0.4.7 (131 агент) подтвердило предохранители (режим C/None не двигает, audit `actor_type='ai'`, only-forward, 502 цел, одна alembic-голова); хвосты к починке: автономный discard+письмо П.4 НЕ пишет `audit_log` (нарушение §2.2); UI-подпись «при скоринге AI >» vs код `>=`; `rejection_text` нельзя очистить в None через форму; `glafira_mode` без Pydantic-`Literal` (500 на мусоре); stale-коммент «П.2/П.3 disabled» в `VacancyFormPage.tsx:277`; П.3 бьёт по всем нетерминальным этапам.

**Свежие фичи (0.5.x) — УМНЫЙ ПОДБОР / активный сорсинг (⚠️ ТРАТИТ РЕАЛЬНЫЕ ДЕНЬГИ КЛИЕНТА — квота hh + AI-токены + списание контактов):** новый раздел `/smart` (экран 11) — Глафира сама ищет резюме в базе hh, оценивает AI-скорингом против вакансии и приглашает лучших в воронку. Бек/предохранители — см. §3; UX — §4 п.11; глубокие детали и грабли — память `smart-search-state` ([[hh-resume-search-recon]]). Модель доступа: поиск+оценка без платного доступа, приглашения только при платном доступе + опубликованной на hh вакансии (иначе превью-режим). Фильтры (проф-область/роль hh) подбирает Глафира из вакансии (LLM). **Первый реальный платный запуск делает заказчик осознанно** — не агент. Открытый риск: сам `GET /resumes/{id}` для оценки МОЖЕТ требовать платный доступ hh (проверяется на живом запуске по диаг-логу).

**Свежие фичи (0.6.x) — ИМПОРТ КАНДИДАТОВ:** новый экран 12 (визард с развилкой источника). 0.6.0–0.6.7 — импорт из Excel (.xlsx); 0.6.8 — вторая ветка «Из Потока» (potok.io) по офиц. API-токену (см. §3, память `potok-resume-import`); 0.6.9 — развилка из 4 карточек (+ «Скоро»-заглушки Talantix/Хантфлоу), кнопка входа «Импорт из файла»→«Импорт кандидатов»; 0.6.10 — кнопки «Назад/Далее» визарда как в форме вакансии/кандидата (`btn-sm`+chevL+arrowRight). Память `candidate-import-excel-state`. Параллельно (инфра): `provision_company.py` (CLI безопасного провижининга 2-го арендатора — в системе РЕАЛЬНЫЙ 2-й клиент, см. `multitenancy-isolation-audit`), `scripts/backup_all.sh` (полный бэкап БД+.env+том).

**Свежие фичи (0.7.x) — УМНЫЙ ПОДБОР ПО СВОЕЙ БАЗЕ (заход A, SQL):** 0.7.0 — развилка источника в `/smart` + ветка Б «по своей базе» (SQL-поиск + LLM-парс промта); 0.7.1 — автофильтры vacancy-метода в стиле фильтров кандидатов. Память `smart-search-state`.

**Свежие фичи (0.8.x–0.9.2) — СЕМАНТИЧЕСКИЙ ПОДБОР ПО СВОЕЙ БАЗЕ (заход B, ГОТОВ):** pgvector-эмбеддинги резюме (локальная ONNX fastembed, `candidate_embeddings`), мгновенный косинус-retrieve по всей базе + AI-rerank топ-N по кнопке (гибрид). 0.8.0 семантический слой; 0.8.1–0.8.2 индексация во вкладке Настройки→AI; 0.8.3 async-поиск (фикс 504); 0.8.4 грабля миграции (`server_default` через `sa.text()`); 0.8.5 + 0.9.0–0.9.2 anti-hang + гибрид (мгновенный косинус + один инпут N для AI-оценки). Детали/грабли — см. §3 + память `smart-search-state`.

**Свежие фичи (0.9.3–0.9.12) — ПОВЕРХ ЭТАЛОНА:** 0.9.3 хаб источников импорта (15 карточек); 0.9.4 скачивание резюме в пуле; 0.9.5 экспорт PDF/DOCX в стиле hh (reportlab+python-docx, память `resume-export-feature`); 0.9.6 вкладка Настройки→AI + **per-company выбор LLM-модели** (память `ai-model-per-company`); 0.9.7–0.9.8 добавление кандидата с автозаполнением из резюме (память `add-candidate-resume-autofill`); 0.9.9–0.9.10 удаление кандидата (память `candidate-delete-and-button-scoping`); 0.9.11 **зарплата-вилка** salary_from/salary_to (память `salary-range-sync-invariant`); 0.9.12 дедуп при ручном добавлении (память `candidate-dedup-manual-add`).

**Свежие фичи (0.9.13–0.9.29) — АУДИТ + ТЕСТ-ДОЛГ (стабилизация):** 0.9.13–0.9.16 фиксы HIGH глубокого бэкенд-аудита; 0.9.21–0.9.22 Medium-бэклог (индексы, надёжность импорта, evaluate-TOCTOU); 0.9.24–0.9.29 разгребание тест-долга полного прогона → **713/713 зелёных** (попутно 9 реальных прод-багов). Память `backend-deep-audit-0-9`, `full-suite-test-debt`.

**Свежие фичи (0.9.30) — ШАБЛОНЫ СООБЩЕНИЙ:** новый раздел Настройки→«Шаблоны сообщений» (CRUD: название + плоский текст, общие на компанию, БЕЗ плейсхолдеров) + выпадашка «Шаблон» в чате карточки кандидата (быстрая вставка текста в поле ввода). Отдельный роутер `/message-templates` (read — все роли, write — admin+recruiter; НЕ под `settings_permission_dependency`). Память `message-templates-state`.

**Свежие фичи (0.9.31–0.9.32) — ГЛАВНАЯ:** баланс колонок шаблонов; блок «Последние сообщения»/чаты (`GET /home/dialogs`) + контекст кандидат/вакансия в ленте событий (см. память `home-features-and-etalon-sync`).

**Свежие фичи (0.9.33–0.9.34) — ЗВОНКИ MANGO OFFICE:** интеграция телефонии в карточку кандидата (новый таб «Звонки»). 0.9.33 — настройка интеграции (ключи Fernet в generic `integrations`, `provider='mango'`) + клиент Mango API. 0.9.34 — выгрузка истории звонков поллингом (двухшаговый `/vpbx/stats/*`), матчинг по нормализованному номеру (`find_duplicate_candidates`, СТРОГО company-scoped), прослушивание записи (проксирование 302→MP3), **расшифровка ПО ЗАПРОСУ + кэш через Gemini-via-OpenRouter** (`GLAFIRA_TRANSCRIBE_MODEL='google/gemini-2.5-pro'`, существующий `OPENROUTER_API_KEY`; образец — соседний проект ArkadyJarvis) + AI-разбор через `call_json`. Записи/расшифровки БЕЗ гейта согласия (решение заказчика). ⚠️ Точный парсинг CSV Mango (направление/время/external_id) и услуги тарифа — **требуют пиннинга на реальном ключе заказчика**. Память `mango-calls-integration-state`.

**Свежие фичи (0.9.41–0.9.46) — СУПЕРАДМИНКА ТЕНАНТОВ (отдельный сервис, развёрнут на VPS):** `backend/superadmin/` — изолированный FastAPI (Jinja UI, своя env-авторизация `SUPERADMIN_*`, profiles:[superadmin], за nginx `/super/`). CRUD компаний через `provision_company` + per-company OpenRouter-ключ (Fernet, маскирован) + просмотр junit-результатов. НЕ импортируется в клиентское приложение. 0.9.42 фикс рендера (Starlette `TemplateResponse` request-first), 0.9.43 хост-порт через `SUPERADMIN_PORT` (.env; на VPS 8001 занят → **18001**), 0.9.44 относительный action формы (по http POST уходил мимо/без Secure-cookie), 0.9.45–0.9.46 версия Глафиры в шапке (маунт ПАПКИ `frontend/src/lib` → читает version.ts на рендер). ⚠️ Авто-пересборка суперадминки в `deploy.yml` есть, но `.github/workflows/*` нельзя пушить токеном без scope `workflow` → правки deploy.yml вносятся через GitHub web UI. Память `superadmin-service-state`.

**Свежие фичи (0.9.48) — ЛЁГКИЙ БИЛЛИНГ:** `companies.paid_until` (Date nullable) + жёсткий дизейбл тенанта 402 `SUBSCRIPTION_EXPIRED` при просрочке/NULL — см. инвариант §2.9. Гейт в `get_current_user`; дата правится в суперадминке (поле «Оплачено до» + красный флаг просрочки в списке); фронт показывает полноэкранный `SubscriptionExpiredScreen`. Тесты: conftest autouse `_bypass_billing_gate` (по умолчанию off) + маркер `billing_gate` для тестов гейта. Полный pytest на VPS зелёный (2026-06-14). ⚠️ NULL=заблокирована → существующим компаниям задать `paid_until` в суперадминке сразу. Память `billing-paid-until-state`.

**Свежие фичи (0.9.62–0.9.65) — TELEGRAM: ДВУСТОРОННЯЯ ПЕРЕПИСКА С КАНДИДАТОМ:** канал Telegram доведён из «теста себе» до реальной переписки в карточке кандидата. Детали/грабли — память `telegram-integration-state`.
- **0.9.62 — вход по QR-коду** (`ExportLoginToken`/`ImportLoginToken`, stateless/DB-backed под 2 воркера, образец ArkadyJarvis `gen_session_qr.py`): SMS-код не доходил → теперь подключение аккаунта сканированием QR (Настройки→Интеграции→Telegram). 2FA переиспользует `confirm_password`. `TELETHON_API_ID/HASH` в env (приоритет над `TELEGRAM_*`).
- **0.9.63 — реальная отправка кандидату:** раньше `message.py::send_message` для `channel='telegram'` молча писал в карточку без отправки (фейк). Теперь `_send_telegram` шлёт через user-аккаунт компании (`send_to_peer`: резолв пира username→телефон через `_resolve_peer`/ImportContacts, телефон нормализуется). Каналы чата: **whatsapp/max убраны**, **sms = «Скоро»** (disabled — SMS-провайдера нет, не делаем вид), активны telegram/hh/email.
- **0.9.64 — обратная синхронизация (ответы кандидатов в чате):** зеркалит hh-поллер. `tg_user_id` пишется в `candidate.extra` при отправке; `sync_inbound` сохраняет входящие как `Message(direction='in', sender_type='candidate', external_id='tg:{peer}:{msg}')`, дедуп, строго company-scoped, только диалоги сопоставленных кандидатов (личные чаты рекрутёра не читаются). Триггеры: `POST /candidates/{id}/messages/telegram/sync` при открытии чата + поллинг 12с + резинк 90с (in-flight guard) + cron `app/jobs/poll_telegram_messages.py` (flock, раз в 3 мин, **заказчик добавляет в crontab вручную**).
- **0.9.65 — фикс «открыл чат — пусто»:** синк одного кандидата (открытие чата) теперь резолвит диалог НАПРЯМУЮ (`fetch_candidate_inbound`, как при отправке), не завися от заранее сохранённого `tg_user_id` и окна топ-N диалогов; бэкфиллит `tg_user_id`. Cron-путь (company-wide) — по-прежнему `iter_dialogs`.
> ⚠️ Между 0.9.48 и 0.9.62 были и другие деплои (hh-фиксы, Поток и т.д.) — здесь зафиксирована только Telegram-эра; при сомнении сверять `git log`.

**Текущая версия:** `frontend/src/lib/version.ts` (`APP_VERSION`) — на 2026-06-17 = **0.9.65**. Видна в Sidebar под «Глафира» (и в шапке суперадминки). **Bump на каждый значимый деплой.**

---

## 6. ДЕПЛОЙ И РЕЛИЗ-ЦИКЛ (VPS)

**Релиз = `git push origin main`.** GitHub Actions (`.github/workflows/deploy.yml`, appleboy/ssh-action) идёт по SSH на VPS `/var/www/glafira`:
1. `git pull --ff-only`;
2. rebuild `backend` — только если в диффе менялись пути `backend/`; rebuild `frontend` — только если `frontend/`;
3. `docker compose -f docker-compose.prod.yml up -d`;
4. `alembic upgrade head` — **ТОЛЬКО если в диффе есть файлы `backend/alembic/versions/`**.
5. пересборка+рестарт `superadmin` (`--profile superadmin build` + `up -d superadmin`) — **ТОЛЬКО если менялись `backend/superadmin/` И контейнер уже запущен** (иначе пропуск; первичная настройка/подъём — ручные). Суперадмин — отдельный сервис (profiles), обычный `up -d` его не трогает. ⚠️ Этот блок в `deploy.yml` правится через GitHub web UI: `.github/workflows/*` нельзя пушить токеном без scope `workflow`.

**CI тесты НЕ гоняет — только деплой.** `pytest`/`seed` запускаются вручную на VPS в контейнере backend.

**Кто релизит:** Claude ведёт **полный цикл сам** — бампнуть `APP_VERSION` → коммит в `main` (с `Co-Authored-By: Claude`) → `git push`. Не переспрашивать. (Коммитим прямо в `main` — так шёл весь конвейер.)

**⚠️ ВЕРСИЯ — ПЕРВЫМ ТОКЕНОМ ЗАГОЛОВКА КОММИТА, ВСЕГДА.** Формат: **`vX.Y.Z тип(scope): описание`** (напр. `v0.3.31 feat(stages): …`). В action/списках GitHub заголовок обрезается — версия в конце/теле НЕ видна, поэтому строго в начале subject. Пользователь требовал это многократно (см. память `claude-commits-and-bumps-version`). Применять к КАЖДОМУ коммиту, включая бэкенд-only и docs.

**Ручные docker-команды на VPS — ВСЕГДА `-f docker-compose.prod.yml`.** Голый `docker compose up -d` хватает дев-`docker-compose.yml` (другой том postgres `postgres_data` ≠ прод `glafira_pgdata`, открытые порты, авто-seed) — это ломает/подменяет прод. Автодеплой и любые ручные операции — только prod-файл.

**Рантайм-реальность этой среды:** локального бэкенд-окружения НЕТ (нет Docker CLI, нет venv/зависимостей, нет SSH к VPS). Значит:
- `pytest`/`seed`/`alembic`/`uvicorn` локально НЕ запускаются — писать код+тесты+миграцию, коммитить, пушить; прогон тестов — на VPS (`docker compose -f docker-compose.prod.yml run --rm backend pytest`). «pytest зелёный» НЕ утверждать как факт, если не прогнан.
- Фронтовый тулинг ЕСТЬ локально: `npx tsc --noEmit` и `npm run build` гонять обязательно перед коммитом.

**Инфра-инварианты VPS (.env НЕ в git):** `DATABASE_URL`, `JWT_SECRET`, `FERNET_KEY`, `OPENROUTER_API_KEY`, `GLAFIRA_MODEL`, `CORS_ORIGINS=https://glafira.dclouds.ru`, `SESSION_COOKIE_SECURE=True`. Верификация: `DADATA_API_KEY`+`DADATA_SECRET_KEY` (контакты), OSINT — `CLAUDE_TOKEN_DIR` (хост-папка с токен-файлом, монтируется в `/app/claude-auth`) + `CLAUDE_TOKEN_FILE=/app/claude-auth/.claude_token.json` (или `CLAUDE_CODE_OAUTH_TOKEN`), `GLAFIRA_OSINT_MODEL=opus`, `GLAFIRA_OSINT_TIMEOUT=120`. Звонки Mango: расшифровка идёт через существующий `OPENROUTER_API_KEY` (модель `GLAFIRA_TRANSCRIBE_MODEL`, дефолт `google/gemini-2.5-pro` — отдельного Gemini-ключа НЕ нужно); ключи самого Mango (`vpbx_api_key`/`vpbx_api_salt`) — per-company в БД (Fernet), НЕ в env. Фронт build-time: `VITE_API_BASE_URL=https://glafira.dclouds.ru/api/v1`.
- Порты бек/фронт — на `127.0.0.1` (наружу только через общий nginx). БД-контейнер без публикации порта.
- CORS в `main.py` читает из env (НЕ хардкод localhost).
- `X-Forwarded-Proto $scheme` в nginx обязателен (Secure-cookie, иначе авторизация слетает).
- nginx **общий** — добавлять только свой server-блок, `nginx -t` перед reload, чужие не трогать.
- При проверке фронта в браузере — **hard-reload (Ctrl+Shift+R)**, CSS/шрифты кэшируются.
- Прод-БД персистентна (named volume); сид НЕ запускается автодеплоем — только вручную. Перед прод-сидом — бэкап БД.

---

## 7. КОМАНДЫ

> Бэкенд-команды выполняются на VPS в контейнере backend (локального рантайма нет). Фронтовые — локально.

**Бэкенд (на VPS, `docker compose -f docker-compose.prod.yml run --rm backend ...`):**
```bash
pytest                                    # тесты (offline, LLM-ключ пуст)
alembic upgrade head                      # миграции
alembic revision --autogenerate -m "..."  # новая миграция
python -m app.seed                        # базовый seed
python -m app.seed_demo                   # демо-данные (сносит/пересоздаёт demo)
```

**Фронтенд (локально):**
```bash
cd frontend
npm run dev          # локальная разработка
npm run build        # production-сборка (tsc -b && vite build)
npx tsc --noEmit     # проверка типов
npm run types:gen    # регенерация типов из ../contracts/openapi.json -> src/api/types.ts
```

**Контракт:** после изменения схем бека — регенерировать `contracts/openapi.json` (нужен живой бэк), затем `npm run types:gen`. Пока сервера нет — новые тела через локальный тип + `as`-cast, и пометить в отчёте, что openapi не регенерён.

---

## 8. ЧЕК-ЛИСТ ПЕРЕД КОММИТОМ

- Фронт: `tsc --noEmit` + `npm run build` — **чистые** (прогнать обязательно). Бек: тесты написаны (прогон на VPS, если локально нечем — не утверждать «зелёный» голословно).
- `grep` по новым/изменённым местам: нет `console.log`, нет `alert()`, нет mock/хардкод-фейков, нет выдуманных токенов в `tokens.css`, нет несуществующих эндпоинтов в тестах.
- Изменяющие действия → `audit_log`; новые записи → `company_id`.
- Контракт: openapi регенерён, если есть живой сервер; иначе локальный тип + cast + явная пометка.
- Обратная совместимость: seed (базовый + demo) не сломан, существующие данные/воронки целы.
- При пересборке экрана: функционал из чек-листа жив (проверить руками/диффом, НЕ по отчёту агента); `.submenu-search` не тронут; CSS scoped; сверено с `project/` (включая новые элементы — ближайший идиом, не своё).
- Bump `APP_VERSION` (`frontend/src/lib/version.ts`).
- **Заголовок коммита начинается с `vX.Y.Z`** (`vX.Y.Z тип(scope): описание`) — первым токеном, ВСЕГДА.
- Релиз: коммит в `main` + `git push` (= автодеплой). Затем ручная проверка в браузере на VPS (hard-reload): визуал + функционал.
