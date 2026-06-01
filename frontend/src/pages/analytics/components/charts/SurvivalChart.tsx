/**
 * Survival curve — кривая удержания сотрудников после найма.
 * Источник: turnover.py:_build_survival_chart
 * Форма data: { points: [{ day: number, retained_pct: number }] }
 * Content-only: карточку и empty-state даёт AnChart.
 */

import { useRef, useEffect, useState } from 'react';
import { ANALYTICS_PALETTE } from '../../palette';

interface SurvivalChartProps {
  data: { points: Array<{ day: number; retained_pct: number }> };
}

export function SurvivalChart({ data }: SurvivalChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(600);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setContainerWidth(e.contentRect.width);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const margin = { top: 12, right: 24, bottom: 40, left: 44 };
  const chartWidth = Math.max(280, containerWidth) - margin.left - margin.right;
  const chartHeight = 240;

  const points = [...data.points].sort((a, b) => a.day - b.day);
  const maxDay = Math.max(...points.map((p) => p.day), 1);
  const xScale = (day: number) => (day / maxDay) * chartWidth;
  const yScale = (pct: number) => chartHeight - (pct / 100) * chartHeight;

  const pathData = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(p.day)} ${yScale(p.retained_pct)}`).join(' ');

  const xTickCount = Math.min(6, Math.max(1, points.length));
  const xTicks: number[] = [];
  for (let i = 0; i <= xTickCount; i++) xTicks.push(Math.round((maxDay / xTickCount) * i));

  const yTicks = [0, 25, 50, 75, 100];

  return (
    <div className="an-chart-wrap" ref={containerRef}>
      <svg width="100%" height={chartHeight + margin.top + margin.bottom} className="an-svg-chart">
        <g transform={`translate(${margin.left}, ${margin.top})`}>
          {yTicks.map((pct, i) => (
            <g key={`y-${i}`}>
              <line x1={0} y1={yScale(pct)} x2={chartWidth} y2={yScale(pct)} stroke="var(--border-2)" strokeWidth={1} strokeDasharray={pct === 0 ? '0' : '3 3'} />
              <text x={-10} y={yScale(pct)} textAnchor="end" dominantBaseline="middle" style={{ fontSize: 11, fill: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>
                {pct}%
              </text>
            </g>
          ))}
          {xTicks.map((day, i) => (
            <text key={`x-${i}`} x={xScale(day)} y={chartHeight + 20} textAnchor="middle" style={{ fontSize: 11, fill: 'var(--fg-3)' }}>
              {day}д
            </text>
          ))}
          <path d={`${pathData} L ${xScale(points[points.length - 1].day)} ${chartHeight} L 0 ${chartHeight} Z`} fill={ANALYTICS_PALETTE.blue} fillOpacity={0.08} />
          <path d={pathData} stroke={ANALYTICS_PALETTE.blue} strokeWidth={2.5} fill="none" strokeLinejoin="round" strokeLinecap="round" />
          {points.map((p, i) => (
            <circle key={i} cx={xScale(p.day)} cy={yScale(p.retained_pct)} r={3} fill={ANALYTICS_PALETTE.blue} stroke="#fff" strokeWidth={1.5}>
              <title>{`День ${p.day}: ${p.retained_pct.toFixed(1)}% остались`}</title>
            </circle>
          ))}
        </g>
      </svg>
    </div>
  );
}
