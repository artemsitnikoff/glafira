/**
 * Horizontal bar chart для Top-вакансий, этапов скорости и причин отказов.
 * Источник: backend/app/services/analytics/overview.py:_build_top_vacancies_chart, speed.py, rejections.py
 * Форма data: { items: [{ label: string, value: number }] }
 */

import { useRef, useEffect, useState } from 'react';

interface HBarChartProps {
  title: string;
  data: {
    items: Array<{ label: string; value: number; highlight?: boolean; [key: string]: any }>;
  };
  onDataClick?: (data: any) => void;
}

export function HBarChart({ title, data, onDataClick }: HBarChartProps) {
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

  const maxValue = Math.max(...data.items.map(item => item.value));
  const barHeight = 32;
  const barGap = 16;
  const leftLabelWidth = 180;
  const rightValueWidth = 80;
  const chartHeight = data.items.length * (barHeight + barGap) - barGap + 40; // padding

  return (
    <div className="analytics-chart-card" ref={containerRef}>
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
      </div>

      <div className="analytics-chart-container">
        <svg width="100%" height={chartHeight} className="analytics-svg-chart">
          {data.items.map((item, index) => {
            const y = 20 + index * (barHeight + barGap);
            const barWidth = Math.max(4, ((item.value / maxValue) * (containerWidth - leftLabelWidth - rightValueWidth - 80)));
            const barColor = item.highlight ? 'var(--score-red)' : 'var(--accent)';

            return (
              <g key={index}>
                {/* Label */}
                <text
                  x={leftLabelWidth - 12}
                  y={y + barHeight / 2}
                  textAnchor="end"
                  dominantBaseline="middle"
                  className="analytics-chart-text"
                  style={{
                    fontSize: '13px',
                    fill: 'var(--fg-1)',
                    fontFamily: 'Inter, sans-serif',
                  }}
                >
                  {item.label}
                </text>

                {/* Bar */}
                <rect
                  x={leftLabelWidth}
                  y={y + 4}
                  width={barWidth}
                  height={barHeight - 8}
                  fill={barColor}
                  rx={4}
                  style={{
                    cursor: onDataClick ? 'pointer' : 'default',
                  }}
                  onClick={() => onDataClick?.(item)}
                />

                {/* Value */}
                <text
                  x={leftLabelWidth + barWidth + 12}
                  y={y + barHeight / 2}
                  dominantBaseline="middle"
                  className="analytics-chart-text"
                  style={{
                    fontSize: '13px',
                    fontFamily: 'var(--font-mono)',
                    fontWeight: '500',
                    fill: 'var(--fg-1)',
                  }}
                >
                  {typeof item.value === 'number' ? item.value.toLocaleString('ru-RU') : item.value}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}