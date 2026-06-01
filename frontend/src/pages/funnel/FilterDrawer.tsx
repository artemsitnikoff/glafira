import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import type { ApplicationFilters } from '@/api/hooks/useApplications';
import { useTags } from '@/api/hooks/useTags';

type Props = {
  onClose: () => void;
  filters: ApplicationFilters;
  onFiltersChange: (filters: ApplicationFilters) => void;
};

// Источники — реальные значения Candidate.source (RU-лейблы), мультивыбор.
const SOURCES = [
  { id: 'hh', label: 'HeadHunter' },
  { id: 'avito', label: 'Авито' },
  { id: 'superjob', label: 'SuperJob' },
  { id: 'telegram', label: 'Telegram' },
  { id: 'referral', label: 'Реферал' },
  { id: 'direct', label: 'Напрямую' },
  { id: 'agency', label: 'Агентство' },
  { id: 'manual', label: 'Вручную' },
  { id: 'import', label: 'Импорт' },
  { id: 'other', label: 'Другое' },
];

// Мессенджер — реальные значения Candidate.preferred_channel, мультивыбор.
const MESSENGERS = [
  { id: 'telegram', label: 'Telegram' },
  { id: 'email', label: 'E-mail' },
  { id: 'phone', label: 'Телефон' },
];

// Период отбора — значения added_period, поддерживаемые беком (одиночный выбор).
const PERIODS = [
  { id: '7d', label: 'Неделя' },
  { id: '30d', label: 'Месяц' },
  { id: '90d', label: 'Квартал' },
  { id: 'all', label: 'Всё время' },
];

// Локальный черновик фильтра — копится в drawer, применяется ТОЛЬКО по кнопке.
type Draft = {
  score_min: number;   // 0 = неактивно
  salary_max: number;  // 500 = неактивно (без потолка)
  source: string[];
  city: string;        // свободный ввод (бэк: ILIKE)
  messenger: string[];
  ready_relocate: boolean;
  added_period: string; // '' = «Всё время» (неактивно)
  repeat: boolean;
  tags: string[];       // id выбранных тегов
};

const EMPTY_DRAFT: Draft = {
  score_min: 0, salary_max: 500, source: [], city: '',
  messenger: [], ready_relocate: false, added_period: '', repeat: false, tags: [],
};

const asArray = (v: string | string[] | undefined): string[] =>
  Array.isArray(v) ? v : v ? [v] : [];

function filtersToDraft(f: ApplicationFilters): Draft {
  return {
    score_min: f.score_min ?? 0,
    salary_max: f.salary_max ? f.salary_max / 1000 : 500, // Конвертация рублей в тысячи для UI
    source: asArray(f.source),
    city: typeof f.city === 'string' ? f.city : '',
    messenger: asArray(f.messenger),
    ready_relocate: !!f.ready_relocate,
    added_period: f.added_period && f.added_period !== 'all' ? f.added_period : '',
    repeat: !!f.repeat,
    tags: asArray(f.tags),
  };
}

// Накладываем черновик на текущие filters — этап/поиск/сортировка сохраняются.
function applyDraft(base: ApplicationFilters, d: Draft): ApplicationFilters {
  return {
    stage: base.stage,
    search: base.search,
    sort: base.sort,
    order: base.order,
    score_min: d.score_min > 0 ? d.score_min : undefined,
    salary_max: d.salary_max < 500 ? d.salary_max * 1000 : undefined, // Конвертация тысяч в рубли для API
    source: d.source.length ? d.source : undefined,
    city: d.city.trim() ? d.city.trim() : undefined,
    messenger: d.messenger.length ? d.messenger : undefined,
    ready_relocate: d.ready_relocate ? true : undefined,
    added_period: d.added_period ? d.added_period : undefined,
    repeat: d.repeat ? true : undefined,
    tags: d.tags.length ? d.tags : undefined,
  };
}

export default function FilterDrawer({ onClose, filters, onFiltersChange }: Props) {
  const [openSections, setOpenSections] = useState(new Set(['ai', 'salary', 'source']));
  // Черновик инициализируется из уже применённых фильтров.
  const [draft, setDraft] = useState<Draft>(() => filtersToDraft(filters));
  const { data: tagsData } = useTags();

  const toggleSection = (id: string) => {
    setOpenSections(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleInArray = (key: 'source' | 'messenger' | 'tags', id: string) => {
    setDraft(d => {
      const arr = d[key];
      return { ...d, [key]: arr.includes(id) ? arr.filter(x => x !== id) : [...arr, id] };
    });
  };

  const activeCount =
    (draft.score_min > 0 ? 1 : 0) +
    (draft.salary_max < 500 ? 1 : 0) +
    draft.source.length +
    (draft.city.trim() ? 1 : 0) +
    draft.messenger.length +
    (draft.ready_relocate ? 1 : 0) +
    (draft.added_period ? 1 : 0) +
    (draft.repeat ? 1 : 0) +
    draft.tags.length;

  const apply = () => { onFiltersChange(applyDraft(filters, draft)); onClose(); };
  const resetAll = () => { onFiltersChange(applyDraft(filters, EMPTY_DRAFT)); onClose(); };
  const resetDraft = () => setDraft(EMPTY_DRAFT);

  return (
    <>
      <div className="fdr-overlay" onClick={onClose} />
      <aside className="fdr">
        <div className="fdr-head">
          <div className="fdr-title">
            Фильтры
            {activeCount > 0 && (
              <button className="fdr-reset-circle" onClick={resetDraft} title="Сбросить">
                <Icon name="refresh" size={14} />
              </button>
            )}
          </div>
          <button className="icon-btn" onClick={onClose}>
            <Icon name="x" size={18} />
          </button>
        </div>

        <div className="fdr-pin-row">
          <button className="fdr-pin-btn" disabled title="Скоро">
            <Icon name="bookmark" size={13} />
            Сохранить настроенный фильтр
          </button>
        </div>

        <div className="fdr-body">
          <FilterSection title="AI-скоринг" count={draft.score_min > 0 ? 1 : 0} open={openSections.has('ai')} onToggle={() => toggleSection('ai')}>
            <div className="fdr-slider-row">
              <input type="range" min="0" max="100" step="5" value={draft.score_min}
                onChange={e => setDraft(d => ({ ...d, score_min: Number(e.target.value) }))} />
              <span className="fdr-slider-val t-mono">от {draft.score_min}</span>
            </div>
            <div className="fdr-tick-row"><span>0</span><span>50</span><span>100</span></div>
          </FilterSection>

          <FilterSection title="Зарплата, тыс ₽" count={draft.salary_max < 500 ? 1 : 0} open={openSections.has('salary')} onToggle={() => toggleSection('salary')}>
            <div className="fdr-slider-row">
              <input type="range" min="100" max="500" step="10" value={draft.salary_max}
                onChange={e => setDraft(d => ({ ...d, salary_max: Number(e.target.value) }))} />
              <span className="fdr-slider-val t-mono">до {draft.salary_max}</span>
            </div>
          </FilterSection>

          <FilterSection title="Источник" count={draft.source.length} open={openSections.has('source')} onToggle={() => toggleSection('source')}>
            <div className="fdr-chip-row">
              {SOURCES.map(s => (
                <button key={s.id} className={`filter-chip ${draft.source.includes(s.id) ? 'active' : ''}`} onClick={() => toggleInArray('source', s.id)}>
                  {s.label}
                </button>
              ))}
            </div>
          </FilterSection>

          <FilterSection title="Город проживания" count={draft.city.trim() ? 1 : 0} open={openSections.has('city')} onToggle={() => toggleSection('city')}>
            <input
              className="fdr-text-input"
              type="text"
              placeholder="Введите город"
              value={draft.city}
              onChange={e => setDraft(d => ({ ...d, city: e.target.value }))}
            />
          </FilterSection>

          <FilterSection title="Мессенджер" count={draft.messenger.length} open={openSections.has('mess')} onToggle={() => toggleSection('mess')}>
            <div className="fdr-chip-row">
              {MESSENGERS.map(m => (
                <button key={m.id} className={`filter-chip ${draft.messenger.includes(m.id) ? 'active' : ''}`} onClick={() => toggleInArray('messenger', m.id)}>
                  {m.label}
                </button>
              ))}
            </div>
          </FilterSection>

          <FilterSection title="Готовность" count={draft.ready_relocate ? 1 : 0} open={openSections.has('ready')} onToggle={() => toggleSection('ready')}>
            <label className="fdr-check">
              <input type="checkbox" checked={draft.ready_relocate} onChange={e => setDraft(d => ({ ...d, ready_relocate: e.target.checked }))} />
              <span>Готов к переезду</span>
            </label>
          </FilterSection>

          <FilterSection title="Период отбора на вакансию" count={draft.added_period ? 1 : 0} open={openSections.has('period')} onToggle={() => toggleSection('period')}>
            <div className="fdr-chip-row">
              {PERIODS.map(p => (
                <button
                  key={p.id}
                  className={`filter-chip ${(draft.added_period || 'all') === p.id ? 'active' : ''}`}
                  onClick={() => setDraft(d => ({ ...d, added_period: p.id === 'all' ? '' : p.id }))}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </FilterSection>

          <FilterSection title="Повторный отклик" count={draft.repeat ? 1 : 0} open={openSections.has('repeat')} onToggle={() => toggleSection('repeat')}>
            <label className="fdr-check">
              <input type="checkbox" checked={draft.repeat} onChange={e => setDraft(d => ({ ...d, repeat: e.target.checked }))} />
              <span>Только повторно откликнувшиеся</span>
            </label>
          </FilterSection>

          {tagsData && tagsData.length > 0 && (
            <FilterSection title="Теги" count={draft.tags.length} open={openSections.has('tags')} onToggle={() => toggleSection('tags')}>
              <div className="fdr-chip-row">
                {tagsData.map(tag => (
                  <button
                    key={tag.id}
                    className={`filter-chip ${draft.tags.includes(tag.id) ? 'active' : ''}`}
                    onClick={() => toggleInArray('tags', tag.id)}
                  >
                    {tag.name}
                  </button>
                ))}
              </div>
            </FilterSection>
          )}
        </div>

        <div className="fdr-foot">
          <button className="btn btn-secondary btn-sm" onClick={resetAll}>Сбросить всё</button>
          <button className="btn btn-primary btn-sm" onClick={apply}>Применить</button>
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
