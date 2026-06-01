/**
 * Stacked bar — карта активности воронки (overview) и отклики→найм по источникам (sources).
 * Источник: overview.py:_build_stages_chart (форма { stages: [...] }),
 *           sources.py:_build_stacked_sources_chart (форма { sources: [{ source, stages: [...] }] })
 * Этапы несут поле color С БЕКА — используем напрямую.
 * Content-only: карточку и empty-state даёт AnChart. CSS-идиом .stacked-* из эталона.
 */

interface Stage {
  stage_key: string;
  label: string;
  color?: string;
  count: number;
}

interface StagesData {
  stages: Stage[];
}

interface SourcesData {
  sources: Array<{ source: string; stages: Stage[] }>;
}

interface StackedChartProps {
  data: StagesData | SourcesData;
}

const FALLBACK = '#9AA3AE';

/** Единая горизонтальная полоса с сегментами + легенда. */
function SingleStack({ stages }: { stages: Stage[] }) {
  const visible = stages.filter((s) => s.count > 0);
  const total = visible.reduce((s, d) => s + d.count, 0) || 1;
  return (
    <div className="stacked-bar-wrap">
      <div className="stacked-bar" style={{ height: 22 }}>
        {visible.map((s) => (
          <div
            key={s.stage_key}
            className="sb-seg"
            title={`${s.label}: ${s.count}`}
            style={{ width: `${(s.count / total) * 100}%`, background: s.color || FALLBACK }}
          />
        ))}
      </div>
      <div className="stacked-legend">
        {visible.map((s) => (
          <div key={s.stage_key} className="sb-legend-item">
            <span className="dot" style={{ background: s.color || FALLBACK }} />
            <span className="lbl">{s.label}</span>
            <span className="num">{s.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function StackedChart({ data }: StackedChartProps) {
  if ('stages' in data) {
    return <SingleStack stages={data.stages} />;
  }

  // sources variant — строка на источник + общая легенда этапов
  const sources = data.sources;
  const stageMeta = new Map<string, { label: string; color?: string }>();
  sources.forEach((src) =>
    src.stages.forEach((st) => {
      if (!stageMeta.has(st.stage_key)) stageMeta.set(st.stage_key, { label: st.label, color: st.color });
    }),
  );

  return (
    <div className="stacked-bar-wrap">
      <div className="stacked-rows">
        {sources.map((src) => {
          const visible = src.stages.filter((s) => s.count > 0);
          const total = visible.reduce((s, d) => s + d.count, 0) || 1;
          return (
            <div key={src.source} className="stacked-srow">
              <div className="sr-label">{src.source}</div>
              <div className="stacked-bar" style={{ height: 18 }}>
                {visible.map((s) => (
                  <div
                    key={s.stage_key}
                    className="sb-seg"
                    title={`${src.source} · ${s.label}: ${s.count}`}
                    style={{ width: `${(s.count / total) * 100}%`, background: s.color || FALLBACK }}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <div className="stacked-legend">
        {Array.from(stageMeta.entries()).map(([key, meta]) => (
          <div key={key} className="sb-legend-item">
            <span className="dot" style={{ background: meta.color || FALLBACK }} />
            <span className="lbl">{meta.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
