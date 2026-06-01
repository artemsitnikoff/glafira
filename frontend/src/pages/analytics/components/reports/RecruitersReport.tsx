import type { AnalyticsResponse } from '@/api/aliases';
import { AnChart } from '../AnChart';
import { AnTable } from '../AnTable';
import { Icon } from '@/components/ui/Icon';

interface RecruitersReportProps {
  data: AnalyticsResponse;
}

/**
 * Рекрутёры. Лидерборд рендерим через общий AnTable — ключи колонок берём
 * напрямую из TableColumn бека (recruiter_name / vacancies_active /
 * applications_handled / interviews / hires / avg_time_to_hire /
 * glafira_autonomy_pct / rank). Это выравнивает фронт под бек (прежний
 * RecruiterLeaderboard ждал несуществующие name/active_vacancies/...).
 */
export function RecruitersReport({ data }: RecruitersReportProps) {
  return (
    <>
      {/* charts[bar «Найма по рекрутёрам», radar «Сравнение топ-рекрутёров»] */}
      {data.charts?.map((chart, i) => (
        <AnChart key={i} chart={chart} />
      ))}

      {data.tables?.map((table, i) => (
        <AnTable key={i} table={table} />
      ))}

      <div className="an-note">
        <Icon name="info" size={14} />
        <span>
          <span className="nt-title">Не построено (нет данных бека):</span> multi-line «динамика
          производительности команды по неделям» — эталонный график, которого
          <code> /analytics/recruiters</code> не отдаёт.
        </span>
      </div>
    </>
  );
}
