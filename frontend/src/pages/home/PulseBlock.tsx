import { useNavigate } from 'react-router-dom';
import { useHomePulseSummary } from '@/api/hooks/useHomePulseSummary';
import { Skeleton } from '@/components/ui/Skeleton';
import { Icon } from '@/components/ui/Icon';

export function PulseBlock() {
  const { data, isLoading } = useHomePulseSummary();
  const navigate = useNavigate();

  if (isLoading) return <Skeleton height={300} />;
  if (!data) return null;


  return (
    <div className="card-block ad-card">
      <div className="card-block-head">
        <div className="title">
          Адаптация
          <span className="ad-sub-title">· Пульс-Онбординг</span>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/pulse')}>
          Все сотрудники <Icon name="chevR" size={14}/>
        </button>
      </div>

      <div className="ad-stats">
        <div className="ad-stat ad-stat-total">
          <div className="ad-stat-num">{data.onboarding_count}</div>
          <div className="ad-stat-label">на адаптации</div>
          <div className="ad-stat-sub">
            {data.onboarding_delta >= 0 ? '+' : ''}{data.onboarding_delta} в этом месяце
          </div>
        </div>

        <div className="ad-stat ad-stat-risk">
          <div className="ad-stat-label-top">Риск ухода</div>
          <div className="ad-risk-bar">
            <span className="seg seg-red" style={{flex: data.risk_split.high}}/>
            <span className="seg seg-yellow" style={{flex: data.risk_split.mid}}/>
            <span className="seg seg-green" style={{flex: data.risk_split.low}}/>
          </div>
          <div className="ad-risk-legend">
            <span><span className="dot dot-red"/>{data.risk_split.high} высокий</span>
            <span><span className="dot dot-yellow"/>{data.risk_split.mid} средний</span>
            <span><span className="dot dot-green"/>{data.risk_split.low} норма</span>
          </div>
        </div>

        <div className="ad-stat">
          <div className="ad-stat-label-top">Средняя оценка</div>
          <div className="ad-stat-row">
            <span className="ad-stat-num-md">
              {data.satisfaction_avg !== null && data.satisfaction_avg !== undefined ? data.satisfaction_avg.toFixed(1) : '—'}
            </span>
            <span className="ad-stat-unit">/ 5</span>
          </div>
          <div className="ad-stat-sub">
            ответили {data.answered_pct.toFixed(0)}% · {data.silent_pct.toFixed(0)}% молчат
          </div>
        </div>

        <div className="ad-stat">
          <div className="ad-stat-label-top">eNPS <span className="ad-mute">90 дн.</span></div>
          <div className="ad-stat-row">
            <span className="ad-stat-num-md">{data.enps !== null ? data.enps : '—'}</span>
            {data.enps_delta !== null && data.enps_delta !== undefined && (
              <span className="delta up" style={{fontSize:11, marginLeft:6}}>
                ▲ +{Math.abs(data.enps_delta)}
              </span>
            )}
          </div>
          <div className="ad-stat-sub">к прошлому периоду</div>
        </div>
      </div>

      {data.attention_hr.length > 0 && (
        <>
          <div className="ad-divider"/>
          <div className="ad-attention-head">
            <span className="ad-attn-title">Требуют внимания HR</span>
            <span className="count-pill">{data.attention_hr.length}</span>
          </div>
          <div className="ad-attention-list">
            {data.attention_hr.map(item => {
              const riskType = item.risk_score >= 70 ? 'red' :
                               item.risk_score >= 50 ? 'yellow' : 'green';
              const flagType = item.risk_score >= 70 ? 'urgent' : 'warn';
              return (
                <div
                  key={item.employee_id}
                  className="att-row ad-att-row"
                  onClick={() => navigate(`/pulse/${item.employee_id}`)}
                >
                  <div className={`flag-icon ${flagType}`}>
                    <Icon name={flagType === 'urgent' ? 'alert-triangle' : 'clock'} size={16}/>
                  </div>
                  <div className="body">
                    <div className="name">
                      {item.full_name}
                      {item.position && (
                        <span className="ad-role">· {item.position}</span>
                      )}
                    </div>
                    <div className="reason">{item.reason}</div>
                  </div>
                  <div className="ad-att-meta">
                    <span className="ad-day t-mono">день {item.adapt_day}</span>
                    <span className={`ad-risk-pill ${riskType}`}>
                      риск <b className="t-mono">{item.risk_score}</b>
                    </span>
                  </div>
                  <div className="arrow">
                    <Icon name="chevR" size={16}/>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}