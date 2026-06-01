import type { AnalyticsResponse } from '@/api/aliases';
import { AnChart } from '../AnChart';
import { AnTable } from '../AnTable';
import { Icon } from '@/components/ui/Icon';

interface FunnelReportProps {
  data: AnalyticsResponse;
}

export function FunnelReport({ data }: FunnelReportProps) {
  return (
    <>
      {/* funnel: kpis=null */}
      {data.charts?.map((chart, i) => (
        <AnChart key={i} chart={chart} />
      ))}

      {data.tables?.map((table, i) => (
        <AnTable key={i} table={table} />
      ))}

      <div className="an-note">
        <Icon name="info" size={14} />
        <span>
          <span className="nt-title">Не построено (нет данных бека):</span> KPI-полоса (Отклик→Нанят, % в
          интервью, Оффер→Нанят) и карточка «Сравнение с прошлым периодом» (дельты по этапам) — эталонные
          элементы Воронки, которые <code>/analytics/funnel</code> не отдаёт.
        </span>
      </div>
    </>
  );
}
