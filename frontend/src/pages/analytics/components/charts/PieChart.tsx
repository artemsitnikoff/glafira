/**
 * Pie chart для отказов (кандидат vs компания), источников.
 * Источник: backend/app/services/analytics/rejections.py
 * Форма data: [{ label: string, value: number, color?: string }] или { our: [...], candidate: [...] } для двойной pie
 */

import { PieChart as RechartsPieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';

interface PieDataItem {
  label: string;
  value: number;
  color?: string;
}

interface DualPieData {
  our: PieDataItem[];
  candidate: PieDataItem[];
}

interface PieChartProps {
  title: string;
  data: PieDataItem[] | DualPieData;
  onDataClick?: (data: any) => void;
}

const DEFAULT_COLORS = [
  'var(--accent)',
  '#8884d8',
  '#82ca9d',
  '#ffc658',
  '#ff7c7c',
  '#8dd1e1',
  '#d084d0',
  '#ffb347',
];

export function PieChart({ title, data, onDataClick }: PieChartProps) {
  const renderTooltip = (props: any) => {
    if (!props.active || !props.payload || props.payload.length === 0) {
      return null;
    }

    const data = props.payload[0].payload;
    return (
      <div className="analytics-chart-tooltip">
        <div className="analytics-chart-tooltip-title">{data.label}</div>
        <div className="analytics-chart-tooltip-item">
          <span className="analytics-chart-tooltip-value">
            {data.value} ({((data.value / props.payload[0].payload.total) * 100).toFixed(1)}%)
          </span>
        </div>
      </div>
    );
  };

  // Check if it's dual pie chart (rejections)
  if (data && typeof data === 'object' && 'our' in data && 'candidate' in data) {
    const ourData = data.our.map((item, index) => ({
      ...item,
      color: item.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length],
      total: data.our.reduce((sum, d) => sum + d.value, 0),
    }));

    const candidateData = data.candidate.map((item, index) => ({
      ...item,
      color: item.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length],
      total: data.candidate.reduce((sum, d) => sum + d.value, 0),
    }));

    return (
      <div className="analytics-chart-card">
        <div className="analytics-chart-header">
          <h3 className="analytics-chart-title">{title}</h3>
        </div>

        <div className="analytics-grid-2">
          {/* Company rejections */}
          <div>
            <h4 style={{ fontSize: '14px', fontWeight: '500', marginBottom: '16px', color: 'var(--fg-2)' }}>
              Отказы компании
            </h4>
            <ResponsiveContainer width="100%" height={200}>
              <RechartsPieChart>
                <Pie
                  data={ourData}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={80}
                  dataKey="value"
                  onClick={onDataClick}
                >
                  {ourData.map((entry, index) => (
                    <Cell key={`our-cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip content={renderTooltip} />
                <Legend
                  wrapperStyle={{ fontSize: '12px' }}
                  iconType="circle"
                />
              </RechartsPieChart>
            </ResponsiveContainer>
          </div>

          {/* Candidate rejections */}
          <div>
            <h4 style={{ fontSize: '14px', fontWeight: '500', marginBottom: '16px', color: 'var(--fg-2)' }}>
              Отказы кандидатов
            </h4>
            <ResponsiveContainer width="100%" height={200}>
              <RechartsPieChart>
                <Pie
                  data={candidateData}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={80}
                  dataKey="value"
                  onClick={onDataClick}
                >
                  {candidateData.map((entry, index) => (
                    <Cell key={`candidate-cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip content={renderTooltip} />
                <Legend
                  wrapperStyle={{ fontSize: '12px' }}
                  iconType="circle"
                />
              </RechartsPieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    );
  }

  // Single pie chart
  if (!Array.isArray(data) || data.length === 0) {
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

  const total = (data as PieDataItem[]).reduce((sum, item) => sum + item.value, 0);
  const chartData = (data as PieDataItem[]).map((item, index) => ({
    ...item,
    color: item.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length],
    total,
  }));

  return (
    <div className="analytics-chart-card">
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
      </div>

      <div className="analytics-chart-container">
        <ResponsiveContainer width="100%" height={280}>
          <RechartsPieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={100}
              dataKey="value"
              onClick={onDataClick}
            >
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip content={renderTooltip} />
            <Legend
              wrapperStyle={{ fontSize: '12px' }}
              iconType="circle"
            />
          </RechartsPieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}