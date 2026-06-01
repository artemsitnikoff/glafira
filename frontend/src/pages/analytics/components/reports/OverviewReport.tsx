import type { AnalyticsResponse } from '@/api/aliases';
import { AnKpiBand } from '../AnKpiBand';
import { AnChart } from '../AnChart';
import { Icon } from '@/components/ui/Icon';

interface OverviewReportProps {
  data: AnalyticsResponse;
}

export function OverviewReport({ data }: OverviewReportProps) {
  return (
    <>
      {data.kpis && data.kpis.length > 0 && <AnKpiBand kpis={data.kpis} />}

      {data.charts?.map((chart, i) => (
        <AnChart key={i} chart={chart} />
      ))}

      <div className="an-note">
        <Icon name="info" size={14} />
        <span>
          <span className="nt-title">Не построено (нет данных бека):</span> мини-карты «Топ узких мест»,
          «Топ источников по конверсии», «Вакансии под угрозой», «Текучка по позициям» — эталонные блоки
          Обзора, которые эндпоинт <code>/analytics/overview</code> не отдаёт.
        </span>
      </div>
    </>
  );
}
