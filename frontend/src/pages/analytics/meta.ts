/**
 * Метаданные раздела «Аналитика»: заголовки отчётов и русские подписи KPI.
 * Бек отдаёт KpiCard.key (англ.), caption=null — подписи задаём на фронте.
 */

export const REPORTS = [
  { key: 'overview', title: 'Обзор' },
  { key: 'speed', title: 'Скорость найма' },
  { key: 'funnel', title: 'Воронка конверсий' },
  { key: 'sources', title: 'Источники' },
  { key: 'rejections', title: 'Причины отказов' },
  { key: 'turnover', title: 'Текучка после найма' },
  { key: 'recruiters', title: 'Рекрутёры' },
] as const;

export type ReportKey = (typeof REPORTS)[number]['key'];

export function reportTitle(key: string): string {
  return REPORTS.find((r) => r.key === key)?.title ?? 'Аналитика';
}

// Русские подписи KPI по ключу бека (overview — единственный отчёт с KPI).
export const KPI_LABELS: Record<string, string> = {
  open_vacancies: 'Открытые вакансии',
  applications_count: 'Откликов за период',
  closed_vacancies: 'Закрытые вакансии',
  avg_time_to_hire: 'Среднее время найма',
  cost_per_hire: 'Стоимость найма',
};

export function kpiLabel(key: string, fallback?: string | null): string {
  return KPI_LABELS[key] ?? fallback ?? key;
}
