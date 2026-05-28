/**
 * Radar chart для сравнения топ-3 рекрутёров.
 * Источник: backend/app/services/analytics/recruiters.py
 * Форма data: { axes: string[], series: [{ name: string, values: number[] }] }
 */

import { RadarChart as RechartsRadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, Tooltip, Legend } from 'recharts';

interface RadarChartProps {
  title: string;
  data: {
    axes: string[];
    series: Array<{ name: string; values: number[] }>;
  };
  onDataClick?: (data: any) => void;
}

export function RadarChart({ title, data, onDataClick }: RadarChartProps) {
  if (!data?.axes || !data?.series || data.axes.length === 0 || data.series.length === 0) {
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

  // Transform data for recharts format
  const chartData = data.axes.map((axis, index) => {
    const point: Record<string, any> = { axis };
    data.series.forEach(serie => {
      point[serie.name] = serie.values[index] || 0;
    });
    return point;
  });

  const colors = ['var(--accent)', '#8884d8', '#82ca9d', '#ffc658', '#ff7c7c'];

  const renderTooltip = (props: any) => {
    if (!props.active || !props.payload || props.payload.length === 0) {
      return null;
    }

    return (
      <div className="analytics-chart-tooltip">
        <div className="analytics-chart-tooltip-title">{props.label}</div>
        {props.payload.map((entry: any, index: number) => (
          <div key={index} className="analytics-chart-tooltip-item">
            <span
              className="analytics-chart-tooltip-dot"
              style={{ backgroundColor: entry.color }}
            />
            <span className="analytics-chart-tooltip-label">{entry.name}:</span>
            <span className="analytics-chart-tooltip-value">{entry.value}</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="analytics-chart-card">
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
        <p className="analytics-chart-subtitle">
          Сравнение показателей топ-рекрутёров по ключевым метрикам
        </p>
      </div>

      <div className="analytics-chart-container">
        <ResponsiveContainer width="100%" height={320}>
          <RechartsRadarChart data={chartData}>
            <PolarGrid stroke="var(--border-2)" />
            <PolarAngleAxis
              dataKey="axis"
              tick={{
                fontSize: 11,
                fill: 'var(--fg-3)',
                fontFamily: 'Inter, sans-serif',
              }}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, 'dataMax']}
              tick={{
                fontSize: 10,
                fill: 'var(--fg-3)',
                fontFamily: 'var(--font-mono)',
              }}
            />
            <Tooltip content={renderTooltip} />
            <Legend
              wrapperStyle={{ fontSize: '12px' }}
              iconType="line"
            />
            {data.series.map((serie, index) => (
              <Radar
                key={serie.name}
                name={serie.name}
                dataKey={serie.name}
                stroke={colors[index % colors.length]}
                fill={colors[index % colors.length]}
                fillOpacity={0.1}
                strokeWidth={2}
                dot={{ r: 4, fill: colors[index % colors.length] }}
                onClick={onDataClick}
              />
            ))}
          </RechartsRadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}