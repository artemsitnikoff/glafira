import type { AnalyticsResponse, AnalyticsFilters } from '@/api/aliases';
import { KpiStrip } from '../KpiStrip';
import { ChartRenderer } from '../ChartRenderer';
import { TableRenderer } from '../TableRenderer';

interface FunnelReportProps {
  data: AnalyticsResponse;
  filters: AnalyticsFilters;
  onFiltersChange: (filters: Partial<AnalyticsFilters>) => void;
}

export function FunnelReport({ data }: FunnelReportProps) {
  return (
    <div>
      {/* KPI Strip */}
      {data.kpis && data.kpis.length > 0 && (
        <KpiStrip kpis={data.kpis} />
      )}

      {/* Charts */}
      <div className="analytics-grid-2">
        {data.charts?.map((chart, index) => (
          <ChartRenderer
            key={index}
            chart={chart}
          />
        ))}
      </div>

      {/* Tables */}
      {data.tables?.map((table, index) => (
        <TableRenderer key={index} table={table} />
      ))}

    </div>
  );
}