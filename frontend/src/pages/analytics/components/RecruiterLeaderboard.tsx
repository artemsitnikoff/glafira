/**
 * Recruiter leaderboard для отчёта рекрутеров.
 * Источник: backend/app/services/analytics/recruiters.py
 * Форма data: массив рекрутеров с полями для рейтинга
 */

import { Avatar } from '@/components/ui/Avatar';

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

interface RecruiterLeaderboardProps {
  recruiters: RecruiterData[];
  onRecruiterClick?: (recruiter: RecruiterData) => void;
}

export function RecruiterLeaderboard({ recruiters, onRecruiterClick }: RecruiterLeaderboardProps) {
  if (!recruiters || recruiters.length === 0) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: 'var(--fg-3)' }}>
        Нет данных о рекрутёрах
      </div>
    );
  }

  // Sort by hires count (primary metric)
  const sortedRecruiters = [...recruiters].sort((a, b) => b.hires - a.hires);
  const topThree = sortedRecruiters.slice(0, 3);

  const getRankBadge = (index: number) => {
    switch (index) {
      case 0:
        return { className: 'gold', icon: '🏆', label: 'Лидер' };
      case 1:
        return { className: 'silver', icon: '🥈', label: 'Второе место' };
      case 2:
        return { className: 'bronze', icon: '🥉', label: 'Третье место' };
      default:
        return { className: 'regular', icon: String(index + 1), label: `${index + 1} место` };
    }
  };

  const getPerformanceColor = (value: number, type: 'time' | 'pct' | 'autonomy') => {
    switch (type) {
      case 'time':
        return value <= 20 ? 'var(--score-green)' :
               value <= 35 ? 'var(--score-yellow)' :
               'var(--score-red)';
      case 'pct':
        return value >= 8 ? 'var(--score-green)' :
               value >= 5 ? 'var(--score-yellow)' :
               'var(--score-red)';
      case 'autonomy':
        return value >= 70 ? 'var(--score-green)' :
               value >= 50 ? 'var(--score-yellow)' :
               'var(--score-red)';
      default:
        return 'var(--fg-2)';
    }
  };

  return (
    <div className="analytics-leaderboard">
      {/* Top 3 highlight */}
      <div style={{ marginBottom: '24px' }}>
        <h4 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '16px', color: 'var(--fg-1)' }}>
          Топ-3 рекрутера
        </h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
          {topThree.map((recruiter, index) => {
            const badge = getRankBadge(index);
            return (
              <div
                key={recruiter.name}
                className="analytics-leaderboard-item"
                style={{ cursor: onRecruiterClick ? 'pointer' : 'default' }}
                onClick={() => onRecruiterClick?.(recruiter)}
              >
                <div className={`analytics-leaderboard-rank ${badge.className}`}>
                  {badge.icon}
                </div>
                <div className="analytics-leaderboard-info">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <Avatar name={recruiter.name} size="sm" />
                    <div className="analytics-leaderboard-name">{recruiter.name}</div>
                  </div>
                  <div className="analytics-leaderboard-stats">
                    {recruiter.hires} найма • {recruiter.avg_time_to_hire.toFixed(1)} дней
                  </div>
                </div>
                {index === 0 && (
                  <div className="analytics-leaderboard-badge champion">
                    Чемпион
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Full table */}
      <div>
        <h4 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '16px', color: 'var(--fg-1)' }}>
          Подробная статистика
        </h4>
        <div style={{ overflowX: 'auto' }}>
          <table className="analytics-table">
            <thead className="analytics-table-header">
              <tr>
                <th style={{ minWidth: '180px' }}>Рекрутер</th>
                <th style={{ width: '80px', textAlign: 'right' }}>Активных</th>
                <th style={{ width: '100px', textAlign: 'right' }}>Обработано</th>
                <th style={{ width: '90px', textAlign: 'right' }}>Скринингов</th>
                <th style={{ width: '120px', textAlign: 'right' }}>Интервью (назн/пров)</th>
                <th style={{ width: '80px', textAlign: 'right' }}>Найма</th>
                <th style={{ width: '100px', textAlign: 'right' }}>Время найма</th>
                <th style={{ width: '100px', textAlign: 'right' }}>Автономия AI</th>
              </tr>
            </thead>
            <tbody>
              {sortedRecruiters.map((recruiter, index) => {
                const badge = getRankBadge(index);
                return (
                  <tr
                    key={recruiter.name}
                    className="analytics-table-row"
                    style={{ cursor: onRecruiterClick ? 'pointer' : 'default' }}
                    onClick={() => onRecruiterClick?.(recruiter)}
                  >
                    <td className="analytics-table-cell">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div className={`analytics-leaderboard-rank ${badge.className}`} style={{ width: '24px', height: '24px', fontSize: '10px' }}>
                          {badge.icon}
                        </div>
                        <Avatar name={recruiter.name} size="sm" />
                        <span style={{ fontWeight: '500' }}>{recruiter.name}</span>
                      </div>
                    </td>
                    <td className="analytics-table-cell mono text-right">
                      {recruiter.active_vacancies}
                    </td>
                    <td className="analytics-table-cell mono text-right">
                      {recruiter.applications_processed}
                    </td>
                    <td className="analytics-table-cell mono text-right">
                      {recruiter.screenings}
                    </td>
                    <td className="analytics-table-cell mono text-right">
                      {recruiter.interviews_scheduled} / {recruiter.interviews_conducted}
                    </td>
                    <td className="analytics-table-cell mono text-right">
                      <span style={{
                        color: getPerformanceColor(recruiter.hires, 'pct'),
                        fontWeight: '600'
                      }}>
                        {recruiter.hires}
                      </span>
                    </td>
                    <td className="analytics-table-cell mono text-right">
                      <span style={{
                        color: getPerformanceColor(recruiter.avg_time_to_hire, 'time')
                      }}>
                        {recruiter.avg_time_to_hire.toFixed(1)} дней
                      </span>
                    </td>
                    <td className="analytics-table-cell mono text-right">
                      <span style={{
                        color: getPerformanceColor(recruiter.glafira_autonomy_pct, 'autonomy')
                      }}>
                        {recruiter.glafira_autonomy_pct.toFixed(0)}%
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}