/**
 * Line chart — динамика откликов / отказов.
 * Источник: overview.py:_build_dynamics_chart, rejections.py:_build_rejections_dynamics_chart
 * Форма data: { points: [{ date: string, value: number }] }
 * Content-only: карточку и empty-state даёт AnChart.
 */

import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { ANALYTICS_PALETTE } from '../../palette';

interface LineChartProps {
  data: { points: Array<{ date: string; value: number }> };
}

function formatDay(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

export function LineChart({ data }: LineChartProps) {
  return (
    <div className="an-chart-wrap">
      <ResponsiveContainer width="100%" height={240}>
        <RechartsLineChart data={data.points} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-2)" vertical={false} />
          <XAxis dataKey="date" tickFormatter={formatDay} stroke="var(--fg-3)" fontSize={11} fontFamily="var(--font-mono)" tickLine={false} />
          <YAxis stroke="var(--fg-3)" fontSize={11} fontFamily="var(--font-mono)" tickLine={false} axisLine={false} width={36} allowDecimals={false} />
          <Tooltip
            labelFormatter={(label) => formatDay(String(label))}
            contentStyle={{
              backgroundColor: '#1F2733',
              border: 'none',
              borderRadius: '6px',
              fontSize: '12px',
            }}
            labelStyle={{ color: 'rgba(255,255,255,0.7)', fontSize: '11px' }}
            itemStyle={{ color: '#fff' }}
          />
          <Line
            type="monotone"
            dataKey="value"
            name="Значение"
            stroke={ANALYTICS_PALETTE.blue}
            strokeWidth={2}
            dot={{ fill: ANALYTICS_PALETTE.blue, r: 3 }}
            activeDot={{ r: 5 }}
          />
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  );
}
