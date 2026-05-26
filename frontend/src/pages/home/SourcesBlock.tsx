import { useHomeSources } from '@/api/hooks/useHomeSources';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { SOURCE_CONFIG } from '@/lib/source-colors';

function periodLabel(period: string): string {
  const labels: Record<string, string> = {
    week: 'неделю',
    month: 'месяц',
    quarter: 'квартал',
    year: 'год',
    all: 'всё время',
  };
  return labels[period] || period;
}

interface Props {
  period: string;
}

export function SourcesBlock({ period }: Props) {
  const { data, isLoading } = useHomeSources(period);

  if (isLoading) return <Skeleton height={200} />;

  const items = (data ?? []).slice().sort((a, b) => b.count - a.count);
  const max = items.length > 0 ? Math.max(...items.map(i => i.count)) : 0;

  return (
    <section className="block sources-block">
      <header className="block__head">
        <div className="block__title">Топ-источники кандидатов</div>
        <span className="block__sub">за {periodLabel(period)}</span>
      </header>
      {items.length === 0 ? (
        <EmptyState title="Пока нет данных" />
      ) : (
        <div className="sources-list">
          {items.map(s => {
            const cfg = SOURCE_CONFIG[s.source] ?? { label: s.source, color: 'var(--fg-3)' };
            const widthPct = max > 0 ? (s.count / max) * 100 : 0;
            return (
              <div key={s.source} className="src-row">
                <div className="src-row__label">{cfg.label}</div>
                <div className="src-row__bar">
                  <span style={{ width: `${widthPct}%`, background: cfg.color }} />
                </div>
                <div className="src-row__count mono">{s.count}</div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}