import { useState, useRef, useEffect } from 'react';
import type { AnalyticsFilters } from '@/api/aliases';
import { useVacancies } from '@/api/hooks/useVacancies';
import { useExportAnalytics } from '@/api/mutations/exportAnalytics';
import { Icon } from '@/components/ui/Icon';

interface AnHeaderControlsProps {
  report: string;
  filters: AnalyticsFilters;
  onChange: (filters: Partial<AnalyticsFilters>) => void;
  isLoading: boolean;
}

const PERIOD_OPTIONS = [
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'quarter', label: 'Квартал' },
  { value: 'year', label: 'Год' },
] as const;

export function AnHeaderControls({ report, filters, onChange, isLoading }: AnHeaderControlsProps) {
  const [periodOpen, setPeriodOpen] = useState(false);
  const [scopeOpen, setScopeOpen] = useState(false);

  const periodRef = useRef<HTMLDivElement>(null);
  const scopeRef = useRef<HTMLDivElement>(null);

  const exportMutation = useExportAnalytics();
  const { data: vacanciesData, isLoading: vacanciesLoading } = useVacancies({ status: 'active', page_size: 100 });

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (periodRef.current && !periodRef.current.contains(event.target as Node)) setPeriodOpen(false);
      if (scopeRef.current && !scopeRef.current.contains(event.target as Node)) setScopeOpen(false);
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const isCustom = filters.period === 'custom';
  const selectedPeriod = PERIOD_OPTIONS.find((p) => p.value === filters.period);
  const periodLabel = isCustom ? 'Произвольный' : selectedPeriod?.label ?? 'Месяц';

  const selectedCount = filters.vacancy_ids?.length || 0;
  const scopeLabel = selectedCount > 0 ? `Выбрано: ${selectedCount}` : 'Все вакансии';

  const toggleVacancy = (id: string) => {
    const current = filters.vacancy_ids || [];
    const updated = current.includes(id) ? current.filter((v) => v !== id) : [...current, id];
    onChange({ vacancy_ids: updated.length > 0 ? updated : undefined });
  };

  const handleExport = () => {
    exportMutation.mutate({ report, format: 'xlsx', ...filters });
  };

  return (
    <div className="an-header-controls">
      {/* Период */}
      <div className="an-dd" ref={periodRef}>
        <button
          className="an-dd-btn"
          onClick={() => {
            setPeriodOpen((o) => !o);
            setScopeOpen(false);
          }}
        >
          <span className="an-dd-cap">Период</span>
          <span className="an-dd-val">{periodLabel}</span>
          <Icon name="chevron-down" size={14} />
        </button>
        {periodOpen && (
          <div className="an-dd-menu">
            {PERIOD_OPTIONS.map((opt) => (
              <div
                key={opt.value}
                className={`an-dd-opt ${opt.value === filters.period ? 'active' : ''}`}
                onClick={() => {
                  onChange({ period: opt.value, date_from: undefined, date_to: undefined });
                  setPeriodOpen(false);
                }}
              >
                <span className="an-dd-opt-left">{opt.label}</span>
                {opt.value === filters.period && <Icon name="check" size={14} />}
              </div>
            ))}
            <div className="an-dd-divider" />
            <div
              className={`an-dd-opt ${isCustom ? 'active' : ''}`}
              onClick={() => onChange({ period: 'custom' })}
            >
              <span className="an-dd-opt-left">
                <Icon name="cal-clock" size={14} /> Произвольный диапазон…
              </span>
            </div>
            {isCustom && (
              <div className="an-dd-range">
                <label>С</label>
                <input
                  type="date"
                  value={filters.date_from || ''}
                  onChange={(e) => onChange({ date_from: e.target.value || undefined })}
                />
                <label>По</label>
                <input
                  type="date"
                  value={filters.date_to || ''}
                  onChange={(e) => onChange({ date_to: e.target.value || undefined })}
                />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Скоуп — мультиселект по вакансиям */}
      <div className="an-dd" ref={scopeRef}>
        <button
          className="an-dd-btn"
          onClick={() => {
            setScopeOpen((o) => !o);
            setPeriodOpen(false);
          }}
        >
          <span className="an-dd-cap">Скоуп</span>
          <span className="an-dd-val">{scopeLabel}</span>
          <Icon name="chevron-down" size={14} />
        </button>
        {scopeOpen && (
          <div className="an-dd-menu an-dd-scroll">
            <div className="an-dd-opt" onClick={() => onChange({ vacancy_ids: undefined })}>
              <span className="an-dd-opt-left">
                <span className={`an-dd-check ${selectedCount === 0 ? 'on' : ''}`}>
                  {selectedCount === 0 && <Icon name="check" size={10} />}
                </span>
                Все вакансии
              </span>
            </div>
            {vacanciesLoading ? (
              <div className="an-dd-opt disabled">
                <span className="an-dd-opt-left">Загрузка вакансий…</span>
              </div>
            ) : vacanciesData?.items?.length ? (
              vacanciesData.items.map((vacancy) => {
                const checked = filters.vacancy_ids?.includes(vacancy.id) || false;
                return (
                  <div key={vacancy.id} className="an-dd-opt" onClick={() => toggleVacancy(vacancy.id)}>
                    <span className="an-dd-opt-left">
                      <span className={`an-dd-check ${checked ? 'on' : ''}`}>
                        {checked && <Icon name="check" size={10} />}
                      </span>
                      {vacancy.name}
                    </span>
                  </div>
                );
              })
            ) : (
              <div className="an-dd-opt disabled">
                <span className="an-dd-opt-left">Нет активных вакансий</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Сравнение с прошлым периодом */}
      <label className="an-compare">
        <input
          type="checkbox"
          checked={filters.compare !== false}
          onChange={(e) => onChange({ compare: e.target.checked })}
        />
        Сравнить с прошлым периодом
      </label>

      {/* Экспорт CSV/XLSX */}
      <button className="an-csv" onClick={handleExport} disabled={isLoading || exportMutation.isPending}>
        <Icon name="download" size={14} className={exportMutation.isPending ? 'an-spin' : undefined} />
        {exportMutation.isPending ? 'Экспорт…' : 'Экспорт'}
      </button>
    </div>
  );
}
