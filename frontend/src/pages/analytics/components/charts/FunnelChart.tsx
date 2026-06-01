/**
 * Funnel chart — воронка конверсий по этапам + терминалы.
 * Источник: funnel.py:_build_funnel_chart
 * Форма data: { stages: [{ stage_key, label, color, count, conversion_from_prev_pct }],
 *               terminals: { hired: { n, pct }, rejected: { n, pct } } }
 * Content-only: карточку и empty-state даёт AnChart. CSS-идиом .funnel-viz из эталона.
 */

import { ANALYTICS_PALETTE } from '../../palette';

interface FunnelStage {
  stage_key: string;
  label: string;
  color?: string;
  count: number;
  conversion_from_prev_pct: number | null;
}

interface FunnelData {
  stages: FunnelStage[];
  terminals?: {
    hired: { n: number; pct: number };
    rejected: { n: number; pct: number };
  };
}

interface FunnelChartProps {
  data: FunnelData;
}

export function FunnelChart({ data }: FunnelChartProps) {
  const stages = data.stages;
  const top = stages[0]?.count || 1;

  // Этап с наибольшим падением конверсии (worst) — по данным бека.
  let worstIdx = -1;
  let worstDrop = -1;
  stages.forEach((s, i) => {
    if (i > 0 && s.conversion_from_prev_pct !== null) {
      const drop = 100 - s.conversion_from_prev_pct;
      if (drop > worstDrop) {
        worstDrop = drop;
        worstIdx = i;
      }
    }
  });

  return (
    <div className="funnel-viz">
      {stages.map((s, i) => {
        const widthPct = Math.max(8, (s.count / top) * 100);
        const conv = s.conversion_from_prev_pct;
        const drop = conv !== null ? 100 - conv : 0;
        const isWorst = i === worstIdx;
        return (
          <div key={s.stage_key} className={`an-funnel-row ${isWorst ? 'worst' : ''}`}>
            <div className="funnel-meta">
              <div className="fr-num">{i + 1}</div>
              <div className="fr-text">
                <div className="fr-label">{s.label}</div>
                <div className="fr-sub">
                  <span className="fr-count">{s.count.toLocaleString('ru-RU')}</span>
                  <span className="fr-sep">·</span>
                  {conv === null ? (
                    <span className="fr-conv">100%</span>
                  ) : (
                    <span className={`fr-conv ${conv < 60 ? 'bad' : conv > 85 ? 'good' : ''}`}>
                      {conv.toFixed(0)}% от пред.
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div className="funnel-bar-outer">
              <div
                className="funnel-bar-fill"
                style={{ width: `${widthPct}%`, background: s.color || (isWorst ? ANALYTICS_PALETTE.red : ANALYTICS_PALETTE.blue) }}
              />
            </div>
            {conv !== null && drop > 5 ? <div className="funnel-drop">−{drop.toFixed(0)}%</div> : <div />}
          </div>
        );
      })}

      {data.terminals && (
        <div className="funnel-terminals">
          <div className="funnel-term hired">
            <span className="ft-label">Нанято</span>
            <span className="ft-value">
              {data.terminals.hired.n} <span style={{ fontSize: 12, fontWeight: 500 }}>({data.terminals.hired.pct.toFixed(1)}%)</span>
            </span>
          </div>
          <div className="funnel-term rejected">
            <span className="ft-label">Отказано</span>
            <span className="ft-value">
              {data.terminals.rejected.n} <span style={{ fontSize: 12, fontWeight: 500 }}>({data.terminals.rejected.pct.toFixed(1)}%)</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
