// Pulse — Обзор + Сотрудники список (главный экран)
const { useState: usePS, useMemo: usePSm, useEffect: usePSe } = React;

function pulseBucket(risk) {
  if (risk >= 61) return 'red';
  if (risk >= 31) return 'yellow';
  return 'green';
}

function PulseEmpCard({ emp, onOpen }) {
  const bucket = pulseBucket(emp.risk);
  return (
    <div className={`emp-card ${bucket}`} onClick={() => onOpen(emp.id)}>
      <div className="top">
        <Avatar name={emp.name} size="sm"/>
        <div className="top-text">
          <div className="name">{emp.name}</div>
          <div className="role">{emp.role} · {emp.dept}</div>
        </div>
        <span className="day-pill">День {emp.day}</span>
      </div>
      {emp.signal && (
        <div className={`signal-badge ${emp.signal.kind === 'warn' ? 'warn' : ''}`}>
          {emp.signal.text}
        </div>
      )}
      <div className="risk-row">
        <span className="risk-num">Risk: <b>{emp.risk}</b></span>
        <span style={{fontSize:11, color:'var(--fg-3)', fontFamily:'var(--font-mono)'}}>
          {emp.lastSurvey ? (
            emp.lastSurvey.answered
              ? `D${emp.lastSurvey.day} ✓`
              : `D${emp.lastSurvey.day} ✗`
          ) : '—'}
        </span>
      </div>
    </div>
  );
}

function PulseHeader({ title, sub, period, onPeriod, segment, onSegment, extraActions, onBack }) {
  return (
    <div className="pulse-header">
      <div className="left">
        {onBack && <div className="pulse-back" onClick={onBack}><Icon name="chevL" size={14}/> К списку</div>}
        <h1>{title}</h1>
        <div className="sub">{sub}</div>
      </div>
      <div className="pulse-header-actions">
        {onPeriod && (
          <select className="dropdown" value={period} onChange={e => onPeriod(e.target.value)}>
            <option value="week">Неделя</option>
            <option value="month">Месяц</option>
            <option value="quarter">Квартал</option>
            <option value="all">Всё время</option>
          </select>
        )}
        {onSegment && (
          <select className="dropdown" value={segment} onChange={e => onSegment(e.target.value)}>
            <option value="all">Все сегменты</option>
            <option value="mass">Массовый</option>
            <option value="office">Офис</option>
          </select>
        )}
        {extraActions}
      </div>
    </div>
  );
}

function PulseChips({ active, onChange, alertCount }) {
  const chips = [
    { id: 'overview',  label: 'Обзор' },
    { id: 'employees', label: 'Сотрудники' },
    { id: 'alerts',    label: 'Алерты', badge: alertCount },
    { id: 'surveys',   label: 'Опросы' },
  ];
  return (
    <div className="set-toptabs">
      {chips.map(c => (
        <button key={c.id}
          className={`set-toptab ${active === c.id ? 'active' : ''}`}
          onClick={() => onChange(c.id)}>
          {c.label}
          {c.badge ? <span className="pulse-tab-badge">{c.badge}</span> : null}
        </button>
      ))}
    </div>
  );
}

function RiskPill({ risk }) {
  const b = pulseBucket(risk);
  return (
    <span className={`risk-pill ${b}`}>
      <span className="dot"/> {risk}
    </span>
  );
}

/* ============================================================
   OVERVIEW
   ============================================================ */
function PulseOverview({ period, onPeriod, segment, onSegment, onOpenEmp, onOpenAlerts }) {
  const [sortBy, setSortBy] = usePS('hireDate'); // hireDate | risk

  const filtered = window.PULSE_EMPLOYEES.filter(e =>
    segment === 'all' || e.segment === segment
  );
  const sortFn = sortBy === 'risk'
    ? (a, b) => b.risk - a.risk
    : (a, b) => b.day - a.day; // newest first by adaptation day asc... use day asc
  // Actually "новые сверху" — недавние, т.е. меньший день. Let's sort by day ascending for "newer".
  const sorted = [...filtered].sort(sortBy === 'risk'
    ? (a, b) => b.risk - a.risk
    : (a, b) => a.day - b.day);

  const reds    = sorted.filter(e => pulseBucket(e.risk) === 'red');
  const yellows = sorted.filter(e => pulseBucket(e.risk) === 'yellow');
  const greens  = sorted.filter(e => pulseBucket(e.risk) === 'green');

  const k = window.PULSE_KPIS;

  // top 3 actionable alerts
  const topAlerts = window.PULSE_ALERTS.filter(a => a.status !== 'closed').slice(0, 4);

  return (
    <div className="pulse-content">
      <div className="pulse-content-inner">
        <PulseHeader
          title="Пульс-Онбординг"
          sub={`Обновлено 12 минут назад · последний сбор данных: 03.05.26 · Сегмент: ${segment === 'all' ? 'все' : segment === 'mass' ? 'массовый' : 'офис'}`}
        />

        {/* KPI strip */}
        <div className="pulse-kpi-grid">
          <div className="kpi" title="Сотрудники в окне 0–90 дней с момента найма">
            <div className="kpi-label">На адаптации сейчас<span className="info">i</span></div>
            <div className="kpi-value-row">
              <span className="kpi-value">{k.active}</span>
              <span className="kpi-unit">человек</span>
            </div>
            <div className="kpi-foot">
              <span className="delta up">▲ {k.activeDelta}</span>
              <span className="kpi-sub">к прошлому месяцу</span>
            </div>
          </div>
          <div className="kpi" title="Risk-score 61–100">
            <div className="kpi-label">🔴 Высокий риск<span className="info">i</span></div>
            <div className="kpi-value-row">
              <span className="kpi-value" style={{color:'var(--ark-red-600)'}}>{k.high}</span>
              <span className="kpi-unit">из {k.active}</span>
            </div>
            <div className="kpi-foot">
              <span className="delta up-bad">▲ {k.highDelta}</span>
              <span className="kpi-sub">к прошлому месяцу</span>
            </div>
          </div>
          <div className="kpi" title="eNPS у сотрудников, прошедших опрос на день 90">
            <div className="kpi-label">eNPS на 90 дней<span className="info">i</span></div>
            <div className="kpi-value-row">
              <span className="kpi-value">+{k.enps}</span>
              <span className="kpi-unit">из 100</span>
            </div>
            <div className="kpi-foot">
              <span className="delta up">▲ {k.enpsDelta}</span>
              <span className="kpi-sub">к прошлому кварталу</span>
            </div>
          </div>
          <div className="kpi" title="% сотрудников, ответивших на отправленный опрос">
            <div className="kpi-label">Completion опросов<span className="info">i</span></div>
            <div className="kpi-value-row">
              <span className="kpi-value">{k.completion}</span>
              <span className="kpi-unit">%</span>
            </div>
            <div className="kpi-foot">
              <span className="delta up">▲ {k.completionDelta} п.п.</span>
              <span className="kpi-sub">к прошлому месяцу</span>
            </div>
          </div>
        </div>

        {/* Traffic light board */}
        <div className="pulse-section-head">
          <h2>
            <Icon name="users" size={16}/>
            Светофор сотрудников на адаптации
            <span className="h-count">{filtered.length}</span>
          </h2>
          <div style={{display:'flex', alignItems:'center', gap:8}}>
            <span style={{fontSize:11, color:'var(--fg-3)', textTransform:'uppercase', letterSpacing:'0.04em', fontWeight:500}}>Сортировка</span>
            <div className="seg-sm">
              <button className={sortBy === 'hireDate' ? 'active' : ''} onClick={() => setSortBy('hireDate')}>По дате найма</button>
              <button className={sortBy === 'risk' ? 'active' : ''} onClick={() => setSortBy('risk')}>По риску</button>
            </div>
          </div>
        </div>

        <div className="tl-board">
          <div className="tl-col red">
            <div className="tl-col-head">
              <span className="light"/> Высокий риск
              <span className="h-count">{reds.length}</span>
            </div>
            {reds.map(e => <PulseEmpCard key={e.id} emp={e} onOpen={onOpenEmp}/>)}
            {reds.length === 0 && <div style={{fontSize:12, color:'var(--fg-3)', textAlign:'center', padding:'12px 0'}}>Никого в красной зоне 🎉</div>}
          </div>
          <div className="tl-col yellow">
            <div className="tl-col-head">
              <span className="light"/> Средний риск
              <span className="h-count">{yellows.length}</span>
            </div>
            {yellows.map(e => <PulseEmpCard key={e.id} emp={e} onOpen={onOpenEmp}/>)}
          </div>
          <div className="tl-col green">
            <div className="tl-col-head">
              <span className="light"/> Норма
              <span className="h-count">{greens.length}</span>
            </div>
            {greens.map(e => <PulseEmpCard key={e.id} emp={e} onOpen={onOpenEmp}/>)}
          </div>
        </div>

        {/* Attention alerts */}
        <div className="pulse-section-head">
          <h2>
            <Icon name="alert" size={16}/>
            Требуют вмешательства
            <span className="h-count">{topAlerts.length}</span>
          </h2>
          <button className="btn btn-ghost btn-sm" onClick={onOpenAlerts}>
            Все алерты <Icon name="chevR" size={14}/>
          </button>
        </div>
        {topAlerts.map(a => (
          <div key={a.id} className="alert-row">
            <div className={`level ${a.level}`}>{a.level === 'crit' ? '🔴' : '🟡'}</div>
            <div className="body">
              <div className="who" onClick={() => onOpenEmp(a.empId)} style={{cursor:'pointer'}}>
                {a.empName}<span className="role-tag">· {a.empRole}</span>
              </div>
              <div className="reason">{a.text}</div>
            </div>
            <div className="when">{a.date}</div>
            <div className="actions">
              <button className="btn btn-secondary btn-sm" onClick={() => onOpenEmp(a.empId)}>Открыть</button>
              <button className="btn btn-ghost btn-sm">Решено</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ============================================================
   EMPLOYEES LIST
   ============================================================ */
function PulseEmployees({ segment, onSegment, onOpenEmp }) {
  const [stage, setStage] = usePS('all');
  const [risk, setRisk]   = usePS('all');
  const [dept, setDept]   = usePS('all');
  const [q, setQ]         = usePS('');
  const [sort, setSort]   = usePS({ key: 'risk', dir: 'desc' });

  const stages = [
    { id: 'all', label: 'Все' },
    { id: 'd0',  label: 'День 0–7' },
    { id: 'd8',  label: 'День 8–30' },
    { id: 'd31', label: 'День 31–60' },
    { id: 'd61', label: 'День 61–90' },
  ];
  const stageMatch = (d) => {
    if (stage === 'all') return true;
    if (stage === 'd0')  return d <= 7;
    if (stage === 'd8')  return d >= 8 && d <= 30;
    if (stage === 'd31') return d >= 31 && d <= 60;
    if (stage === 'd61') return d >= 61 && d <= 90;
    return true;
  };
  const riskMatch = (r) => {
    if (risk === 'all') return true;
    return pulseBucket(r) === risk;
  };
  const segMatch = (s) => segment === 'all' || s === segment;

  const depts = ['all', ...new Set(window.PULSE_EMPLOYEES.map(e => e.dept))];

  const rows = window.PULSE_EMPLOYEES.filter(e =>
    stageMatch(e.day) && riskMatch(e.risk) && segMatch(e.segment) &&
    (dept === 'all' || e.dept === dept) &&
    (!q || e.name.toLowerCase().includes(q.toLowerCase()))
  );
  const sorted = [...rows].sort((a, b) => {
    const m = sort.dir === 'asc' ? 1 : -1;
    if (sort.key === 'risk')  return m * (a.risk - b.risk);
    if (sort.key === 'day')   return m * (a.day - b.day);
    if (sort.key === 'name')  return m * a.name.localeCompare(b.name, 'ru');
    return 0;
  });

  return (
    <div className="pulse-content">
      <div className="pulse-content-inner">
        <PulseHeader
          title="Сотрудники на адаптации"
          sub={`${rows.length} человек${rows.length === 1 ? '' : rows.length < 5 ? 'а' : ''} из ${window.PULSE_EMPLOYEES.length}`}
          extraActions={
            <button className="btn btn-secondary">
              <Icon name="plus" size={14}/> Добавить вручную
            </button>
          }
        />

        <div className="pulse-filters">
          <div className="filter-group">
            <span className="filter-label">Этап</span>
            <select className="dropdown" value={stage} onChange={e => setStage(e.target.value)}>
              {stages.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </div>
          <div className="filter-group">
            <span className="filter-label">Риск</span>
            <div className="seg-sm">
              {[
                { id:'all', label:'Все' },
                { id:'red', label:'🔴 Высокий' },
                { id:'yellow', label:'🟡 Средний' },
                { id:'green', label:'🟢 Норма' },
              ].map(o => (
                <button key={o.id} className={risk === o.id ? 'active' : ''} onClick={() => setRisk(o.id)}>{o.label}</button>
              ))}
            </div>
          </div>
          <div className="filter-group">
            <span className="filter-label">Сегмент</span>
            <div className="seg-sm">
              <button className={segment === 'all' ? 'active' : ''} onClick={() => onSegment('all')}>Все</button>
              <button className={segment === 'mass' ? 'active' : ''} onClick={() => onSegment('mass')}>Массовый</button>
              <button className={segment === 'office' ? 'active' : ''} onClick={() => onSegment('office')}>Офис</button>
            </div>
          </div>
          <div className="filter-group">
            <span className="filter-label">Подразделение</span>
            <select className="dropdown" value={dept} onChange={e => setDept(e.target.value)}>
              {depts.map(d => <option key={d} value={d}>{d === 'all' ? 'Все' : d}</option>)}
            </select>
          </div>
          <div className="filter-spacer"/>
          <div className="pulse-search">
            <Icon name="search" size={13} style={{color:'var(--fg-3)'}}/>
            <input placeholder="Поиск по ФИО…" value={q} onChange={e => setQ(e.target.value)}/>
          </div>
        </div>

        <div className="emp-table">
          <div className="emp-thead">
            <div onClick={() => setSort({key:'name', dir: sort.key==='name' && sort.dir==='asc' ? 'desc':'asc'})} style={{cursor:'pointer'}}>
              Сотрудник {sort.key==='name' ? (sort.dir==='asc'?'▲':'▼') : ''}
            </div>
            <div>Должность</div>
            <div>Подразделение</div>
            <div>Руководитель</div>
            <div onClick={() => setSort({key:'day', dir: sort.key==='day' && sort.dir==='asc' ? 'desc':'asc'})} style={{cursor:'pointer'}}>
              День {sort.key==='day' ? (sort.dir==='asc'?'▲':'▼') : ''}
            </div>
            <div onClick={() => setSort({key:'risk', dir: sort.key==='risk' && sort.dir==='asc' ? 'desc':'asc'})} style={{cursor:'pointer'}}>
              Risk {sort.key==='risk' ? (sort.dir==='asc'?'▲':'▼') : ''}
            </div>
            <div>Последний опрос</div>
          </div>
          {sorted.map(e => (
            <div key={e.id} className="emp-trow" onClick={() => onOpenEmp(e.id)}>
              <div className="cell-emp">
                <Avatar name={e.name} size="sm"/>
                <div className="em-text">
                  <div className="em-name">{e.name}</div>
                  <div className="em-meta">
                    {e.segment === 'mass' ? '🏗 Массовый' : '💼 Офис'} · нанят {e.hireDate}
                  </div>
                </div>
              </div>
              <div>{e.role}</div>
              <div>{e.dept}</div>
              <div style={{color:'var(--fg-2)'}}>{e.mgr}</div>
              <div className="day-num">{e.day}</div>
              <div><RiskPill risk={e.risk}/></div>
              <div>
                <div className="last-survey">
                  <span className="ls-day">День {e.lastSurvey?.day || '—'}</span>
                  {e.lastSurvey ? (
                    <span className={`ls-status ${e.lastSurvey.answered ? 'ok' : 'bad'}`}>
                      {e.lastSurvey.answered ? '✓ ответил' : '✗ нет ответа'}
                    </span>
                  ) : <span className="ls-status">—</span>}
                </div>
              </div>
            </div>
          ))}
          {sorted.length === 0 && (
            <div style={{padding:'40px', textAlign:'center', color:'var(--fg-3)', fontSize:13}}>
              По заданным фильтрам никого не найдено
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

window.PulseOverview = PulseOverview;
window.PulseEmployees = PulseEmployees;
window.PulseHeader = PulseHeader;
window.PulseChips = PulseChips;
window.RiskPill = RiskPill;
window.pulseBucket = pulseBucket;
