import { useState, useRef, useEffect } from 'react';
import type { AnalyticsFilters } from '@/api/aliases';
import { useExportAnalytics } from '@/api/mutations/exportAnalytics';
import { useVacancies } from '@/api/hooks/useVacancies';
import { useUsers } from '@/api/hooks/useUsers';
import { Icon } from '@/components/ui/Icon';

interface GlobalFiltersProps {
  filters: AnalyticsFilters;
  onChange: (filters: Partial<AnalyticsFilters>) => void;
  isLoading: boolean;
}

const PERIOD_OPTIONS = [
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'quarter', label: 'Квартал' },
  { value: 'year', label: 'Год' },
  { value: 'custom', label: 'Произвольный' },
] as const;

export function GlobalFilters({ filters, onChange, isLoading }: GlobalFiltersProps) {
  const [periodOpen, setPeriodOpen] = useState(false);
  const [vacancyOpen, setVacancyOpen] = useState(false);
  const [recruiterOpen, setRecruiterOpen] = useState(false);

  const periodRef = useRef<HTMLDivElement>(null);
  const vacancyRef = useRef<HTMLDivElement>(null);
  const recruiterRef = useRef<HTMLDivElement>(null);

  const exportMutation = useExportAnalytics();

  // Load data for multi-selects
  const { data: vacanciesData, isLoading: vacanciesLoading } = useVacancies({
    status: 'active',
    page_size: 100
  });

  const { data: usersData, isLoading: usersLoading } = useUsers();

  // Close dropdowns when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (periodRef.current && !periodRef.current.contains(event.target as Node)) {
        setPeriodOpen(false);
      }
      if (vacancyRef.current && !vacancyRef.current.contains(event.target as Node)) {
        setVacancyOpen(false);
      }
      if (recruiterRef.current && !recruiterRef.current.contains(event.target as Node)) {
        setRecruiterOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleExport = () => {
    const reportMatch = window.location.search.match(/[?&]report=([^&]+)/);
    const report = reportMatch?.[1] || 'overview';

    exportMutation.mutate({
      report,
      format: 'xlsx',
      ...filters,
    });
  };

  const selectedPeriod = PERIOD_OPTIONS.find(p => p.value === filters.period) || PERIOD_OPTIONS[1];

  const handleVacancyToggle = (vacancyId: string) => {
    const current = filters.vacancy_ids || [];
    const updated = current.includes(vacancyId)
      ? current.filter(id => id !== vacancyId)
      : [...current, vacancyId];
    onChange({ vacancy_ids: updated.length > 0 ? updated : undefined });
  };

  const handleRecruiterToggle = (recruiterId: string) => {
    const current = filters.recruiter_ids || [];
    const updated = current.includes(recruiterId)
      ? current.filter(id => id !== recruiterId)
      : [...current, recruiterId];
    onChange({ recruiter_ids: updated.length > 0 ? updated : undefined });
  };

  // Filter recruiters from users - UserShort has role field
  const recruiters = usersData?.items?.filter(user =>
    user.role === 'recruiter'
  ) || [];

  return (
    <div className="analytics-filters">
      {/* Period Selector */}
      <div className="analytics-filter">
        <label className="analytics-filter-label">Период</label>
        <div className="analytics-dropdown" ref={periodRef}>
          <button
            className="analytics-dropdown-trigger"
            onClick={() => {
              setPeriodOpen(!periodOpen);
              setVacancyOpen(false);
              setRecruiterOpen(false);
            }}
          >
            <span>{selectedPeriod.label}</span>
            <Icon name="chevron-down" size={14} />
          </button>

          {periodOpen && (
            <div className="analytics-dropdown-content">
              {PERIOD_OPTIONS.map((option) => (
                <div
                  key={option.value}
                  className={`analytics-dropdown-item ${option.value === filters.period ? 'active' : ''}`}
                  onClick={() => {
                    onChange({ period: option.value });
                    setPeriodOpen(false);
                  }}
                >
                  {option.label}
                  {option.value === filters.period && <Icon name="check" size={14} />}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Custom Date Range */}
      {filters.period === 'custom' && (
        <div className="analytics-filter">
          <label className="analytics-filter-label">Диапазон</label>
          <div className="analytics-date-inputs">
            <input
              type="date"
              className="analytics-date-input"
              value={filters.date_from || ''}
              onChange={(e) => onChange({ date_from: e.target.value })}
            />
            <span style={{ color: 'var(--fg-3)' }}>—</span>
            <input
              type="date"
              className="analytics-date-input"
              value={filters.date_to || ''}
              onChange={(e) => onChange({ date_to: e.target.value })}
            />
          </div>
        </div>
      )}

      {/* Vacancy Multi-select */}
      <div className="analytics-filter">
        <label className="analytics-filter-label">Вакансии</label>
        <div className="analytics-dropdown" ref={vacancyRef}>
          <button
            className="analytics-dropdown-trigger"
            onClick={() => {
              setVacancyOpen(!vacancyOpen);
              setPeriodOpen(false);
              setRecruiterOpen(false);
            }}
          >
            <span>
              {filters.vacancy_ids?.length ?
                `Выбрано: ${filters.vacancy_ids.length}` :
                'Все вакансии'
              }
            </span>
            <Icon name="chevron-down" size={14} />
          </button>

          {vacancyOpen && (
            <div className="analytics-dropdown-content" style={{ maxHeight: '240px', overflowY: 'auto' }}>
              {vacanciesLoading ? (
                <div className="analytics-dropdown-item">
                  Загрузка вакансий...
                </div>
              ) : vacanciesData?.items?.length ? (
                <>
                  <div
                    className="analytics-dropdown-item"
                    onClick={() => onChange({ vacancy_ids: undefined })}
                  >
                    <input type="checkbox" checked={!filters.vacancy_ids?.length} readOnly />
                    <span>Все вакансии</span>
                  </div>
                  {vacanciesData.items.map(vacancy => (
                    <div
                      key={vacancy.id}
                      className="analytics-dropdown-item"
                      onClick={() => handleVacancyToggle(vacancy.id)}
                    >
                      <input
                        type="checkbox"
                        checked={filters.vacancy_ids?.includes(vacancy.id) || false}
                        readOnly
                      />
                      <span>{vacancy.name}</span>
                    </div>
                  ))}
                </>
              ) : (
                <div className="analytics-dropdown-item">
                  Нет активных вакансий
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Recruiter Multi-select */}
      <div className="analytics-filter">
        <label className="analytics-filter-label">Рекрутеры</label>
        <div className="analytics-dropdown" ref={recruiterRef}>
          <button
            className="analytics-dropdown-trigger"
            onClick={() => {
              setRecruiterOpen(!recruiterOpen);
              setPeriodOpen(false);
              setVacancyOpen(false);
            }}
          >
            <span>
              {filters.recruiter_ids?.length ?
                `Выбрано: ${filters.recruiter_ids.length}` :
                'Все рекрутеры'
              }
            </span>
            <Icon name="chevron-down" size={14} />
          </button>

          {recruiterOpen && (
            <div className="analytics-dropdown-content" style={{ maxHeight: '240px', overflowY: 'auto' }}>
              {usersLoading ? (
                <div className="analytics-dropdown-item">
                  Загрузка пользователей...
                </div>
              ) : recruiters.length ? (
                <>
                  <div
                    className="analytics-dropdown-item"
                    onClick={() => onChange({ recruiter_ids: undefined })}
                  >
                    <input type="checkbox" checked={!filters.recruiter_ids?.length} readOnly />
                    <span>Все рекрутеры</span>
                  </div>
                  {recruiters.map(recruiter => (
                    <div
                      key={recruiter.id}
                      className="analytics-dropdown-item"
                      onClick={() => handleRecruiterToggle(recruiter.id)}
                    >
                      <input
                        type="checkbox"
                        checked={filters.recruiter_ids?.includes(recruiter.id) || false}
                        readOnly
                      />
                      <span>{recruiter.full_name || 'Пользователь'}</span>
                    </div>
                  ))}
                </>
              ) : (
                <div className="analytics-dropdown-item">
                  Нет доступных рекрутёров
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Compare Toggle */}
      <div className="analytics-filter">
        <label className="analytics-filter-label">Сравнение</label>
        <label className="analytics-toggle">
          <input
            type="checkbox"
            checked={filters.compare}
            onChange={(e) => onChange({ compare: e.target.checked })}
          />
          <span>С прошлым периодом</span>
        </label>
      </div>

      {/* Export Button */}
      <div className="analytics-filter">
        <label className="analytics-filter-label">&nbsp;</label>
        <button
          className="analytics-export-btn"
          onClick={handleExport}
          disabled={isLoading || exportMutation.isPending}
        >
          {exportMutation.isPending ? (
            <>
              <Icon name="spinner" size={14} />
              Экспорт...
            </>
          ) : (
            <>
              <Icon name="download" size={14} />
              Excel
            </>
          )}
        </button>
      </div>
    </div>
  );
}