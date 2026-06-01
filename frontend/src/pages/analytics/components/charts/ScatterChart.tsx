/**
 * Scatter chart — источники: качество (avg AI-score) × объём.
 * Источник: sources.py:_build_scatter_chart
 * Форма data: { points: [{ label: string, x: number, y: number }] }
 * Пусто если у источников нет ai_score → AnChart покажет empty-state.
 * Content-only: карточку даёт AnChart.
 */

import {
  ScatterChart as RechartsScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { ANALYTICS_PALETTE } from '../../palette';

interface ScatterPoint {
  label: string;
  x: number;
  y: number;
}

interface ScatterChartProps {
  data: { points: ScatterPoint[] };
}

function renderTooltip(props: { active?: boolean; payload?: Array<{ payload: ScatterPoint }> }) {
  if (!props.active || !props.payload || props.payload.length === 0) return null;
  const p = props.payload[0].payload;
  return (
    <div className="an-chart-tooltip">
      <div className="an-chart-tooltip-title">{p.label}</div>
      <div className="an-chart-tooltip-item">
        <span className="an-chart-tooltip-label">Качество (AI):</span>
        <span className="an-chart-tooltip-value">{p.x}</span>
      </div>
      <div className="an-chart-tooltip-item">
        <span className="an-chart-tooltip-label">Объём:</span>
        <span className="an-chart-tooltip-value">{p.y}</span>
      </div>
    </div>
  );
}

export function ScatterChart({ data }: ScatterChartProps) {
  return (
    <div className="an-chart-wrap">
      <div className="an-card-head" style={{ marginBottom: 8 }}>
        <div className="sub">X — качество (средний AI-скоринг), Y — объём откликов. Правый верх = лучшие каналы.</div>
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <RechartsScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-2)" />
          <XAxis dataKey="x" type="number" name="Качество" stroke="var(--fg-3)" fontSize={11} fontFamily="var(--font-mono)" tickLine={false} domain={['dataMin - 5', 'dataMax + 5']} />
          <YAxis dataKey="y" type="number" name="Объём" stroke="var(--fg-3)" fontSize={11} fontFamily="var(--font-mono)" tickLine={false} axisLine={false} width={36} domain={['dataMin - 2', 'dataMax + 2']} />
          <ZAxis range={[80, 80]} />
          <Tooltip content={renderTooltip as never} cursor={{ strokeDasharray: '3 3' }} />
          <Scatter data={data.points} fill={ANALYTICS_PALETTE.blue} />
        </RechartsScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
