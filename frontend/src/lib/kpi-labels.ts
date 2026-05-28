export interface KpiLabel {
  label: string;
  tooltip: string;
}

export const KPI_LABELS: Record<string, KpiLabel> = {
  open_vacancies: { label: 'Открытые вакансии', tooltip: 'Текущее число активных вакансий' },
  closed_vacancies: { label: 'Закрытые вакансии', tooltip: 'Сколько закрыто за выбранный период' },
  avg_time_to_hire: { label: 'Среднее время найма', tooltip: 'От создания вакансии до статуса «Нанят»' },
  turnover_90d: { label: 'Текучесть (90 дней)', tooltip: '% сотрудников, ушедших в первые 90 дней' },
  active_candidates: { label: 'Активных кандидатов', tooltip: 'Кандидаты в воронках (не нанятые/не отказ)' },
  conversion: { label: 'Конверсия отклик→найм', tooltip: '% откликов, дошедших до найма' },
  cost_per_hire: { label: 'Стоимость найма', tooltip: 'Средняя стоимость одного найма' },
  recruiter_response_speed: { label: 'Скорость ответа рекрутёра', tooltip: 'Среднее время от отклика до первого исходящего сообщения' },
};