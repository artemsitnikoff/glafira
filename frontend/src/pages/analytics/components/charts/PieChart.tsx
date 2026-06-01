/**
 * Pie/donut chart — причины отказов (наши vs кандидата).
 * Источник: rejections.py:_build_rejections_pie_chart
 * Форма data: { our: [{ reason, value, pct }], candidate: [{ reason, value, pct }] }
 * (одиночный вариант — массив [{ label|reason, value, color? }])
 * Content-only: карточку и empty-state даёт AnChart.
 */

import { paletteAt } from '../../palette';

interface PieItem {
  reason?: string;
  label?: string;
  value: number;
  pct?: number;
  color?: string;
}

interface DualPieData {
  our: PieItem[];
  candidate: PieItem[];
}

interface PieChartProps {
  data: PieItem[] | DualPieData;
}

const SIZE = 180;
const THICKNESS = 28;

function itemLabel(it: PieItem): string {
  return it.reason ?? it.label ?? 'Не указано';
}

interface Arc extends PieItem {
  path: string;
  computedColor: string;
  computedPct: number;
}

function buildArcs(items: PieItem[]): Arc[] {
  const total = items.reduce((s, d) => s + d.value, 0) || 1;
  const r = SIZE / 2;
  const innerR = r - THICKNESS;
  const cx = r;
  const cy = r;
  let acc = 0;
  return items.map((d, i) => {
    const start = acc / total;
    acc += d.value;
    const end = acc / total;
    const a0 = start * Math.PI * 2 - Math.PI / 2;
    const a1 = end * Math.PI * 2 - Math.PI / 2;
    const large = end - start > 0.5 ? 1 : 0;
    const x0 = cx + Math.cos(a0) * r;
    const y0 = cy + Math.sin(a0) * r;
    const x1 = cx + Math.cos(a1) * r;
    const y1 = cy + Math.sin(a1) * r;
    const xi0 = cx + Math.cos(a0) * innerR;
    const yi0 = cy + Math.sin(a0) * innerR;
    const xi1 = cx + Math.cos(a1) * innerR;
    const yi1 = cy + Math.sin(a1) * innerR;
    const path = `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} L ${xi1} ${yi1} A ${innerR} ${innerR} 0 ${large} 0 ${xi0} ${yi0} Z`;
    return {
      ...d,
      path,
      computedColor: d.color || paletteAt(i),
      computedPct: d.pct ?? (d.value / total) * 100,
    };
  });
}

function Donut({ items, centerLabel }: { items: PieItem[]; centerLabel: string }) {
  if (!items || items.length === 0) {
    return <div className="an-table-empty">Нет данных за период</div>;
  }
  const arcs = buildArcs(items);
  const total = items.reduce((s, d) => s + d.value, 0);
  const r = SIZE / 2;
  return (
    <div className="donut-wrap">
      <svg width={SIZE} height={SIZE}>
        {arcs.map((a, i) => (
          <path key={i} d={a.path} fill={a.computedColor} />
        ))}
        <text x={r} y={r - 4} textAnchor="middle" fontSize="22" fontWeight="600" fill="var(--fg-1)" fontFamily="Inter">
          {total.toLocaleString('ru-RU')}
        </text>
        <text x={r} y={r + 16} textAnchor="middle" fontSize="11" fill="var(--fg-3)" fontFamily="Inter">
          {centerLabel}
        </text>
      </svg>
      <div className="donut-legend">
        {arcs.map((a, i) => (
          <div key={i} className="legend-row">
            <span className="dot" style={{ background: a.computedColor }} />
            <span className="lbl">{itemLabel(a)}</span>
            <span className="num">{a.value}</span>
            <span className="pct">{a.computedPct.toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PieChart({ data }: PieChartProps) {
  // Двойной вариант (отказы наши vs кандидата)
  if (data && typeof data === 'object' && 'our' in data && 'candidate' in data) {
    const dual = data as DualPieData;
    const ourEmpty = !dual.our || dual.our.length === 0;
    const candEmpty = !dual.candidate || dual.candidate.length === 0;
    return (
      <div className="pie-dual">
        <div>
          <div className="pie-side-title">Мы отказали</div>
          {ourEmpty ? <div className="an-table-empty">Нет данных за период</div> : <Donut items={dual.our} centerLabel="отказов" />}
        </div>
        <div>
          <div className="pie-side-title">Кандидат отказал</div>
          {candEmpty ? <div className="an-table-empty">Нет данных за период</div> : <Donut items={dual.candidate} centerLabel="отказов" />}
        </div>
      </div>
    );
  }

  const items = Array.isArray(data) ? data : [];
  return <Donut items={items} centerLabel="всего" />;
}
