import { useNavigate } from 'react-router-dom';
import { useVacancies } from '@/api/hooks/useVacancies';
import { useSidebar } from '@/api/hooks/useSidebar';
import './AllVacanciesPage.css';

function stripHtml(html: string): string {
  return new DOMParser().parseFromString(html, 'text/html').body.textContent ?? '';
}

function formatSalary(
  from: number | null | undefined,
  to: number | null | undefined,
  currency: string
): string {
  if (!from && !to) return 'ЗП не указана';
  const cur = currency === 'RUB' ? '₽' : currency;
  if (from && to) return `${from.toLocaleString('ru-RU')} – ${to.toLocaleString('ru-RU')} ${cur}`;
  if (from) return `от ${from.toLocaleString('ru-RU')} ${cur}`;
  return `до ${to!.toLocaleString('ru-RU')} ${cur}`;
}

const EMPLOYMENT_LABELS: Record<string, string> = {
  full: 'Полная',
  part: 'Частичная',
  project: 'Проектная',
  volunteer: 'Волонтёрская',
  probation: 'Стажировка',
};

export default function AllVacanciesPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useVacancies({ status: 'active', page_size: 200 });
  const { data: sidebar } = useSidebar();

  const sidebarMap = new Map<string, number>(
    (sidebar?.items ?? []).map((item) => [item.id, item.count])
  );

  const vacancies = data?.items ?? [];

  return (
    <div className="av-page content-inner">
      <div className="av-header">
        <h1>Все вакансии</h1>
        {!isLoading && (
          <span className="av-header-count">{vacancies.length} активных</span>
        )}
      </div>

      {isLoading && (
        <div className="av-empty">Загрузка…</div>
      )}

      {!isLoading && vacancies.length === 0 && (
        <div className="av-empty">Активных вакансий нет</div>
      )}

      {!isLoading && vacancies.length > 0 && (
        <div className="av-grid">
          {vacancies.map((v) => {
            const candidateCount = sidebarMap.get(v.id) ?? 0;
            const descRaw = v.description ? stripHtml(v.description).trim() : '';
            const salaryText = formatSalary(v.salary_from, v.salary_to, v.currency);
            const employmentLabel = v.employment_type
              ? (EMPLOYMENT_LABELS[v.employment_type] ?? v.employment_type)
              : null;

            return (
              <div
                key={v.id}
                className="av-card"
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/vacancies/${v.id}`)}
                onKeyDown={(e) => e.key === 'Enter' && navigate(`/vacancies/${v.id}`)}
              >
                <div className="av-card-title">{v.name}</div>

                {descRaw ? (
                  <div className="av-card-desc">{descRaw}</div>
                ) : (
                  <div className="av-card-desc av-card-desc--empty">Без описания</div>
                )}

                <div className="av-meta">
                  <span className="av-badge">
                    {v.responsible_user?.full_name ?? 'Не назначен'}
                  </span>
                  <span className="av-badge">{salaryText}</span>
                  {v.city && <span className="av-badge">{v.city}</span>}
                  {employmentLabel && <span className="av-badge">{employmentLabel}</span>}
                  {v.positions_count > 0 && (
                    <span className="av-badge">{v.positions_count} позиций</span>
                  )}
                  {candidateCount > 0 && (
                    <span className="av-count">{candidateCount} кандидатов</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
