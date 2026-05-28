import type { PulseKPI } from '@/api/aliases';

type Props = {
  kpi: PulseKPI | undefined;
  onKpiClick?: (metric: string) => void;
};

export function KpiStrip({ kpi, onKpiClick }: Props) {
  if (!kpi) {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-4)' }}>
        {Array(4).fill(null).map((_, i) => (
          <div
            key={i}
            style={{
              padding: 'var(--space-5)',
              backgroundColor: 'var(--bg-2)',
              border: '1px solid var(--border-1)',
              borderRadius: 'var(--radius-lg)',
              opacity: 0.7,
            }}
          >
            <div style={{ height: '60px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-3)' }}>
              Загрузка...
            </div>
          </div>
        ))}
      </div>
    );
  }

  const kpiCards = [
    {
      id: 'onboarding',
      title: 'На адаптации',
      value: kpi.onboarding_count,
      unit: 'человек',
      delta: null, // Нет дельты в схеме для onboarding_count
      deltaType: null,
      description: 'Сотрудники в первые 90 дней',
    },
    {
      id: 'passed',
      title: 'Прошли испытательный',
      value: kpi.passed_probation,
      unit: 'человек',
      delta: kpi.passed_probation_delta,
      deltaType: kpi.passed_probation_delta >= 0 ? 'good' : 'bad',
      description: 'За выбранный период',
    },
    {
      id: 'left',
      title: 'Ушли в первые 90 дней',
      value: kpi.left_in_90d,
      unit: `${kpi.left_in_90d_pct.toFixed(1)}%`,
      delta: null, // Процент уже показан
      deltaType: 'bad',
      description: 'Текучка в адаптации',
    },
    {
      id: 'enps',
      title: 'eNPS',
      value: kpi.enps ? `+${kpi.enps}` : '—',
      unit: kpi.enps ? 'из 100' : '',
      delta: null,
      deltaType: null,
      description: 'Лояльность новых сотрудников',
    },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-4)' }}>
      {kpiCards.map((card) => (
        <div
          key={card.id}
          onClick={() => onKpiClick?.(card.id)}
          style={{
            padding: 'var(--space-5)',
            backgroundColor: 'var(--bg-2)',
            border: '1px solid var(--border-1)',
            borderRadius: 'var(--radius-lg)',
            cursor: onKpiClick ? 'pointer' : 'default',
            transition: 'all 0.2s ease',
          }}
          onMouseEnter={(e) => {
            if (onKpiClick) {
              e.currentTarget.style.borderColor = 'var(--accent)';
              e.currentTarget.style.transform = 'translateY(-1px)';
            }
          }}
          onMouseLeave={(e) => {
            if (onKpiClick) {
              e.currentTarget.style.borderColor = 'var(--border-1)';
              e.currentTarget.style.transform = 'translateY(0)';
            }
          }}
        >
          <div style={{ fontSize: '13px', color: 'var(--fg-3)', marginBottom: 'var(--space-2)' }}>
            {card.title}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-2)', marginBottom: 'var(--space-1)' }}>
            <span style={{ fontSize: '28px', fontWeight: 700, color: 'var(--fg-1)' }}>
              {card.value}
            </span>
            {card.unit && (
              <span style={{ fontSize: '14px', color: 'var(--fg-3)' }}>
                {card.unit}
              </span>
            )}
          </div>
          {card.delta !== null && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}>
              <span
                style={{
                  fontSize: '11px',
                  color: card.deltaType === 'good' ? 'var(--risk-low)' : 'var(--risk-high)',
                  fontWeight: 600,
                }}
              >
                {card.delta >= 0 ? '▲' : '▼'} {Math.abs(card.delta)}
              </span>
              <span style={{ fontSize: '11px', color: 'var(--fg-3)' }}>к прошлому периоду</span>
            </div>
          )}
          <div style={{ fontSize: '11px', color: 'var(--fg-3)', marginTop: 'var(--space-1)' }}>
            {card.description}
          </div>
        </div>
      ))}
    </div>
  );
}