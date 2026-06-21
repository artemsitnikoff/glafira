"""Схемы для умного подбора кандидатов через hh.ru"""

from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SmartSkillChip(BaseModel):
    """Навык из справочника hh с id (для структурного фильтра skill=)"""
    id: str
    text: str


class SmartAccessResponse(BaseModel):
    """Ответ на проверку доступа к умному подбору"""
    has_access: bool
    has_paid_access: bool = False
    reason: Optional[str] = None


class SmartVacancyItem(BaseModel):
    """Вакансия с предзаполненными фильтрами для умного подбора"""
    id: UUID
    title: str
    city: Optional[str] = None
    area: Optional[str] = None  # ID региона в hh.ru
    professional_role: Optional[str] = None
    experience: Optional[str] = None
    salary_from: Optional[int] = None
    salary_to: Optional[int] = None
    skills: list[str] = Field(default_factory=list)
    found: Optional[int] = None  # количество найденных резюме
    hh_published: bool = False  # опубликована ли на hh.ru


class SmartSearchRequest(BaseModel):
    """Запрос на запуск умного поиска"""
    vacancy_id: UUID
    area: Optional[str] = None
    professional_role: Optional[str] = None
    experience: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    skill_chips: list[SmartSkillChip] = Field(default_factory=list)
    skill_mode: Literal["exact", "soft"] = "soft"
    salary_from: Optional[int] = None
    salary_to: Optional[int] = None
    include_no_salary: bool = True
    scan_n: int = Field(ge=1, le=400)  # количество резюме для сканирования
    invite_m: int = Field(ge=1, le=100)  # количество лучших для приглашения
    threshold: int = Field(ge=0, le=100)  # минимальный балл для приглашения
    confirm_cost: bool = False  # подтверждение расхода для scan_n > 50
    area_id: Optional[str] = None  # ID региона из справочника hh
    period: Optional[int] = None  # дни свежести резюме (1/3/7/30/365)


class SmartSearchResponse(BaseModel):
    """Ответ на запуск умного поиска"""
    run_id: UUID


class SmartRequirementMatch(BaseModel):
    """Соответствие требованию при скоринге в умном подборе"""
    criterion: str  # критерий оценки
    weight: int  # максимальный вес критерия
    points: int  # набранные баллы (≤ weight)
    comment: Optional[str] = None  # комментарий по критерию


class SmartScoredExperience(BaseModel):
    """Опыт работы в компактном резюме"""
    position: Optional[str] = None
    company: Optional[str] = None
    period: Optional[str] = None
    description: Optional[str] = None


class SmartScoredResume(BaseModel):
    """Компактное резюме для отображения"""
    title: Optional[str] = None
    total_experience_months: Optional[int] = None
    city: Optional[str] = None
    age: Optional[int] = None
    salary: Optional[str] = None  # Форматированная строка
    experience: list[SmartScoredExperience] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: Optional[str] = None


class InvitedCandidate(BaseModel):
    """Приглашенный кандидат"""
    candidate_id: Optional[UUID] = None  # None для превью режима
    name: str
    age: Optional[int] = None
    experience_years: Optional[int] = None
    last_company: Optional[str] = None
    city: Optional[str] = None
    score: int
    verdict: str
    passed: Optional[bool] = None  # для переиспользования в scored_candidates
    # Новые поля с полным разбором (необязательные для обратной совместимости)
    summary: Optional[str] = None
    strengths: Optional[list[str]] = None
    risks: Optional[list[str]] = None
    forecast: Optional[str] = None
    requirements_match: Optional[list[SmartRequirementMatch]] = None
    resume: Optional[SmartScoredResume] = None
    # Новые поля для ручного приглашения
    hh_resume_id: Optional[str] = None
    invited: Optional[bool] = None


class SmartRunStatus(BaseModel):
    """Статус выполнения умного поиска"""
    id: UUID
    status: Literal['running', 'done', 'error']
    stage: Literal['search', 'eval', 'finalizing', 'invite', 'done'] = 'search'
    found: int = 0
    scan_n: int = 0  # план скана (для прогресса: оценено из min(scan_n, found))
    scanned: int = 0
    evaluated: int = 0
    invited: int = 0
    error: Optional[str] = None
    invites_skipped: bool = False
    invited_candidates: list[InvitedCandidate] = Field(default_factory=list)
    scored_candidates: list[InvitedCandidate] = Field(default_factory=list)
    passed_threshold: int = 0
    note: Optional[str] = None
    log: list[str] = Field(default_factory=list)


class SmartRunHistoryItem(BaseModel):
    """Элемент истории умного поиска"""
    id: UUID
    vacancy_id: UUID
    vacancy_title: str
    created_at: datetime
    found: int
    evaluated: int
    passed: int = 0  # сколько прошло порог (живой счёт по scored_candidates)
    invited: int


class SmartVacancyFilters(BaseModel):
    """AI-фильтры для умного подбора по вакансии"""
    area: str
    professional_role: str
    experience: str
    skills: list[str]
    skill_chips: list[SmartSkillChip] = Field(default_factory=list)


class SmartCountRequest(BaseModel):
    """Запрос на превью количества резюме"""
    vacancy_id: UUID
    area: Optional[str] = None
    professional_role: Optional[str] = None
    experience: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    skill_chips: list[SmartSkillChip] = Field(default_factory=list)
    skill_mode: Literal["exact", "soft"] = "soft"
    salary_from: Optional[int] = None
    salary_to: Optional[int] = None
    include_no_salary: bool = True
    area_id: Optional[str] = None  # ID региона из справочника hh
    period: Optional[int] = None  # дни свежести резюме (1/3/7/30/365)


class SmartAreaSuggestItem(BaseModel):
    """Элемент подсказок регионов"""
    id: str
    text: str


class SmartSkillSuggestItem(BaseModel):
    """Элемент подсказок навыков из справочника hh (skill_set)"""
    id: str
    text: str


class SmartRoleSuggestItem(BaseModel):
    """Элемент подсказок профессиональных ролей hh.ru"""
    id: str
    name: str
    category: Optional[str] = None


class SmartRoleOption(BaseModel):
    """Роль внутри категории в сгруппированном справочнике"""
    id: str
    name: str


class SmartRoleCategory(BaseModel):
    """Категория (профобласть) со списком ролей — для двухуровневой выпадашки на фронте"""
    category_id: str
    category: str
    roles: list[SmartRoleOption]


class SmartDebugTextBlock(BaseModel):
    """Один text-блок в расширенном поиске hh (повторяющийся ключ text=)"""
    label: str          # «роль» | «навыки»
    text: str           # содержимое блока
    field: str          # text.field: everywhere | skills | ...
    logic: str          # text.logic: any | all | phrase | except
    period: Optional[str] = None  # text.period: all_time | last_year | ...


class SmartDebugSkill(BaseModel):
    """Навык с id, который ушёл как структурный фильтр skill= в hh"""
    id: str
    text: str


class SmartDebugParams(BaseModel):
    """
    Структурированное описание параметров запроса к hh для UI-диагностики.
    Показывает структурные фильтры и каждый text-блок отдельно.
    В режиме exact: skill_filter содержит список навыков с id, ушедших как skill=.
    В режиме soft: skill_filter пуст, навыки видны в text_blocks (label=«навыки»).
    """
    structural: dict = Field(default_factory=dict)
    text_blocks: list[SmartDebugTextBlock] = Field(default_factory=list)
    skill_filter: list[SmartDebugSkill] = Field(default_factory=list)


class SmartCountResponse(BaseModel):
    """Ответ с количеством найденных резюме"""
    found: Optional[int] = None
    debug_params: Optional[SmartDebugParams] = None  # Параметры, ушедшие в hh (для диагностики)


class SmartInviteRequest(BaseModel):
    """Запрос на ручное приглашение выбранных кандидатов"""
    resume_ids: list[str] = Field(max_length=500, description="Список hh_resume_id для приглашения")


class SmartInviteResultItem(BaseModel):
    """Результат приглашения одного кандидата"""
    resume_id: str
    status: Literal['invited', 'already', 'error']
    message: Optional[str] = None
    candidate_id: Optional[UUID] = None
    name: Optional[str] = None


class SmartInviteResponse(BaseModel):
    """Ответ на ручное приглашение кандидатов"""
    results: list[SmartInviteResultItem]
    invited_count: int


class SmartTakeRequest(BaseModel):
    """Запрос на «Забрать к себе» — открыть контакт и создать кандидата без negotiation"""
    resume_ids: list[str] = Field(max_length=500, description="Список hh_resume_id для забирания")


class SmartTakeResultItem(BaseModel):
    """Результат «забора» одного кандидата"""
    resume_id: str
    status: Literal['taken', 'already', 'error']
    message: Optional[str] = None
    candidate_id: Optional[UUID] = None
    name: Optional[str] = None


class SmartTakeResponse(BaseModel):
    """Ответ на «Забрать к себе»"""
    results: list[SmartTakeResultItem]
    taken_count: int