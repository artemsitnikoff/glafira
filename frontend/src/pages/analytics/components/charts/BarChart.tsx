/**
 * Vertical bar chart.
 * Используется в recruiters.py:_build_hires_bar_chart — форма { items: [{ recruiter, value }] }.
 * (общий случай — { items: [{ label, value }] }).
 * Content-only: карточку и empty-state даёт AnChart.
 */

import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { ANALYTICS_PALETTE } from '../../palette';

interface BarItem {
  label?: string;
  recruiter?: string;
  value: number;
}

interface BarChartProps {
  data: { items: BarItem[] };
}

export function BarChart({ data }: BarChartProps) {
  // Бек для рекрутёров отдаёт ключ `recruiter`, общий случай — `label`.
  const items = data.items.map((it) => ({
    label: it.label ?? it.recruiter ?? '—',
    value: it.value,
  }));

  return (
    <div className="an-chart-wrap">
      <ResponsiveContainer width="100%" height={220}>
        <RechartsBarChart data={items} margin={{ top: 8, right: 16, left: 0, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-2)" vertical={false} />
          <XAxis
            dataKey="label"
            stroke="var(--fg-3)"
            fontSize={11}
            fontFamily="var(--font-sans)"
            angle={-30}
            textAnchor="end"
            height={48}
            interval={0}
            tickLine={false}
          />
          <YAxis stroke="var(--fg-3)" fontSize={11} fontFamily="var(--font-mono)" tickLine={false} axisLine={false} width={32} allowDecimals={false} />
          <Tooltip
            cursor={{ fill: 'var(--bg-panel-2)' }}
            contentStyle={{ backgroundColor: '#1F2733', border: 'none', borderRadius: '6px', fontSize: '12px' }}
            labelStyle={{ color: 'rgba(255,255,255,0.7)', fontSize: '11px' }}
            itemStyle={{ color: '#fff' }}
          />
          <Bar dataKey="value" name="Найма" fill={ANALYTICS_PALETTE.blue} radius={[4, 4, 0, 0]} maxBarSize={48} />
        </RechartsBarChart>
      </ResponsiveContainer>
    </div>
  );
}
