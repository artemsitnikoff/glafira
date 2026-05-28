import type { AnalyticsKpiCard } from '@/api/aliases';

interface KpiStripProps {
  kpis: AnalyticsKpiCard[];
}

export function KpiStrip({ kpis }: KpiStripProps) {
  if (!kpis || kpis.length === 0) {
    return null;
  }

  return (
    <div className="analytics-kpi-strip">
      {kpis.map((kpi, index) => (
        <KpiCard key={kpi.key || index} kpi={kpi} />
      ))}
    </div>
  );
}

interface KpiCardProps {
  kpi: AnalyticsKpiCard;
}

function KpiCard({ kpi }: KpiCardProps) {
  const formatValue = (value: number | null | undefined) => {
    if (value === null || value === undefined) {
      return '—';
    }

    // Format large numbers
    if (value >= 1000000) {
      return `${(value / 1000000).toFixed(1)}M`;
    }
    if (value >= 1000) {
      return `${(value / 1000).toFixed(1)}K`;
    }

    // Check if it's a percentage-like value (between 0 and 100)
    if (value > 0 && value <= 100 && value % 1 !== 0) {
      return value.toFixed(1);
    }

    return Math.round(value).toLocaleString('ru-RU');
  };

  const formatDelta = (delta: number | null | undefined, deltaDir: string) => {
    if (delta === null || delta === undefined) {
      return null;
    }

    const sign = delta > 0 ? '+' : '';
    const formattedDelta = kpi.unit === '%' || kpi.unit === 'п.п.'
      ? `${sign}${delta.toFixed(1)}`
      : `${sign}${delta.toFixed(0)}`;

    const arrow = deltaDir.includes('up') ? '↑' : deltaDir.includes('down') ? '↓' : '';

    return (
      <span className={`analytics-delta ${deltaDir}`}>
        {arrow} {formattedDelta}{kpi.unit === '%' ? 'п.п.' : kpi.unit || ''}
      </span>
    );
  };

  return (
    <div className="analytics-kpi-card">
      <div className="analytics-kpi-label">{kpi.caption || kpi.key}</div>
      <div className="analytics-kpi-value">
        {formatValue(kpi.value)}
        {kpi.unit && kpi.value !== null && (
          <span className="analytics-kpi-unit">{kpi.unit}</span>
        )}
      </div>

      {(kpi.delta !== null || kpi.caption) && (
        <div className="analytics-kpi-delta">
          {formatDelta(kpi.delta, kpi.delta_dir || 'flat')}
          <span className="analytics-kpi-caption">
            {kpi.delta !== null ? 'к прошлому периоду' : ''}
          </span>
        </div>
      )}
    </div>
  );
}