import type { AnalyticsResponse, AnalyticsFilters } from '@/api/aliases';
import { KpiStrip } from '../KpiStrip';
import { ChartRenderer } from '../ChartRenderer';
import { TableRenderer } from '../TableRenderer';

interface SpeedReportProps {
  data: AnalyticsResponse;
  filters: AnalyticsFilters;
  onFiltersChange: (filters: Partial<AnalyticsFilters>) => void;
}

export function SpeedReport({ data }: SpeedReportProps) {
  return (
    <div>
      {/* KPI Strip */}
      {data.kpis && data.kpis.length > 0 && (
        <KpiStrip kpis={data.kpis} />
      )}

      {/* Charts */}
      {data.charts?.map((chart, index) => (
        <ChartRenderer
          key={index}
          chart={chart}
        />
      ))}

      {/* Tables */}
      {data.tables?.map((table, index) => (
        <TableRenderer key={index} table={table} />
      ))}

    </div>
  );
}