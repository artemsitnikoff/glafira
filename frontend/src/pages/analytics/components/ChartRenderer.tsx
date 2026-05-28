import type { ChartData } from '@/api/aliases';
import { LineChart } from './charts/LineChart';
import { BarChart } from './charts/BarChart';
import { PieChart } from './charts/PieChart';
import { ScatterChart } from './charts/ScatterChart';
import { RadarChart } from './charts/RadarChart';
import { HBarChart } from './charts/HBarChart';
import { FunnelChart } from './charts/FunnelChart';
import { BoxplotChart } from './charts/BoxplotChart';
import { HeatmapChart } from './charts/HeatmapChart';
import { SurvivalChart } from './charts/SurvivalChart';
import { CohortChart } from './charts/CohortChart';
import { StackedChart } from './charts/StackedChart';

// Chart data shapes from backend analytics services:
// - Line: { points: [{ date: string, value: number }] }
// - HBar: { items: [{ label: string, value: number }] }
// - Stacked: { stages: [...] } or { sources: [...] }
// - Funnel: { stages: [...], terminals: [...] }
// - Scatter: { points: [...] }

interface ChartRendererProps {
  chart: ChartData;
  onDataClick?: (data: any) => void;
}

export function ChartRenderer({ chart, onDataClick }: ChartRendererProps) {
  const commonProps = {
    title: chart.title,
    data: chart.data as any, // Dynamic shape depends on chart.type - see backend services above
    onDataClick,
  };

  switch (chart.type) {
    case 'line':
      return <LineChart {...commonProps} />;
    case 'bar':
      return <BarChart {...commonProps} />;
    case 'hbar':
      return <HBarChart {...commonProps} />;
    case 'pie':
      return <PieChart {...commonProps} />;
    case 'scatter':
      return <ScatterChart {...commonProps} />;
    case 'radar':
      return <RadarChart {...commonProps} />;
    case 'funnel':
      return <FunnelChart {...commonProps} />;
    case 'boxplot':
      return <BoxplotChart {...commonProps} />;
    case 'heatmap':
      return <HeatmapChart {...commonProps} />;
    case 'survival':
      return <SurvivalChart {...commonProps} />;
    case 'cohort':
      return <CohortChart {...commonProps} />;
    case 'stacked':
      return <StackedChart {...commonProps} />;
    default:
      return (
        <div className="analytics-chart-card">
          <div className="analytics-chart-header">
            <h3 className="analytics-chart-title">{chart.title}</h3>
          </div>
          <div style={{ padding: '20px', textAlign: 'center', color: 'var(--fg-3)' }}>
            Неизвестный тип графика: {chart.type}
          </div>
        </div>
      );
  }
}