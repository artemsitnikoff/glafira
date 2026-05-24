# ТЗ-2. API-контракты, Pydantic-схемы и TS-типы

> **Кому:** FastAPI-агент (реализует) + React-агент (берёт TS-типы и список эндпойнтов).
> **Зависит от:** ТЗ-0 (соглашения), ТЗ-1 (схема БД).
> **Результат:** все роутеры `app/api/*`, все схемы `app/schemas/*`, файл `frontend/src/api/types.ts`.

---

## 0. Общие конвенции для всех схем

### 0.1 Базовые Pydantic-схемы (app/schemas/base.py)

```python
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from uuid import UUID

class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class Paginated(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    pages: int
```

### 0.2 Общие query-параметры (app/core/pagination.py)

```python
from fastapi import Query
from dataclasses import dataclass

@dataclass
class PageParams:
    page: int = Query(1, ge=1)
    page_size: int = Query(24, ge=1, le=100)
    sort: str | None = Query(None)
    order: str = Query("desc", pattern="^(asc|desc)$")
```

### 0.3 Формат ошибки (app/core/errors.py)

Все исключения → единый JSON (ТЗ-0 §3.3). Реализовать `AppError(code, message, http_status, details=None)` + обработчик `@app.exception_handler`. Pydantic-валидация (422) маппится в тот же формат с `details`.

### 0.4 Базовые TS-типы (frontend/src/api/types.ts — шапка)

```typescript
export type UUID = string;
export type ISODateTime = string; // "2026-04-08T14:32:00Z"
export type ISODate = string;     // "2026-04-08"

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details: { field: string; message: string }[] | null;
  };
}

// Enums (зеркало CHECK-констрейнтов из ТЗ-1)
export type UserRole = "admin" | "recruiter" | "manager";
export type VacancyStatus = "active" | "paused" | "archived";
export type GlafiraMode = "A" | "B" | "C";
export type StageKey =
  | "response" | "added" | "selected" | "recruiter"
  | "interview" | "manager" | "offer" | "hired" | "rejected";
export type CandidateSource =
  | "hh" | "avito" | "telegram" | "referral" | "direct"
  | "agency" | "import" | "manual" | "other";
export type Channel = "telegram" | "hh" | "whatsapp" | "max" | "sms" | "email";
export type RiskLevel = "low" | "mid" | "high";
export type ConsentStatus = "pending" | "signed" | "revoked";
export type VerifyStatus = "clean" | "info" | "warn" | "risk";
export type ActorType = "human" | "ai" | "system";
```

---

## 1. ДОМЕН: Auth (app/api/auth.py)

### Эндпойнты

| Метод | Путь | Описание | Авторизация |
|---|---|---|---|
| POST | `/auth/login` | Вход по email+пароль | нет |
| POST | `/auth/refresh` | Обновить access по refresh-cookie | refresh-cookie |
| POST | `/auth/logout` | Выход (чистит refresh-cookie) | да |
| GET | `/auth/me` | Текущий пользователь | да |

### Схемы (Pydantic)

```python
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # refresh — в HttpOnly cookie, не в теле

class UserMe(ORMBase):
    id: UUID
    email: str
    full_name: str
    role: str          # admin|recruiter|manager
    position: str | None
    avatar_url: str | None
    timezone: str
```

### TS-типы

```typescript
export interface LoginRequest { email: string; password: string; }
export interface TokenResponse { access_token: string; token_type: string; }
export interface UserMe {
  id: UUID; email: string; full_name: string; role: UserRole;
  position: string | null; avatar_url: string | null; timezone: string;
}
```

### Бизнес-правила
- `POST /auth/login`: неверные креды → `401 INVALID_CREDENTIALS`. Неактивный юзер → `403 USER_INACTIVE`.
- access живёт `ACCESS_TOKEN_EXPIRE_MINUTES`, refresh — `REFRESH_TOKEN_EXPIRE_DAYS`, refresh в HttpOnly+Secure+SameSite=Lax cookie.
- `get_current_user` (deps.py) парсит Bearer, грузит юзера, подставляет `company_id` в контекст запроса.

---

## 2. ДОМЕН: Users / Team (app/api/users.py)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/users` | Список пользователей компании (для селектов команды, фильтров) |
| GET | `/users/{id}` | Один пользователь |
| POST | `/users` | Создать (пригласить) — только admin |
| PATCH | `/users/{id}` | Изменить (роль, статус) — admin |

```python
class UserShort(ORMBase):    # для селектов, аватаров в списках
    id: UUID
    full_name: str
    position: str | None
    avatar_url: str | None
    role: str

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    role: str
    position: str | None = None

class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    position: str | None = None
    is_active: bool | None = None
```

```typescript
export interface UserShort {
  id: UUID; full_name: string; position: string | null;
  avatar_url: string | null; role: UserRole;
}
```

---

## 3. ДОМЕН: Vacancies (app/api/vacancies.py)

### Эндпойнты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/vacancies` | Список (для сайдбара и архива). Параметры: `status`, `search`, `sort` |
| GET | `/vacancies/{id}` | Одна вакансия (шапка воронки) |
| POST | `/vacancies` | Создать |
| PATCH | `/vacancies/{id}` | Редактировать |
| POST | `/vacancies/{id}/archive` | В архив (с итогом) |
| GET | `/vacancies/{id}/stages` | Этапы воронки этой вакансии со счётчиками |
| GET | `/vacancies/sidebar` | Спец-эндпойнт для сайдбара: активные + счётчики + «новых» + число архивных |

### Схемы

```python
class VacancySidebarItem(ORMBase):
    id: UUID
    name: str
    count: int            # всего кандидатов (computed)
    new_count: int        # новых откликов "+N" (computed)
    has_unread: bool      # точка непрочитанных

class VacancySidebar(BaseModel):
    items: list[VacancySidebarItem]
    archived_count: int

class VacancyStageCount(BaseModel):
    stage_key: str
    label: str
    color: str
    count: int
    is_terminal: bool

class VacancyDetail(ORMBase):
    id: UUID
    name: str
    sort_order: int
    client_id: UUID | None
    client_name: str | None          # join
    city: str | None
    deadline: date | None
    positions_count: int
    department: str | None
    employment_type: str | None
    is_confidential: bool
    salary_from: int | None
    salary_to: int | None
    currency: str
    description: str | None
    status: str
    glafira_mode: str
    responsible_user_id: UUID | None
    responsible_user: UserShort | None
    team: list[UserShort]
    external_source: str | None
    external_url: str | None
    created_at: datetime

class VacancyCreate(BaseModel):
    name: str
    sort_order: int = 500
    client_id: UUID | None = None
    city: str | None = None
    deadline: date | None = None
    positions_count: int = 1
    department: str | None = None
    employment_type: str | None = None
    is_confidential: bool = False
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str = "RUB"
    description: str | None = None
    funnel_template: str = "default"   # default|mass|technical|sales
    glafira_mode: str = "A"
    team: list[UUID] = []              # первый = ответственный
    # Автоматизация
    auto_move: bool = False
    auto_move_threshold: int | None = None
    auto_qa_from: str | None = None
    auto_qa_to: str | None = None
    auto_reject: bool = False

class VacancyUpdate(BaseModel):
    # все поля опциональны
    ...

class VacancyArchive(BaseModel):
    result: str   # hired|cancelled|frozen
```

### TS-типы

```typescript
export interface VacancySidebarItem {
  id: UUID; name: string; count: number; new_count: number; has_unread: boolean;
}
export interface VacancySidebar { items: VacancySidebarItem[]; archived_count: number; }

export interface VacancyStageCount {
  stage_key: StageKey; label: string; color: string; count: number; is_terminal: boolean;
}

export interface VacancyDetail {
  id: UUID; name: string; sort_order: number;
  client_id: UUID | null; client_name: string | null;
  city: string | null; deadline: ISODate | null;
  positions_count: number; department: string | null;
  employment_type: string | null; is_confidential: boolean;
  salary_from: number | null; salary_to: number | null; currency: string;
  description: string | null; status: VacancyStatus; glafira_mode: GlafiraMode;
  responsible_user_id: UUID | null; responsible_user: UserShort | null;
  team: UserShort[]; external_source: string | null; external_url: string | null;
  created_at: ISODateTime;
}

export interface VacancyCreate {
  name: string; sort_order?: number; client_id?: UUID | null;
  city?: string | null; deadline?: ISODate | null; positions_count?: number;
  department?: string | null; employment_type?: string | null;
  is_confidential?: boolean; salary_from?: number | null; salary_to?: number | null;
  currency?: string; description?: string | null;
  funnel_template?: "default" | "mass" | "technical" | "sales";
  glafira_mode?: GlafiraMode; team?: UUID[];
  auto_move?: boolean; auto_move_threshold?: number | null;
  auto_qa_from?: StageKey | null; auto_qa_to?: StageKey | null; auto_reject?: boolean;
}
```

### Бизнес-правила
- При `POST /vacancies` из `funnel_template` создаётся набор `vacancy_stages`. Шаблоны:
  - `default` — все 8 этапов (response→hired + rejected).
  - `mass` — упрощённая (response, selected, interview, hired, rejected).
  - `technical` — добавляет этап «Тестовое» (можно как кастомный stage_key `test`).
  - `sales` — стандартная.
- `team[0]` → `is_responsible=true`, проставляется `responsible_user_id`.
- `GET /vacancies/sidebar` — `count` = число applications (кроме rejected), `new_count` = applications в стадии `response` за последние 24ч, `has_unread` = есть непрочитанные сообщения/события.
- `POST /archive` → `status='archived'`, `archive_result`, `closed_at=today`. Пишет в audit_log.
- Сортировка сайдбара: по `sort_order ASC, name ASC`.

---

## 4. ДОМЕН: Candidates — общая база (app/api/candidates.py)

### Эндпойнты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/candidates` | Сетка общей базы. Фильтры: `search, city, exp, score_min/score_max, source, vacancy_id, stage, tags, added_period`. Сортировка: `added, score, name, activity` |
| GET | `/candidates/{id}` | Карточка кандидата (шапка + история участия) |
| POST | `/candidates` | Создать вручную |
| PATCH | `/candidates/{id}` | Изменить |
| DELETE | `/candidates/{id}` | Мягкое удаление |
| GET | `/candidates/{id}/applications` | История участия в вакансиях |
| POST | `/candidates/{id}/tags` | Добавить тег |
| DELETE | `/candidates/{id}/tags/{tag_id}` | Убрать тег |

### Схемы

```python
class TagOut(ORMBase):
    id: UUID
    name: str
    color: str | None

class CandidateCardVacancy(BaseModel):   # лейбл вакансии на карточке в сетке
    application_id: UUID
    vacancy_id: UUID
    vacancy_name: str
    stage: str
    stage_color: str
    is_last: bool

class CandidateGridItem(ORMBase):        # карточка в сетке (Экран 05)
    id: UUID
    display_number: str | None
    full_name: str
    age: int | None                      # computed из birth_date
    last_position: str | None
    last_company: str | None
    last_period: str | None
    ai_score: int | None
    avatar_url: str | None
    is_duplicate: bool
    has_pdn: bool                        # есть signed consent
    last_vacancy: CandidateCardVacancy | None
    other_vacancies_count: int           # бейдж "+N"

class CandidateExperienceOut(ORMBase):
    position: str; company: str | None; period: str | None; description: str | None

class CandidateDetail(ORMBase):
    id: UUID
    display_number: str | None
    last_name: str; first_name: str; middle_name: str | None
    full_name: str
    age: int | None
    birth_date: date | None
    gender: str | None
    city: str | None; region: str | None
    phone: str | None; email: str | None
    messengers: list[str]
    salary_expectation: int | None; currency: str
    last_position: str | None; last_company: str | None; last_period: str | None
    source: str
    preferred_channel: str
    resume_text: str | None; resume_summary: str | None
    ai_score: int | None
    has_pdn: bool
    is_duplicate: bool; duplicate_of: UUID | None
    is_anonymized: bool
    tags: list[TagOut]
    experience: list[CandidateExperienceOut]
    skills: list[str]
    extra: dict | None
    created_at: datetime

class ApplicationHistoryItem(ORMBase):   # строка в "Истории участия"
    application_id: UUID
    vacancy_id: UUID
    vacancy_name: str
    vacancy_status: str                  # active|archived
    stage: str
    stage_color: str
    client_name: str | None
    recruiter_name: str | None
    ai_score: int | None
    selected_at: datetime | None
    stage_changed_at: datetime | None
    reject_reason: str | None

class CandidateCreate(BaseModel):
    last_name: str
    first_name: str
    middle_name: str | None = None
    source: str                          # обязателен (ТЗ-1)
    phone: str | None = None
    email: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    city: str | None = None
    salary_expectation: int | None = None
    currency: str = "RUB"
    add_type: str = "manual"             # manual|resume|pool|hh_link
    vacancy_id: UUID | None = None       # если добавляем сразу в вакансию
    comment: str | None = None
```

### TS-типы (ключевые)

```typescript
export interface CandidateGridItem {
  id: UUID; display_number: string | null; full_name: string;
  age: number | null; last_position: string | null; last_company: string | null;
  last_period: string | null; ai_score: number | null; avatar_url: string | null;
  is_duplicate: boolean; has_pdn: boolean;
  last_vacancy: CandidateCardVacancy | null; other_vacancies_count: number;
}
export interface CandidateCardVacancy {
  application_id: UUID; vacancy_id: UUID; vacancy_name: string;
  stage: StageKey; stage_color: string; is_last: boolean;
}
export interface ApplicationHistoryItem {
  application_id: UUID; vacancy_id: UUID; vacancy_name: string;
  vacancy_status: VacancyStatus; stage: StageKey; stage_color: string;
  client_name: string | null; recruiter_name: string | null;
  ai_score: number | null; selected_at: ISODateTime | null;
  stage_changed_at: ISODateTime | null; reject_reason: string | null;
}
// CandidateDetail — полное зеркало Pydantic-схемы выше
```

### Бизнес-правила
- `age` вычисляется из `birth_date`.
- `has_pdn` = существует consent со `status='signed'`.
- `CandidateCreate`: валидно только если `last_name + first_name + source` заполнены (иначе `422`). Если `vacancy_id` задан — сразу создаётся `application` в стадии `added`.
- Фильтр `vacancy_id` в `GET /candidates` — кандидаты, у которых есть application на эту вакансию.
- Бесконечный скролл — через пагинацию `page_size=24`.
- Все фильтры синхронизируются с URL на фронте (бек просто принимает query).

---

## 5. ДОМЕН: Applications — воронка (app/api/applications.py)

### Эндпойнты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/vacancies/{vid}/applications` | Таблица воронки. Фильтры: `stage, search, score_min, salary_max, source, city, messenger, period, ready_relocate, repeat`. Сортировка: `score, name, phone, salary, city, date, stage, age` |
| GET | `/applications/{id}` | Одно участие (для карточки соискателя в контексте вакансии) |
| POST | `/applications/{id}/move` | Перевести на этап |
| POST | `/applications/{id}/reject` | Отклонить (причина + сторона) |
| POST | `/applications/{id}/restore` | Восстановить из отказа |
| POST | `/applications/bulk/move` | Массовый перевод |
| POST | `/applications/bulk/reject` | Массовый отказ |
| GET | `/applications/{id}/history` | История переходов (stage_history) |

### Схемы

```python
class ApplicationRow(ORMBase):           # строка таблицы воронки (Экран 03)
    id: UUID
    candidate_id: UUID
    display_number: str | None
    full_name: str
    avatar_url: str | None
    age: int | None
    last_position: str | None
    ai_score: int | None
    has_pdn: bool
    phone: str | None
    messengers: list[str]
    salary_expectation: int | None
    currency: str
    city: str | None
    stage: str
    stage_color: str
    selected_at: datetime | None         # "Дата отбора"

class MoveRequest(BaseModel):
    to_stage: str

class RejectRequest(BaseModel):
    reason: str
    side: str                            # candidate|company

class BulkMoveRequest(BaseModel):
    application_ids: list[UUID]
    to_stage: str

class BulkRejectRequest(BaseModel):
    application_ids: list[UUID]
    reason: str
    side: str

class StageHistoryItem(ORMBase):
    from_stage: str | None
    to_stage: str
    actor_type: str
    actor_name: str | None
    reason: str | None
    created_at: datetime
```

### TS-типы

```typescript
export interface ApplicationRow {
  id: UUID; candidate_id: UUID; display_number: string | null; full_name: string;
  avatar_url: string | null; age: number | null; last_position: string | null;
  ai_score: number | null; has_pdn: boolean; phone: string | null;
  messengers: string[]; salary_expectation: number | null; currency: string;
  city: string | null; stage: StageKey; stage_color: string;
  selected_at: ISODateTime | null;
}
export interface MoveRequest { to_stage: StageKey; }
export interface RejectRequest { reason: string; side: "candidate" | "company"; }
```

### Бизнес-правила
- `move`: нельзя в терминальный `hired` напрямую через обычный move без подтверждения — но в MVP разрешаем, пишем в `stage_history` (`actor_type='human'`). Переход `→ hired` создаёт запись в `employees` (Пульс) — см. домен Pulse.
- `reject`: ставит `stage='rejected'`, `reject_reason`, `reject_side`, пишет историю + событие + audit.
- Список причин фронт берёт из `/settings/reject-reasons`.
- Все переходы пишут `events` (type=`move`) и `audit_log`.
- Терминальный `rejected` — отдельный фильтр-чип «Отказ», отделён от остальных.

---

(продолжение в части 2: Glafira, Pulse, Analytics, Settings, Verification, Chat — см. ниже)
