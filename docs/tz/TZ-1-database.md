# ТЗ-1. Схема базы данных PostgreSQL

> **Кому:** FastAPI-агент.
> **Зависит от:** ТЗ-0 (соглашения, company_id, ПдН, аудит).
> **Результат:** SQLAlchemy 2.0 модели + первая Alembic-миграция, поднимающая всю схему.

---

## 0. Общие правила схемы

1. **Все PK — `UUID` (server_default `gen_random_uuid()`).** Включить расширение `pgcrypto` или использовать `uuid-ossp`. В первой миграции: `CREATE EXTENSION IF NOT EXISTS pgcrypto;`
2. **Все доменные таблицы** имеют `company_id UUID NOT NULL` (FK → `companies.id`). Реализовать миксином `CompanyMixin`.
3. **Все таблицы** имеют `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` и `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` (обновляется триггером или в ORM). Миксин `TimestampMixin`.
4. **Мягкое удаление** где имеет смысл (кандидаты, вакансии): `deleted_at TIMESTAMPTZ NULL`. Запросы по умолчанию фильтруют `deleted_at IS NULL`.
5. **Денормализация счётчиков** (например, число кандидатов на вакансии) — НЕ хранить в колонках, считать запросом ИЛИ кэшировать в отдельном вычисляемом поле только если упрётся в производительность. В MVP — считаем запросом.
6. **Enum'ы** — реализовать как PostgreSQL ENUM-типы ИЛИ `VARCHAR + CHECK`. Рекомендую `VARCHAR + CHECK` (проще менять значения миграцией, чем ALTER TYPE). Значения фиксированы в этом ТЗ.
7. **Индексы** — указаны явно у каждой таблицы. Как минимум: FK-колонки, поля сортировки/фильтрации.

---

## 1. companies — компании (тенанты-заглушка)

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| name | VARCHAR(255) | NOT NULL | Название компании |
| created_at | TIMESTAMPTZ | NOT NULL | |
| updated_at | TIMESTAMPTZ | NOT NULL | |

В seed-данных создаётся ОДНА компания с id = `DEFAULT_COMPANY_ID` из конфига.

---

## 2. users — пользователи (рекрутёры, менеджеры, админы)

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK companies, NOT NULL | |
| email | VARCHAR(255) | NOT NULL, UNIQUE | Логин |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt |
| full_name | VARCHAR(255) | NOT NULL | ФИО (напр. «Анна Седова») |
| role | VARCHAR(20) | NOT NULL, CHECK in (admin, recruiter, manager) | |
| position | VARCHAR(120) | NULL | Должность («Старший рекрутер») |
| avatar_url | VARCHAR(500) | NULL | |
| timezone | VARCHAR(50) | NOT NULL DEFAULT 'Europe/Moscow' | |
| is_active | BOOLEAN | NOT NULL DEFAULT true | |
| created_at, updated_at | TIMESTAMPTZ | | |

Индексы: `email` (unique), `company_id`.
Seed: один admin-пользователь «Анна Седова», роль recruiter→admin (для входа).

---

## 3. clients — заказчики / клиенты (для агентского режима)

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| name | VARCHAR(255) | NOT NULL | Компания-заказчик |
| contact_person | VARCHAR(255) | NULL | Контактное лицо («Иван Петров») |
| created_at, updated_at | | | |

Индексы: `company_id`.

---

## 4. vacancies — вакансии

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| name | VARCHAR(255) | NOT NULL | «Frontend-разработчик (Senior)» |
| sort_order | INTEGER | NOT NULL DEFAULT 500 | Порядок в сайдбаре (меньше = выше) |
| client_id | UUID | FK clients, NULL | Заказчик |
| city | VARCHAR(120) | NULL | |
| deadline | DATE | NULL | Дедлайн закрытия |
| positions_count | INTEGER | NOT NULL DEFAULT 1 | Сколько человек нанимаем |
| department | VARCHAR(120) | NULL | Отдел |
| employment_type | VARCHAR(40) | NULL | Тип занятости |
| is_confidential | BOOLEAN | NOT NULL DEFAULT false | |
| salary_from | INTEGER | NULL | Вилка от (руб) |
| salary_to | INTEGER | NULL | Вилка до (руб) |
| currency | VARCHAR(3) | NOT NULL DEFAULT 'RUB' | |
| description | TEXT | NULL | Тело описания |
| status | VARCHAR(20) | NOT NULL DEFAULT 'active', CHECK in (active, paused, archived) | |
| archive_result | VARCHAR(20) | NULL, CHECK in (hired, cancelled, frozen) | Итог при архивации |
| closed_at | DATE | NULL | Дата закрытия |
| funnel_template | VARCHAR(40) | NOT NULL DEFAULT 'default' | default/mass/technical/sales |
| glafira_mode | VARCHAR(1) | NOT NULL DEFAULT 'A', CHECK in (A, B, C) | Режим автономии: A полуавтомат, B автомат, C под контролем |
| responsible_user_id | UUID | FK users, NULL | Ответственный рекрутёр |
| external_source | VARCHAR(40) | NULL | hh / avito — если опубликована во внешнем источнике |
| external_id | VARCHAR(120) | NULL | ID вакансии во внешнем источнике |
| external_url | VARCHAR(500) | NULL | Ссылка на оригинал |
| created_at, updated_at | | | |
| deleted_at | TIMESTAMPTZ | NULL | Мягкое удаление |

Индексы: `company_id`, `status`, `sort_order`, `responsible_user_id`, `(external_source, external_id)`.

### 4.1 vacancy_team — команда вакансии (M2M users)

| Колонка | Тип | Ограничения |
|---|---|---|
| id | UUID | PK |
| vacancy_id | UUID | FK vacancies, NOT NULL |
| user_id | UUID | FK users, NOT NULL |
| is_responsible | BOOLEAN | NOT NULL DEFAULT false |

Уникальность: `(vacancy_id, user_id)`. Индекс: `vacancy_id`.

### 4.2 vacancy_stages — этапы воронки вакансии

Воронка настраивается на уровне вакансии (шаблон + редактирование этапов). Но базовый набор фиксирован (см. §6 STAGES). В MVP можно хранить набор этапов вакансии как упорядоченный список:

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| vacancy_id | UUID | FK vacancies, NOT NULL | |
| stage_key | VARCHAR(20) | NOT NULL | response/selected/recruiter/interview/manager/offer/hired/rejected/added |
| label | VARCHAR(60) | NOT NULL | Отображаемое имя |
| order_index | INTEGER | NOT NULL | Порядок |
| is_terminal | BOOLEAN | NOT NULL DEFAULT false | hired/rejected |

Индекс: `vacancy_id`. При создании вакансии заполняется из шаблона.

---

## 5. candidates — кандидаты (общая база)

Кандидат существует НЕЗАВИСИМО от вакансий — это общая база компании. Участие в вакансиях — через `applications` (§7).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| display_number | VARCHAR(10) | NULL | Внешний номер («#029») |
| last_name | VARCHAR(120) | NOT NULL | Фамилия |
| first_name | VARCHAR(120) | NOT NULL | Имя |
| middle_name | VARCHAR(120) | NULL | Отчество |
| birth_date | DATE | NULL | ДР (для возраста) |
| gender | VARCHAR(10) | NULL, CHECK in (male, female) | |
| city | VARCHAR(120) | NULL | Город |
| region | VARCHAR(120) | NULL | Область |
| phone | VARCHAR(20) | NULL | Телефон (E.164 или маска) |
| email | VARCHAR(255) | NULL | |
| salary_expectation | INTEGER | NULL | Ожидаемая ЗП (руб) |
| currency | VARCHAR(3) | NOT NULL DEFAULT 'RUB' | |
| last_position | VARCHAR(255) | NULL | Должность с последнего места |
| last_company | VARCHAR(255) | NULL | Последняя компания |
| last_period | VARCHAR(120) | NULL | Период работы (текст) |
| source | VARCHAR(40) | NOT NULL, CHECK | hh / avito / telegram / referral / direct / agency / import / manual / other |
| preferred_channel | VARCHAR(20) | NOT NULL DEFAULT 'telegram', CHECK in (telegram, email, phone) | Предпочтительный способ связи |
| resume_text | TEXT | NULL | Парсенный текст резюме |
| resume_summary | TEXT | NULL | AI-summary резюме |
| ai_score | INTEGER | NULL | Глобальный AI-скоринг 0–100 (last) |
| messengers | JSONB | NOT NULL DEFAULT '[]' | Найденные мессенджеры: ["telegram","whatsapp"] |
| is_duplicate | BOOLEAN | NOT NULL DEFAULT false | Помечен как дубль |
| duplicate_of | UUID | FK candidates, NULL | На кого ссылается дубль |
| is_anonymized | BOOLEAN | NOT NULL DEFAULT false | Анонимизирован по 152-ФЗ |
| external_source | VARCHAR(40) | NULL | Откуда импортирован |
| external_id | VARCHAR(120) | NULL | ID в источнике |
| created_at, updated_at | | | |
| deleted_at | TIMESTAMPTZ | NULL | |

Индексы: `company_id`, `(last_name, first_name)`, `city`, `ai_score`, `source`, `(external_source, external_id)`, GIN на `messengers`.

> **Возраст** не хранится — вычисляется из `birth_date` на лету.

### 5.1 candidate_experience — опыт работы

| Колонка | Тип | Описание |
|---|---|---|
| id | UUID PK | |
| candidate_id | UUID FK, NOT NULL | |
| position | VARCHAR(255) NOT NULL | Должность |
| company | VARCHAR(255) | Компания |
| period | VARCHAR(120) | Период (текст: «апрель 2024 — наст. время») |
| description | TEXT | Обязанности/достижения |
| order_index | INTEGER NOT NULL | |

Индекс: `candidate_id`.

### 5.2 candidate_skills — навыки

| id UUID PK | candidate_id UUID FK | skill VARCHAR(120) | order_index INTEGER |

Индекс: `candidate_id`.

### 5.3 candidate_education — образование

| id UUID PK | candidate_id UUID FK | institution VARCHAR(255) | specialty VARCHAR(255) | years VARCHAR(40) | order_index INTEGER |

### 5.4 candidate_tags — теги (M2M)

Теги — пользовательские маркеры. Справочник тегов + связь:

`tags`: | id UUID PK | company_id UUID FK | name VARCHAR(80) NOT NULL | color VARCHAR(7) NULL |
Уникальность: `(company_id, name)`.

`candidate_tags`: | id UUID PK | candidate_id UUID FK | tag_id UUID FK |
Уникальность: `(candidate_id, tag_id)`.

### 5.5 candidate_extra — дополнительно (1:1 или JSONB)

Хранить как JSONB-поле `extra` прямо в `candidates` ИЛИ отдельной таблицей. Рекомендую JSONB:
```json
{
  "languages": ["Русский", "English B2"],
  "relocation": false,
  "business_trips": "раз в месяц",
  "remote": "предпочитает"
}
```

---

## 6. STAGES — справочник этапов воронки (константа кода, не таблица)

Базовый набор (из Экрана 03). Хранится как enum/константа в коде, копируется в `vacancy_stages` при создании вакансии.

| stage_key | label | color | terminal |
|---|---|---|---|
| response | Отклик | #5B6573 | нет |
| added | Добавлен | #7E5CF0 | нет (system) |
| selected | Отобран | #9AA3AE | нет |
| recruiter | Контакт с рекрутером | #7AB4F5 | нет |
| interview | Интервью | #2A8AF0 | нет |
| manager | Контакт с менеджером | #5778E8 | нет |
| offer | Оффер | #E0A21A | нет |
| hired | Нанят | #16A34A | да |
| rejected | Отказ | #DC4646 | да |

---

## 7. applications — участие кандидата в вакансии (СЕРДЦЕ ВОРОНКИ)

Один кандидат может участвовать в нескольких вакансиях. Каждое участие — отдельная запись. Это связующая таблица между `candidates` и `vacancies` с богатым состоянием.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| candidate_id | UUID | FK candidates, NOT NULL | |
| vacancy_id | UUID | FK vacancies, NOT NULL | |
| stage | VARCHAR(20) | NOT NULL DEFAULT 'response', CHECK (см. STAGES) | Текущий этап |
| ai_score | INTEGER | NULL | Скоринг AI на момент отбора на ЭТУ вакансию |
| selected_at | TIMESTAMPTZ | NULL | Когда Глафира добавила в воронку |
| stage_changed_at | TIMESTAMPTZ | NULL | Когда перешёл в текущий этап |
| reject_reason | VARCHAR(120) | NULL | Причина отказа (если stage=rejected) |
| reject_side | VARCHAR(20) | NULL, CHECK in (candidate, company) | Кто отказал |
| is_repeat | BOOLEAN | NOT NULL DEFAULT false | Повторный отклик |
| source | VARCHAR(40) | NULL | Источник именно этого отклика |
| created_at, updated_at | | | |

Уникальность: `(candidate_id, vacancy_id)` — кандидат участвует в вакансии один раз.
Индексы: `company_id`, `vacancy_id`, `candidate_id`, `stage`, `(vacancy_id, stage)`, `selected_at`.

### 7.1 stage_history — история переходов по этапам

| id UUID PK | application_id UUID FK NOT NULL | from_stage VARCHAR(20) NULL | to_stage VARCHAR(20) NOT NULL | actor_type VARCHAR(10) CHECK in (human, ai, system) | actor_user_id UUID FK users NULL | reason VARCHAR(255) NULL | created_at TIMESTAMPTZ |

Индекс: `application_id`, `created_at`.

---

## 8. consents — согласия на обработку ПД (152-ФЗ)

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| candidate_id | UUID | FK candidates, NOT NULL | |
| number | VARCHAR(40) | NOT NULL, UNIQUE | «PD-029/26» |
| status | VARCHAR(20) | NOT NULL, CHECK in (pending, signed, revoked) | |
| channel | VARCHAR(20) | NULL | Канал подписания (telegram/email/...) |
| signed_at | TIMESTAMPTZ | NULL | Когда подписано |
| requested_at | TIMESTAMPTZ | NULL | Когда запрошено |
| revoked_at | TIMESTAMPTZ | NULL | Когда отозвано |
| created_at, updated_at | | | |

Индексы: `candidate_id`, `status`, `number`.

> **Бизнес-правило:** верификация (§11) доступна, только если у кандидата есть consent со `status='signed'`. Иначе API → `403 CONSENT_REQUIRED`.

---

## 9. messages — чат с кандидатом (все каналы)

Унифицированная переписка по всем каналам (TG/hh/WhatsApp/Max/SMS/Email).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| candidate_id | UUID | FK candidates, NOT NULL | |
| application_id | UUID | FK applications, NULL | Контекст вакансии (для разделителей в общей базе) |
| channel | VARCHAR(20) | NOT NULL, CHECK in (telegram, hh, whatsapp, max, sms, email) | |
| direction | VARCHAR(10) | NOT NULL, CHECK in (in, out) | Входящее/исходящее |
| sender_type | VARCHAR(10) | NOT NULL, CHECK in (candidate, recruiter, ai) | AI = Глафира |
| sender_user_id | UUID | FK users, NULL | Кто из команды отправил |
| body | TEXT | NOT NULL | Текст сообщения |
| sent_at | TIMESTAMPTZ | NOT NULL | |
| created_at | TIMESTAMPTZ | | |

Индексы: `candidate_id`, `(candidate_id, sent_at)`, `channel`.

---

## 10. documents — файлы кандидата

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| candidate_id | UUID | FK candidates, NOT NULL | |
| filename | VARCHAR(255) | NOT NULL | «Резюме.pdf» |
| file_type | VARCHAR(20) | NOT NULL | pdf/img/doc |
| size_bytes | BIGINT | NOT NULL | |
| storage_path | VARCHAR(500) | NOT NULL | Путь в хранилище (локально в MVP) |
| source | VARCHAR(60) | NULL | «импорт hh» |
| uploaded_by | UUID | FK users, NULL | |
| created_at | TIMESTAMPTZ | | |

Индекс: `candidate_id`.

> Хранилище файлов в MVP — локальная папка `backend/storage/` (или volume). Интерфейс storage-сервиса абстрактный, чтобы заменить на S3 позже.

---

## 11. verifications — верификация по реестрам (MOCK в MVP)

Результат проверки кандидата. В MVP заполняется мок-сервисом, но схема — финальная.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| candidate_id | UUID | FK candidates, NOT NULL | |
| consent_id | UUID | FK consents, NOT NULL | Обязательно — без ПдН нельзя |
| checked_at | TIMESTAMPTZ | NOT NULL | Дата проверки |
| status | VARCHAR(20) | NOT NULL, CHECK in (clean, info, warn, risk) | Сводный статус |
| blocks | JSONB | NOT NULL | Результаты по 7 блокам (см. ниже) |
| created_at, updated_at | | | |

`blocks` — массив результатов по блокам из Экрана 04 §8.5:
```json
[
  {
    "key": "inn",
    "title": "ИНН — идентификация",
    "sources": [{"name": "ФНС", "type": "reg"}, {"name": "DaData", "type": "api"}],
    "status": "clean",
    "data": { "inn": "771234567890", "match": "full" }
  },
  { "key": "fssp", "title": "Исполнительные производства", "sources": [...], "status": "warn", "data": {...} },
  { "key": "bankruptcy", "title": "Банкротство и связи с юрлицами", ... },
  { "key": "registries", "title": "Реестры и санкции", ... },
  { "key": "public", "title": "Публичная экспертиза", ... },
  { "key": "ai_intel", "title": "AI-разведка", ... },
  { "key": "alimony", "title": "Алиментные обязательства", ... }
]
```
Типы источников: `api` / `reg` / `pub` / `ai`. Статусы: `clean` / `info` / `warn` / `risk`.

Индексы: `candidate_id`, `consent_id`.

---

## 12. ai_evaluations — оценки AI (скоринг по вакансиям)

Развёрнутая оценка Глафиры. Кандидат может иметь оценку по каждой вакансии (контекст разный).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| candidate_id | UUID | FK candidates, NOT NULL | |
| application_id | UUID | FK applications, NULL | По какой вакансии (NULL = общая оценка резюме) |
| score | INTEGER | NOT NULL | 0–100 |
| verdict | VARCHAR(20) | NOT NULL, CHECK in (good, partial, bad) | Подходит/частично/не подходит |
| summary | TEXT | NOT NULL | Краткий вердикт (1–2 абзаца) |
| strengths | JSONB | NOT NULL DEFAULT '[]' | Сильные стороны (массив строк) |
| risks | JSONB | NOT NULL DEFAULT '[]' | Слабые стороны/риски |
| requirements_match | JSONB | NOT NULL DEFAULT '[]' | Таблица соответствия: [{req, status, comment}] |
| forecast | TEXT | NULL | Прогноз срока выхода |
| model | VARCHAR(60) | NULL | Какая модель считала |
| created_at, updated_at | | | |

Индексы: `candidate_id`, `application_id`.

---

## 13. comments — внутренние комментарии по кандидату

| id UUID PK | company_id UUID FK | candidate_id UUID FK NOT NULL | application_id UUID FK NULL | author_user_id UUID FK users NOT NULL | body TEXT NOT NULL | mentions JSONB DEFAULT '[]' (массив user_id) | created_at TIMESTAMPTZ |

Индекс: `candidate_id`, `created_at`.

---

## 14. ПУЛЬС: employees — сотрудники в адаптации

Когда кандидат становится `hired`, создаётся сотрудник в Пульсе.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| candidate_id | UUID | FK candidates, NOT NULL | Ссылка на исходного кандидата |
| application_id | UUID | FK applications, NULL | Из какой вакансии нанят |
| full_name | VARCHAR(255) | NOT NULL | |
| position | VARCHAR(255) | NULL | Должность |
| department | VARCHAR(120) | NULL | Отдел |
| manager_user_id | UUID | FK users, NULL | Руководитель |
| recruiter_user_id | UUID | FK users, NULL | Кто рекрутил |
| hire_source | VARCHAR(40) | NULL | Источник найма (для аналитики) |
| start_date | DATE | NOT NULL | Дата выхода |
| probation_days | INTEGER | NOT NULL DEFAULT 90 | Длина испытательного |
| status | VARCHAR(20) | NOT NULL DEFAULT 'onboarding', CHECK in (onboarding, passed, left) | |
| risk_level | VARCHAR(10) | NOT NULL DEFAULT 'low', CHECK in (low, mid, high) | Риск ухода |
| enps | INTEGER | NULL | eNPS (-100..100) |
| left_at | DATE | NULL | Дата ухода |
| left_reason | VARCHAR(255) | NULL | |
| created_at, updated_at | | | |

Индексы: `company_id`, `status`, `risk_level`, `manager_user_id`, `start_date`.

> **День адаптации** = `today - start_date`, вычисляется на лету (не хранится).

### 14.1 pulse_surveys — пульс-опросы

| id UUID PK | company_id UUID FK | employee_id UUID FK NOT NULL | template_key VARCHAR(60) | type VARCHAR(20) CHECK in (weekly, monthly, special, enps) | sent_at TIMESTAMPTZ | answered_at TIMESTAMPTZ NULL | overall_score NUMERIC(3,1) NULL | answers JSONB DEFAULT '[]' | created_at |

`answers`: `[{question, type, value, comment}]`.
Индексы: `employee_id`, `(employee_id, sent_at)`.

### 14.2 pulse_plan_items — план адаптации (чек-лист)

| id UUID PK | employee_id UUID FK NOT NULL | phase VARCHAR(20) CHECK in (welcome, month1, month2, month3) | title VARCHAR(255) NOT NULL | deadline_day INTEGER (день N от выхода) | responsible VARCHAR(20) CHECK in (hr, manager, employee) | is_done BOOLEAN DEFAULT false | done_at TIMESTAMPTZ NULL | order_index INTEGER |

Индекс: `employee_id`.

### 14.3 pulse_alerts — алерты Глафиры по сотрудникам

| id UUID PK | company_id UUID FK | employee_id UUID FK NOT NULL | level VARCHAR(10) CHECK in (high, mid, info) | title VARCHAR(255) NOT NULL | context TEXT | action_type VARCHAR(40) (open_card/contact/run_survey/remind_manager) | is_dismissed BOOLEAN DEFAULT false | created_at |

Индексы: `employee_id`, `(company_id, is_dismissed)`.

---

## 15. events — глобальная лента событий (Экран 01)

Живая лента всех значимых событий системы.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| type | VARCHAR(20) | NOT NULL, CHECK in (qual, new, score, offer, move) | Тип события (цвет иконки) |
| actor_type | VARCHAR(10) | NOT NULL, CHECK in (human, ai, system) | |
| actor_user_id | UUID | FK users, NULL | |
| text | TEXT | NOT NULL | Готовый текст события (с разметкой сущностей) |
| entities | JSONB | NOT NULL DEFAULT '[]' | Ссылки на сущности: [{type, id, label}] |
| candidate_id | UUID | FK, NULL | |
| vacancy_id | UUID | FK, NULL | |
| created_at | TIMESTAMPTZ | NOT NULL | |

Индексы: `company_id`, `created_at DESC`, `candidate_id`.

> «Все действия» в карточке кандидата (Экран 04 таб) — это выборка `events WHERE candidate_id = ?`. Глобальная лента — последние N по компании.

---

## 16. attention_items — «Требуют внимания» (Экран 01)

Сигналы по вакансиям, которые залипли/горят. Могут вычисляться на лету правилами ЛИБО храниться. В MVP — **вычисляются сервисом** на основе данных (нет движения N дней, необработанные отклики, дедлайн близко). Таблица НЕ нужна, если логика детерминирована. Если решите кэшировать — схема:

| id UUID PK | company_id UUID FK | vacancy_id UUID FK | kind VARCHAR(20) CHECK in (urgent, warn, deadline) | text VARCHAR(255) | created_at |

> **Решение для MVP:** вычислять на лету в `services/attention.py`. Не создавать таблицу.

---

## 17. audit_log — аудит всех действий (сквозной, ТЗ-0 §5.3)

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| id | UUID | PK | |
| company_id | UUID | FK, NOT NULL | |
| actor_type | VARCHAR(10) | NOT NULL, CHECK in (human, ai, system) | |
| actor_user_id | UUID | FK users, NULL | |
| action | VARCHAR(60) | NOT NULL | create/update/delete/stage_change/reject/hire/... |
| entity_type | VARCHAR(60) | NOT NULL | vacancy/candidate/application/... |
| entity_id | UUID | NULL | |
| changes | JSONB | NULL | {field: {old, new}} |
| ip | VARCHAR(45) | NULL | |
| created_at | TIMESTAMPTZ | NOT NULL | |

Индексы: `company_id`, `(entity_type, entity_id)`, `created_at`, `actor_user_id`.

---

## 18. settings: справочники

### 18.1 reject_reasons — причины отказа (Настройки → Воронка по умолчанию)

Справочник, используется в popover «Отклонить» (Экран 04), bulk-bar (Экран 03), отчёте «Отказы» (Экран 06).

| id UUID PK | company_id UUID FK | side VARCHAR(20) CHECK in (candidate, company) | label VARCHAR(120) NOT NULL | order_index INTEGER | is_active BOOLEAN DEFAULT true |

Seed (из Экрана 03/09):
- side=candidate: «Не вышел на связь», «Не устроила ЗП», «Принял другой оффер», «Не устроил график», «Слишком далеко от дома».
- side=company: «Несоответствие опыта», «Несоответствие навыков», «Не прошёл интервью», «Не прошёл СБ», «Завышенные ожидания по ЗП».

### 18.2 email_templates — шаблоны писем

| id UUID PK | company_id UUID FK | name VARCHAR(120) | event_type VARCHAR(40) (invite/offer/reject) | subject VARCHAR(255) | body TEXT | is_enabled BOOLEAN DEFAULT true | created_at, updated_at |

### 18.3 survey_templates — шаблоны опросов Пульса

| id UUID PK | company_id UUID FK | name VARCHAR(120) | trigger_day INTEGER NULL | interval_days INTEGER NULL | channels JSONB | questions JSONB | is_enabled BOOLEAN | created_at, updated_at |

### 18.4 glafira_settings — настройки Глафиры (1 строка на компанию)

| id UUID PK | company_id UUID FK UNIQUE | tone VARCHAR(20) CHECK in (friendly, formal, business) | use_informal BOOLEAN (на ты/вы) | emoji_level VARCHAR(20) | auto_reject_below INTEGER (порог автоотказа) | auto_select_above INTEGER (порог автоотбора) | days_no_response INTEGER (дней до закрытия) | stop_words JSONB | default_mode VARCHAR(1) CHECK in (A,B,C) | created_at, updated_at |

### 18.5 integrations — интеграции (источники, мессенджеры)

| id UUID PK | company_id UUID FK | provider VARCHAR(40) (hh/avito/telegram/whatsapp/...) | status VARCHAR(20) CHECK in (connected, disconnected) | config JSONB (токены, ключи — шифровать!) | created_at, updated_at |

> Токены в `config` — **шифровать** (Fernet/симметрично, ключ из env). Не хранить в открытом виде.

---

## 19. Диаграмма связей (текстом)

```
companies ──┬─< users
            ├─< clients
            ├─< vacancies ──┬─< vacancy_team >── users
            │               ├─< vacancy_stages
            │               └─< applications
            ├─< candidates ─┬─< candidate_experience
            │               ├─< candidate_skills
            │               ├─< candidate_education
            │               ├─< candidate_tags >── tags
            │               ├─< consents
            │               ├─< messages
            │               ├─< documents
            │               ├─< verifications (req. consent)
            │               ├─< ai_evaluations
            │               ├─< comments
            │               └─< applications (M2M candidate×vacancy)
            │                      └─< stage_history
            ├─< employees (Пульс) ─┬─< pulse_surveys
            │   ↑ candidate_id      ├─< pulse_plan_items
            │                       └─< pulse_alerts
            ├─< events
            ├─< audit_log
            └─< settings: reject_reasons, email_templates,
                          survey_templates, glafira_settings, integrations
```

---

## 20. Задачи для агента (чек-лист)

1. Поднять `pgcrypto`, создать миксины `TimestampMixin`, `CompanyMixin` в `models/base.py`.
2. Реализовать все модели SQLAlchemy 2.0 (typed, `Mapped[...]`) по таблицам §1–18.
3. Настроить Alembic (`env.py` под async-engine), сгенерировать первую миграцию `0001_initial` со всей схемой.
4. Написать seed-скрипт (`backend/app/seed.py`): 1 компания, 1 admin-юзер (Анна Седова), справочник `reject_reasons`, дефолтные `glafira_settings`, набор STAGES.
5. Проверить, что `alembic upgrade head` поднимает чистую БД без ошибок, `downgrade` откатывает.
6. Все enum-поля — через `VARCHAR + CHECK` (значения строго из этого ТЗ).
7. Все FK — с явным `ondelete` (CASCADE для дочерних типа experience/skills; RESTRICT/SET NULL где удаление родителя не должно каскадить).

---

## 21. Открытые вопросы к продакт-оунеру (отметить, не блокируют старт схемы)

- Нужна ли отдельная сущность «нанимающий менеджер» вне `users`, или менеджер — это роль пользователя? (Сейчас: роль `manager` в `users`.)
- Хранить ли историю изменения скоринга или только последний? (Сейчас: `ai_evaluations` хранит все оценки, в `candidates.ai_score` — последняя.)
- Объединение дублей — каскадное слияние applications/messages? (Вне MVP, но повлияет на `duplicate_of`.)
