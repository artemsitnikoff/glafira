import { useUiStore } from '@/store/uiStore';
import { useHomeKpi } from '@/api/hooks/useHomeKpi';
import { Skeleton } from '@/components/ui/Skeleton';
import { KPI_LABELS } from '@/lib/kpi-labels';
import type { HomeKpiCard } from '@/api/aliases';

interface KpiGridProps {
  period: string;
}

export function KpiGrid({ period }: KpiGridProps) {
  const { kpiExtended } = useUiStore();
  const { data, isLoading } = useHomeKpi(period, kpiExtended);

  if (isLoading) {
    const n = kpiExtended ? 8 : 6;
    return (
      <div className="kpi-grid">
        {Array.from({ length: n }).map((_, i) => (
          <Skeleton key={i} height={120} />
        ))}
      </div>
    );
  }

  return (
    <div className="kpi-grid">
      {(data?.cards ?? []).map((card) => (
        <KpiCard key={card.key} card={card} period={period} />
      ))}
    </div>
  );
}

interface KpiCardProps {
  card: HomeKpiCard;
  period: string;
}

function KpiCard({ card, period }: KpiCardProps) {
  const meta = KPI_LABELS[card.key] ?? { label: card.key, tooltip: '' };
  const dir = card.delta_dir;
  const symbol = dir === 'up' || dir === 'up-bad' ? '▲' : dir === 'down' || dir === 'down-good' ? '▼' : '—';
  const deltaClass =
    dir === 'up' ? 'up' :
    dir === 'down' ? 'down' :
    dir === 'up-bad' ? 'up-bad' :
    dir === 'down-good' ? 'down-good' :
    'flat';
  const showDelta = period !== 'all' && card.delta !== null && card.delta !== undefined;
  const value = card.value === null || card.value === undefined ? '—' : Math.round(card.value).toLocaleString('ru-RU');

  return (
    <div className="kpi" title={meta.tooltip}>
      <div className="kpi-label">
        {meta.label}
        <span className="info" title={meta.tooltip}>i</span>
      </div>
      <div className="kpi-value-row">
        <span className="kpi-value">{value}</span>
        {card.unit && <span className="kpi-unit">{card.unit}</span>}
      </div>
      <div className="kpi-foot">
        {showDelta ? (
          <span className={`delta ${deltaClass}`}>
            {symbol} {Math.abs(card.delta!).toFixed(1)}
          </span>
        ) : (
          <span className="delta flat">—</span>
        )}
        <span className="kpi-sub">{card.caption}</span>
      </div>
    </div>
  );
}