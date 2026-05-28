import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { GlobalFilters } from './components/GlobalFilters';
import { OverviewReport } from './components/reports/OverviewReport';
import { SpeedReport } from './components/reports/SpeedReport';
import { FunnelReport } from './components/reports/FunnelReport';
import { SourcesReport } from './components/reports/SourcesReport';
import { RejectionsReport } from './components/reports/RejectionsReport';
import { TurnoverReport } from './components/reports/TurnoverReport';
import { RecruitersReport } from './components/reports/RecruitersReport';
import { useAnalytics } from '@/api/hooks/useAnalytics';
import type { AnalyticsFilters } from '@/api/aliases';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import './Analytics.css';

const REPORTS = [
  { key: 'overview', title: 'Обзор' },
  { key: 'speed', title: 'Скорость найма' },
  { key: 'funnel', title: 'Воронка конверсий' },
  { key: 'sources', title: 'Источники' },
  { key: 'rejections', title: 'Причины отказов' },
  { key: 'turnover', title: 'Текучка после найма' },
  { key: 'recruiters', title: 'Рекрутеры' },
] as const;

type ReportKey = typeof REPORTS[number]['key'];

export default function AnalyticsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Get current report from URL
  const currentReport = (searchParams.get('report') as ReportKey) || 'overview';
  const reportConfig = REPORTS.find(r => r.key === currentReport) || REPORTS[0];

  // Build filters from URL params
  const filters = useMemo((): AnalyticsFilters => {
    return {
      period: (searchParams.get('period') as AnalyticsFilters['period']) || 'month',
      date_from: searchParams.get('date_from') || undefined,
      date_to: searchParams.get('date_to') || undefined,
      vacancy_ids: searchParams.getAll('vacancy_ids').filter(Boolean),
      recruiter_ids: searchParams.getAll('recruiter_ids').filter(Boolean),
      compare: searchParams.get('compare') !== 'false',
    };
  }, [searchParams]);

  const handleFiltersChange = (newFilters: Partial<AnalyticsFilters>) => {
    const params = new URLSearchParams(searchParams);

    // Update filters in URL
    Object.entries(newFilters).forEach(([key, value]) => {
      if (key === 'vacancy_ids' || key === 'recruiter_ids') {
        // Remove all existing values for this key
        params.delete(key);
        // Add new values
        if (Array.isArray(value) && value.length > 0) {
          value.forEach(v => params.append(key, v));
        }
      } else if (value !== undefined) {
        params.set(key, String(value));
      } else {
        params.delete(key);
      }
    });

    setSearchParams(params);
  };

  const handleReportChange = (report: ReportKey) => {
    const params = new URLSearchParams(searchParams);
    params.set('report', report);
    setSearchParams(params);
  };

  // Fetch analytics data
  const { data: analyticsData, isLoading, error, refetch } = useAnalytics(currentReport, filters);

  // Render specific report component
  const renderReport = () => {
    if (isLoading) {
      return (
        <div className="analytics-loading">
          <Skeleton className="analytics-skeleton analytics-skeleton-kpi" />
          <Skeleton className="analytics-skeleton analytics-skeleton-chart" />
          <Skeleton className="analytics-skeleton analytics-skeleton-table" />
        </div>
      );
    }

    if (error) {
      return (
        <div className="analytics-error">
          <div className="analytics-error-title">Ошибка загрузки данных</div>
          <div className="analytics-error-message">
            {error instanceof Error ? error.message : 'Произошла неизвестная ошибка'}
          </div>
          <button className="analytics-error-retry" onClick={() => refetch()}>
            Повторить
          </button>
        </div>
      );
    }

    if (!analyticsData || ((analyticsData.charts?.length || 0) === 0 && (analyticsData.tables?.length || 0) === 0)) {
      return (
        <EmptyState
          icon="bar-chart"
          title="Нет данных за период"
          description="Попробуйте расширить период или изменить фильтры"
          action={
            <button
              className="analytics-empty-action"
              onClick={() => handleFiltersChange({ period: 'month', vacancy_ids: [], recruiter_ids: [] })}
            >
              Сбросить фильтры
            </button>
          }
        />
      );
    }

    const commonProps = {
      data: analyticsData,
      filters,
      onFiltersChange: handleFiltersChange,
    };

    switch (currentReport) {
      case 'overview':
        return <OverviewReport {...commonProps} onReportChange={(report: string) => handleReportChange(report as ReportKey)} />;
      case 'speed':
        return <SpeedReport {...commonProps} />;
      case 'funnel':
        return <FunnelReport {...commonProps} />;
      case 'sources':
        return <SourcesReport {...commonProps} />;
      case 'rejections':
        return <RejectionsReport {...commonProps} />;
      case 'turnover':
        return <TurnoverReport {...commonProps} />;
      case 'recruiters':
        return <RecruitersReport {...commonProps} />;
      default:
        return <OverviewReport {...commonProps} onReportChange={(report: string) => handleReportChange(report as ReportKey)} />;
    }
  };

  return (
    <div className="analytics-page">
      {/* Header */}
      <div className="analytics-header">
        <div>
          <h1 className="analytics-title">{reportConfig.title}</h1>
          <p className="analytics-subtitle">
            Обновлено {new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>

        <GlobalFilters
          filters={filters}
          onChange={handleFiltersChange}
          isLoading={isLoading}
        />
      </div>

      {/* Content */}
      <div className="analytics-content">
        {renderReport()}
      </div>
    </div>
  );
}