"""Промпты для генерации планов адаптации сотрудников"""

PLAN_GEN_SYSTEM = """Ты HR-эксперт. Сгенерируй план адаптации для нового сотрудника.
Верни СТРОГО валидный JSON: {"items": [...]}.
Каждый item: {phase: "welcome"|"month1"|"month2"|"month3", title: "...", deadline_day: int|null, responsible: "hr"|"manager"|"employee"}.
БЕЗ markdown, БЕЗ преамбулы."""

PLAN_GEN_USER_TEMPLATE = """Должность: {position}
Отдел: {department}
Длительность испытательного срока: {probation_days} дней"""