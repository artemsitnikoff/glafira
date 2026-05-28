/**
 * Heatmap chart для speed-отчёта (вакансия × этап).
 * Источник: backend/app/services/analytics/speed.py:_build_heatmap_chart
 * Форма data: { x_labels: string[], y_labels: string[], cells: [{ x: number, y: number, value: number | null }] }
 */

import { useRef, useEffect, useState } from 'react';

interface HeatmapData {
  x_labels: string[];
  y_labels: string[];
  cells: Array<{ x: number; y: number; value: number | null }>;
}

interface HeatmapChartProps {
  title: string;
  data: HeatmapData;
  onDataClick?: (data: any) => void;
}

export function HeatmapChart({ title, data, onDataClick }: HeatmapChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(800);

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

  if (!data?.x_labels || !data?.y_labels || !data?.cells ||
      data.x_labels.length === 0 || data.y_labels.length === 0) {
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

  // Calculate dimensions
  const margin = { top: 20, right: 40, bottom: 60, left: 180 };
  const cellWidth = Math.max(40, (containerWidth - margin.left - margin.right) / data.x_labels.length);
  const cellHeight = 40;
  const chartWidth = data.x_labels.length * cellWidth;
  const chartHeight = data.y_labels.length * cellHeight;

  // Find min/max values for color scale
  const values = data.cells.map(cell => cell.value).filter((v): v is number => v !== null);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);

  // Color interpolation function
  const getColor = (value: number | null | undefined): string => {
    if (value === null || value === undefined) {
      return 'var(--bg-3)';
    }

    const normalizedValue = (value - minValue) / (maxValue - minValue);

    // Color scale from light (low values) to dark accent (high values)
    if (normalizedValue <= 0.33) {
      // Light blue
      const intensity = normalizedValue / 0.33;
      return `rgba(42, 138, 240, ${0.2 + intensity * 0.3})`;
    } else if (normalizedValue <= 0.66) {
      // Medium blue
      const intensity = (normalizedValue - 0.33) / 0.33;
      return `rgba(42, 138, 240, ${0.5 + intensity * 0.3})`;
    } else {
      // Dark blue to red (high values)
      const intensity = (normalizedValue - 0.66) / 0.34;
      if (normalizedValue > 0.8) {
        return `rgba(220, 70, 70, ${0.6 + intensity * 0.4})`; // Red for very high values
      }
      return `rgba(42, 138, 240, ${0.8 + intensity * 0.2})`;
    }
  };

  // Create a map for quick cell lookup
  const cellMap = new Map<string, number | null>();
  data.cells.forEach(cell => {
    cellMap.set(`${cell.x},${cell.y}`, cell.value);
  });

  return (
    <div className="analytics-chart-card" ref={containerRef}>
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
        <p className="analytics-chart-subtitle">
          Среднее время в днях. Темнее = дольше.
        </p>
      </div>

      <div className="analytics-chart-container" style={{ overflowX: 'auto' }}>
        <svg
          width={chartWidth + margin.left + margin.right}
          height={chartHeight + margin.top + margin.bottom}
          className="analytics-svg-chart"
        >
          <g transform={`translate(${margin.left}, ${margin.top})`}>
            {/* Y axis labels (vacancies) */}
            {data.y_labels.map((label, yIndex) => (
              <text
                key={`y-label-${yIndex}`}
                x={-12}
                y={yIndex * cellHeight + cellHeight / 2}
                textAnchor="end"
                dominantBaseline="middle"
                className="analytics-chart-text"
                style={{ fontSize: '12px', fill: 'var(--fg-1)' }}
              >
                {label}
              </text>
            ))}

            {/* X axis labels (stages) */}
            {data.x_labels.map((label, xIndex) => (
              <text
                key={`x-label-${xIndex}`}
                x={xIndex * cellWidth + cellWidth / 2}
                y={chartHeight + 15}
                textAnchor="middle"
                className="analytics-chart-text"
                style={{ fontSize: '11px', fill: 'var(--fg-3)' }}
              >
                {label}
              </text>
            ))}

            {/* Heatmap cells */}
            {data.y_labels.map((yLabel, yIndex) =>
              data.x_labels.map((xLabel, xIndex) => {
                const value = cellMap.get(`${xIndex},${yIndex}`);
                const color = getColor(value);

                return (
                  <g key={`cell-${xIndex}-${yIndex}`}>
                    <rect
                      x={xIndex * cellWidth + 1}
                      y={yIndex * cellHeight + 1}
                      width={cellWidth - 2}
                      height={cellHeight - 2}
                      fill={color}
                      stroke="var(--bg-2)"
                      strokeWidth={1}
                      rx={2}
                      style={{ cursor: onDataClick ? 'pointer' : 'default' }}
                      onClick={() => onDataClick?.({ x: xIndex, y: yIndex, value, xLabel, yLabel })}
                    />
                    {/* Value text */}
                    {value !== null && value !== undefined && (
                      <text
                        x={xIndex * cellWidth + cellWidth / 2}
                        y={yIndex * cellHeight + cellHeight / 2}
                        textAnchor="middle"
                        dominantBaseline="middle"
                        style={{
                          fontSize: '11px',
                          fontFamily: 'var(--font-mono)',
                          fontWeight: '500',
                          fill: (value || 0) > (maxValue * 0.6) ? 'white' : 'var(--fg-1)',
                        }}
                      >
                        {value?.toFixed(1)}
                      </text>
                    )}
                    {(value === null || value === undefined) && (
                      <text
                        x={xIndex * cellWidth + cellWidth / 2}
                        y={yIndex * cellHeight + cellHeight / 2}
                        textAnchor="middle"
                        dominantBaseline="middle"
                        style={{
                          fontSize: '10px',
                          fill: 'var(--fg-3)',
                        }}
                      >
                        —
                      </text>
                    )}
                  </g>
                );
              })
            )}

            {/* Legend */}
            <g transform={`translate(${chartWidth + 20}, 20)`}>
              <text
                x={0}
                y={-5}
                style={{ fontSize: '11px', fill: 'var(--fg-3)', fontWeight: '500' }}
              >
                Дни
              </text>
              {[0, 0.25, 0.5, 0.75, 1].map((ratio, index) => {
                const value = minValue + (maxValue - minValue) * ratio;
                const color = getColor(value);

                return (
                  <g key={index}>
                    <rect
                      x={0}
                      y={index * 20}
                      width={15}
                      height={15}
                      fill={color}
                      rx={2}
                    />
                    <text
                      x={20}
                      y={index * 20 + 7.5}
                      dominantBaseline="middle"
                      style={{ fontSize: '10px', fill: 'var(--fg-3)' }}
                    >
                      {value.toFixed(1)}
                    </text>
                  </g>
                );
              })}
            </g>
          </g>
        </svg>
      </div>
    </div>
  );
}