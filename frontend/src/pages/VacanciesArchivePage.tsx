import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import './archive/Archive.css';
import { Icon } from '@/components/ui/Icon';
import { EmptyState } from '@/components/ui/EmptyState';
import { useArchivedVacancies } from '@/api/hooks/useArchivedVacancies';
import { Skeleton } from '@/components/ui/Skeleton';
import type { components } from '@/api/types';

type VacancyDetail = components['schemas']['VacancyDetail'];

export default function VacanciesArchivePage() {
  const { data, isLoading } = useArchivedVacancies();
  const [resultFilter, setResultFilter] = useState<'all' | 'success' | 'fail'>('all');
  const [periodFilter, setPeriodFilter] = useState<'week' | 'month' | 'quarter' | 'year' | 'all'>('all');
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    if (!data?.items) return [];
    return data.items.filter(item => {
      // For now just apply query filter
      if (query && !item.name.toLowerCase().includes(query.toLowerCase())) {
        return false;
      }
      return true;
    });
  }, [data?.items, query]);

  const hasFilters = resultFilter !== 'all' || periodFilter !== 'all' || query !== '';

  const reset = () => {
    setResultFilter('all');
    setPeriodFilter('all');
    setQuery('');
  };

  if (isLoading) {
    return (
      <div className="content-inner">
        <div className="archive-head">
          <h1>Архив вакансий</h1>
          <Skeleton width={200} height={16} />
        </div>
        <div className="filter-bar">
          <Skeleton width={300} height={32} />
          <Skeleton width={400} height={32} />
          <Skeleton width={240} height={32} />
        </div>
        <div className="archive-grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} height={180} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="content-inner">
      <div className="archive-head">
        <h1>Архив вакансий</h1>
        <div className="sub">
          {hasFilters ? (
            <>
              Показано <span className="t-mono">{filtered.length}</span> из{' '}
              <span className="t-mono">{data?.items?.length || 0}</span>
            </>
          ) : (
            <>
              <span className="t-mono">{data?.items?.length || 0}</span> закрытых вакансий
            </>
          )}
        </div>
      </div>

      <div className="filter-bar">
        <div className="filter-group">
          <span className="filter-label">Результат</span>
          <div className="seg-sm">
            <button
              className={resultFilter === 'all' ? 'active' : ''}
              onClick={() => setResultFilter('all')}
            >
              Все
            </button>
            <button
              className={resultFilter === 'success' ? 'active' : ''}
              onClick={() => setResultFilter('success')}
            >
              ✓ Успех
            </button>
            <button
              className={resultFilter === 'fail' ? 'active' : ''}
              onClick={() => setResultFilter('fail')}
            >
              ✕ Без найма
            </button>
          </div>
        </div>

        <div className="filter-group">
          <span className="filter-label">Период</span>
          <div className="seg-sm">
            {[
              { id: 'week' as const, l: 'Неделя' },
              { id: 'month' as const, l: 'Месяц' },
              { id: 'quarter' as const, l: 'Квартал' },
              { id: 'year' as const, l: 'Год' },
              { id: 'all' as const, l: 'Всё время' },
            ].map(p => (
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

        <div style={{ flex: 1 }} />

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
        <EmptyState
          icon="filter"
          title="Ничего не найдено"
          description="По заданным фильтрам ничего не найдено. Попробуйте сбросить часть условий."
        />
      ) : (
        <ArchiveTable items={filtered} />
      )}
    </div>
  );
}

function ArchiveTable({ items }: { items: VacancyDetail[] }) {
  const navigate = useNavigate();

  const getResultBadge = (result: string | null | undefined) => {
    if (result === 'hired') {
      return (
        <span className="result-badge success">
          <Icon name="check" size={11} /> Нанят
        </span>
      );
    }
    if (result === 'cancelled') {
      return (
        <span className="result-badge fail">
          <Icon name="x" size={11} /> Отменена
        </span>
      );
    }
    if (result === 'frozen') {
      return (
        <span className="result-badge frozen">
          <Icon name="pause" size={11} /> Заморожена
        </span>
      );
    }
    return <span className="result-badge frozen">—</span>;
  };

  const daysAgo = (iso: string | null | undefined): string => {
    if (!iso) return '—';
    const days = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86400000));
    if (days === 0) return 'сегодня';
    if (days === 1) return '1 день назад';
    if (days < 5) return `${days} дня назад`;
    return `${days} дней назад`;
  };

  const durationDays = (start: string | null | undefined, end: string | null | undefined): string => {
    if (!start || !end) return '—';
    const days = Math.max(0, Math.floor((new Date(end).getTime() - new Date(start).getTime()) / 86400000));
    return `срок: ${days} дн`;
  };

  return (
    <div className="archive-grid">
      {items.map(item => (
        <div
          key={item.id}
          className="arch-card"
          onClick={() => navigate(`/vacancies/${item.id}`)}
        >
          <div className="top-row">
            {getResultBadge(item.archive_result)}
            <button
              className="more-btn"
              onClick={e => e.stopPropagation()}
            >
              <Icon name="more" size={14} />
            </button>
          </div>
          <div className="title">{item.name}</div>
          <div className="meta">
            {item.client_name || 'Без клиента'}
            <span className="sep">·</span>
            {item.responsible_user?.full_name || 'Без ответственного'}
          </div>
          <div className="meta" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <Icon name="clock" size={13} style={{ color: 'var(--fg-3)' }} />
            Закрыта {daysAgo(item.closed_at)}
            <span className="sep">·</span>
            {durationDays(item.created_at, item.closed_at)}
          </div>
          <div className="stats-row">
            <div className="stat-cell">
              <span className="stat-val">0</span>
              <span className="stat-lbl">кандидатов</span>
            </div>
            <div className="stat-cell">
              <span className="stat-val" style={{ color: 'var(--fg-3)' }}>
                0
              </span>
              <span className="stat-lbl">нанято</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}