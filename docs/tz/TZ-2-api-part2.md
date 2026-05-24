# ТЗ-2 (часть 2). Glafira AI, Чат, Верификация, Пульс, Аналитика, Настройки

> Продолжение ТЗ-2. Зависит от части 1.

---

## 6. ДОМЕН: Glafira — AI-агент (app/api/glafira.py + services/glafira/)

Это ядро дифференциации продукта. В MVP **реально работают** скоринг резюме и чат-скрининг через Claude API; верификация — мок с финальным контрактом.

### 6.1 Эндпойнты

| Метод | Путь | Описание |
|---|---|---|
| POST | `/glafira/score` | Посчитать скоринг кандидата по вакансии (Claude API) |
| GET | `/candidates/{id}/evaluation` | Получить оценку AI (последнюю или по `application_id`) |
| POST | `/glafira/screening/start` | Запустить чат-скрининг (Claude генерит первое сообщение) |
| POST | `/glafira/screening/reply` | Ход диалога скрининга |
| POST | `/candidates/{id}/verify` | Запустить верификацию (требует ПдН!) |
| GET | `/candidates/{id}/verification` | Получить результат верификации |

### 6.2 Скоринг резюме (services/glafira/scoring.py)

**Вход:** кандидат (резюме, опыт, навыки) + вакансия (описание, требования).
**Через Claude API** (модель из `GLAFIRA_MODEL`) с системным промптом, требующим строго JSON-ответ (ТЗ-0 про структурированный вывод — system prompt явно требует «только JSON, без преамбулы, без markdown-ограждений», затем безопасный парсинг).

**Контракт ответа Claude (JSON-схема):**
```json
{
  "score": 92,
  "verdict": "good",
  "summary": "Хорошо подходит. Релевантный опыт, ключевые навыки совпадают.",
  "strengths": ["6 лет в B2B-продажах", "опыт в Сбере и Альфе"],
  "risks": ["английский заявлен B2, не подтверждён", "не готов к переезду"],
  "requirements_match": [
    {"req": "Опыт в B2B ≥ 3 лет", "status": "pass", "comment": "6 лет"},
    {"req": "Английский B2+", "status": "warn", "comment": "не подтверждён"},
    {"req": "Готовность к переезду", "status": "fail", "comment": "живёт в Москве"}
  ],
  "forecast": "Готов выйти через 4 недели"
}
```

Результат сохраняется в `ai_evaluations`, `score` дублируется в `applications.ai_score` (и в `candidates.ai_score` как последний). Действие пишется в `events` (type=`score`) и `audit_log` (`actor_type='ai'`).

```python
class ScoreRequest(BaseModel):
    candidate_id: UUID
    vacancy_id: UUID | None = None    # если None — общая оценка резюме

class RequirementMatch(BaseModel):
    req: str
    status: str                       # pass|warn|fail
    comment: str

class EvaluationOut(ORMBase):
    id: UUID
    candidate_id: UUID
    application_id: UUID | None
    score: int
    verdict: str                      # good|partial|bad
    summary: str
    strengths: list[str]
    risks: list[str]
    requirements_match: list[RequirementMatch]
    forecast: str | None
    model: str | None
    created_at: datetime
```

```typescript
export interface RequirementMatch { req: string; status: "pass" | "warn" | "fail"; comment: string; }
export interface EvaluationOut {
  id: UUID; candidate_id: UUID; application_id: UUID | null;
  score: number; verdict: "good" | "partial" | "bad"; summary: string;
  strengths: string[]; risks: string[]; requirements_match: RequirementMatch[];
  forecast: string | null; model: string | null; created_at: ISODateTime;
}
```

### 6.3 Чат-скрининг (services/glafira/screening.py)

Глафира ведёт диалог с кандидатом. В MVP — текстовый скрининг через Claude API, тон/скрипт берутся из `glafira_settings`. Каждый ход — сообщение сохраняется в `messages` (`sender_type='ai'`).

```python
class ScreeningStartRequest(BaseModel):
    candidate_id: UUID
    application_id: UUID | None = None
    script_key: str | None = None     # скрипт из настроек

class ScreeningReplyRequest(BaseModel):
    candidate_id: UUID
    message: str                      # ответ кандидата (или ввод рекрутёра-симуляция)

class ScreeningTurn(BaseModel):
    message: str                      # реплика Глафиры
    finished: bool                    # скрининг завершён
    extracted: dict | None            # извлечённые данные (ЗП, опыт, готовность)
```

**Промпт-инжиниринг (services/glafira/prompts.py):** держать промпты отдельным модулем, версионировать. System prompt включает тон из настроек (`friendly/formal/business`), обращение на ты/вы, уровень эмодзи. Для скоринга — отдельный промпт, требующий JSON. Реализовать защищённый парсинг (strip ```json-ограждений, try/except, при ошибке → `502 GLAFIRA_PARSE_ERROR`).

### 6.4 Верификация (services/glafira/verify.py) — MOCK в MVP

**Жёсткое правило:** если у кандидата нет consent со `status='signed'` → `403 CONSENT_REQUIRED`. Фронт показывает замок и кнопку «Запросить ПдН».

В MVP (`GLAFIRA_VERIFY_MODE=mock`) сервис генерит правдоподобный результат по 7 блокам (структура из ТЗ-1 §11). Контракт ответа — финальный, чтобы при включении `real` фронт не менялся.

```python
class VerifySource(BaseModel):
    name: str                         # "ФНС", "DaData", "Datanewton"
    type: str                         # api|reg|pub|ai

class VerifyBlock(BaseModel):
    key: str                          # inn|fssp|bankruptcy|registries|public|ai_intel|alimony
    title: str
    sources: list[VerifySource]
    status: str                       # clean|info|warn|risk
    data: dict

class VerificationOut(ORMBase):
    id: UUID
    candidate_id: UUID
    consent_id: UUID
    consent_number: str
    checked_at: datetime
    status: str                       # сводный clean|info|warn|risk
    blocks: list[VerifyBlock]
```

```typescript
export type VerifySourceType = "api" | "reg" | "pub" | "ai";
export interface VerifySource { name: string; type: VerifySourceType; }
export interface VerifyBlock {
  key: "inn" | "fssp" | "bankruptcy" | "registries" | "public" | "ai_intel" | "alimony";
  title: string; sources: VerifySource[]; status: VerifyStatus; data: Record<string, unknown>;
}
export interface VerificationOut {
  id: UUID; candidate_id: UUID; consent_id: UUID; consent_number: string;
  checked_at: ISODateTime; status: VerifyStatus; blocks: VerifyBlock[];
}
```

---

## 7. ДОМЕН: Consents — ПдН 152-ФЗ (app/api/consents.py)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/candidates/{id}/consent` | Текущее согласие кандидата |
| POST | `/candidates/{id}/consent/request` | Запросить ПдН (отправить кандидату через канал) |
| POST | `/candidates/{id}/consent/sign` | Отметить подписанным (вручную/по факту) |

```python
class ConsentOut(ORMBase):
    id: UUID
    candidate_id: UUID
    number: str          # "PD-029/26"
    status: str          # pending|signed|revoked
    channel: str | None
    signed_at: datetime | None
    requested_at: datetime | None

class ConsentRequest(BaseModel):
    channel: str         # telegram|email|...
```

Бизнес: `number` генерится автоинкрементом по компании в формате `PD-{seq}/{YY}`. `request` создаёт consent в `pending` + отправляет шаблон сообщения через канал (в MVP — пишет в `messages` исходящее от AI).

---

## 8. ДОМЕН: Chat — переписка (app/api/chat.py)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/candidates/{id}/messages` | Лента сообщений (все каналы, опц. фильтр `channel`, `application_id`) |
| POST | `/candidates/{id}/messages` | Отправить сообщение в канал |

```python
class MessageOut(ORMBase):
    id: UUID
    channel: str
    direction: str       # in|out
    sender_type: str     # candidate|recruiter|ai
    sender_name: str | None
    body: str
    sent_at: datetime
    application_context: str | None   # "Контекст: вакансия XYZ" в общей базе

class MessageCreate(BaseModel):
    channel: str         # telegram|hh|max|whatsapp|sms|email
    body: str
    application_id: UUID | None = None
```

```typescript
export interface MessageOut {
  id: UUID; channel: Channel; direction: "in" | "out";
  sender_type: "candidate" | "recruiter" | "ai"; sender_name: string | null;
  body: string; sent_at: ISODateTime; application_context: string | null;
}
```

Бизнес: дефолтный канал ответа — `telegram`. В MVP реальной отправки в мессенджеры нет (кроме hh/avito если интеграция активна) — исходящее просто сохраняется. Структура готова под подключение провайдеров.

---

## 9. ДОМЕН: Documents (app/api/documents.py)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/candidates/{id}/documents` | Список файлов |
| POST | `/candidates/{id}/documents` | Загрузить (multipart) |
| GET | `/documents/{id}/download` | Скачать |
| DELETE | `/documents/{id}` | Удалить |

```python
class DocumentOut(ORMBase):
    id: UUID
    filename: str
    file_type: str       # pdf|img|doc
    size_bytes: int
    source: str | None
    uploaded_by_name: str | None
    created_at: datetime
```

Хранилище — локальная папка через абстрактный `StorageService` (метод `save`, `get_path`, `delete`). При загрузке PDF-резюме — опционально триггерить парсинг и обновление `resume_text`/`resume_summary` (через Глафиру). Импорт резюме → автозаполнение полей кандидата.

---

## 10. ДОМЕН: Comments (app/api/comments.py)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/candidates/{id}/comments` | Лента комментариев |
| POST | `/candidates/{id}/comments` | Добавить (поддержка @упоминаний) |

```python
class CommentOut(ORMBase):
    id: UUID
    author_name: str
    author_role: str
    body: str
    mentions: list[UUID]
    created_at: datetime

class CommentCreate(BaseModel):
    body: str
    application_id: UUID | None = None
    mentions: list[UUID] = []
```

---

## 11. ДОМЕН: Pulse — пост-найм (app/api/pulse.py)

### Эндпойнты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/pulse/employees` | Таблица сотрудников. Фильтры: `manager, department, risk, period, survey_status`, сегменты, поиск |
| GET | `/pulse/employees/{id}` | Карточка сотрудника (Экран 08) |
| GET | `/pulse/kpi` | KPI-полоса (на адаптации, прошли испытательный, ушли, eNPS) |
| GET | `/pulse/alerts` | Алерты Глафиры (список) |
| POST | `/pulse/alerts/{id}/dismiss` | Скрыть алерт |
| GET | `/pulse/employees/{id}/plan` | План адаптации (чек-лист) |
| PATCH | `/pulse/plan-items/{id}` | Отметить пункт выполненным |
| GET | `/pulse/employees/{id}/surveys` | История опросов |
| POST | `/pulse/employees/{id}/surveys` | Запустить опрос (шаблон + получатели) |
| POST | `/pulse/employees/{id}/note` | Заметка руководителя |

### Схемы

```python
class PulseKPI(BaseModel):
    onboarding_count: int
    passed_probation: int
    passed_delta: int
    left_in_90d: int
    left_in_90d_pct: float
    enps: int

class EmployeeRow(ORMBase):
    id: UUID
    full_name: str
    position: str | None
    avatar_url: str | None
    manager_name: str | None
    start_date: date
    adapt_day: int                    # computed: today - start_date
    probation_days: int
    risk_level: str                   # low|mid|high
    last_survey_date: date | None
    last_survey_mood: str | None      # good|neutral|bad (👍/😐/👎)

class EmployeeDetail(ORMBase):
    id: UUID
    candidate_id: UUID
    full_name: str
    position: str | None
    department: str | None
    manager_name: str | None
    recruiter_name: str | None
    hire_source: str | None
    start_date: date
    adapt_day: int
    probation_days: int
    status: str                       # onboarding|passed|left
    risk_level: str
    enps: int | None
    # Обзор
    satisfaction_avg: float | None
    activity_pct: float | None
    plan_progress_pct: float | None
    left_at: date | None
    left_reason: str | None

class PulseAlertOut(ORMBase):
    id: UUID
    employee_id: UUID
    employee_name: str
    level: str                        # high|mid|info
    title: str
    context: str | None
    action_type: str | None

class PlanItemOut(ORMBase):
    id: UUID
    phase: str                        # welcome|month1|month2|month3
    title: str
    deadline_day: int | None
    responsible: str                  # hr|manager|employee
    is_done: bool

class SurveyOut(ORMBase):
    id: UUID
    type: str                         # weekly|monthly|special|enps
    sent_at: datetime
    answered_at: datetime | None
    overall_score: float | None
    answers: list[dict]

class RunSurveyRequest(BaseModel):
    template_key: str
    send_at: datetime | None = None
```

```typescript
export interface PulseKPI {
  onboarding_count: number; passed_probation: number; passed_delta: number;
  left_in_90d: number; left_in_90d_pct: number; enps: number;
}
export interface EmployeeRow {
  id: UUID; full_name: string; position: string | null; avatar_url: string | null;
  manager_name: string | null; start_date: ISODate; adapt_day: number;
  probation_days: number; risk_level: RiskLevel;
  last_survey_date: ISODate | null; last_survey_mood: "good" | "neutral" | "bad" | null;
}
export interface PulseAlertOut {
  id: UUID; employee_id: UUID; employee_name: string;
  level: "high" | "mid" | "info"; title: string; context: string | null;
  action_type: string | null;
}
// EmployeeDetail, PlanItemOut, SurveyOut — зеркала Pydantic
```

### Бизнес-правила
- При переходе application `→ hired` автоматически создаётся `employee` (start_date=today, status=onboarding, probation_days из настроек). Глафира генерит план адаптации (`pulse_plan_items`) по должности/шаблону.
- `risk_level` пересчитывается правилами (services): 2+ сигнала за неделю → high, 1 сигнал → mid. Сигналы: пропуск опроса, низкая оценка.
- `adapt_day` вычисляется на лету.
- KPI и алерты с главной (Экран 01) берут данные отсюда.

---

## 12. ДОМЕН: Home / Dashboard (app/api/home.py)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/home/kpi?period=month` | 6 базовых + 2 расширенных KPI с дельтами |
| GET | `/home/attention` | «Требуют внимания» (вычисляется) |
| GET | `/home/events?limit=30` | Лента событий (polling) |
| GET | `/home/pulse-summary` | Сводка адаптации + «Требуют внимания HR» |
| GET | `/home/sources?period=month` | Топ-источники |

```python
class KpiCard(BaseModel):
    key: str
    value: float
    unit: str | None                  # %|дней|₽|часа|None
    delta: float | None
    delta_dir: str                    # up|down|up-bad|down-good|flat
    caption: str | None

class HomeKpi(BaseModel):
    period: str
    cards: list[KpiCard]              # 6 базовых (+2 если extended)

class AttentionItem(BaseModel):
    vacancy_id: UUID
    vacancy_name: str
    kind: str                         # urgent|warn|deadline
    text: str

class EventItem(ORMBase):
    id: UUID
    type: str                         # qual|new|score|offer|move
    text: str
    entities: list[dict]              # [{type,id,label}]
    created_at: datetime
```

```typescript
export interface KpiCard {
  key: string; value: number; unit: string | null; delta: number | null;
  delta_dir: "up" | "down" | "up-bad" | "down-good" | "flat"; caption: string | null;
}
export interface AttentionItem {
  vacancy_id: UUID; vacancy_name: string; kind: "urgent" | "warn" | "deadline"; text: string;
}
export interface EventItem {
  id: UUID; type: "qual" | "new" | "score" | "offer" | "move";
  text: string; entities: { type: string; id: UUID; label: string }[]; created_at: ISODateTime;
}
```

> **Polling вместо WebSocket:** фронт опрашивает `/home/events` через TanStack Query `refetchInterval: 15000`. KPI — без авто-рефреша, только по смене периода.

---

## 13. ДОМЕН: Analytics (app/api/analytics.py)

7 отчётов (Экран 06). Каждый — отдельный эндпойнт с общими фильтрами (`period`, `vacancy_ids`, `recruiter_ids`, `compare`).

| Метод | Путь | Отчёт |
|---|---|---|
| GET | `/analytics/overview` | 1. Обзор (KPI + динамика + top-5) |
| GET | `/analytics/speed` | 2. Скорость (время на этапах, p50/p90, heatmap) |
| GET | `/analytics/funnel` | 3. Воронка (конверсии) |
| GET | `/analytics/sources` | 4. Источники (эффективность) |
| GET | `/analytics/rejections` | 5. Отказы (наши/кандидата) |
| GET | `/analytics/turnover` | 6. Текучка (cohort, survival) |
| GET | `/analytics/recruiters` | 7. Рекрутёры (лидерборд) |
| GET | `/analytics/export?report=X&format=xlsx` | Экспорт |

Каждый возвращает структуру под графики/таблицы. Контракт каждого отчёта детализируется в отдельном ТЗ по Аналитике (Экран 06 фронт) — здесь фиксируем список эндпойнтов и общий конверт:

```python
class AnalyticsResponse(BaseModel):
    report: str
    period: str
    kpis: list[KpiCard] | None
    charts: list[dict]                # каждый chart: {type, title, data}
    tables: list[dict]                # каждая table: {title, columns, rows}
```

> Детальные контракты данных по каждому отчёту вынесены в ТЗ фронта Аналитики, т.к. структура графиков завязана на визуализацию. Бек-агент реализует расчёты, фронт-агент — рендеринг по согласованным `charts[].data`.

---

## 14. ДОМЕН: Settings (app/api/settings.py)

| Метод | Путь | Описание |
|---|---|---|
| GET/PATCH | `/settings/profile` | Профиль текущего юзера |
| GET | `/settings/team` / POST `/users` | Команда (см. домен Users) |
| GET/PATCH | `/settings/glafira` | Настройки Глафиры (тон, пороги, режим) |
| GET/POST/DELETE | `/settings/reject-reasons` | Справочник причин отказа |
| GET/POST/PATCH | `/settings/email-templates` | Шаблоны писем |
| GET/POST/PATCH | `/settings/survey-templates` | Шаблоны опросов Пульса |
| GET/PATCH | `/settings/integrations` | Интеграции (hh, avito, ...) |
| GET | `/settings/billing` | Биллинг (заглушка в MVP) |

```python
class GlafiraSettings(ORMBase):
    tone: str                         # friendly|formal|business
    use_informal: bool
    emoji_level: str
    auto_reject_below: int | None
    auto_select_above: int | None
    days_no_response: int | None
    default_mode: str                 # A|B|C

class RejectReasonOut(ORMBase):
    id: UUID
    side: str                         # candidate|company
    label: str
    order_index: int
    is_active: bool
```

```typescript
export interface GlafiraSettings {
  tone: "friendly" | "formal" | "business"; use_informal: boolean; emoji_level: string;
  auto_reject_below: number | null; auto_select_above: number | null;
  days_no_response: number | null; default_mode: GlafiraMode;
}
export interface RejectReasonOut {
  id: UUID; side: "candidate" | "company"; label: string; order_index: number; is_active: boolean;
}
```

---

## 15. Сводная карта эндпойнтов (для быстрой сверки)

```
AUTH      POST /auth/login | /auth/refresh | /auth/logout    GET /auth/me
USERS     GET /users | /users/{id}    POST /users    PATCH /users/{id}
VACANCY   GET /vacancies | /vacancies/{id} | /vacancies/sidebar | /vacancies/{id}/stages
          POST /vacancies | /vacancies/{id}/archive    PATCH /vacancies/{id}
CANDID    GET /candidates | /candidates/{id} | /candidates/{id}/applications
          POST /candidates | /candidates/{id}/tags    PATCH/DELETE /candidates/{id}
          DELETE /candidates/{id}/tags/{tag_id}
APPLIC    GET /vacancies/{vid}/applications | /applications/{id} | /applications/{id}/history
          POST /applications/{id}/move | /reject | /restore | /bulk/move | /bulk/reject
GLAFIRA   POST /glafira/score | /glafira/screening/start | /glafira/screening/reply
          GET /candidates/{id}/evaluation
          POST /candidates/{id}/verify    GET /candidates/{id}/verification
CONSENT   GET /candidates/{id}/consent    POST .../consent/request | .../consent/sign
CHAT      GET /candidates/{id}/messages    POST /candidates/{id}/messages
DOCS      GET /candidates/{id}/documents    POST .../documents    GET /documents/{id}/download    DELETE /documents/{id}
COMMENT   GET /candidates/{id}/comments    POST /candidates/{id}/comments
PULSE     GET /pulse/employees | /pulse/employees/{id} | /pulse/kpi | /pulse/alerts
          GET /pulse/employees/{id}/plan | /surveys    POST .../surveys | /note
          PATCH /pulse/plan-items/{id}    POST /pulse/alerts/{id}/dismiss
HOME      GET /home/kpi | /home/attention | /home/events | /home/pulse-summary | /home/sources
ANALYT    GET /analytics/{overview|speed|funnel|sources|rejections|turnover|recruiters} | /export
SETTINGS  GET/PATCH /settings/{profile|glafira|integrations|billing}
          GET/POST/PATCH/DELETE /settings/{reject-reasons|email-templates|survey-templates}
```

---

## 16. ЧЕК-ЛИСТ ПРИЁМКИ (для ревьювера)

### Общее
- [ ] Все эндпойнты под `/api/v1/`, отвечают в форматах ТЗ-0 §3.2/§3.3.
- [ ] Ошибки — единый конверт `{error: {code, message, details}}`, коды HTTP корректны.
- [ ] Все ID в ответах — UUID-строки. Даты — ISO 8601 UTC.
- [ ] Пагинация: конверт `{items,total,page,page_size,pages}`, дефолт 24, макс 100.
- [ ] OpenAPI генерится, экспортирован в `contracts/openapi.json`.
- [ ] TS-типы в `frontend/src/api/types.ts` соответствуют Pydantic-схемам 1:1.

### Auth
- [ ] Неверные креды → 401 `INVALID_CREDENTIALS`; неактивный → 403 `USER_INACTIVE`.
- [ ] Refresh в HttpOnly+Secure+SameSite cookie; access в теле.
- [ ] `/auth/me` возвращает текущего юзера; защищённые эндпойнты без токена → 401.

### Вакансии
- [ ] `POST /vacancies` создаёт `vacancy_stages` из шаблона; `team[0]` → ответственный.
- [ ] `/vacancies/sidebar` отдаёт `count`, `new_count`, `archived_count` корректно.
- [ ] `/vacancies/{id}/stages` отдаёт счётчики по этапам (кроме rejected в «Все»).
- [ ] Архивация ставит status/result/closed_at + audit_log.

### Кандидаты / Воронка
- [ ] `age` вычисляется из `birth_date`; `has_pdn` = signed consent.
- [ ] `CandidateCreate` без `last_name|first_name|source` → 422.
- [ ] История участия отдаёт все applications кандидата с этапами и причинами отказа.
- [ ] `move` пишет stage_history + event + audit; `→hired` создаёт employee в Пульсе.
- [ ] `reject` ставит rejected/reason/side; причины валидируются по справочнику.
- [ ] Bulk-операции работают на массиве application_ids.

### Глафира (AI)
- [ ] `/glafira/score` реально вызывает Claude API, парсит строгий JSON, сохраняет в `ai_evaluations`, дублирует score.
- [ ] При ошибке парсинга JSON → 502 `GLAFIRA_PARSE_ERROR` (не падает 500).
- [ ] Скоринг и скрининг логируются как `actor_type='ai'` в audit + events.
- [ ] Тон/скрипт берутся из `glafira_settings`.
- [ ] Промпты вынесены в `prompts.py`, не захардкожены в хендлерах.

### Верификация / ПдН (152-ФЗ)
- [ ] `/candidates/{id}/verify` без signed consent → **403 `CONSENT_REQUIRED`** (критично!).
- [ ] Mock-верификация отдаёт все 7 блоков в финальном контракте.
- [ ] Consent number в формате `PD-{seq}/{YY}`, уникален.

### Пульс
- [ ] Найм создаёт employee + план адаптации.
- [ ] `adapt_day`, `risk_level` вычисляются правилами.
- [ ] KPI и алерты согласованы с данными.

### Сквозное
- [ ] Каждое изменяющее действие → запись в `audit_log` (включая AI).
- [ ] Все доменные таблицы пишутся с `company_id` из контекста.
- [ ] Polling-эндпойнты (`/home/events`) отдают свежие данные без кэш-проблем.

### Тесты (минимум)
- [ ] Auth happy-path + 401/403.
- [ ] Создание вакансии + проверка stages.
- [ ] Создание кандидата + назначение на вакансию + move по этапам.
- [ ] Verify без ПдН → 403; с ПдН → 200.
- [ ] Скоринг с замоканным Claude-ответом → корректное сохранение.
