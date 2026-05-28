import type { AnalyticsResponse, AnalyticsFilters } from '@/api/aliases';
import { KpiStrip } from '../KpiStrip';
import { ChartRenderer } from '../ChartRenderer';

interface OverviewReportProps {
  data: AnalyticsResponse;
  filters: AnalyticsFilters;
  onFiltersChange: (filters: Partial<AnalyticsFilters>) => void;
  onReportChange: (report: string) => void;
}

export function OverviewReport({ data, onReportChange }: OverviewReportProps) {
  return (
    <div>
      {/* KPI Strip */}
      {data.kpis && data.kpis.length > 0 && (
        <KpiStrip kpis={data.kpis} />
      )}

      {/* Charts */}
      {data.charts?.map((chart, index) => (
        <ChartRenderer
          key={index}
          chart={chart}
          onDataClick={(_data) => {
            // Handle chart clicks - navigate to specific reports
            if (chart.type === 'line') {
              // Dynamic chart click - no specific action
              return;
            }
            if (chart.type === 'stacked') {
              onReportChange('funnel');
            }
            if (chart.type === 'hbar') {
              // Could navigate to specific vacancy detail
            }
          }}
        />
      ))}

      {/* Quick action cards */}
      <div className="analytics-grid-2" style={{ marginTop: '32px' }}>
        <div className="analytics-chart-card">
          <div className="analytics-chart-header">
            <h3 className="analytics-chart-title">Быстрые переходы</h3>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', padding: '8px 0' }}>
            {[
              { key: 'speed', title: 'Скорость найма' },
              { key: 'sources', title: 'Источники' },
              { key: 'rejections', title: 'Отказы' },
              { key: 'turnover', title: 'Текучка' },
            ].map(item => (
              <button
                key={item.key}
                onClick={() => onReportChange(item.key)}
                style={{
                  padding: '12px',
                  background: 'var(--bg-3)',
                  border: '1px solid var(--border-2)',
                  borderRadius: '8px',
                  textAlign: 'left',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--bg-4)';
                  e.currentTarget.style.borderColor = 'var(--border-3)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'var(--bg-3)';
                  e.currentTarget.style.borderColor = 'var(--border-2)';
                }}
              >
                <div style={{ fontSize: '14px', fontWeight: '500', color: 'var(--fg-1)' }}>
                  {item.title}
                </div>
              </button>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}