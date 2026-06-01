import type { AnalyticsResponse } from '@/api/aliases';
import { AnChart } from '../AnChart';
import { AnTable } from '../AnTable';
import { Icon } from '@/components/ui/Icon';

interface SourcesReportProps {
  data: AnalyticsResponse;
}

export function SourcesReport({ data }: SourcesReportProps) {
  return (
    <>
      {/* sources: charts[stacked, scatter] + table[эффективность] */}
      {data.charts?.map((chart, i) => (
        <AnChart key={i} chart={chart} />
      ))}

      {data.tables?.map((table, i) => (
        <AnTable key={i} table={table} />
      ))}

      <div className="an-note">
        <Icon name="info" size={14} />
        <span>
          <span className="nt-title">Не построено (нет данных бека):</span> multi-line «динамика источников по
          неделям» — эталонный график, которого <code>/analytics/sources</code> не отдаёт. Колонки
          «Стоимость» / «ROI» в таблице бек возвращает <code>null</code> → показаны как «—».
        </span>
      </div>
    </>
  );
}
