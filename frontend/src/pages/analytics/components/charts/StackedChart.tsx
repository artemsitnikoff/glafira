/**
 * Stacked chart для карты активности воронки и источников по этапам.
 * Источник: backend/app/services/analytics/overview.py:_build_stages_chart, sources.py
 * Форма data: { stages: [{ stage_key: string, label: string, color: string, count: number }] }
 * ИЛИ: { sources: [{ source: string, stages: [{ stage_key: string, label: string, color: string, count: number }] }] }
 */

import { BarChart as RechartsBarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface StackedChartProps {
  title: string;
  data:
    | { stages: Array<{ stage_key: string; label: string; color?: string; count: number }> }
    | { sources: Array<{ source: string; stages: Array<{ stage_key: string; label: string; color?: string; count: number }> }> };
  onDataClick?: (data: any) => void;
}

const DEFAULT_COLORS = [
  '#5B6573', // response
  '#7E5CF0', // added
  '#9AA3AE', // selected
  '#7AB4F5', // recruiter
  '#2A8AF0', // interview
  '#5778E8', // manager
  '#E0A21A', // offer
  '#16A34A', // hired
  '#DC4646', // rejected
];

export function StackedChart({ title, data, onDataClick }: StackedChartProps) {
  const renderTooltip = (props: any) => {
    if (!props.active || !props.payload || props.payload.length === 0) {
      return null;
    }
    return (
      <div className="analytics-chart-tooltip">
        <div className="analytics-chart-tooltip-title">{props.label}</div>
        {props.payload.map((entry: any, index: number) => (
          <div key={index} className="analytics-chart-tooltip-item">
            <span
              className="analytics-chart-tooltip-dot"
              style={{ backgroundColor: entry.color }}
            />
            <span className="analytics-chart-tooltip-label">{entry.name}</span>
            <span className="analytics-chart-tooltip-value">{entry.value}</span>
          </div>
        ))}
      </div>
    );
  };

  // Handle single stacked bar (overview report)
  if ('stages' in data) {
    if (!data.stages || data.stages.length === 0) {
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

    // Convert to horizontal bar format
    const chartData = [
      {
        category: 'Активность',
        ...data.stages.reduce((acc, stage) => {
          acc[stage.stage_key] = stage.count;
          return acc;
        }, {} as Record<string, number>)
      }
    ];

    return (
      <div className="analytics-chart-card">
        <div className="analytics-chart-header">
          <h3 className="analytics-chart-title">{title}</h3>
        </div>

        <div className="analytics-chart-container">
          <ResponsiveContainer width="100%" height={120}>
            <RechartsBarChart
              data={chartData}
              layout="horizontal"
              margin={{ top: 20, right: 30, left: 80, bottom: 20 }}
            >
              <XAxis type="number" hide />
              <YAxis dataKey="category" type="category" hide />
              <Tooltip content={renderTooltip} />
              {data.stages.map((stage, index) => (
                <Bar
                  key={stage.stage_key}
                  dataKey={stage.stage_key}
                  stackId="stages"
                  fill={stage.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length]}
                  name={stage.label}
                  onClick={onDataClick}
                />
              ))}
            </RechartsBarChart>
          </ResponsiveContainer>

          {/* Legend */}
          <div style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '12px',
            marginTop: '16px',
            fontSize: '12px'
          }}>
            {data.stages.map((stage, index) => (
              <div key={stage.stage_key} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <div
                  style={{
                    width: '12px',
                    height: '12px',
                    borderRadius: '50%',
                    backgroundColor: stage.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length],
                  }}
                />
                <span style={{ color: 'var(--fg-2)' }}>{stage.label}</span>
                <span style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>
                  ({stage.count})
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Handle sources variant (sources report)
  if ('sources' in data) {
    if (!data.sources || data.sources.length === 0) {
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

    // Convert sources data for vertical stacked bars
    const chartData = data.sources.map(source => {
      const sourceData: Record<string, any> = { source: source.source };
      source.stages.forEach(stage => {
        sourceData[stage.stage_key] = stage.count;
      });
      return sourceData;
    });

    // Get all unique stages across sources
    const allStages = Array.from(new Set(
      data.sources.flatMap(source => source.stages.map(stage => stage.stage_key))
    ));

    return (
      <div className="analytics-chart-card">
        <div className="analytics-chart-header">
          <h3 className="analytics-chart-title">{title}</h3>
        </div>

        <div className="analytics-chart-container">
          <ResponsiveContainer width="100%" height={320}>
            <RechartsBarChart
              data={chartData}
              margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-2)" />
              <XAxis
                dataKey="source"
                stroke="var(--fg-3)"
                fontSize={11}
                fontFamily="var(--font-mono)"
                angle={-45}
                textAnchor="end"
                height={60}
              />
              <YAxis
                stroke="var(--fg-3)"
                fontSize={11}
                fontFamily="var(--font-mono)"
              />
              <Tooltip content={renderTooltip} />
              {allStages.map((stageKey, index) => {
                // Find stage info from any source that has this stage
                const stageInfo = data.sources
                  .flatMap(source => source.stages)
                  .find(stage => stage.stage_key === stageKey);

                return (
                  <Bar
                    key={stageKey}
                    dataKey={stageKey}
                    stackId="sources"
                    fill={stageInfo?.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length]}
                    name={stageInfo?.label || stageKey}
                    onClick={onDataClick}
                  />
                );
              })}
            </RechartsBarChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  return (
    <div className="analytics-chart-card">
      <div className="analytics-chart-header">
        <h3 className="analytics-chart-title">{title}</h3>
      </div>
      <div style={{ padding: '40px', textAlign: 'center', color: 'var(--fg-3)' }}>
        Неподдерживаемый формат данных
      </div>
    </div>
  );
}