import { useUiStore } from '@/store/uiStore';
import { useHomeKpi } from '@/api/hooks/useHomeKpi';
import { Skeleton } from '@/components/ui/Skeleton';
import { Tooltip } from '@/components/ui/Tooltip';
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
  const cls =
    dir === 'up' || dir === 'down-good' ? 'kpi-card__delta--good' :
    dir === 'down' || dir === 'up-bad' ? 'kpi-card__delta--bad' :
    'kpi-card__delta--flat';
  const showDelta = period !== 'all' && card.delta !== null && card.delta !== undefined;
  const value = card.value === null || card.value === undefined ? '—' : Math.round(card.value).toLocaleString('ru-RU');

  return (
    <div className="kpi-card">
      <div className="kpi-card__head">
        <span className="kpi-card__label">{meta.label}</span>
        <Tooltip content={meta.tooltip}>
          <span className="kpi-card__info">i</span>
        </Tooltip>
      </div>
      <div className="kpi-card__value mono">
        {value} {card.unit && <span className="kpi-card__unit">{card.unit}</span>}
      </div>
      <div className="kpi-card__foot">
        {showDelta ? (
          <span className={`kpi-card__delta ${cls}`}>
            {symbol} {Math.abs(card.delta!).toFixed(1)}
          </span>
        ) : (
          <span className="kpi-card__delta kpi-card__delta--flat">—</span>
        )}
        {card.caption && <span className="kpi-card__caption">{card.caption}</span>}
      </div>
    </div>
  );
}