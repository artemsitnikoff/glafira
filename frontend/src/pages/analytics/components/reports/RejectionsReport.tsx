import type { AnalyticsResponse, AnalyticsFilters } from '@/api/aliases';
import { ChartRenderer } from '../ChartRenderer';
import { TableRenderer } from '../TableRenderer';

interface RejectionsReportProps {
  data: AnalyticsResponse;
  filters: AnalyticsFilters;
  onFiltersChange: (filters: Partial<AnalyticsFilters>) => void;
}

export function RejectionsReport({ data }: RejectionsReportProps) {
  return (
    <div>
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