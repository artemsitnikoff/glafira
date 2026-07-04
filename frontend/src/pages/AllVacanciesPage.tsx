import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import { useVacancies } from '@/api/hooks/useVacancies';
import { useSidebar } from '@/api/hooks/useSidebar';
import './AllVacanciesPage.css';

const PER_PAGE = 30;

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

// Список номеров страниц с «…» (шаблон как в Автоподборе .ssa-pager).
function pageList(cur: number, count: number): (number | '…')[] {
  const out: (number | '…')[] = [];
  for (let p = 1; p <= count; p++) {
    if (p === 1 || p === count || (p >= cur - 1 && p <= cur + 1)) {
      out.push(p);
    } else if (out[out.length - 1] !== '…') {
      out.push('…');
    }
  }
  return out;
}

export default function AllVacanciesPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const { data, isLoading, isError } = useVacancies({ status: 'active', page, page_size: PER_PAGE });
  const { data: sidebar } = useSidebar();

  const sidebarMap = new Map<string, number>(
    (sidebar?.items ?? []).map((item) => [item.id, item.count])
  );

  const vacancies = data?.items ?? [];
  const total = data?.total ?? 0;
  const pages = data?.pages ?? 1;
  const rangeStart = total === 0 ? 0 : (page - 1) * PER_PAGE + 1;
  const rangeEnd = (page - 1) * PER_PAGE + vacancies.length;

  const goPage = (p: number) => {
    const next = Math.min(Math.max(1, p), pages);
    if (next !== page) {
      setPage(next);
      window.scrollTo({ top: 0 });
    }
  };

  return (
    <div className="av-page content-inner">
      <div className="av-header">
        <h1>Все вакансии</h1>
        {!isLoading && !isError && (
          <span className="av-header-count">{total} активных</span>
        )}
      </div>

      {isLoading && <div className="av-empty">Загрузка…</div>}

      {!isLoading && isError && (
        <div className="av-empty">Не удалось загрузить вакансии. Обновите страницу.</div>
      )}

      {!isLoading && !isError && vacancies.length === 0 && (
        <div className="av-empty">Активных вакансий нет</div>
      )}

      {!isLoading && !isError && vacancies.length > 0 && (
        <>
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

          {pages > 1 && (
            <div className="av-pager">
              <div className="av-pager-info">
                Показано <b>{rangeStart}–{rangeEnd}</b> из <b className="t-mono">{total}</b>
              </div>
              <div className="av-pager-ctrls">
                <button
                  className="av-pg-nav"
                  disabled={page <= 1}
                  onClick={() => goPage(page - 1)}
                  aria-label="Назад"
                >
                  <Icon name="chevron-left" size={15} />
                </button>
                {pageList(page, pages).map((p, i) =>
                  p === '…' ? (
                    <span key={`e${i}`} className="av-pg-ell">…</span>
                  ) : (
                    <button
                      key={p}
                      className={`av-pg ${p === page ? 'active' : ''}`}
                      onClick={() => goPage(p)}
                    >
                      {p}
                    </button>
                  )
                )}
                <button
                  className="av-pg-nav"
                  disabled={page >= pages}
                  onClick={() => goPage(page + 1)}
                  aria-label="Вперёд"
                >
                  <Icon name="chevron-right" size={15} />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
