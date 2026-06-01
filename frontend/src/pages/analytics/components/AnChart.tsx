import type { ChartData } from '@/api/aliases';
import { AnCard, AnCardEmpty } from './AnCard';
import { LineChart } from './charts/LineChart';
import { BarChart } from './charts/BarChart';
import { HBarChart } from './charts/HBarChart';
import { PieChart } from './charts/PieChart';
import { ScatterChart } from './charts/ScatterChart';
import { RadarChart } from './charts/RadarChart';
import { FunnelChart } from './charts/FunnelChart';
import { BoxplotChart } from './charts/BoxplotChart';
import { HeatmapChart } from './charts/HeatmapChart';
import { SurvivalChart } from './charts/SurvivalChart';
import { CohortChart } from './charts/CohortChart';
import { StackedChart } from './charts/StackedChart';

interface AnChartProps {
  chart: ChartData;
  sub?: string;
  className?: string;
}

type AnyData = Record<string, unknown> & {
  points?: unknown[];
  items?: unknown[];
  stages?: unknown[];
  sources?: unknown[];
  cohorts?: unknown[];
  cells?: unknown[];
  series?: unknown[];
  axes?: unknown[];
  our?: unknown[];
  candidate?: unknown[];
};

/**
 * Возвращает true, если у графика нет реальных данных бека для отрисовки.
 * Тогда рисуем честный empty-state, НЕ выдумываем числа.
 */
function isEmpty(chart: ChartData): boolean {
  const d = (chart.data || {}) as AnyData;
  switch (chart.type) {
    case 'line':
    case 'scatter':
    case 'survival':
      return !d.points || d.points.length === 0;
    case 'bar':
    case 'hbar':
      return !d.items || d.items.length === 0;
    case 'pie':
      // dual pie: пусто если обе стороны пусты
      if ('our' in d || 'candidate' in d) {
        return (!d.our || d.our.length === 0) && (!d.candidate || d.candidate.length === 0);
      }
      return !Array.isArray(chart.data) || (chart.data as unknown[]).length === 0;
    case 'radar':
      return !d.series || d.series.length === 0 || !d.axes || d.axes.length === 0;
    case 'funnel':
      return !d.stages || d.stages.length === 0;
    case 'boxplot': {
      // пусто, если ни у одного этапа нет медианы
      const stages = (d.stages as Array<{ median: number | null }> | undefined) || [];
      return stages.length === 0 || stages.every((s) => s.median === null || s.median === undefined);
    }
    case 'heatmap': {
      const cells = (d.cells as Array<{ value: number | null }> | undefined) || [];
      return cells.length === 0 || cells.every((c) => c.value === null || c.value === undefined);
    }
    case 'cohort':
      return !d.cohorts || d.cohorts.length === 0;
    case 'stacked':
      if ('sources' in d) return !d.sources || d.sources.length === 0;
      return !d.stages || d.stages.length === 0;
    default:
      return false;
  }
}

function renderInner(chart: ChartData) {
  const props = { data: chart.data as never };
  switch (chart.type) {
    case 'line':
      return <LineChart {...props} />;
    case 'bar':
      return <BarChart {...props} />;
    case 'hbar':
      return <HBarChart {...props} />;
    case 'pie':
      return <PieChart {...props} />;
    case 'scatter':
      return <ScatterChart {...props} />;
    case 'radar':
      return <RadarChart {...props} />;
    case 'funnel':
      return <FunnelChart {...props} />;
    case 'boxplot':
      return <BoxplotChart {...props} />;
    case 'heatmap':
      return <HeatmapChart {...props} />;
    case 'survival':
      return <SurvivalChart {...props} />;
    case 'cohort':
      return <CohortChart {...props} />;
    case 'stacked':
      return <StackedChart {...props} />;
    default:
      return <AnCardEmpty title={`Неизвестный тип графика: ${chart.type}`} sub="" />;
  }
}

export function AnChart({ chart, sub, className }: AnChartProps) {
  return (
    <AnCard title={chart.title} sub={sub} className={className}>
      {isEmpty(chart) ? <AnCardEmpty /> : renderInner(chart)}
    </AnCard>
  );
}
