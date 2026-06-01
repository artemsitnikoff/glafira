/**
 * Boxplot — время на этапах воронки (dwell time, дни).
 * Источник: speed.py:_build_boxplot_chart
 * Форма data: { stages: [{ stage_key, label, median, q1, q3, min, max, outliers }] }
 * Этапы без данных (median=null) рисуем «нет данных».
 * Content-only: карточку и empty-state даёт AnChart.
 */

import { useRef, useEffect, useState } from 'react';
import { ANALYTICS_PALETTE } from '../../palette';

interface BoxStage {
  stage_key: string;
  label: string;
  median: number | null;
  q1: number | null;
  q3: number | null;
  min: number | null;
  max: number | null;
  outliers: number[];
}

interface BoxplotChartProps {
  data: { stages: BoxStage[] };
}

/** Детерминированный jitter по индексу выброса (без RNG) в [-0.5, 0.5]. */
function jitterFor(index: number): number {
  // золотое сечение для равномерного псевдослучайного распределения по индексу
  const frac = (index * 0.6180339887) % 1;
  return frac - 0.5;
}

export function BoxplotChart({ data }: BoxplotChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(800);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setContainerWidth(e.contentRect.width);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const margin = { top: 16, right: 32, bottom: 50, left: 56 };
  const chartWidth = Math.max(280, containerWidth) - margin.left - margin.right;
  const chartHeight = 260;
  const boxWidth = Math.min(56, (chartWidth / data.stages.length) * 0.55);

  const allValues = data.stages
    .flatMap((s) => [s.min, s.max, s.median, s.q1, s.q3, ...s.outliers])
    .filter((v): v is number => v !== null && v !== undefined);
  const globalMin = Math.min(...allValues, 0);
  const globalMax = Math.max(...allValues, 1);
  const span = globalMax - globalMin || 1;
  const yScale = (value: number) => chartHeight - ((value - globalMin) / span) * chartHeight;
  const stageWidth = chartWidth / data.stages.length;

  const yTicks: number[] = [];
  for (let i = 0; i <= 4; i++) yTicks.push(globalMin + span * (i / 4));

  return (
    <div className="an-chart-wrap" ref={containerRef}>
      <svg width="100%" height={chartHeight + margin.top + margin.bottom} className="an-svg-chart">
        <g transform={`translate(${margin.left}, ${margin.top})`}>
          {yTicks.map((tick, i) => (
            <g key={i}>
              <line x1={0} y1={yScale(tick)} x2={chartWidth} y2={yScale(tick)} stroke="var(--border-2)" strokeWidth={1} strokeDasharray={i === 0 ? '0' : '3 3'} />
              <text x={-10} y={yScale(tick)} textAnchor="end" dominantBaseline="middle" style={{ fontSize: 11, fill: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>
                {tick.toFixed(0)}
              </text>
            </g>
          ))}

          {data.stages.map((stage, index) => {
            const centerX = (index + 0.5) * stageWidth;
            if (stage.median === null || stage.q1 === null || stage.q3 === null) {
              return (
                <g key={stage.stage_key}>
                  <text x={centerX} y={chartHeight - 12} textAnchor="middle" style={{ fontSize: 11, fill: 'var(--fg-4)' }}>
                    нет данных
                  </text>
                  <text x={centerX} y={chartHeight + 22} textAnchor="middle" style={{ fontSize: 11, fill: 'var(--fg-3)' }}>
                    {stage.label}
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
                <line x1={centerX} y1={minY} x2={centerX} y2={q1Y} stroke="var(--fg-3)" strokeWidth={1} />
                <line x1={centerX} y1={q3Y} x2={centerX} y2={maxY} stroke="var(--fg-3)" strokeWidth={1} />
                <line x1={centerX - boxWidth / 4} y1={minY} x2={centerX + boxWidth / 4} y2={minY} stroke="var(--fg-3)" strokeWidth={1} />
                <line x1={centerX - boxWidth / 4} y1={maxY} x2={centerX + boxWidth / 4} y2={maxY} stroke="var(--fg-3)" strokeWidth={1} />
                <rect
                  x={centerX - boxWidth / 2}
                  y={q3Y}
                  width={boxWidth}
                  height={Math.max(1, q1Y - q3Y)}
                  fill={ANALYTICS_PALETTE.blue}
                  fillOpacity={0.18}
                  stroke={ANALYTICS_PALETTE.blue}
                  strokeWidth={1.5}
                  rx={2}
                />
                <line x1={centerX - boxWidth / 2} y1={medianY} x2={centerX + boxWidth / 2} y2={medianY} stroke={ANALYTICS_PALETTE.blue} strokeWidth={2} />
                {stage.outliers.map((outlier, oi) => (
                  <circle key={oi} cx={centerX + jitterFor(oi) * boxWidth * 0.5} cy={yScale(outlier)} r={2} fill={ANALYTICS_PALETTE.red} opacity={0.7} />
                ))}
                <text x={centerX} y={chartHeight + 22} textAnchor="middle" style={{ fontSize: 11, fill: 'var(--fg-3)' }}>
                  {stage.label}
                </text>
                <text x={centerX + boxWidth / 2 + 6} y={medianY} dominantBaseline="middle" style={{ fontSize: 10, fill: 'var(--fg-2)', fontFamily: 'var(--font-mono)', fontWeight: 500 }}>
                  {stage.median.toFixed(1)}д
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
