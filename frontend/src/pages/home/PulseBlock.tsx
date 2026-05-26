import { useNavigate } from 'react-router-dom';
import { useHomePulseSummary } from '@/api/hooks/useHomePulseSummary';
import { Skeleton } from '@/components/ui/Skeleton';
import { Badge } from '@/components/ui/Badge';
import { Icon } from '@/components/ui/Icon';

export function PulseBlock() {
  const { data, isLoading } = useHomePulseSummary();
  const navigate = useNavigate();

  if (isLoading) return <Skeleton height={300} />;
  if (!data) return null;

  const total = data.risk_split.high + data.risk_split.mid + data.risk_split.low;
  const pct = (n: number) => total > 0 ? (n / total) * 100 : 0;

  return (
    <section className="block pulse-block">
      <header className="block__head">
        <div className="block__title">
          Адаптация <span className="block__sub">· Пульс-Онбординг</span>
        </div>
        <button className="ghost-btn" onClick={() => navigate('/pulse')}>
          Все сотрудники →
        </button>
      </header>

      <div className="pulse-stats">
        <div className="pulse-stat">
          <div className="pulse-stat__label">На адаптации</div>
          <div className="pulse-stat__value mono">{data.onboarding_count}</div>
          <div className="pulse-stat__cap">
            {data.onboarding_delta >= 0 ? '+' : ''}{data.onboarding_delta} в этом месяце
          </div>
        </div>

        <div className="pulse-stat">
          <div className="pulse-stat__label">Риск ухода</div>
          <div className="risk-bar">
            <span style={{ width: `${pct(data.risk_split.high)}%`, background: 'var(--risk-high)' }} />
            <span style={{ width: `${pct(data.risk_split.mid)}%`, background: 'var(--risk-mid)' }} />
            <span style={{ width: `${pct(data.risk_split.low)}%`, background: 'var(--risk-low)' }} />
          </div>
          <div className="pulse-stat__legend">
            <span>высокий: {data.risk_split.high}</span>
            <span>средний: {data.risk_split.mid}</span>
            <span>низкий: {data.risk_split.low}</span>
          </div>
        </div>

        <div className="pulse-stat">
          <div className="pulse-stat__label">Средняя оценка</div>
          <div className="pulse-stat__value mono">
            {data.satisfaction_avg !== null && data.satisfaction_avg !== undefined ? `${data.satisfaction_avg.toFixed(1)} / 5` : '—'}
          </div>
          <div className="pulse-stat__cap">
            ответили {data.answered_pct.toFixed(0)}% · {data.silent_pct.toFixed(0)}% молчат
          </div>
        </div>

        <div className="pulse-stat">
          <div className="pulse-stat__label">
            eNPS <span className="pulse-stat__hint">90 дн.</span>
          </div>
          <div className="pulse-stat__value mono">{data.enps !== null ? data.enps : '—'}</div>
          {data.enps_delta !== null && data.enps_delta !== undefined && (
            <div className="pulse-stat__cap">
              {data.enps_delta >= 0 ? '+' : ''}{data.enps_delta} к прошлому периоду
            </div>
          )}
        </div>
      </div>

      {data.attention_hr.length > 0 && (
        <>
          <div className="pulse-divider" />
          <div className="hr-att__head">
            <span className="hr-att__label">ТРЕБУЮТ ВНИМАНИЯ HR</span>
            <Badge variant="error">{data.attention_hr.length}</Badge>
          </div>
          <div className="hr-att__list">
            {data.attention_hr.map(item => {
              const riskColor = item.risk_score >= 70 ? 'var(--risk-high)' :
                               item.risk_score >= 50 ? 'var(--risk-mid)' : 'var(--risk-low)';
              return (
                <button
                  key={item.employee_id}
                  className="hr-att-row"
                  onClick={() => navigate(`/pulse/${item.employee_id}`)}
                >
                  <span className="hr-att-row__flag" style={{ color: riskColor }}>
                    <Icon name="flag" size={14} />
                  </span>
                  <div className="hr-att-row__body">
                    <div className="hr-att-row__name">
                      {item.full_name}
                      {item.position && (
                        <span className="hr-att-row__pos mono"> · {item.position}</span>
                      )}
                    </div>
                    <div className="hr-att-row__reason">{item.reason}</div>
                  </div>
                  <span className="mono">день {item.adapt_day}</span>
                  <span className="risk-pill" style={{ background: riskColor }}>
                    риск {item.risk_score}
                  </span>
                  <Icon name="chevron-right" size={14} />
                </button>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}