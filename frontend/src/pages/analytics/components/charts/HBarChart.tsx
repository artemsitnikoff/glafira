/**
 * Horizontal bar chart — Top-5 вакансий по откликам.
 * Источник: overview.py:_build_top_vacancies_chart
 * Форма data: { items: [{ label: string, value: number }] }
 * Content-only: карточку и empty-state даёт AnChart. CSS-идиом .hbar-* из эталона.
 */

import { ANALYTICS_PALETTE } from '../../palette';

interface HBarItem {
  label: string;
  value: number;
  highlight?: boolean;
  color?: string;
}

interface HBarChartProps {
  data: { items: HBarItem[] };
}

export function HBarChart({ data }: HBarChartProps) {
  const max = Math.max(...data.items.map((d) => d.value)) * 1.05 || 1;

  return (
    <div className="hbar-chart">
      {data.items.map((d, i) => (
        <div key={i} className="hbar-row">
          <div className="hbar-label">{d.label}</div>
          <div className="hbar-track">
            <div
              className="hbar-fill"
              style={{
                width: `${(d.value / max) * 100}%`,
                background: d.color || (d.highlight ? ANALYTICS_PALETTE.red : ANALYTICS_PALETTE.blue),
              }}
            />
          </div>
          <div className="hbar-val">{d.value.toLocaleString('ru-RU')}</div>
        </div>
      ))}
    </div>
  );
}
