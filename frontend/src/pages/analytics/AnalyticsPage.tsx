import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAnalytics } from '@/api/hooks/useAnalytics';
import type { AnalyticsFilters } from '@/api/aliases';
import { Icon } from '@/components/ui/Icon';
import { AnHeaderControls } from './components/AnHeaderControls';
import { OverviewReport } from './components/reports/OverviewReport';
import { SpeedReport } from './components/reports/SpeedReport';
import { FunnelReport } from './components/reports/FunnelReport';
import { SourcesReport } from './components/reports/SourcesReport';
import { RejectionsReport } from './components/reports/RejectionsReport';
import { TurnoverReport } from './components/reports/TurnoverReport';
import { RecruitersReport } from './components/reports/RecruitersReport';
import { reportTitle, type ReportKey } from './meta';
import './Analytics.css';

export default function AnalyticsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const currentReport = (searchParams.get('report') as ReportKey) || 'overview';

  const filters = useMemo((): AnalyticsFilters => {
    const period = (searchParams.get('period') as AnalyticsFilters['period']) || 'month';
    return {
      period,
      date_from: searchParams.get('date_from') || undefined,
      date_to: searchParams.get('date_to') || undefined,
      vacancy_ids: searchParams.getAll('vacancy_ids').filter(Boolean),
      recruiter_ids: searchParams.getAll('recruiter_ids').filter(Boolean),
      // compare всегда true по умолчанию (бек применяет только в overview — это ОК).
      compare: searchParams.get('compare') !== 'false',
    };
  }, [searchParams]);

  const handleFiltersChange = (newFilters: Partial<AnalyticsFilters>) => {
    const params = new URLSearchParams(searchParams);
    Object.entries(newFilters).forEach(([key, value]) => {
      if (key === 'vacancy_ids' || key === 'recruiter_ids') {
        params.delete(key);
        if (Array.isArray(value) && value.length > 0) value.forEach((v) => params.append(key, v));
      } else if (value !== undefined) {
        params.set(key, String(value));
      } else {
        params.delete(key);
      }
    });
    setSearchParams(params);
  };

  const { data, isLoading, error, refetch, dataUpdatedAt } = useAnalytics(currentReport, filters);

  const renderBody = () => {
    if (isLoading) {
      return (
        <>
          <div className="an-kpi-band">
            <div className="an-card" style={{ height: 96 }} />
            <div className="an-card" style={{ height: 96 }} />
            <div className="an-card" style={{ height: 96 }} />
            <div className="an-card" style={{ height: 96 }} />
          </div>
          <div className="an-card" style={{ height: 280 }} />
          <div className="an-card" style={{ height: 220 }} />
        </>
      );
    }

    if (error) {
      return (
        <div className="an-card">
          <div className="an-card-empty">
            <Icon name="alert-triangle" size={32} />
            <div className="em-title">Не удалось загрузить данные</div>
            <div className="em-sub">{error instanceof Error ? error.message : 'Неизвестная ошибка'}</div>
            <button className="an-csv" style={{ marginTop: 12 }} onClick={() => refetch()}>
              Повторить
            </button>
          </div>
        </div>
      );
    }

    const noContent = !data || ((data.charts?.length || 0) === 0 && (data.tables?.length || 0) === 0 && (data.kpis?.length || 0) === 0);
    if (noContent) {
      return (
        <div className="an-card">
          <div className="an-card-empty">
            <Icon name="bar-chart" size={32} />
            <div className="em-title">Нет данных за период</div>
            <div className="em-sub">Расширьте период или измените фильтры.</div>
          </div>
        </div>
      );
    }

    switch (currentReport) {
      case 'overview':
        return <OverviewReport data={data} />;
      case 'speed':
        return <SpeedReport data={data} />;
      case 'funnel':
        return <FunnelReport data={data} />;
      case 'sources':
        return <SourcesReport data={data} />;
      case 'rejections':
        return <RejectionsReport data={data} />;
      case 'turnover':
        return <TurnoverReport data={data} />;
      case 'recruiters':
        return <RecruitersReport data={data} />;
      default:
        return <OverviewReport data={data} />;
    }
  };

  const updatedLabel =
    !isLoading && dataUpdatedAt
      ? `Обновлено ${new Date(dataUpdatedAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`
      : '';

  const showLowDataWarn = filters.period === 'week';

  return (
    <div className="an-shell">
      <div className="an-header">
        <div className="an-header-left">
          <div className="an-title">{reportTitle(currentReport)}</div>
          {updatedLabel && <div className="an-sub">{updatedLabel}</div>}
        </div>
        <AnHeaderControls
          report={currentReport}
          filters={filters}
          onChange={handleFiltersChange}
          isLoading={isLoading}
        />
      </div>

      {showLowDataWarn && (
        <div className="an-warn">
          <Icon name="alert-triangle" size={14} />
          Данных за неделю обычно мало — выводы могут быть неточными. Расширьте период.
        </div>
      )}

      <div className="an-body">{renderBody()}</div>
    </div>
  );
}
