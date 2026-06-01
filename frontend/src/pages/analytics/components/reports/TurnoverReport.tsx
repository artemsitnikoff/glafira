import type { AnalyticsResponse } from '@/api/aliases';
import { AnChart } from '../AnChart';
import { AnTable } from '../AnTable';
import { Icon } from '@/components/ui/Icon';

interface TurnoverReportProps {
  data: AnalyticsResponse;
}

export function TurnoverReport({ data }: TurnoverReportProps) {
  return (
    <>
      {/* turnover: kpis=null; charts[cohort, survival] + table[руководители] */}
      {data.charts?.map((chart, i) => (
        <AnChart key={i} chart={chart} />
      ))}

      {data.tables?.map((table, i) => (
        <AnTable key={i} table={table} />
      ))}

      <div className="an-note">
        <Icon name="info" size={14} />
        <span>
          <span className="nt-title">Не построено (нет данных бека):</span> KPI-полоса (текучка 30/90д,
          удержание 1 год) и vbar «когда уходят» — эталонные элементы Текучки, которых
          <code> /analytics/turnover</code> не отдаёт. Cohort/Survival пусты без сотрудников (раздел Пульс).
        </span>
      </div>
    </>
  );
}
