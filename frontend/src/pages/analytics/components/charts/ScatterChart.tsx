/**
 * Scatter chart для источников (качество × объём).
 * Источник: backend/app/services/analytics/sources.py
 * Форма data: { points: [{ label: string, x: number, y: number }] }
 */

import { ScatterChart as RechartsScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface ScatterChartProps {
  title: string;
  data: {
    points: Array<{ label: string; x: number; y: number; [key: string]: any }>;
  };
  onDataClick?: (data: any) => void;
}

export function ScatterChart({ title, data, onDataClick }: ScatterChartProps) {
  if (!data?.points || data.points.length === 0) {
    return (
      <div className="analytics-chart-card">
        <div className="analytics-chart-header">
          <h3 className="analytics-chart-title">{title}</h3>
        </div>
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--fg-3)' }}>
          Нет данных для отображения
        </div>
      </div>
    );
  }

  const renderTooltip = (props: any) => {
    if (!props.active || !props.payload || props.payload.length === 0) {
      return null;
    }

    const point = props.payload[0].payload;
    return (
      <div className="analytics-chart-tooltip">
        <div className="analytics-chart-tooltip-title">{point.label}</div>
        <div className="analytics-chart-tooltip-item">
          <span className="analytics-chart-tooltip-label">Качество:</span>
          <span className="analytics-chart-tooltip-value">{point.x}</span>
        </div>
        <div className="analytics-chart-tooltip-item">
          <span className="analytics-chart-tooltip-label">Объём:</span>
          <span className="analytics-chart-tooltip-value">{point.y}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="analytics-chart-card">
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
        <p className="analytics-chart-subtitle">
          X = Качество, Y = Объём. Правый верхний квадрант = лучшие источники.
        </p>
      </div>

      <div className="analytics-chart-container">
        <ResponsiveContainer width="100%" height={280}>
          <RechartsScatterChart
            data={data.points}
            margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-2)" />
            <XAxis
              dataKey="x"
              type="number"
              stroke="var(--fg-3)"
              fontSize={11}
              fontFamily="var(--font-mono)"
              domain={['dataMin - 5', 'dataMax + 5']}
            />
            <YAxis
              dataKey="y"
              type="number"
              stroke="var(--fg-3)"
              fontSize={11}
              fontFamily="var(--font-mono)"
              domain={['dataMin - 10', 'dataMax + 10']}
            />
            <Tooltip content={renderTooltip} />
            <Scatter
              dataKey="y"
              fill="var(--accent)"
              onClick={onDataClick}
            />
          </RechartsScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}