import type { AnalyticsKpiCard } from '@/api/aliases';
import { kpiLabel } from '../meta';

interface AnKpiBandProps {
  kpis: AnalyticsKpiCard[];
}

function formatValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (Math.abs(value) >= 1000) return Math.round(value).toLocaleString('ru-RU');
  // дробные (время, %) — 1 знак; целые — без дробей
  return value % 1 !== 0 ? value.toFixed(1) : String(Math.round(value));
}

function deltaText(kpi: AnalyticsKpiCard): { text: string; cls: string } | null {
  if (kpi.delta === null || kpi.delta === undefined) return null;
  const dir = kpi.delta_dir || 'flat';
  const arrow = dir.includes('up') ? '▲' : dir.includes('down') ? '▼' : '';
  const unitSuffix = kpi.unit === '%' || kpi.unit === 'дней' ? '' : '';
  const abs = Math.abs(kpi.delta);
  const num = abs % 1 !== 0 ? abs.toFixed(1) : String(Math.round(abs));
  return { text: `${arrow} ${num}${unitSuffix}`.trim(), cls: dir };
}

export function AnKpiBand({ kpis }: AnKpiBandProps) {
  if (!kpis || kpis.length === 0) return null;

  const bandClass = kpis.length === 3 ? 'band-3' : kpis.length === 5 ? 'band-5' : '';

  return (
    <div className={`an-kpi-band ${bandClass}`}>
      {kpis.map((kpi, i) => {
        const empty = kpi.value === null || kpi.value === undefined;
        const delta = deltaText(kpi);
        return (
          <div key={kpi.key || i} className={`an-kpi ${empty ? 'empty' : ''}`}>
            <div className="kpi-label">{kpiLabel(kpi.key, kpi.caption)}</div>
            <div className="kpi-value-row">
              <span className="kpi-value">{formatValue(kpi.value)}</span>
              {kpi.unit && !empty && <span className="kpi-unit">{kpi.unit}</span>}
            </div>
            <div className="kpi-foot">
              {delta ? <span className={`delta ${delta.cls}`}>{delta.text}</span> : <span />}
              <span className="kpi-sub">
                {empty ? 'нет данных' : delta ? 'к прошлому периоду' : ''}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
