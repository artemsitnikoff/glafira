/**
 * Heatmap — среднее время (дни) по этапам × вакансиям.
 * Источник: speed.py:_build_heatmap_chart
 * Форма data: { x_labels: string[], y_labels: string[], cells: [{ x, y, value | null }] }
 * Content-only: карточку и empty-state даёт AnChart.
 */

import { useRef, useEffect, useState } from 'react';

interface HeatmapData {
  x_labels: string[];
  y_labels: string[];
  cells: Array<{ x: number; y: number; value: number | null }>;
}

interface HeatmapChartProps {
  data: HeatmapData;
}

const LABEL_W = 170;
const CELL_H = 38;

export function HeatmapChart({ data }: HeatmapChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(760);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setContainerWidth(e.contentRect.width);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const cellWidth = Math.max(54, (containerWidth - LABEL_W) / data.x_labels.length);
  const chartWidth = data.x_labels.length * cellWidth;
  const chartHeight = data.y_labels.length * CELL_H;

  const values = data.cells.map((c) => c.value).filter((v): v is number => v !== null && v !== undefined);
  const minValue = values.length ? Math.min(...values) : 0;
  const maxValue = values.length ? Math.max(...values) : 1;
  const span = maxValue - minValue || 1;

  // ank-blue scale: светлее = быстрее, насыщеннее = дольше.
  const colorFor = (value: number | null | undefined): string => {
    if (value === null || value === undefined) return 'var(--bg-panel-2)';
    const t = (value - minValue) / span;
    return `rgba(42, 138, 240, ${0.12 + t * 0.78})`;
  };

  const cellMap = new Map<string, number | null>();
  data.cells.forEach((c) => cellMap.set(`${c.x},${c.y}`, c.value));

  return (
    <div className="an-chart-wrap heatmap-scroll" ref={containerRef}>
      <svg width={LABEL_W + chartWidth} height={chartHeight + 30} className="an-svg-chart">
        <g transform={`translate(${LABEL_W}, 0)`}>
          {data.y_labels.map((label, yIndex) => (
            <text key={`y-${yIndex}`} x={-12} y={yIndex * CELL_H + CELL_H / 2} textAnchor="end" dominantBaseline="middle" style={{ fontSize: 12, fill: 'var(--fg-1)' }}>
              {label}
            </text>
          ))}
          {data.x_labels.map((label, xIndex) => (
            <text key={`x-${xIndex}`} x={xIndex * cellWidth + cellWidth / 2} y={chartHeight + 16} textAnchor="middle" style={{ fontSize: 11, fill: 'var(--fg-3)' }}>
              {label}
            </text>
          ))}
          {data.y_labels.map((_yLabel, yIndex) =>
            data.x_labels.map((_xLabel, xIndex) => {
              const value = cellMap.get(`${xIndex},${yIndex}`);
              const dark = value !== null && value !== undefined && (value - minValue) / span > 0.55;
              return (
                <g key={`c-${xIndex}-${yIndex}`}>
                  <rect x={xIndex * cellWidth + 1} y={yIndex * CELL_H + 1} width={cellWidth - 2} height={CELL_H - 2} fill={colorFor(value)} stroke="var(--bg-app)" strokeWidth={1} rx={2} />
                  <text x={xIndex * cellWidth + cellWidth / 2} y={yIndex * CELL_H + CELL_H / 2} textAnchor="middle" dominantBaseline="middle" style={{ fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 500, fill: value === null || value === undefined ? 'var(--fg-4)' : dark ? '#fff' : 'var(--fg-1)' }}>
                    {value === null || value === undefined ? '—' : value.toFixed(1)}
                  </text>
                </g>
              );
            }),
          )}
        </g>
      </svg>
      <div className="heatmap-legend">
        <span>Дни:</span>
        <span className="hl-swatch" style={{ background: 'rgba(42,138,240,0.12)' }} />
        <span>{minValue.toFixed(0)}</span>
        <span className="hl-swatch" style={{ background: 'rgba(42,138,240,0.9)' }} />
        <span>{maxValue.toFixed(0)}</span>
      </div>
    </div>
  );
}
