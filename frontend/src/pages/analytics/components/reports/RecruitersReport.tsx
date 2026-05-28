import type { AnalyticsResponse, AnalyticsFilters } from '@/api/aliases';
import { ChartRenderer } from '../ChartRenderer';
import { TableRenderer } from '../TableRenderer';
import { RecruiterLeaderboard } from '../RecruiterLeaderboard';

interface RecruiterData {
  name: string;
  active_vacancies: number;
  applications_processed: number;
  screenings: number;
  interviews_scheduled: number;
  interviews_conducted: number;
  hires: number;
  avg_time_to_hire: number;
  glafira_autonomy_pct: number;
  [key: string]: any;
}

interface RecruitersReportProps {
  data: AnalyticsResponse;
  filters: AnalyticsFilters;
  onFiltersChange: (filters: Partial<AnalyticsFilters>) => void;
}

export function RecruitersReport({ data }: RecruitersReportProps) {
  // Extract recruiter data from tables for leaderboard
  const recruiterData = data.tables?.find(table => table.title.toLowerCase().includes('рекрут'))?.rows || [];

  return (
    <div>
      {/* Recruiter Leaderboard */}
      {recruiterData.length > 0 && (
        <div className="analytics-chart-card" style={{ marginBottom: '24px' }}>
          <div className="analytics-chart-header">
            <h3 className="analytics-chart-title">Рейтинг рекрутёров</h3>
            <p className="analytics-chart-subtitle">
              Лидерборд команды по ключевым показателям эффективности
            </p>
          </div>
          <RecruiterLeaderboard
            recruiters={recruiterData as RecruiterData[]} // Backend table rows: { [key: string]: unknown }[] → RecruiterData[]
          />
        </div>
      )}

      {/* Charts */}
      {data.charts?.map((chart, index) => (
        <ChartRenderer
          key={index}
          chart={chart}
        />
      ))}

      {/* Additional tables */}
      {data.tables
        ?.filter(table => !table.title.toLowerCase().includes('рекрут'))
        .map((table, index) => (
          <TableRenderer key={index} table={table} />
        ))}

    </div>
  );
}