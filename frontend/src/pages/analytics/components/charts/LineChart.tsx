/**
 * Line chart для динамики откликов.
 * Источник: backend/app/services/analytics/overview.py:_build_dynamics_chart
 * Форма data: { points: [{ date: string, value: number }] }
 */

import { LineChart as RechartsLineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface LineChartProps {
  title: string;
  data: {
    points: Array<{ date: string; value: number; [key: string]: any }>;
  };
  onDataClick?: (data: any) => void;
}

export function LineChart({ title, data, onDataClick }: LineChartProps) {
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

  const formatTooltipLabel = (label: string) => {
    try {
      const date = new Date(label);
      return date.toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'short',
        year: '2-digit'
      });
    } catch {
      return label;
    }
  };

  const formatXAxisLabel = (value: string) => {
    try {
      const date = new Date(value);
      return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
    } catch {
      return value;
    }
  };

  return (
    <div className="analytics-chart-card">
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
      </div>

      <div className="analytics-chart-container">
        <ResponsiveContainer width="100%" height={280}>
          <RechartsLineChart
            data={data.points}
            margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-2)" />
            <XAxis
              dataKey="date"
              tickFormatter={formatXAxisLabel}
              stroke="var(--fg-3)"
              fontSize={11}
              fontFamily="var(--font-mono)"
            />
            <YAxis
              stroke="var(--fg-3)"
              fontSize={11}
              fontFamily="var(--font-mono)"
            />
            <Tooltip
              labelFormatter={(label: any) => formatTooltipLabel(String(label))}
              contentStyle={{
                backgroundColor: 'var(--bg-1)',
                border: '1px solid var(--border-2)',
                borderRadius: '8px',
                fontSize: '14px',
              }}
              labelStyle={{ color: 'var(--fg-3)', fontSize: '12px' }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--accent)"
              strokeWidth={2}
              dot={{ fill: 'var(--accent)', r: 4 }}
              activeDot={{ r: 6, fill: 'var(--accent)' }}
              onClick={onDataClick}
            />
          </RechartsLineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}