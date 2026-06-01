import type { AnalyticsResponse } from '@/api/aliases';
import { AnChart } from '../AnChart';
import { AnTable } from '../AnTable';
import { Icon } from '@/components/ui/Icon';

interface SpeedReportProps {
  data: AnalyticsResponse;
}

export function SpeedReport({ data }: SpeedReportProps) {
  return (
    <>
      {/* speed: kpis=null — KPI-полосу НЕ рисуем */}
      {data.charts?.map((chart, i) => (
        <AnChart key={i} chart={chart} />
      ))}

      {data.tables?.map((table, i) => (
        <AnTable key={i} table={table} />
      ))}

      <div className="an-note">
        <Icon name="info" size={14} />
        <span>
          <span className="nt-title">Не построено (нет данных бека):</span> KPI-полоса (время найма / до
          первого контакта / на «Оффере») и линия «время найма по периодам» — эталонные элементы Скорости,
          которые <code>/analytics/speed</code> не отдаёт.
        </span>
      </div>
    </>
  );
}
