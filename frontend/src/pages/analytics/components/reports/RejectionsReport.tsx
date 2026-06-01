import type { AnalyticsResponse } from '@/api/aliases';
import { AnChart } from '../AnChart';
import { AnTable } from '../AnTable';

interface RejectionsReportProps {
  data: AnalyticsResponse;
}

export function RejectionsReport({ data }: RejectionsReportProps) {
  return (
    <>
      {/* rejections: charts[pie «Причины отказов», line «Динамика отказов»] + table */}
      {data.charts?.map((chart, i) => (
        <AnChart key={i} chart={chart} />
      ))}

      {data.tables?.map((table, i) => (
        <AnTable key={i} table={table} />
      ))}
    </>
  );
}
