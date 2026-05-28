/**
 * Survival curve chart для turnover-отчёта.
 * Источник: backend/app/services/analytics/turnover.py
 * Форма data: { points: [{ day: number, retained_pct: number }] }
 */

import { useRef, useEffect, useState } from 'react';

interface SurvivalData {
  points: Array<{ day: number; retained_pct: number }>;
}

interface SurvivalChartProps {
  title: string;
  data: SurvivalData;
  onDataClick?: (data: any) => void;
}

export function SurvivalChart({ title, data, onDataClick }: SurvivalChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(600);

  useEffect(() => {
    if (!containerRef.current) return;

    const resizeObserver = new ResizeObserver(entries => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });

    resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

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

  const margin = { top: 20, right: 40, bottom: 60, left: 60 };
  const chartWidth = containerWidth - margin.left - margin.right;
  const chartHeight = 280;

  // Sort points by day
  const sortedPoints = [...data.points].sort((a, b) => a.day - b.day);

  // Scale functions
  const maxDay = Math.max(...sortedPoints.map(p => p.day));
  const xScale = (day: number) => (day / maxDay) * chartWidth;
  const yScale = (pct: number) => chartHeight - (pct / 100) * chartHeight;

  // Generate path
  const pathData = sortedPoints.map((point, index) => {
    const x = xScale(point.day);
    const y = yScale(point.retained_pct);
    return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
  }).join(' ');

  // X axis ticks
  const xTicks = [];
  const tickCount = Math.min(6, Math.ceil(maxDay / 30));
  for (let i = 0; i <= tickCount; i++) {
    const day = (maxDay / tickCount) * i;
    xTicks.push({ day: Math.round(day), x: xScale(day) });
  }

  // Y axis ticks
  const yTicks = [];
  for (let i = 0; i <= 5; i++) {
    const pct = (i / 5) * 100;
    yTicks.push({ pct, y: yScale(pct) });
  }

  return (
    <div className="analytics-chart-card" ref={containerRef}>
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
        <p className="analytics-chart-subtitle">
          Кривая удержания сотрудников. Снижение показывает отток.
        </p>
      </div>

      <div className="analytics-chart-container">
        <svg
          width={containerWidth}
          height={chartHeight + margin.top + margin.bottom}
          className="analytics-svg-chart"
        >
          <g transform={`translate(${margin.left}, ${margin.top})`}>
            {/* Grid lines */}
            {yTicks.map((tick, index) => (
              <line
                key={`y-grid-${index}`}
                x1={0}
                y1={tick.y}
                x2={chartWidth}
                y2={tick.y}
                stroke="var(--border-2)"
                strokeWidth={1}
                strokeDasharray={index === 0 || index === yTicks.length - 1 ? '0' : '3 3'}
              />
            ))}

            {xTicks.map((tick, index) => (
              <line
                key={`x-grid-${index}`}
                x1={tick.x}
                y1={0}
                x2={tick.x}
                y2={chartHeight}
                stroke="var(--border-2)"
                strokeWidth={1}
                strokeDasharray={index === 0 || index === xTicks.length - 1 ? '0' : '3 3'}
              />
            ))}

            {/* X axis */}
            <line
              x1={0}
              y1={chartHeight}
              x2={chartWidth}
              y2={chartHeight}
              stroke="var(--border-2)"
              strokeWidth={1}
            />

            {/* Y axis */}
            <line
              x1={0}
              y1={0}
              x2={0}
              y2={chartHeight}
              stroke="var(--border-2)"
              strokeWidth={1}
            />

            {/* X axis labels */}
            {xTicks.map((tick, index) => (
              <text
                key={`x-label-${index}`}
                x={tick.x}
                y={chartHeight + 20}
                textAnchor="middle"
                className="analytics-chart-text"
                style={{ fontSize: '11px', fill: 'var(--fg-3)' }}
              >
                {tick.day}д
              </text>
            ))}

            {/* Y axis labels */}
            {yTicks.map((tick, index) => (
              <text
                key={`y-label-${index}`}
                x={-10}
                y={tick.y}
                textAnchor="end"
                dominantBaseline="middle"
                className="analytics-chart-text"
                style={{ fontSize: '11px', fill: 'var(--fg-3)' }}
              >
                {tick.pct.toFixed(0)}%
              </text>
            ))}

            {/* Survival curve */}
            <path
              d={pathData}
              stroke="var(--accent)"
              strokeWidth={3}
              fill="none"
              strokeLinejoin="round"
              strokeLinecap="round"
            />

            {/* Fill area under curve */}
            <path
              d={`${pathData} L ${xScale(sortedPoints[sortedPoints.length - 1].day)} ${chartHeight} L 0 ${chartHeight} Z`}
              fill="var(--accent)"
              fillOpacity={0.1}
            />

            {/* Data points */}
            {sortedPoints.map((point, index) => (
              <circle
                key={index}
                cx={xScale(point.day)}
                cy={yScale(point.retained_pct)}
                r={4}
                fill="var(--accent)"
                stroke="white"
                strokeWidth={2}
                style={{ cursor: onDataClick ? 'pointer' : 'default' }}
                onClick={() => onDataClick?.(point)}
              >
                <title>
                  День {point.day}: {point.retained_pct.toFixed(1)}% остались
                </title>
              </circle>
            ))}

            {/* Key milestones */}
            {[30, 60, 90].map(milestone => {
              const point = sortedPoints.find(p => p.day === milestone);
              if (!point) return null;

              const x = xScale(point.day);
              const y = yScale(point.retained_pct);

              return (
                <g key={milestone}>
                  <line
                    x1={x}
                    y1={0}
                    x2={x}
                    y2={chartHeight}
                    stroke="var(--score-yellow)"
                    strokeWidth={1}
                    strokeDasharray="5 5"
                    opacity={0.7}
                  />
                  <text
                    x={x + 5}
                    y={y - 10}
                    style={{
                      fontSize: '10px',
                      fill: 'var(--fg-1)',
                      fontWeight: '500',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {point.retained_pct.toFixed(1)}%
                  </text>
                </g>
              );
            })}

            {/* Axis titles */}
            <text
              x={chartWidth / 2}
              y={chartHeight + 45}
              textAnchor="middle"
              style={{ fontSize: '12px', fill: 'var(--fg-3)', fontWeight: '500' }}
            >
              Дни после найма
            </text>

            <text
              x={-35}
              y={chartHeight / 2}
              textAnchor="middle"
              transform={`rotate(-90, -35, ${chartHeight / 2})`}
              style={{ fontSize: '12px', fill: 'var(--fg-3)', fontWeight: '500' }}
            >
              % удержания
            </text>
          </g>
        </svg>
      </div>
    </div>
  );
}