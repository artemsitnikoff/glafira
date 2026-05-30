"""Stage definitions and templates for vacancy funnels"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class StageDefinition:
    key: str
    label: str
    color: str
    order_index: int
    is_terminal: bool = False


# Protected stage keys that cannot be deleted
PROTECTED_STAGE_KEYS = {"hired", "rejected", "added", "response"}

# Default stages for all vacancies
STAGES: Dict[str, StageDefinition] = {
    "response": StageDefinition("response", "Отклик", "#5B6573", 1),
    "added": StageDefinition("added", "Добавлен", "#7E5CF0", 2),
    "selected": StageDefinition("selected", "Отобран", "#9AA3AE", 3),
    "recruiter": StageDefinition("recruiter", "Контакт с рекрутером", "#7AB4F5", 4),
    "interview": StageDefinition("interview", "Интервью", "#2A8AF0", 5),
    "manager": StageDefinition("manager", "Контакт с менеджером", "#5778E8", 6),
    "offer": StageDefinition("offer", "Оффер", "#E0A21A", 7),
    "hired": StageDefinition("hired", "Нанят", "#16A34A", 8, is_terminal=True),
    "rejected": StageDefinition("rejected", "Отказ", "#DC4646", 9, is_terminal=True),
}

# Funnel templates
FUNNEL_TEMPLATES: Dict[str, List[str]] = {
    "default": ["response", "added", "selected", "recruiter", "interview", "manager", "offer", "hired", "rejected"],
    "mass": ["response", "selected", "interview", "hired", "rejected"],
    "technical": ["response", "added", "selected", "recruiter", "interview", "manager", "offer", "hired", "rejected"],
    "sales": ["response", "added", "selected", "recruiter", "interview", "manager", "offer", "hired", "rejected"],  # same as default
}


def get_stages_for_template(template: str) -> List[StageDefinition]:
    """Get stage definitions for a funnel template"""
    if template not in FUNNEL_TEMPLATES:
        template = "default"

    stage_keys = FUNNEL_TEMPLATES[template]
    return [STAGES[key] for key in stage_keys if key in STAGES]