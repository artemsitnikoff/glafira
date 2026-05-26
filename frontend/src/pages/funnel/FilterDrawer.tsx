import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import type { ApplicationFilters } from '@/api/hooks/useApplications';

type Props = {
  onClose: () => void;
  filters: ApplicationFilters;
  onFiltersChange: (filters: ApplicationFilters) => void;
};

const SOURCES = [
  { id: 'hh', label: 'HeadHunter' },
  { id: 'telegram', label: 'Глафира · Telegram' },
  { id: 'avito', label: 'Авито' },
];

const MESSENGERS = [
  { id: 'telegram', label: 'Telegram' },
  { id: 'whatsapp', label: 'WhatsApp' },
  { id: 'max', label: 'Max' },
];

const CITIES = ['Москва', 'СПб', 'Новосибирск'];

const PERIODS = [
  { id: '1d', label: 'Сегодня' },
  { id: '7d', label: 'Неделя' },
  { id: '30d', label: 'Месяц' },
  { id: '90d', label: 'Квартал' },
  { id: 'all', label: 'Всё время' },
];

export default function FilterDrawer({ onClose, filters, onFiltersChange }: Props) {
  const [openSections, setOpenSections] = useState(new Set(['ai', 'salary', 'source']));

  const toggleSection = (id: string) => {
    const next = new Set(openSections);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setOpenSections(next);
  };

  const resetFilters = () => {
    onFiltersChange({
      sort: filters.sort,
      order: filters.order,
    });
  };

  const hasActiveFilters = !!(
    filters.score_min ||
    filters.salary_max ||
    filters.source ||
    filters.city ||
    filters.messenger ||
    filters.ready_relocate ||
    filters.added_period ||
    filters.repeat
  );

  return (
    <>
      <div className="fdr-overlay" onClick={onClose} />
      <aside className="fdr">
        <div className="fdr-head">
          <div className="fdr-title">
            Фильтры
            {hasActiveFilters && (
              <button className="fdr-reset-circle" onClick={resetFilters} title="Сбросить">
                <Icon name="refresh" size={14} />
              </button>
            )}
          </div>
          <button className="icon-btn" onClick={onClose}>
            <Icon name="x" size={18} />
          </button>
        </div>

        <div className="fdr-pin-row">
          <button className="fdr-pin-btn" disabled>
            <Icon name="bookmark" size={13} />
            Сохранить настроенный фильтр
          </button>
        </div>

        <div className="fdr-body">
          <FilterSection
            title="AI-скоринг"
            count={filters.score_min ? 1 : 0}
            open={openSections.has('ai')}
            onToggle={() => toggleSection('ai')}
          >
            <div className="fdr-slider-row">
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                value={filters.score_min || 0}
                onChange={e =>
                  onFiltersChange({ ...filters, score_min: Number(e.target.value) })
                }
              />
              <span className="fdr-slider-val t-mono">от {filters.score_min || 0}</span>
            </div>
            <div className="fdr-tick-row">
              <span>0</span>
              <span>50</span>
              <span>100</span>
            </div>
          </FilterSection>

          <FilterSection
            title="Зарплата, тыс ₽"
            count={filters.salary_max && filters.salary_max < 500 ? 1 : 0}
            open={openSections.has('salary')}
            onToggle={() => toggleSection('salary')}
          >
            <div className="fdr-slider-row">
              <input
                type="range"
                min="100"
                max="500"
                step="10"
                value={filters.salary_max || 500}
                onChange={e =>
                  onFiltersChange({ ...filters, salary_max: Number(e.target.value) })
                }
              />
              <span className="fdr-slider-val t-mono">до {filters.salary_max || 500}</span>
            </div>
          </FilterSection>

          <FilterSection
            title="Источник"
            count={0} // TODO: calculate count
            open={openSections.has('source')}
            onToggle={() => toggleSection('source')}
          >
            <div className="fdr-chip-row">
              {SOURCES.map(source => (
                <button
                  key={source.id}
                  className={`filter-chip ${filters.source === source.id ? 'active' : ''}`}
                  onClick={() =>
                    onFiltersChange({
                      ...filters,
                      source: filters.source === source.id ? undefined : source.id,
                    })
                  }
                >
                  {source.label}
                </button>
              ))}
            </div>
          </FilterSection>

          <FilterSection
            title="Город проживания"
            count={0}
            open={openSections.has('city')}
            onToggle={() => toggleSection('city')}
          >
            <div className="fdr-chip-row">
              {CITIES.map(city => (
                <button
                  key={city}
                  className={`filter-chip ${filters.city === city ? 'active' : ''}`}
                  onClick={() =>
                    onFiltersChange({
                      ...filters,
                      city: filters.city === city ? undefined : city,
                    })
                  }
                >
                  {city}
                </button>
              ))}
            </div>
          </FilterSection>

          <FilterSection
            title="Мессенджер"
            count={0}
            open={openSections.has('mess')}
            onToggle={() => toggleSection('mess')}
          >
            <div className="fdr-chip-row">
              {MESSENGERS.map(messenger => (
                <button
                  key={messenger.id}
                  className={`filter-chip ${filters.messenger === messenger.id ? 'active' : ''}`}
                  onClick={() =>
                    onFiltersChange({
                      ...filters,
                      messenger: filters.messenger === messenger.id ? undefined : messenger.id,
                    })
                  }
                >
                  {messenger.label}
                </button>
              ))}
            </div>
          </FilterSection>

          <FilterSection
            title="Готовность"
            count={filters.ready_relocate ? 1 : 0}
            open={openSections.has('ready')}
            onToggle={() => toggleSection('ready')}
          >
            <label className="fdr-check">
              <input
                type="checkbox"
                checked={filters.ready_relocate || false}
                onChange={e =>
                  onFiltersChange({ ...filters, ready_relocate: e.target.checked })
                }
              />
              <span>Готов к переезду</span>
            </label>
          </FilterSection>

          <FilterSection
            title="Период отбора на вакансию"
            count={filters.added_period ? 1 : 0}
            open={openSections.has('period')}
            onToggle={() => toggleSection('period')}
          >
            <div className="fdr-chip-row">
              {PERIODS.map(period => (
                <button
                  key={period.id}
                  className={`filter-chip ${filters.added_period === period.id ? 'active' : ''}`}
                  onClick={() =>
                    onFiltersChange({
                      ...filters,
                      added_period: filters.added_period === period.id ? undefined : period.id,
                    })
                  }
                >
                  {period.label}
                </button>
              ))}
            </div>
          </FilterSection>

          <FilterSection
            title="Повторный отклик"
            count={filters.repeat ? 1 : 0}
            open={openSections.has('repeat')}
            onToggle={() => toggleSection('repeat')}
          >
            <label className="fdr-check">
              <input
                type="checkbox"
                checked={filters.repeat || false}
                onChange={e => onFiltersChange({ ...filters, repeat: e.target.checked })}
              />
              <span>Только повторно откликнувшиеся</span>
            </label>
          </FilterSection>
        </div>

        <div className="fdr-foot">
          <button className="btn btn-secondary btn-sm" onClick={resetFilters}>
            Сбросить всё
          </button>
          <button className="btn btn-primary btn-sm" onClick={onClose}>
            Показать результаты
          </button>
        </div>
      </aside>
    </>
  );
}

function FilterSection({
  title,
  count,
  open,
  onToggle,
  children,
}: {
  title: string;
  count: number;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className={`fdr-section ${open ? 'open' : ''}`}>
      <button className="fdr-section-head" onClick={onToggle}>
        <span className="fdr-section-title">{title}</span>
        {count > 0 && <span className="fdr-section-count">{count}</span>}
        <Icon name="chevD" size={14} className={`fdr-chev ${open ? 'rot' : ''}`} />
      </button>
      {open && <div className="fdr-section-body">{children}</div>}
    </div>
  );
}