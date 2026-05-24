// AnalyticsCharts — chart primitives used across analytics reports.
// All charts are static SVG with hover tooltips.

const ANALYTICS_PALETTE = {
  blue:    '#2A8AF0',
  bluesoft:'#7AB4F5',
  green:   '#16A34A',
  red:     '#DC4646',
  yellow:  '#E0A21A',
  violet:  '#7E5CF0',
  gray:    '#5B6573',
  orange:  '#E08A3C',
  teal:    '#3FA3B3',
};

/* ------------------------------------------------------------------
   Tooltip — простой floating tooltip, controlled
------------------------------------------------------------------- */
function ChartTooltip({ x, y, children, visible }) {
  if (!visible) return null;
  return (
    <div className="chart-tip" style={{ left: x, top: y }}>{children}</div>
  );
}

/* ------------------------------------------------------------------
   LineChart — простая линия (или 2 линии) с подписями.
   data: [{ x: string, y: number, y2?: number }]
------------------------------------------------------------------- */
function LineChart({ data, height = 220, lines = [{ key: 'y', label: '', color: ANALYTICS_PALETTE.blue }], yLabel = '', formatY = v => v }) {
  const wrapRef = React.useRef(null);
  const [w, setW] = React.useState(640);
  const [hover, setHover] = React.useState(null);
  React.useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setW(Math.max(320, e.contentRect.width));
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const pad = { l: 44, r: 16, t: 12, b: 28 };
  const W = w, H = height;
  const innerW = W - pad.l - pad.r;
  const innerH = H - pad.t - pad.b;

  const allYs = data.flatMap(d => lines.map(L => d[L.key])).filter(v => typeof v === 'number');
  const yMax = Math.max(...allYs) * 1.18 || 1;
  const yMin = 0;
  const xStep = innerW / Math.max(1, data.length - 1);

  const xPos = i => pad.l + i * xStep;
  const yPos = v => pad.t + innerH - ((v - yMin) / (yMax - yMin)) * innerH;

  // Build paths
  const pathFor = (key) => {
    return data.map((d, i) => {
      const x = xPos(i);
      const y = yPos(d[key]);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
    }).join(' ');
  };

  // Y grid (4 lines)
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map(t => yMin + (yMax - yMin) * t);

  return (
    <div ref={wrapRef} className="chart-wrap">
      <svg width={W} height={H} className="chart-svg">
        {/* grid */}
        {yTicks.map((t, i) => {
          const y = yPos(t);
          return (
            <g key={i}>
              <line x1={pad.l} y1={y} x2={W - pad.r} y2={y}
                stroke="#ECEFF2" strokeWidth="1" strokeDasharray={i === 0 ? '0' : '3 3'}/>
              <text x={pad.l - 8} y={y + 3} textAnchor="end"
                fontSize="11" fill="#9AA3AE" fontFamily="JetBrains Mono">{formatY(Math.round(t))}</text>
            </g>
          );
        })}
        {/* x labels */}
        {data.map((d, i) => (
          <text key={i} x={xPos(i)} y={H - 8} textAnchor="middle"
            fontSize="11" fill="#9AA3AE" fontFamily="Inter">{d.x}</text>
        ))}
        {/* lines */}
        {lines.map((L, li) => (
          <g key={li}>
            {/* fill area for first line */}
            {li === 0 && (
              <path
                d={`${pathFor(L.key)} L ${xPos(data.length - 1)} ${pad.t + innerH} L ${pad.l} ${pad.t + innerH} Z`}
                fill={L.color} opacity="0.08"/>
            )}
            <path d={pathFor(L.key)} fill="none" stroke={L.color}
              strokeWidth="2" strokeDasharray={L.dashed ? '5 4' : ''} strokeLinejoin="round" strokeLinecap="round"/>
            {data.map((d, i) => (
              <circle key={i} cx={xPos(i)} cy={yPos(d[L.key])} r={hover === i ? 5 : 3}
                fill="#fff" stroke={L.color} strokeWidth="2"
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                style={{ cursor: 'pointer' }}/>
            ))}
          </g>
        ))}
      </svg>
      {/* Tooltip overlay */}
      {hover !== null && (
        <div className="chart-tip"
          style={{ left: xPos(hover), top: yPos(data[hover][lines[0].key]) - 12, transform: 'translate(-50%, -100%)' }}>
          <div className="tip-title">{data[hover].x}</div>
          {lines.map(L => (
            <div key={L.key} className="tip-row">
              <span className="dot" style={{ background: L.color }}/>
              <span className="lbl">{L.label || yLabel}</span>
              <span className="val">{formatY(data[hover][L.key])}</span>
            </div>
          ))}
          {data[hover].note && <div className="tip-note">{data[hover].note}</div>}
        </div>
      )}
      {/* Legend */}
      {lines.length > 1 && (
        <div className="chart-legend">
          {lines.map(L => (
            <div key={L.key} className="legend-item">
              <span className="dot" style={{ background: L.color, ...(L.dashed ? { backgroundImage: `repeating-linear-gradient(90deg, ${L.color} 0 4px, transparent 4px 8px)` } : {}) }}/>
              {L.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------
   HBarChart — горизонтальные бары (этапы воронки / причины и т.п.)
   data: [{ label, value, sub?, color?, highlight?, count? }]
------------------------------------------------------------------- */
function HBarChart({ data, formatV = v => v, unit = '', maxLabel = 200, onClick }) {
  const max = Math.max(...data.map(d => d.value)) * 1.05 || 1;
  return (
    <div className="hbar-chart">
      {data.map((d, i) => (
        <div key={i} className={`hbar-row ${d.highlight ? 'highlight' : ''} ${onClick ? 'clickable' : ''}`}
          onClick={onClick ? () => onClick(d) : undefined}>
          <div className="hbar-label" style={{ width: maxLabel }}>{d.label}</div>
          <div className="hbar-track">
            <div className="hbar-fill" style={{
              width: `${(d.value / max) * 100}%`,
              background: d.color || (d.highlight ? '#DC4646' : '#2A8AF0'),
            }}/>
          </div>
          <div className="hbar-val t-num">{formatV(d.value)}{unit}</div>
          {d.sub != null && <div className="hbar-sub">{d.sub}</div>}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------
   FunnelViz — классическая воронка с конверсиями
   stages: [{ label, value, dropped?, color? }]
------------------------------------------------------------------- */
function FunnelViz({ stages, onStageClick }) {
  const top = stages[0].value;
  return (
    <div className="funnel-viz">
      {stages.map((s, i) => {
        const widthPct = Math.max(8, (s.value / top) * 100);
        const convFromPrev = i === 0 ? 100 : (s.value / stages[i - 1].value) * 100;
        const convFromPrevDrop = i > 0 ? 100 - convFromPrev : 0;
        const isWorst = i > 0 && stages.slice(1).reduce((acc, st, idx) => {
          const drop = 100 - (st.value / stages[idx].value) * 100;
          return drop > acc.drop ? { i: idx + 1, drop } : acc;
        }, { i: 0, drop: 0 }).i === i;

        return (
          <div key={i} className={`an-funnel-row ${isWorst ? 'worst' : ''}`}
            onClick={onStageClick ? () => onStageClick(s, i) : undefined}>
            <div className="funnel-meta">
              <div className="fr-num">{i + 1}</div>
              <div className="fr-text">
                <div className="fr-label">{s.label}</div>
                <div className="fr-sub">
                  <span className="fr-count">{s.value.toLocaleString('ru-RU')}</span>
                  <span className="fr-sep">·</span>
                  {i === 0
                    ? <span className="fr-conv">100%</span>
                    : <span className={`fr-conv ${convFromPrev < 60 ? 'bad' : convFromPrev > 85 ? 'good' : ''}`}>
                        {convFromPrev.toFixed(0)}% от пред.
                      </span>}
                </div>
              </div>
            </div>
            <div className="funnel-bar-outer">
              <div className="funnel-bar-fill" style={{
                width: `${widthPct}%`,
                background: s.color || (isWorst ? '#DC4646' : '#2A8AF0'),
              }}/>
            </div>
            {i > 0 && convFromPrevDrop > 5 && (
              <div className="funnel-drop">−{convFromPrevDrop.toFixed(0)}%</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------
   Donut chart — простой donut
   data: [{ label, value, color }]
------------------------------------------------------------------- */
function DonutChart({ data, size = 180, thickness = 28, centerLabel = '', centerValue = '' }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const r = size / 2;
  const innerR = r - thickness;
  const cx = r, cy = r;
  let acc = 0;
  const arcs = data.map(d => {
    const start = acc / total;
    acc += d.value;
    const end = acc / total;
    const a0 = start * Math.PI * 2 - Math.PI / 2;
    const a1 = end * Math.PI * 2 - Math.PI / 2;
    const large = end - start > 0.5 ? 1 : 0;
    const x0 = cx + Math.cos(a0) * r, y0 = cy + Math.sin(a0) * r;
    const x1 = cx + Math.cos(a1) * r, y1 = cy + Math.sin(a1) * r;
    const xi0 = cx + Math.cos(a0) * innerR, yi0 = cy + Math.sin(a0) * innerR;
    const xi1 = cx + Math.cos(a1) * innerR, yi1 = cy + Math.sin(a1) * innerR;
    const path = `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} L ${xi1} ${yi1} A ${innerR} ${innerR} 0 ${large} 0 ${xi0} ${yi0} Z`;
    return { ...d, path, pct: (d.value / total * 100) };
  });

  return (
    <div className="donut-wrap">
      <svg width={size} height={size}>
        {arcs.map((a, i) => (
          <path key={i} d={a.path} fill={a.color}/>
        ))}
        {centerValue && (
          <>
            <text x={cx} y={cy - 4} textAnchor="middle" fontSize="22" fontWeight="600" fill="#0F1620"
              fontFamily="Inter">{centerValue}</text>
            <text x={cx} y={cy + 16} textAnchor="middle" fontSize="11" fill="#9AA3AE"
              fontFamily="Inter">{centerLabel}</text>
          </>
        )}
      </svg>
      <div className="donut-legend">
        {arcs.map((a, i) => (
          <div key={i} className="legend-row">
            <span className="dot" style={{ background: a.color }}/>
            <span className="lbl">{a.label}</span>
            <span className="num t-num">{a.value}</span>
            <span className="pct t-num">{a.pct.toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   StackedBar — единая горизонтальная полоса с сегментами
   data: [{ label, value, color }]
------------------------------------------------------------------- */
function StackedBar({ data, height = 18 }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  return (
    <div className="stacked-bar-wrap">
      <div className="stacked-bar" style={{ height }}>
        {data.map((d, i) => (
          <div key={i} className="sb-seg" title={`${d.label}: ${d.value}`}
            style={{ width: `${(d.value / total) * 100}%`, background: d.color }}/>
        ))}
      </div>
      <div className="stacked-legend">
        {data.map((d, i) => (
          <div key={i} className="sb-legend-item">
            <span className="dot" style={{ background: d.color }}/>
            <span className="lbl">{d.label}</span>
            <span className="num t-num">{d.value}</span>
            <span className="pct t-num">{((d.value / total) * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   CohortMatrix — матрица "месяц найма × % выживших к Nд / 90д / 180д"
------------------------------------------------------------------- */
function CohortMatrix({ rows, cols }) {
  // rows: [{ month, hired, retention: { d30, d90, d180 } }]
  // cols: list of {key, label}
  const colorFor = pct => {
    if (pct == null) return '#F4F6F8';
    // green if good (>80), yellow mid, red if bad (<60)
    if (pct >= 90) return '#16A34A';
    if (pct >= 80) return '#59A861';
    if (pct >= 70) return '#E0A21A';
    if (pct >= 60) return '#E08A3C';
    return '#DC4646';
  };
  return (
    <div className="cohort-table">
      <div className="cohort-row cohort-head">
        <div className="ch-cell ch-month">Месяц найма</div>
        <div className="ch-cell ch-hired">Нанято</div>
        {cols.map(c => <div key={c.key} className="ch-cell">{c.label}</div>)}
      </div>
      {rows.map(r => (
        <div key={r.month} className="cohort-row">
          <div className="ch-cell ch-month">{r.month}</div>
          <div className="ch-cell ch-hired t-num">{r.hired}</div>
          {cols.map(c => {
            const pct = r.retention[c.key];
            return (
              <div key={c.key} className="ch-cell ch-pct">
                {pct == null ? (
                  <span className="ch-empty">—</span>
                ) : (
                  <div className="ch-pill" style={{
                    background: colorFor(pct) + '22',
                    color: colorFor(pct),
                    borderColor: colorFor(pct) + '44',
                  }}>
                    {pct}%
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------
   MultiLineChart — несколько линий (для Источников, Рекрутеров)
   series: [{ key, label, color }]
   data:   [{ x, [seriesKey]: number }]
------------------------------------------------------------------- */
function MultiLineChart({ data, series, height = 240, formatY = v => v }) {
  const wrapRef = React.useRef(null);
  const [w, setW] = React.useState(640);
  const [hover, setHover] = React.useState(null);
  React.useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setW(Math.max(320, e.contentRect.width));
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const pad = { l: 44, r: 16, t: 12, b: 28 };
  const W = w, H = height;
  const innerW = W - pad.l - pad.r;
  const innerH = H - pad.t - pad.b;

  const allYs = data.flatMap(d => series.map(s => d[s.key])).filter(v => typeof v === 'number');
  const yMax = Math.max(...allYs) * 1.15 || 1;
  const xStep = innerW / Math.max(1, data.length - 1);

  const xPos = i => pad.l + i * xStep;
  const yPos = v => pad.t + innerH - (v / yMax) * innerH;

  const pathFor = key => data.map((d, i) =>
    `${i === 0 ? 'M' : 'L'}${xPos(i).toFixed(1)} ${yPos(d[key]).toFixed(1)}`
  ).join(' ');

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map(t => yMax * t);

  return (
    <div ref={wrapRef} className="chart-wrap">
      <svg width={W} height={H} className="chart-svg">
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={pad.l} y1={yPos(t)} x2={W - pad.r} y2={yPos(t)}
              stroke="#ECEFF2" strokeDasharray={i === 0 ? '0' : '3 3'}/>
            <text x={pad.l - 8} y={yPos(t) + 3} textAnchor="end"
              fontSize="11" fill="#9AA3AE" fontFamily="JetBrains Mono">{formatY(Math.round(t))}</text>
          </g>
        ))}
        {data.map((d, i) => (
          <text key={i} x={xPos(i)} y={H - 8} textAnchor="middle"
            fontSize="11" fill="#9AA3AE" fontFamily="Inter">{d.x}</text>
        ))}
        {series.map(s => (
          <g key={s.key}>
            <path d={pathFor(s.key)} fill="none" stroke={s.color}
              strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"/>
            {data.map((d, i) => (
              <circle key={i} cx={xPos(i)} cy={yPos(d[s.key])} r={hover === i ? 4 : 2.5}
                fill="#fff" stroke={s.color} strokeWidth="2"
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                style={{ cursor: 'pointer' }}/>
            ))}
          </g>
        ))}
      </svg>
      {hover !== null && (
        <div className="chart-tip"
          style={{ left: xPos(hover), top: pad.t + 4, transform: 'translate(-50%, 0)' }}>
          <div className="tip-title">{data[hover].x}</div>
          {series.map(s => (
            <div key={s.key} className="tip-row">
              <span className="dot" style={{ background: s.color }}/>
              <span className="lbl">{s.label}</span>
              <span className="val">{formatY(data[hover][s.key])}</span>
            </div>
          ))}
        </div>
      )}
      <div className="chart-legend">
        {series.map(s => (
          <div key={s.key} className="legend-item">
            <span className="dot" style={{ background: s.color }}/>
            {s.label}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   VBarChart — вертикальные бары (распределение увольнений по периодам)
------------------------------------------------------------------- */
function VBarChart({ data, height = 200, formatV = v => v, unit = '' }) {
  const wrapRef = React.useRef(null);
  const [w, setW] = React.useState(640);
  React.useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) setW(Math.max(320, e.contentRect.width));
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const pad = { l: 36, r: 12, t: 12, b: 38 };
  const W = w, H = height;
  const innerW = W - pad.l - pad.r;
  const innerH = H - pad.t - pad.b;
  const max = Math.max(...data.map(d => d.value)) * 1.15 || 1;
  const barWidth = innerW / data.length;

  const yTicks = [0, 0.5, 1].map(t => max * t);

  return (
    <div ref={wrapRef} className="chart-wrap">
      <svg width={W} height={H} className="chart-svg">
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={pad.l} y1={pad.t + innerH - (t / max) * innerH}
              x2={W - pad.r} y2={pad.t + innerH - (t / max) * innerH}
              stroke="#ECEFF2" strokeDasharray={i === 0 ? '0' : '3 3'}/>
            <text x={pad.l - 8} y={pad.t + innerH - (t / max) * innerH + 3} textAnchor="end"
              fontSize="11" fill="#9AA3AE" fontFamily="JetBrains Mono">{formatV(Math.round(t))}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const bx = pad.l + i * barWidth + barWidth * 0.18;
          const bw = barWidth * 0.64;
          const bh = (d.value / max) * innerH;
          const by = pad.t + innerH - bh;
          return (
            <g key={i}>
              <rect x={bx} y={by} width={bw} height={bh} rx="3"
                fill={d.color || '#2A8AF0'}>
                <title>{d.label}: {formatV(d.value)}{unit}</title>
              </rect>
              <text x={bx + bw / 2} y={by - 6} textAnchor="middle"
                fontSize="11" fontWeight="600" fill="#0F1620"
                fontFamily="JetBrains Mono">{formatV(d.value)}{unit}</text>
              <text x={pad.l + i * barWidth + barWidth / 2} y={H - 18}
                textAnchor="middle" fontSize="11" fill="#5B6573"
                fontFamily="Inter">{d.label}</text>
              {d.sub && (
                <text x={pad.l + i * barWidth + barWidth / 2} y={H - 4}
                  textAnchor="middle" fontSize="10" fill="#9AA3AE"
                  fontFamily="Inter">{d.sub}</text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

Object.assign(window, {
  ANALYTICS_PALETTE,
  LineChart, MultiLineChart, HBarChart, VBarChart,
  FunnelViz, DonutChart, StackedBar, CohortMatrix,
});
