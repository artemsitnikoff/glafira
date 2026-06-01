/**
 * Radar chart — сравнение топ-3 рекрутёров по 5 осям.
 * Источник: recruiters.py:_build_radar_chart
 * Форма data: { axes: string[], series: [{ name: string, values: number[] }] }
 * Пусто без наймов → AnChart покажет empty-state.
 * Content-only: карточку даёт AnChart.
 */

import {
  RadarChart as RechartsRadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from 'recharts';
import { paletteAt } from '../../palette';

interface RadarChartProps {
  data: {
    axes: string[];
    series: Array<{ name: string; values: number[] }>;
  };
}

// recharts content-callback signature сложная — типизируем как unknown-проп.
function renderTooltip(props: {
  active?: boolean;
  label?: string | number;
  payload?: ReadonlyArray<{ name?: string; value?: number; color?: string }>;
}) {
  if (!props.active || !props.payload || props.payload.length === 0) return null;
  return (
    <div className="an-chart-tooltip">
      <div className="an-chart-tooltip-title">{props.label}</div>
      {props.payload.map((entry, i) => (
        <div key={i} className="an-chart-tooltip-item">
          <span className="an-chart-tooltip-dot" style={{ backgroundColor: entry.color }} />
          <span className="an-chart-tooltip-label">{entry.name}</span>
          <span className="an-chart-tooltip-value">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

export function RadarChart({ data }: RadarChartProps) {
  const chartData = data.axes.map((axis, index) => {
    const point: Record<string, string | number> = { axis };
    data.series.forEach((serie) => {
      point[serie.name] = serie.values[index] ?? 0;
    });
    return point;
  });

  return (
    <div className="an-chart-wrap">
      <ResponsiveContainer width="100%" height={320}>
        <RechartsRadarChart data={chartData}>
          <PolarGrid stroke="var(--border-2)" />
          <PolarAngleAxis dataKey="axis" tick={{ fontSize: 11, fill: 'var(--fg-3)', fontFamily: 'Inter, sans-serif' }} />
          <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10, fill: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }} />
          <Tooltip content={renderTooltip as never} />
          <Legend wrapperStyle={{ fontSize: '12px' }} iconType="line" />
          {data.series.map((serie, index) => (
            <Radar
              key={serie.name}
              name={serie.name}
              dataKey={serie.name}
              stroke={paletteAt(index)}
              fill={paletteAt(index)}
              fillOpacity={0.12}
              strokeWidth={2}
              dot={{ r: 3, fill: paletteAt(index) }}
            />
          ))}
        </RechartsRadarChart>
      </ResponsiveContainer>
    </div>
  );
}
