/**
 * Boxplot chart для speed-отчёта.
 * Источник: backend/app/services/analytics/speed.py:_build_boxplot_chart
 * Форма data: { stages: [{ stage_key: string, label: string, median: number, q1: number, q3: number, min: number, max: number, outliers: number[] }] }
 */

import { useRef, useEffect, useState } from 'react';

interface BoxplotData {
  stages: Array<{
    stage_key: string;
    label: string;
    median: number | null;
    q1: number | null;
    q3: number | null;
    min: number | null;
    max: number | null;
    outliers: number[];
  }>;
}

interface BoxplotChartProps {
  title: string;
  data: BoxplotData;
  onDataClick?: (data: any) => void;
}

export function BoxplotChart({ title, data, onDataClick }: BoxplotChartProps) {
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

  if (!data?.stages || data.stages.length === 0) {
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

  // Calculate chart dimensions
  const margin = { top: 20, right: 40, bottom: 60, left: 80 };
  const chartWidth = containerWidth - margin.left - margin.right;
  const chartHeight = 300;
  const boxWidth = Math.min(60, chartWidth / data.stages.length * 0.6);

  // Find the global min/max for Y scale
  const allValues = data.stages.flatMap(stage => [
    stage.min,
    stage.max,
    stage.median,
    stage.q1,
    stage.q3,
    ...stage.outliers
  ]).filter((v): v is number => v !== null && v !== undefined);

  const globalMin = Math.min(...allValues);
  const globalMax = Math.max(...allValues);
  const yScale = (value: number) => chartHeight - ((value - globalMin) / (globalMax - globalMin)) * chartHeight;

  // X positions for stages
  const stageWidth = chartWidth / data.stages.length;

  // Y axis ticks
  const yTicks = [];
  const tickCount = 5;
  for (let i = 0; i <= tickCount; i++) {
    const value = globalMin + (globalMax - globalMin) * (i / tickCount);
    yTicks.push(value);
  }

  return (
    <div className="analytics-chart-card" ref={containerRef}>
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
        <p className="analytics-chart-subtitle">
          Ящики с усами показывают медиану, квартили и выбросы времени на каждом этапе
        </p>
      </div>

      <div className="analytics-chart-container">
        <svg width="100%" height={chartHeight + margin.top + margin.bottom} className="analytics-svg-chart">
          <g transform={`translate(${margin.left}, ${margin.top})`}>
            {/* Y axis */}
            <line
              x1={0}
              y1={0}
              x2={0}
              y2={chartHeight}
              stroke="var(--border-2)"
              strokeWidth={1}
            />

            {/* Y axis ticks and labels */}
            {yTicks.map((tick, index) => {
              const y = yScale(tick);
              return (
                <g key={index}>
                  <line
                    x1={-5}
                    y1={y}
                    x2={chartWidth}
                    y2={y}
                    stroke="var(--border-2)"
                    strokeWidth={1}
                    strokeDasharray={index === 0 ? '0' : '3 3'}
                  />
                  <text
                    x={-10}
                    y={y}
                    textAnchor="end"
                    dominantBaseline="middle"
                    className="analytics-chart-text"
                    style={{ fontSize: '11px', fill: 'var(--fg-3)' }}
                  >
                    {tick.toFixed(1)}
                  </text>
                </g>
              );
            })}

            {/* X axis */}
            <line
              x1={0}
              y1={chartHeight}
              x2={chartWidth}
              y2={chartHeight}
              stroke="var(--border-2)"
              strokeWidth={1}
            />

            {/* Boxplots */}
            {data.stages.map((stage, index) => {
              const centerX = (index + 0.5) * stageWidth;

              // Skip stages with no data
              if (stage.median === null || stage.q1 === null || stage.q3 === null) {
                return (
                  <g key={stage.stage_key}>
                    {/* X axis label */}
                    <text
                      x={centerX}
                      y={chartHeight + 20}
                      textAnchor="middle"
                      className="analytics-chart-text"
                      style={{ fontSize: '11px', fill: 'var(--fg-3)' }}
                    >
                      {stage.label}
                    </text>
                    <text
                      x={centerX}
                      y={chartHeight - 20}
                      textAnchor="middle"
                      style={{ fontSize: '12px', fill: 'var(--fg-3)' }}
                    >
                      Нет данных
                    </text>
                  </g>
                );
              }

              const medianY = yScale(stage.median);
              const q1Y = yScale(stage.q1);
              const q3Y = yScale(stage.q3);
              const minY = stage.min !== null ? yScale(stage.min) : q1Y;
              const maxY = stage.max !== null ? yScale(stage.max) : q3Y;

              return (
                <g key={stage.stage_key}>
                  {/* Whiskers */}
                  <line
                    x1={centerX}
                    y1={minY}
                    x2={centerX}
                    y2={q1Y}
                    stroke="var(--fg-2)"
                    strokeWidth={1}
                  />
                  <line
                    x1={centerX}
                    y1={q3Y}
                    x2={centerX}
                    y2={maxY}
                    stroke="var(--fg-2)"
                    strokeWidth={1}
                  />

                  {/* Whisker caps */}
                  <line
                    x1={centerX - boxWidth / 4}
                    y1={minY}
                    x2={centerX + boxWidth / 4}
                    y2={minY}
                    stroke="var(--fg-2)"
                    strokeWidth={1}
                  />
                  <line
                    x1={centerX - boxWidth / 4}
                    y1={maxY}
                    x2={centerX + boxWidth / 4}
                    y2={maxY}
                    stroke="var(--fg-2)"
                    strokeWidth={1}
                  />

                  {/* Box */}
                  <rect
                    x={centerX - boxWidth / 2}
                    y={q3Y}
                    width={boxWidth}
                    height={q1Y - q3Y}
                    fill="var(--accent)"
                    fillOpacity={0.2}
                    stroke="var(--accent)"
                    strokeWidth={1.5}
                    rx={2}
                    style={{ cursor: onDataClick ? 'pointer' : 'default' }}
                    onClick={() => onDataClick?.(stage)}
                  />

                  {/* Median line */}
                  <line
                    x1={centerX - boxWidth / 2}
                    y1={medianY}
                    x2={centerX + boxWidth / 2}
                    y2={medianY}
                    stroke="var(--accent)"
                    strokeWidth={2}
                  />

                  {/* Outliers */}
                  {stage.outliers.map((outlier, outlierIndex) => (
                    <circle
                      key={outlierIndex}
                      cx={centerX + (Math.random() - 0.5) * boxWidth * 0.5} // slight jitter
                      cy={yScale(outlier)}
                      r={2}
                      fill="var(--score-red)"
                      opacity={0.7}
                    />
                  ))}

                  {/* X axis label */}
                  <text
                    x={centerX}
                    y={chartHeight + 20}
                    textAnchor="middle"
                    className="analytics-chart-text"
                    style={{ fontSize: '11px', fill: 'var(--fg-3)' }}
                  >
                    {stage.label}
                  </text>

                  {/* Median value label */}
                  <text
                    x={centerX + boxWidth / 2 + 8}
                    y={medianY}
                    dominantBaseline="middle"
                    style={{
                      fontSize: '10px',
                      fill: 'var(--fg-2)',
                      fontFamily: 'var(--font-mono)',
                      fontWeight: '500',
                    }}
                  >
                    {stage.median.toFixed(1)}д
                  </text>
                </g>
              );
            })}

            {/* Y axis title */}
            <text
              x={-50}
              y={chartHeight / 2}
              textAnchor="middle"
              transform={`rotate(-90, -50, ${chartHeight / 2})`}
              style={{ fontSize: '12px', fill: 'var(--fg-3)', fontWeight: '500' }}
            >
              Дни
            </text>
          </g>
        </svg>
      </div>
    </div>
  );
}