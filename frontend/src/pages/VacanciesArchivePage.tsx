import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import './archive/Archive.css';
import { Icon } from '@/components/ui/Icon';
import { useArchivedVacancies, type ArchivedVacancyItem } from '@/api/hooks/useArchivedVacancies';
import { Skeleton } from '@/components/ui/Skeleton';

type ResultKind = 'success' | 'fail' | 'frozen';
type ResultFilter = 'all' | 'success' | 'fail';
type PeriodFilter = 'all' | 'week' | 'month' | 'quarter' | 'year';

const MONTHS_RU = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];

const PERIOD_LIMITS: Record<Exclude<PeriodFilter, 'all'>, number> = {
  week: 7,
  month: 31,
  quarter: 92,
  year: 366,
};

function mapResult(archiveResult: string | null): ResultKind {
  if (archiveResult === 'hired') return 'success';
  if (archiveResult === 'frozen') return 'frozen';
  return 'fail'; // cancelled или неизвестно
}

function formatRuDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${d.getDate()} ${MONTHS_RU[d.getMonth()]} ${d.getFullYear()}`;
}

function diffDays(startIso: string, endIso: string | null): number {
  if (!endIso) return 0;
  const start = new Date(startIso).getTime();
  const end = new Date(endIso).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return 0;
  return Math.max(0, Math.round((end - start) / 86400000));
}

function daysWord(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'день';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'дня';
  return 'дней';
}

export default function VacanciesArchivePage() {
  const { data, isLoading } = useArchivedVacancies();
  const items = data ?? [];

  const [resultFilter, setResultFilter] = useState<ResultFilter>('all');
  const [periodFilter, setPeriodFilter] = useState<PeriodFilter>('all');
  const [clientFilter, setClientFilter] = useState<string>('all');
  const [recruiterFilter, setRecruiterFilter] = useState<string>('all');
  const [query, setQuery] = useState('');

  const clients = useMemo(
    () => Array.from(new Set(items.map(i => i.client_name).filter(Boolean) as string[])).sort(),
    [items],
  );
  const recruiters = useMemo(
    () => Array.from(new Set(items.map(i => i.recruiter_name).filter(Boolean) as string[])).sort(),
    [items],
  );

  const filtered = useMemo(() => {
    const now = Date.now();
    return items.filter(it => {
      if (resultFilter !== 'all' && mapResult(it.archive_result) !== resultFilter) return false;
      if (periodFilter !== 'all') {
        if (!it.closed_at) return false;
        const age = Math.max(0, Math.round((now - new Date(it.closed_at).getTime()) / 86400000));
        if (age > PERIOD_LIMITS[periodFilter]) return false;
      }
      if (clientFilter !== 'all' && it.client_name !== clientFilter) return false;
      if (recruiterFilter !== 'all' && it.recruiter_name !== recruiterFilter) return false;
      if (query && !it.name.toLowerCase().includes(query.toLowerCase())) return false;
      return true;
    });
  }, [items, resultFilter, periodFilter, clientFilter, recruiterFilter, query]);

  const hasFilters =
    resultFilter !== 'all' ||
    periodFilter !== 'all' ||
    clientFilter !== 'all' ||
    recruiterFilter !== 'all' ||
    query !== '';

  const reset = () => {
    setResultFilter('all');
    setPeriodFilter('all');
    setClientFilter('all');
    setRecruiterFilter('all');
    setQuery('');
  };

  if (isLoading) {
    return (
      <div className="content-inner archive-page">
        <div className="archive-head">
          <h1>Архив вакансий</h1>
          <Skeleton width={180} height={14} />
        </div>
        <div className="filter-bar">
          <Skeleton width={260} height={28} />
          <Skeleton width={360} height={28} />
          <div className="filter-spacer" />
          <Skeleton width={240} height={28} />
        </div>
        <div className="archive-grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} height={170} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="content-inner archive-page">
      <div className="archive-head">
        <h1>Архив вакансий</h1>
        <div className="sub">
          {hasFilters ? (
            <>
              Показано <span className="t-mono">{filtered.length}</span> из{' '}
              <span className="t-mono">{items.length}</span>
            </>
          ) : (
            <>
              <span className="t-mono">{items.length}</span>{' '}
              {items.length === 1 ? 'закрытая вакансия' : 'закрытых вакансий'}
            </>
          )}
        </div>
      </div>

      <div className="filter-bar">
        <div className="filter-group">
          <span className="filter-label">Результат</span>
          <div className="seg-sm">
            <button className={resultFilter === 'all' ? 'active' : ''} onClick={() => setResultFilter('all')}>
              Все
            </button>
            <button className={resultFilter === 'success' ? 'active' : ''} onClick={() => setResultFilter('success')}>
              ✓ Успех
            </button>
            <button className={resultFilter === 'fail' ? 'active' : ''} onClick={() => setResultFilter('fail')}>
              ✕ Без найма
            </button>
          </div>
        </div>

        <div className="filter-group">
          <span className="filter-label">Период</span>
          <div className="seg-sm">
            {([
              { id: 'week', l: 'Неделя' },
              { id: 'month', l: 'Месяц' },
              { id: 'quarter', l: 'Квартал' },
              { id: 'year', l: 'Год' },
              { id: 'all', l: 'Всё время' },
            ] as { id: PeriodFilter; l: string }[]).map(p => (
              <button
                key={p.id}
                className={periodFilter === p.id ? 'active' : ''}
                onClick={() => setPeriodFilter(p.id)}
              >
                {p.l}
              </button>
            ))}
          </div>
        </div>

        {clients.length > 0 && (
          <div className="filter-group">
            <span className="filter-label">Заказчик</span>
            <FilterDropdown value={clientFilter} options={clients} onChange={setClientFilter} />
          </div>
        )}

        {recruiters.length > 0 && (
          <div className="filter-group">
            <span className="filter-label">Рекрутер</span>
            <FilterDropdown value={recruiterFilter} options={recruiters} onChange={setRecruiterFilter} />
          </div>
        )}

        <div className="filter-spacer" />

        <div className="submenu-search" style={{ width: 240, height: 28 }}>
          <Icon name="search" size={14} style={{ color: 'var(--fg-3)', flex: 'none' }} />
          <input
            placeholder="Поиск по архиву…"
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
        </div>

        {hasFilters && (
          <button className="btn btn-ghost btn-sm" onClick={reset}>
            <Icon name="x" size={14} /> Сбросить
          </button>
        )}
      </div>

      {filtered.length === 0 ? (
        <div className="empty-pane" style={{ minHeight: 280 }}>
          <div className="empty-illust">
            <Icon name={items.length === 0 ? 'archive' : 'filter'} size={36} />
          </div>
          <h3>{items.length === 0 ? 'Архив пуст' : 'Ничего не найдено'}</h3>
          <p>
            {items.length === 0
              ? 'Закрытые вакансии появятся здесь. Закройте вакансию из карточки воронки — она переедет в архив.'
              : 'По заданным фильтрам ничего не найдено. Попробуйте сбросить часть условий.'}
          </p>
          {hasFilters && (
            <button className="btn btn-secondary btn-sm" onClick={reset}>
              Сбросить фильтры
            </button>
          )}
        </div>
      ) : (
        <ArchiveGrid items={filtered} />
      )}
    </div>
  );
}

function FilterDropdown({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const select = (v: string) => {
    onChange(v);
    setOpen(false);
  };
  return (
    <div className="dropdown-wrap">
      <button
        className={`dropdown${value !== 'all' ? ' active' : ''}`}
        onClick={() => setOpen(o => !o)}
      >
        {value === 'all' ? 'Все' : value}
        <Icon name="chevD" size={12} />
      </button>
      {open && (
        <>
          <div className="dropdown-overlay" onClick={() => setOpen(false)} />
          <div className="dropdown-menu">
            <button className={value === 'all' ? 'active' : ''} onClick={() => select('all')}>
              Все
            </button>
            {options.map(opt => (
              <button key={opt} className={value === opt ? 'active' : ''} onClick={() => select(opt)}>
                {opt}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ArchiveGrid({ items }: { items: ArchivedVacancyItem[] }) {
  const navigate = useNavigate();

  const resultBadge = (archiveResult: string | null) => {
    const kind = mapResult(archiveResult);
    if (kind === 'success') {
      return (
        <span className="result-badge success">
          <Icon name="check" size={11} /> Успех
        </span>
      );
    }
    if (kind === 'frozen') {
      return (
        <span className="result-badge frozen">
          <Icon name="pause" size={11} /> Заморожена
        </span>
      );
    }
    return (
      <span className="result-badge fail">
        <Icon name="x" size={11} /> Без найма
      </span>
    );
  };

  return (
    <div className="archive-grid">
      {items.map(item => {
        const days = diffDays(item.created_at, item.closed_at);
        return (
          <div key={item.id} className="arch-card" onClick={() => navigate(`/vacancies/${item.id}`)}>
            <div className="top-row">
              {resultBadge(item.archive_result)}
              <button className="more-btn" onClick={e => e.stopPropagation()}>
                <Icon name="more" size={14} />
              </button>
            </div>
            <div className="title">{item.name}</div>
            <div className="meta">
              {item.client_name || '—'}
              <span className="sep">·</span>
              {item.recruiter_name || '—'}
            </div>
            <div className="meta" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <Icon name="clock" size={13} style={{ color: 'var(--fg-3)' }} />
              {item.closed_at ? `Закрыта за ${days} ${daysWord(days)}` : 'Закрыта'}
              <span className="sep">·</span>
              {formatRuDate(item.closed_at)}
            </div>
            <div className="stats-row">
              <div className="stat-cell">
                <span className="stat-val">{item.candidates}</span>
                <span className="stat-lbl">кандидатов</span>
              </div>
              <div className="stat-cell">
                <span
                  className="stat-val"
                  style={{ color: item.hired > 0 ? 'var(--ark-green-600)' : 'var(--fg-3)' }}
                >
                  {item.hired}
                </span>
                <span className="stat-lbl">{item.hired === 1 ? 'нанят' : 'нанято'}</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
