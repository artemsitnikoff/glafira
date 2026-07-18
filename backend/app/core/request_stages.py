"""Стадии воронки «Заявки на подбор».

Фиксированный скелет (нередактируемый, код-константы) + кастомные этапы компании
(таблица request_funnel_stages), вставляемые МЕЖДУ «В работе» (work) и «В подборе»
(sourcing). Статус заявки хранится СТРОКОЙ (HiringRequest.status = stage_key), как
Application.stage — без FK, по образцу воронки вакансий (core/stages.py).
"""
from dataclasses import dataclass


@dataclass
class RequestStageDef:
    key: str
    label: str
    color: str
    system: bool = False    # 'sourcing' — привязан к созданию вакансии
    terminal: bool = False


# Фиксированный скелет в порядке прохождения.
REQUEST_FIXED_STAGES: list[RequestStageDef] = [
    RequestStageDef("new", "Новая", "#2A8AF0"),
    RequestStageDef("work", "В работе", "#D9A514"),
    RequestStageDef("sourcing", "В подборе", "#7E5CF0", system=True),
    RequestStageDef("done", "Закрыта", "#16A34A", terminal=True),
    RequestStageDef("rejected", "Отклонена", "#DC4646", terminal=True),
]

# Нередактируемые/неудаляемые ключи (серверная защита правится ТОЛЬКО в этих границах).
PROTECTED_REQUEST_STAGE_KEYS = {"new", "work", "sourcing", "done", "rejected"}
TERMINAL_REQUEST_STAGE_KEYS = {"done", "rejected"}

# Палитра для кастомных этапов (по кругу, как вычисляемые цвета вакансий).
_CUSTOM_COLORS = ["#7AB4F5", "#5778E8", "#9AA3AE", "#E0A21A", "#5B6573"]


def custom_stage_color(order_index: int) -> str:
    return _CUSTOM_COLORS[order_index % len(_CUSTOM_COLORS)]


def build_stage_flow(custom_stages: list[dict]) -> list[dict]:
    """Собирает полный список стадий: фиксированные + кастомные между work и sourcing.

    custom_stages — список dict {stage_key, label, order_index, description, color}
    из request_funnel_stages, отсортированный по order_index. Возвращает список dict
    {key, label, color, system, terminal, custom, description}.
    """
    ordered_custom = sorted(custom_stages, key=lambda s: s.get("order_index", 0))
    flow: list[dict] = []
    for fixed in REQUEST_FIXED_STAGES:
        flow.append({
            "key": fixed.key, "label": fixed.label, "color": fixed.color,
            "system": fixed.system, "terminal": fixed.terminal, "custom": False,
            "description": None,
        })
        if fixed.key == "work":
            for i, cs in enumerate(ordered_custom):
                flow.append({
                    "key": cs["stage_key"], "label": cs["label"],
                    "color": cs.get("color") or custom_stage_color(i),
                    "system": False, "terminal": False, "custom": True,
                    "description": cs.get("description"),
                })
    return flow


def valid_stage_keys(custom_stages: list[dict]) -> set[str]:
    """Все допустимые ключи статуса заявки (фиксированные + кастомные компании)."""
    keys = {s.key for s in REQUEST_FIXED_STAGES}
    keys.update(cs["stage_key"] for cs in custom_stages)
    return keys
