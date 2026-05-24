// Analytics — shell + первые 3 отчёта (Обзор, Скорость, Воронка)
const { useState: useAnState, useMemo: useAnMemo } = React;

/* ============================================================
   ОБЩИЕ ДАННЫЕ — фейковые, но согласованные между отчётами
   ============================================================ */
const AN_PERIODS = [
  { id: 'week',    label: 'Неделя',  short: 'нед.' },
  { id: 'month',   label: 'Месяц',   short: 'мес.' },
  { id: 'quarter', label: 'Квартал', short: 'кв.' },
  { id: 'year',    label: 'Год',     short: 'г.' },
];
const AN_SCOPES = [
  { id: 'all',       label: 'Вся компания' },
  { id: 'fe',        label: 'Frontend (Senior)' },
  { id: 'logos',     label: 'Заказчик «Логос»' },
  { id: 'me',        label: 'Анна С. (я)' },
];

// Для «Скорость найма» — только вакансии
const AN_SCOPES_VACANCY_ONLY = [
  { id: 'all',         label: 'Все вакансии' },
  { id: 'fe',          label: 'Frontend (Senior)' },
  { id: 'warehouse',   label: 'Кладовщик · смена 2/2' },
  { id: 'sales',       label: 'Менеджер по продажам' },
  { id: 'devops',      label: 'DevOps-инженер' },
  { id: 'hr',          label: 'HR-дженералист' },
  { id: 'qa',          label: 'QA-инженер' },
];

const AN_REPORTS = [
  { id: 'overview',   label: 'Обзор',             icon: 'pin-an',   url: '/analytics' },
  { id: 'speed',      label: 'Скорость найма',    icon: 'clock',    url: '/analytics/speed' },
  { id: 'funnel',     label: 'Воронка конверсий', icon: 'funnel',   url: '/analytics/funnel' },
  { id: 'sources',    label: 'Источники',         icon: 'antenna',  url: '/analytics/sources' },
  { id: 'rejections', label: 'Причины отказов',   icon: 'x',        url: '/analytics/rejections' },
  { id: 'turnover',   label: 'Текучка после найма', icon: 'down', url: '/analytics/turnover' },
  { id: 'recruiters', label: 'Рекрутеры',         icon: 'users',    url: '/analytics/recruiters' },
];

/* ============================================================
   SHELL — Analytics
   ============================================================ */
function Analytics({ reportId = 'overview', period, scope, onPeriodChange, onScopeChange, onReportChange, hasBitrix = true }) {
  // local controls — fall back to defaults
  const _period = period || 'month';
  const _scope = scope || 'all';
  const periodMeta = AN_PERIODS.find(p => p.id === _period);
  const scopesForReport = AN_SCOPES_VACANCY_ONLY;
  const scopeMeta = scopesForReport.find(s => s.id === _scope) || scopesForReport[0];
  const report = AN_REPORTS.find(r => r.id === reportId) || AN_REPORTS[0];

  // dropdown state
  const [periodOpen, setPeriodOpen] = useAnState(false);
  const [scopeOpen, setScopeOpen] = useAnState(false);

  // small data warning if scope is narrow
  const lowData = _scope !== 'all' && _period === 'week';

  let body;
  switch (reportId) {
    case 'overview':   body = <AnOverview period={_period} scope={_scope} hasBitrix={hasBitrix} onReportChange={onReportChange}/>; break;
    case 'speed':      body = <AnSpeed period={_period} scope={_scope}/>; break;
    case 'funnel':     body = <AnFunnel period={_period} scope={_scope}/>; break;
    case 'sources':    body = <AnSources period={_period} scope={_scope}/>; break;
    case 'rejections': body = <AnRejections period={_period} scope={_scope}/>; break;
    case 'turnover':   body = <AnTurnover period={_period} scope={_scope} hasBitrix={hasBitrix}/>; break;
    case 'recruiters': body = <AnRecruiters period={_period} scope={_scope}/>; break;
    default:           body = <AnOverview period={_period} scope={_scope} hasBitrix={hasBitrix} onReportChange={onReportChange}/>;
  }

  return (
    <div className="an-shell">
      <div className="an-header">
        <div className="an-header-left">
          <div className="an-title">{report.label}</div>
          <div className="an-sub">Обновлено 5 мин назад · 14:32</div>
        </div>
        <div className="an-header-controls">
          {/* Period dropdown */}
          <div className="an-dd">
            <button className="an-dd-btn" onClick={() => { setPeriodOpen(o => !o); setScopeOpen(false); }}>
              <span className="an-dd-cap">Период</span>
              <span className="an-dd-val">{periodMeta.label}</span>
              <Icon name="chevD" size={14}/>
            </button>
            {periodOpen && (
              <div className="an-dd-menu" onMouseLeave={() => setPeriodOpen(false)}>
                {AN_PERIODS.map(p => (
                  <div key={p.id}
                    className={`an-dd-opt ${p.id === _period ? 'active' : ''}`}
                    onClick={() => { onPeriodChange?.(p.id); setPeriodOpen(false); }}>
                    {p.label}
                    {p.id === _period && <Icon name="check" size={14}/>}
                  </div>
                ))}
                <div className="an-dd-divider"/>
                <div className="an-dd-opt"><Icon name="calClock" size={14}/> Произвольный диапазон…</div>
              </div>
            )}
          </div>

          {/* Scope dropdown */}
          <div className="an-dd">
            <button className="an-dd-btn" onClick={() => { setScopeOpen(o => !o); setPeriodOpen(false); }}>
              <span className="an-dd-cap">Скоуп</span>
              <span className="an-dd-val">{scopeMeta.label}</span>
              <Icon name="chevD" size={14}/>
            </button>
            {scopeOpen && (
              <div className="an-dd-menu" onMouseLeave={() => setScopeOpen(false)}>
                {scopesForReport.map(s => (
                  <div key={s.id}
                    className={`an-dd-opt ${s.id === _scope ? 'active' : ''}`}
                    onClick={() => { onScopeChange?.(s.id); setScopeOpen(false); }}>
                    {s.label}
                    {s.id === _scope && <Icon name="check" size={14}/>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Compare toggle (cosmetic) */}
          <label className="an-compare">
            <input type="checkbox" defaultChecked/>
            Сравнить с прошлым периодом
          </label>

          <button className="an-csv">
            <Icon name="download" size={14}/>
            CSV
          </button>
        </div>
      </div>

      {lowData && (
        <div className="an-warn">
          <Icon name="alert" size={14}/>
          Данных пока мало — выводы могут быть неточными. Расширьте период или скоуп.
        </div>
      )}

      <div className="an-body">{body}</div>
    </div>
  );
}

/* ============================================================
   AnKpi — карточка KPI для аналитики (та же эстетика, но с onClick)
   ============================================================ */
function AnKpi({ label, value, unit, sub, delta, deltaSub, onClick, accent, big = false, empty = false }) {
  return (
    <div className={`an-kpi ${onClick ? 'clickable' : ''} ${big ? 'big' : ''} ${empty ? 'empty' : ''}`}
      onClick={onClick}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value-row">
        <span className="kpi-value" style={accent ? { color: accent } : null}>{value}</span>
        {unit && <span className="kpi-unit">{unit}</span>}
      </div>
      <div className="kpi-foot">
        {delta ? <span className={`delta ${delta.kind}`}>{delta.text}</span> : <span/>}
        <span className="kpi-sub">{deltaSub || sub}</span>
      </div>
    </div>
  );
}

/* ============================================================
   ОТЧЁТ 1. ОБЗОР
   ============================================================ */
function AnOverview({ period, hasBitrix, onReportChange }) {
  const periodLabelLow = {
    week: 'к прошлой неделе', month: 'к прошлому месяцу',
    quarter: 'к прошлому кварталу', year: 'к прошлому году',
  }[period];

  const data = {
    week:    { time: 28, timeD: -8, conv: 11.8, convD: 0.4, openV: 23, closedV: 4, churn: 6.1, churnD: -0.4 },
    month:   { time: 31, timeD: -12, conv: 12.4, convD: 1.8, openV: 23, closedV: 18, churn: 6.2, churnD: -0.8 },
    quarter: { time: 33, timeD: -6, conv: 11.9, convD: 0.6, openV: 23, closedV: 47, churn: 7.0, churnD: 0.3 },
    year:    { time: 36, timeD: -3, conv: 11.2, convD: -0.4, openV: 23, closedV: 184, churn: 8.4, churnD: -1.1 },
  }[period];

  const bottlenecks = [
    { stage: 'Оффер', days: 8.4, drop: 22 },
    { stage: 'Контакт с менеджером', days: 6.1, drop: 18 },
    { stage: 'Интервью', days: 4.7, drop: 24 },
    { stage: 'Контакт с рекрутером', days: 3.2, drop: 14 },
    { stage: 'Отобран', days: 2.4, drop: 9 },
  ];

  const topSources = [
    { src: '✋ Ручной ввод', conv: 21.7, color: '#7E5CF0' },
    { src: '🤖 Анатолий (TG)', conv: 12.1, color: '#2A8AF0' },
    { src: '📥 Импорт / парсинг', conv: 9.0, color: '#3FA3B3' },
    { src: '🟧 Авито Работа', conv: 6.8, color: '#E08A3C' },
    { src: '🟦 hh.ru', conv: 4.2, color: '#DC4646' },
  ];

  const atRisk = [
    { name: 'Кладовщик · смена 2/2', reason: '12 откликов не обработано >24ч', flag: 'urgent' },
    { name: 'Frontend (Senior)', reason: 'Цикл 41 день при норме 28', flag: 'warn' },
    { name: 'HR-дженералист', reason: 'Дедлайн через 4 дня, 0 офферов', flag: 'deadline' },
  ];

  const turnoverWorst = [
    { v: 'Кладовщик', churn: 58, hired: 12, left: 7 },
    { v: 'Менеджер по продажам', churn: 38, hired: 8, left: 3 },
    { v: 'Оператор склада', churn: 33, hired: 9, left: 3 },
  ];

  return (
    <div className="an-overview">
      {/* KPI band */}
      <div className="an-kpi-band">
        <AnKpi label="Среднее время найма" value={data.time} unit="дней"
          delta={{ kind: data.timeD < 0 ? 'down-good' : 'up-bad', text: `${data.timeD < 0 ? '▼' : '▲'} ${Math.abs(data.timeD)}%` }}
          deltaSub={periodLabelLow}
          onClick={() => onReportChange?.('speed')}/>
        <AnKpi label="Конверсия Отклик → Нанят" value={data.conv} unit="%"
          delta={{ kind: data.convD > 0 ? 'up' : 'down', text: `${data.convD > 0 ? '▲' : '▼'} ${Math.abs(data.convD).toFixed(1)} п.п.` }}
          deltaSub={periodLabelLow}
          onClick={() => onReportChange?.('funnel')}/>
        <AnKpi label="Открытые / закрытые вакансии"
          value={<><span>{data.openV}</span><span className="an-kpi-slash">/</span><span style={{color:'#16A34A'}}>{data.closedV}</span></>}
          sub={`${data.openV} активны · ${data.closedV} закрыты`}/>
        {hasBitrix ? (
          <AnKpi label="Текучка 90 дней" value={data.churn} unit="%"
            delta={{ kind: data.churnD < 0 ? 'down-good' : 'up-bad', text: `${data.churnD < 0 ? '▼' : '▲'} ${Math.abs(data.churnD).toFixed(1)} п.п.` }}
            deltaSub={periodLabelLow}
            onClick={() => onReportChange?.('turnover')}/>
        ) : (
          <AnKpi label="Текучка 90 дней" value="—" empty
            sub="Подключите Битрикс·24 в Настройках"
            onClick={() => onReportChange?.('turnover')}/>
        )}
      </div>

      {/* Mini-blocks */}
      <div className="an-mini-grid">
        <div className="an-mini-card">
          <div className="an-mini-head">
            <div className="title">Топ-5 узких мест</div>
            <button className="an-mini-link" onClick={() => onReportChange?.('speed')}>Подробнее →</button>
          </div>
          <div className="an-mini-body">
            {bottlenecks.map((b, i) => (
              <div key={i} className="an-mini-row">
                <div className="lbl">{b.stage}</div>
                <div className="val t-num">{b.days} дн.</div>
                <div className="bar"><div className="bar-fill" style={{ width: `${(b.days / 10) * 100}%` }}/></div>
              </div>
            ))}
          </div>
        </div>

        <div className="an-mini-card">
          <div className="an-mini-head">
            <div className="title">Топ-5 источников по конверсии</div>
            <button className="an-mini-link" onClick={() => onReportChange?.('sources')}>Подробнее →</button>
          </div>
          <div className="an-mini-body">
            {topSources.map((s, i) => (
              <div key={i} className="an-mini-row">
                <div className="lbl">{s.src}</div>
                <div className="val t-num" style={{ color: s.color }}>{s.conv}%</div>
                <div className="bar"><div className="bar-fill" style={{ width: `${(s.conv / 25) * 100}%`, background: s.color }}/></div>
              </div>
            ))}
          </div>
        </div>

        <div className="an-mini-card">
          <div className="an-mini-head">
            <div className="title">Вакансии под угрозой</div>
            <button className="an-mini-link">Все вакансии →</button>
          </div>
          <div className="an-mini-body">
            {atRisk.map((a, i) => (
              <div key={i} className="an-risk-row">
                <div className={`flag-icon ${a.flag}`}><Icon name={a.flag === 'urgent' ? 'alert' : a.flag === 'deadline' ? 'calClock' : 'clock'} size={14}/></div>
                <div className="body">
                  <div className="name">{a.name}</div>
                  <div className="reason">{a.reason}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="an-mini-card">
          <div className="an-mini-head">
            <div className="title">Текучка по позициям</div>
            <button className="an-mini-link" onClick={() => onReportChange?.('turnover')}>Подробнее →</button>
          </div>
          {hasBitrix ? (
            <div className="an-mini-body">
              {turnoverWorst.map((t, i) => (
                <div key={i} className="an-mini-row">
                  <div className="lbl">{t.v}</div>
                  <div className="val t-num" style={{ color: t.churn > 50 ? '#DC4646' : t.churn > 30 ? '#E0A21A' : '#16A34A' }}>{t.churn}%</div>
                  <div className="hint">{t.left} из {t.hired}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="an-empty-mini">
              <Icon name="alert" size={18}/>
              <span>Подключите Битрикс·24 — будем считать текучку автоматически.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   ОТЧЁТ 2. СКОРОСТЬ НАЙМА
   ============================================================ */
function AnSpeed({ period }) {
  const lineData = {
    week: [
      { x: 'Пн', y: 28, y2: 1.4, note: '4 закрытых' },
      { x: 'Вт', y: 31, y2: 1.6 },
      { x: 'Ср', y: 27, y2: 1.2 },
      { x: 'Чт', y: 33, y2: 2.0 },
      { x: 'Пт', y: 29, y2: 1.8 },
      { x: 'Сб', y: 30, y2: 1.5 },
      { x: 'Вс', y: 28, y2: 1.4 },
    ],
    month: [
      { x: 'Нед.1', y: 36, y2: 2.2 },
      { x: 'Нед.2', y: 34, y2: 2.0 },
      { x: 'Нед.3', y: 32, y2: 1.6 },
      { x: 'Нед.4', y: 31, y2: 1.4, note: '5 закрытых' },
    ],
    quarter: [
      { x: 'Янв', y: 38, y2: 2.4 },
      { x: 'Фев', y: 36, y2: 2.0 },
      { x: 'Мар', y: 33, y2: 1.6 },
    ],
    year: [
      { x: 'Q1', y: 38, y2: 2.4 },
      { x: 'Q2', y: 36, y2: 2.0 },
      { x: 'Q3', y: 34, y2: 1.7 },
      { x: 'Q4', y: 31, y2: 1.4 },
    ],
  }[period];

  const stages = [
    { label: '1. Отклик',                value: 0.4, sub: '142 чел.' },
    { label: '2. Отобран',               value: 2.4, sub: '89 чел.' },
    { label: '3. Контакт с рекрутером',  value: 3.2, sub: '64 чел.' },
    { label: '4. Интервью',              value: 4.7, sub: '34 чел.', highlight: true },
    { label: '5. Контакт с менеджером',  value: 6.1, sub: '18 чел.', highlight: true },
    { label: '6. Оффер',                 value: 8.4, sub: '11 чел.', highlight: true },
    { label: '7. Нанят',                 value: 1.0, sub: '6 чел.' },
  ];

  const longest = [
    { vacancy: 'Кладовщик · смена 2/2', days: 64, success: false, recruiter: 'Анна С.' },
    { vacancy: 'Frontend (Senior)',     days: 58, success: true,  recruiter: 'Анна С.' },
    { vacancy: 'Менеджер по продажам',  days: 51, success: true,  recruiter: 'Иван П.' },
    { vacancy: 'DevOps-инженер',         days: 47, success: true,  recruiter: 'Анна С.' },
    { vacancy: 'HR-дженералист',         days: 43, success: false, recruiter: 'Иван П.' },
  ];

  return (
    <>
      <div className="an-kpi-band band-3">
        <AnKpi label="Среднее время найма" value="31" unit="дней"
          delta={{ kind: 'down-good', text: '▼ 12%' }} deltaSub="к прошлому месяцу"/>
        <AnKpi label="Время до первого контакта" value="3.2" unit="часа"
          delta={{ kind: 'down-good', text: '▼ 18%' }} deltaSub="к прошлому месяцу"/>
        <AnKpi label="Среднее время на «Оффер»" value="8.4" unit="дней"
          delta={{ kind: 'up-bad', text: '▲ 6%' }} deltaSub="к прошлому месяцу"/>
      </div>

      <div className="an-card">
        <div className="an-card-head">
          <div>
            <div className="title">Среднее время найма по периодам</div>
            <div className="sub">Линия — закрытые вакансии. Пунктир — время до первого контакта.</div>
          </div>
        </div>
        <LineChart data={lineData} height={240}
          lines={[
            { key: 'y',  label: 'Время найма (дней)', color: '#2A8AF0' },
            { key: 'y2', label: 'До первого контакта (часов)', color: '#7E5CF0', dashed: true },
          ]}
          formatY={v => v}/>
      </div>

      <div className="an-card">
        <div className="an-card-head">
          <div>
            <div className="title">Среднее время на этапе воронки</div>
            <div className="sub">Красным — этапы-«узкие горлышки» (&gt;4 дней). Кликните, чтобы увидеть кандидатов, которые там зависли.</div>
          </div>
        </div>
        <HBarChart data={stages} unit=" дн." formatV={v => v.toFixed(1)} maxLabel={220}
          onClick={s => console.log('drill', s)}/>
      </div>

      <div className="an-card">
        <div className="an-card-head">
          <div className="title">Топ-5 самых долгих закрытий</div>
        </div>
        <div className="an-table">
          <div className="an-thead">
            <div style={{ flex: 3 }}>Вакансия</div>
            <div style={{ width: 90, textAlign: 'right' }}>Дней</div>
            <div style={{ width: 130 }}>Результат</div>
            <div style={{ flex: 1 }}>Рекрутер</div>
          </div>
          {longest.map((r, i) => (
            <div key={i} className="an-trow">
              <div style={{ flex: 3 }} className="an-cell-link">{r.vacancy}</div>
              <div style={{ width: 90, textAlign: 'right' }} className="t-num">{r.days}</div>
              <div style={{ width: 130 }}>
                {r.success
                  ? <span className="an-pill an-pill-green">Нанят</span>
                  : <span className="an-pill an-pill-red">Без найма</span>}
              </div>
              <div style={{ flex: 1 }}>
                <Avatar name={r.recruiter} size="sm"/>
                <span style={{ marginLeft: 8 }}>{r.recruiter}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

/* ============================================================
   ОТЧЁТ 3. ВОРОНКА КОНВЕРСИЙ
   ============================================================ */
function AnFunnel({ period }) {
  const stages = [
    { label: 'Отклик',               value: 1248 },
    { label: 'Отобран',              value: 487 },
    { label: 'Контакт с рекрутером', value: 312 },
    { label: 'Интервью',             value: 184 },
    { label: 'Контакт с менеджером', value: 96 },
    { label: 'Оффер',                value: 38 },
    { label: 'Нанят',                value: 22 },
  ];

  const deltas = [
    { stage: 'Отклик → Отобран',              cur: 39.0, prev: 36.4, dPp: 2.6 },
    { stage: 'Отобран → Контакт с рекрутером', cur: 64.1, prev: 60.8, dPp: 3.3 },
    { stage: 'Контакт → Интервью',             cur: 59.0, prev: 62.2, dPp: -3.2 },
    { stage: 'Интервью → Контакт с менеджером', cur: 52.2, prev: 48.0, dPp: 4.2 },
    { stage: 'Контакт с менеджером → Оффер',    cur: 39.6, prev: 44.1, dPp: -4.5 },
    { stage: 'Оффер → Нанят',                   cur: 57.9, prev: 61.2, dPp: -3.3 },
  ];

  const byVacancy = [
    { v: 'Frontend (Senior)',     responses: 184, interview: 38, offer: 8, hired: 4, conv: 2.2 },
    { v: 'Кладовщик · смена 2/2', responses: 312, interview: 28, offer: 6, hired: 3, conv: 1.0 },
    { v: 'Менеджер по продажам',  responses: 248, interview: 42, offer: 10, hired: 5, conv: 2.0 },
    { v: 'DevOps-инженер',         responses: 96,  interview: 18, offer: 4, hired: 2, conv: 2.1 },
    { v: 'HR-дженералист',         responses: 142, interview: 22, offer: 5, hired: 2, conv: 1.4 },
    { v: 'QA-инженер',             responses: 88,  interview: 16, offer: 4, hired: 3, conv: 3.4 },
  ];

  return (
    <>
      <div className="an-kpi-band band-3">
        <AnKpi label="Конверсия Отклик → Нанят" value="1.8" unit="%"
          delta={{ kind: 'up', text: '▲ 0.3 п.п.' }} deltaSub="к прошлому периоду"/>
        <AnKpi label="Конверсия в Интервью" value="14.7" unit="%"
          delta={{ kind: 'up', text: '▲ 1.2 п.п.' }} deltaSub="% от всех откликов"/>
        <AnKpi label="Оффер → Нанят" value="57.9" unit="%"
          delta={{ kind: 'down', text: '▼ 3.3 п.п.' }} deltaSub="принятых офферов"/>
      </div>

      <div className="an-row-2">
        <div className="an-card">
          <div className="an-card-head">
            <div>
              <div className="title">Воронка по этапам</div>
              <div className="sub">Красным — этап с самым большим падением. Кликните по ступени.</div>
            </div>
          </div>
          <FunnelViz stages={stages} onStageClick={(s, i) => console.log(s, i)}/>
        </div>
        <div className="an-card">
          <div className="an-card-head">
            <div className="title">Сравнение с прошлым периодом</div>
          </div>
          <div className="an-deltas">
            {deltas.map((d, i) => (
              <div key={i} className="an-delta-row">
                <div className="lbl">{d.stage}</div>
                <div className="cur t-num">{d.cur}%</div>
                <span className={`delta ${d.dPp > 0 ? 'up' : 'down'}`}>
                  {d.dPp > 0 ? '▲' : '▼'} {Math.abs(d.dPp).toFixed(1)} п.п.
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="an-card">
        <div className="an-card-head">
          <div className="title">Воронки по вакансиям</div>
        </div>
        <div className="an-table">
          <div className="an-thead">
            <div style={{ flex: 2 }}>Вакансия</div>
            <div style={{ width: 90, textAlign: 'right' }}>Откликов</div>
            <div style={{ width: 110, textAlign: 'right' }}>Интервью</div>
            <div style={{ width: 90, textAlign: 'right' }}>Офферов</div>
            <div style={{ width: 90, textAlign: 'right' }}>Нанято</div>
            <div style={{ width: 110, textAlign: 'right' }}>Конверсия</div>
          </div>
          {byVacancy.map((r, i) => (
            <div key={i} className="an-trow">
              <div style={{ flex: 2 }} className="an-cell-link">{r.v}</div>
              <div style={{ width: 90, textAlign: 'right' }} className="t-num">{r.responses}</div>
              <div style={{ width: 110, textAlign: 'right' }} className="t-num">
                {r.interview}
                <span className="an-mu"> ({((r.interview / r.responses) * 100).toFixed(0)}%)</span>
              </div>
              <div style={{ width: 90, textAlign: 'right' }} className="t-num">{r.offer}</div>
              <div style={{ width: 90, textAlign: 'right' }} className="t-num">{r.hired}</div>
              <div style={{ width: 110, textAlign: 'right' }}>
                <span className={`an-pill ${r.conv > 2.5 ? 'an-pill-green' : r.conv < 1.5 ? 'an-pill-red' : 'an-pill-gray'}`}>
                  {r.conv}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

window.Analytics = Analytics;
window.AN_PERIODS = AN_PERIODS;
window.AN_SCOPES = AN_SCOPES;
window.AN_REPORTS = AN_REPORTS;
window.AnKpi = AnKpi;
