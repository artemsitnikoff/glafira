/**
 * Funnel chart для конверсий по этапам.
 * Источник: backend/app/services/analytics/funnel.py:_build_funnel_chart
 * Форма data: { stages: [{ stage_key: string, label: string, color: string, count: number, conversion_from_prev_pct: number | null }], terminals: { hired: { n: number, pct: number }, rejected: { n: number, pct: number } } }
 */

interface FunnelData {
  stages: Array<{
    stage_key: string;
    label: string;
    color?: string;
    count: number;
    conversion_from_prev_pct: number | null;
  }>;
  terminals: {
    hired: { n: number; pct: number };
    rejected: { n: number; pct: number };
  };
}

interface FunnelChartProps {
  title: string;
  data: FunnelData;
  onDataClick?: (data: any) => void;
}

export function FunnelChart({ title, data, onDataClick }: FunnelChartProps) {
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

  const maxCount = Math.max(...data.stages.map(s => s.count));
  const funnelHeight = 400;
  const funnelWidth = 300;
  const stageHeight = 45;
  const stageGap = 8;

  return (
    <div className="analytics-chart-card">
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
        <p className="analytics-chart-subtitle">
          Кликните по этапу для детализации
        </p>
      </div>

      <div className="analytics-chart-container">
        <div style={{ display: 'flex', justifyContent: 'center', padding: '20px' }}>
          <svg width={funnelWidth + 200} height={funnelHeight} className="analytics-svg-chart">
            {/* Funnel stages */}
            {data.stages.map((stage, index) => {
              const y = 50 + index * (stageHeight + stageGap);
              const widthPercent = stage.count / maxCount;
              const stageWidth = Math.max(20, funnelWidth * widthPercent);
              const x = (funnelWidth - stageWidth) / 2;

              const color = stage.color || 'var(--accent)';

              return (
                <g key={stage.stage_key}>
                  {/* Stage bar (trapezoid shape) */}
                  <rect
                    x={x}
                    y={y}
                    width={stageWidth}
                    height={stageHeight}
                    fill={color}
                    fillOpacity={0.8}
                    stroke={color}
                    strokeWidth={1}
                    rx={4}
                    style={{ cursor: onDataClick ? 'pointer' : 'default' }}
                    onClick={() => onDataClick?.(stage)}
                  />

                  {/* Stage label and count */}
                  <text
                    x={x - 10}
                    y={y + stageHeight / 2 - 5}
                    textAnchor="end"
                    dominantBaseline="middle"
                    style={{ fontSize: '14px', fontWeight: '500', fill: 'var(--fg-1)' }}
                  >
                    {stage.label}
                  </text>

                  <text
                    x={x - 10}
                    y={y + stageHeight / 2 + 10}
                    textAnchor="end"
                    dominantBaseline="middle"
                    style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', fill: 'var(--fg-2)' }}
                  >
                    {stage.count.toLocaleString('ru-RU')}
                  </text>

                  {/* Conversion rate */}
                  {stage.conversion_from_prev_pct !== null && (
                    <text
                      x={x + stageWidth + 15}
                      y={y + stageHeight / 2}
                      dominantBaseline="middle"
                      style={{
                        fontSize: '12px',
                        fontFamily: 'var(--font-mono)',
                        fontWeight: '500',
                        fill: stage.conversion_from_prev_pct < 60 ? 'var(--score-red)' :
                              stage.conversion_from_prev_pct > 85 ? 'var(--score-green)' :
                              'var(--fg-2)'
                      }}
                    >
                      {stage.conversion_from_prev_pct.toFixed(1)}%
                    </text>
                  )}

                  {/* Drop indicator for low conversion */}
                  {stage.conversion_from_prev_pct !== null && stage.conversion_from_prev_pct < 50 && (
                    <text
                      x={x + stageWidth + 35}
                      y={y + stageHeight / 2}
                      dominantBaseline="middle"
                      style={{
                        fontSize: '11px',
                        fill: 'var(--score-red)',
                        fontWeight: '500',
                      }}
                    >
                      ⚠
                    </text>
                  )}

                  {/* Connection line to next stage */}
                  {index < data.stages.length - 1 && (
                    <line
                      x1={x + stageWidth / 2}
                      y1={y + stageHeight}
                      x2={x + stageWidth / 2}
                      y2={y + stageHeight + stageGap}
                      stroke="var(--border-3)"
                      strokeWidth={1}
                      strokeDasharray="3 3"
                    />
                  )}
                </g>
              );
            })}

            {/* Terminal states */}
            {data.terminals && (
              <g transform={`translate(0, ${50 + data.stages.length * (stageHeight + stageGap) + 20})`}>
                <text
                  x={funnelWidth / 2}
                  y={0}
                  textAnchor="middle"
                  style={{ fontSize: '13px', fontWeight: '500', fill: 'var(--fg-2)' }}
                >
                  Финальные результаты:
                </text>

                {/* Hired */}
                <g transform="translate(50, 25)">
                  <rect
                    x={0}
                    y={0}
                    width={80}
                    height={30}
                    fill="var(--score-green)"
                    fillOpacity={0.2}
                    stroke="var(--score-green)"
                    strokeWidth={1}
                    rx={4}
                  />
                  <text
                    x={40}
                    y={10}
                    textAnchor="middle"
                    style={{ fontSize: '11px', fontWeight: '500', fill: 'var(--score-green)' }}
                  >
                    Нанято
                  </text>
                  <text
                    x={40}
                    y={23}
                    textAnchor="middle"
                    style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', fontWeight: '500', fill: 'var(--score-green)' }}
                  >
                    {data.terminals.hired.n} ({data.terminals.hired.pct.toFixed(1)}%)
                  </text>
                </g>

                {/* Rejected */}
                <g transform="translate(170, 25)">
                  <rect
                    x={0}
                    y={0}
                    width={80}
                    height={30}
                    fill="var(--score-red)"
                    fillOpacity={0.2}
                    stroke="var(--score-red)"
                    strokeWidth={1}
                    rx={4}
                  />
                  <text
                    x={40}
                    y={10}
                    textAnchor="middle"
                    style={{ fontSize: '11px', fontWeight: '500', fill: 'var(--score-red)' }}
                  >
                    Отказано
                  </text>
                  <text
                    x={40}
                    y={23}
                    textAnchor="middle"
                    style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', fontWeight: '500', fill: 'var(--score-red)' }}
                  >
                    {data.terminals.rejected.n} ({data.terminals.rejected.pct.toFixed(1)}%)
                  </text>
                </g>
              </g>
            )}
          </svg>
        </div>
      </div>
    </div>
  );
}