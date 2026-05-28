/**
 * Vertical bar chart для общих случаев.
 * Источник: различные сервисы с данными в виде массива объектов с полями label/value
 * Форма data: { items: [{ label: string, value: number }] }
 */

import { BarChart as RechartsBarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface BarChartProps {
  title: string;
  data: {
    items: Array<{ label: string; value: number; [key: string]: any }>;
  };
  onDataClick?: (data: any) => void;
}

export function BarChart({ title, data, onDataClick }: BarChartProps) {
  if (!data?.items || data.items.length === 0) {
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

  return (
    <div className="analytics-chart-card">
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
      </div>

      <div className="analytics-chart-container">
        <ResponsiveContainer width="100%" height={280}>
          <RechartsBarChart
            data={data.items}
            margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-2)" />
            <XAxis
              dataKey="label"
              stroke="var(--fg-3)"
              fontSize={11}
              fontFamily="var(--font-mono)"
              angle={-45}
              textAnchor="end"
              height={60}
            />
            <YAxis
              stroke="var(--fg-3)"
              fontSize={11}
              fontFamily="var(--font-mono)"
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--bg-1)',
                border: '1px solid var(--border-2)',
                borderRadius: '8px',
                fontSize: '14px',
              }}
              labelStyle={{ color: 'var(--fg-3)', fontSize: '12px' }}
            />
            <Bar
              dataKey="value"
              fill="var(--accent)"
              radius={[4, 4, 0, 0]}
              onClick={onDataClick}
              cursor="pointer"
            />
          </RechartsBarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}