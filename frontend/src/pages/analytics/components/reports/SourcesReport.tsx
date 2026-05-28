import type { AnalyticsResponse, AnalyticsFilters } from '@/api/aliases';
import { ChartRenderer } from '../ChartRenderer';
import { TableRenderer } from '../TableRenderer';

interface SourcesReportProps {
  data: AnalyticsResponse;
  filters: AnalyticsFilters;
  onFiltersChange: (filters: Partial<AnalyticsFilters>) => void;
}

export function SourcesReport({ data }: SourcesReportProps) {
  return (
    <div>
      {/* Main table first (primary content) */}
      {data.tables?.map((table, index) => (
        <TableRenderer key={index} table={table} />
      ))}

      {/* Charts */}
      {data.charts?.map((chart, index) => (
        <ChartRenderer
          key={index}
          chart={chart}
        />
      ))}

    </div>
  );
}