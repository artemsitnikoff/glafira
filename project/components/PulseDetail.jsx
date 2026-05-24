// PulseDetail — карточка сотрудника, алерты, опросы
const { useState: usePD } = React;

function AdaptBar({ day }) {
  const total = 90;
  const pct = Math.min(100, (day / total) * 100);
  const ticks = [
    { d: 0,  label: 'Найм' },
    { d: 7,  label: 'D7' },
    { d: 30, label: 'D30' },
    { d: 90, label: 'D90' },
  ];
  return (
    <div className="adapt-bar">
      <div className="track"/>
      <div className="fill" style={{width: `${pct}%`}}/>
      {ticks.map(t => {
        const left = (t.d / total) * 100;
        const done = day > t.d;
        const now  = Math.abs(day - t.d) < 4;
        return (
          <React.Fragment key={t.d}>
            <div className={`tick ${done ? 'done' : ''} ${now ? 'now' : ''}`} style={{left: `${left}%`}}/>
            <div className="tick-label" style={{left: `${left}%`}}>{t.label}</div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

function PulseEmployeeCard({ empId, onBack }) {
  const e = window.PULSE_EMPLOYEES.find(x => x.id === empId);
  if (!e) return <div style={{padding:40}}>Сотрудник не найден</div>;
  const bucket = window.pulseBucket(e.risk);

  // Use rich data if available, otherwise basic
  const breakdown = e.breakdown || [
    { kind: 'green', text: 'Нет критических сигналов', pts: 0 },
    { kind: 'green', text: 'Опросы заполняются', pts: 0 },
  ];
  const surveys = e.surveys || [];
  const quotes = e.quotes || [];
  const alerts = e.alerts || [];
  const hrLog = e.hrLog || [];
  const total = breakdown.reduce((s, r) => s + r.pts, 0);

  return (
    <div className="pulse-content">
      <div className="pulse-content-inner">
        <div style={{marginBottom:12}}>
          <div className="pulse-back" onClick={onBack}><Icon name="chevL" size={14}/> К списку сотрудников</div>
        </div>

        {/* Head */}
        <div className="ec-head">
          <div className="ec-head-left">
            <div style={{display:'flex', alignItems:'center', gap:14}}>
              <Avatar name={e.name} size="lg"/>
              <div>
                <h1 className="ec-name">{e.name}</h1>
                <div className="ec-meta">
                  {e.role} <span className="sep">·</span> {e.dept} <span className="sep">·</span>
                  Руководитель: {e.mgr} <span className="sep">·</span>
                  {e.segment === 'mass' ? '🏗 Массовый' : '💼 Офис'}
                </div>
              </div>
            </div>
            <div className="ec-day-line">
              <span className="ec-day-num">День {e.day} из 90</span>
              <span style={{color:'var(--fg-3)'}}>·</span>
              <span>Нанят: {e.hireDate}</span>
            </div>
            <div style={{marginTop:8}}>
              <AdaptBar day={e.day}/>
            </div>
            <div className="ec-actions">
              <button className="btn btn-primary"><Icon name="message" size={14}/> Связаться</button>
              <button className="btn btn-secondary"><Icon name="calClock" size={14}/> Запланировать 1-on-1</button>
              <button className="btn btn-ghost">Пометить как уволенного</button>
            </div>
          </div>
          <div className="ec-head-right">
            <div className={`ec-risk-big ${bucket}`}>
              <div className="num">{e.risk}</div>
              <div className="lbl">Risk-score</div>
            </div>
            <div style={{fontSize:11, color:'var(--fg-3)', fontFamily:'var(--font-mono)'}}>
              {bucket === 'red' ? 'высокий' : bucket === 'yellow' ? 'средний' : 'норма'} (61–100)
            </div>
          </div>
        </div>

        <div className="ec-grid">
          <div>
            {/* Breakdown */}
            <div className="ec-block">
              <h3>
                Risk-score breakdown
                <span className="helper">— почему сотрудник попал в эту зону</span>
              </h3>
              {breakdown.map((r, i) => (
                <div key={i} className="rb-row">
                  <div className={`rb-icon ${r.kind}`}>{r.kind === 'green' ? '✓' : '!'}</div>
                  <div>{r.text}</div>
                  <div className={`rb-pts ${r.pts === 0 ? 'zero' : 'add'}`}>
                    {r.pts === 0 ? '0' : `+${r.pts}`}
                  </div>
                </div>
              ))}
              <div className="rb-total">
                <div>Итого: сигналы + базовый риск ({e.base || 3})</div>
                <div className="num" style={{color: bucket === 'red' ? 'var(--ark-red-600)' : bucket === 'yellow' ? 'var(--ark-yellow-600)' : 'var(--ark-green-600)'}}>
                  {total} + {e.base || 3} = {e.risk}
                </div>
              </div>
            </div>

            {/* Surveys history */}
            <div className="ec-block">
              <h3>История опросов</h3>
              <table className="surv-tbl">
                <thead>
                  <tr>
                    <th>Опрос</th>
                    <th>Отправлен</th>
                    <th>Ответ</th>
                    <th>Время</th>
                    <th>Сводка</th>
                  </tr>
                </thead>
                <tbody>
                  {surveys.length === 0 ? (
                    <tr><td colSpan={5} style={{color:'var(--fg-3)', textAlign:'center'}}>Опросы ещё не отправлялись</td></tr>
                  ) : surveys.map((s, i) => (
                    <tr key={i}>
                      <td><b>День {s.day}</b></td>
                      <td className="t-mono" style={{color:'var(--fg-2)'}}>{s.sentDate || '—'}</td>
                      <td className="t-mono" style={{color:'var(--fg-2)'}}>{s.answeredDate || (s.scheduled ? <span className="tag-pending">запл. {s.scheduled}</span> : '—')}</td>
                      <td className="t-mono">{s.responseTime || '—'}</td>
                      <td>
                        {s.mood && <span style={{fontSize:16, marginRight:6}}>{s.mood}</span>}
                        {s.rate ? <b className="t-mono">{s.rate}/5</b> : ''}
                        {s.summary ? ` — ${s.summary}` : ''}
                        {s.critical && <span className="tag-crit">CRITICAL</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Open quotes */}
            <div className="ec-block">
              <h3>Открытые ответы<span className="helper">— автотеги по темам</span></h3>
              {quotes.length === 0 ? (
                <div style={{color:'var(--fg-3)', fontSize:13}}>Сотрудник ещё не оставлял открытых комментариев.</div>
              ) : quotes.map((q, i) => (
                <div key={i} className={`quote-card ${q.crit ? 'crit' : q.warn ? 'warn' : ''}`}>
                  «{q.text}»
                  <div className="qmeta">
                    {q.tags.map(t => <span key={t} className="qtag">{t}</span>)}
                    <span style={{marginLeft:'auto'}}>{q.date}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            {/* Alerts */}
            <div className="ec-block">
              <h3>Алерты по сотруднику<span className="helper">— {alerts.length}</span></h3>
              {alerts.length === 0 ? (
                <div style={{color:'var(--fg-3)', fontSize:13}}>Нет активных алертов.</div>
              ) : alerts.map((a, i) => (
                <div key={i} className="alert-row" style={{marginTop: i ? 8 : 0}}>
                  <div className={`level ${a.type}`}>{a.type === 'crit' ? '🔴' : '🟡'}</div>
                  <div className="body">
                    <div style={{fontSize:13, fontWeight:500}}>{a.text}</div>
                    <div style={{fontSize:11, color:'var(--fg-3)', fontFamily:'var(--font-mono)', marginTop:2}}>
                      {a.date}
                      {a.status === 'work' && <span style={{color:'var(--ark-yellow-600)'}}> · в работе ({a.by})</span>}
                      {a.status === 'open' && <span style={{color:'var(--ark-red-600)'}}> · открыт</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* HR log */}
            <div className="ec-block">
              <h3>Действия HR<span className="helper">— журнал</span></h3>
              {hrLog.length === 0 ? (
                <div style={{color:'var(--fg-3)', fontSize:13}}>Действий ещё не зарегистрировано.</div>
              ) : (
                <div className="hr-log">
                  {hrLog.map((l, i) => (
                    <div key={i} className="hr-log-row">
                      <div className="dot"/>
                      <div className="body">
                        <div>{l.text}</div>
                        <div className="meta">{l.date} · {l.author} · #{l.tag}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="hr-log-add">
                <textarea placeholder="Записать действие или заметку…"/>
              </div>
              <div style={{display:'flex', gap:6, marginTop:8}}>
                <button className="btn btn-primary btn-sm">Сохранить</button>
                <select className="dropdown">
                  <option>Тег: 1-on-1</option>
                  <option>эскалация</option>
                  <option>звонок</option>
                  <option>прочее</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   ALERTS LIST
   ============================================================ */
function PulseAlerts({ onOpenEmp }) {
  const [level, setLevel]   = usePD('all');
  const [status, setStatus] = usePD('active');
  const [openId, setOpenId] = usePD(null);

  const filtered = window.PULSE_ALERTS.filter(a => {
    if (level !== 'all' && a.level !== level) return false;
    if (status === 'active' && a.status === 'closed') return false;
    if (status === 'work' && a.status !== 'work') return false;
    return true;
  });
  const open = openId ? window.PULSE_ALERTS.find(a => a.id === openId) : null;

  if (open) {
    return (
      <div className="pulse-content">
        <div className="pulse-content-inner">
          <div style={{marginBottom:12}}>
            <div className="pulse-back" onClick={() => setOpenId(null)}><Icon name="chevL" size={14}/> К списку алертов</div>
          </div>
          <div className="alert-detail">
            <div>
              <div style={{display:'flex', alignItems:'center', gap:10, marginBottom:4}}>
                <span className={`lvl-pill ${open.level}`}>{open.level === 'crit' ? '🔴' : '🟡'}</span>
                <span style={{fontSize:11, fontFamily:'var(--font-mono)', color:'var(--fg-3)', textTransform:'uppercase', letterSpacing:'0.06em', fontWeight:600}}>
                  {open.level === 'crit' ? 'CRITICAL · SLA 4 ч' : 'MEDIUM · SLA 48 ч'}
                </span>
                <span className={`sla-tag ${open.sla.state}`} style={{marginLeft:'auto'}}>{open.sla.text}</span>
              </div>
              <h2 style={{margin:'6px 0 4px', fontSize:20, letterSpacing:'-0.015em'}}>{open.text}</h2>
              <div style={{fontSize:13, color:'var(--fg-2)'}}>
                <span style={{cursor:'pointer', color:'var(--accent)'}} onClick={() => onOpenEmp(open.empId)}>{open.empName}</span> · {open.empRole} · {open.date}
              </div>
              {open.quote && (
                <div className="ad-quote">«{open.quote.replace(/^«|»$/g, '')}»</div>
              )}
              <div style={{display:'flex', gap:8, marginTop:14}}>
                <button className="btn btn-primary">Взять в работу</button>
                <button className="btn btn-success">Закрыть с комментарием</button>
                <button className="btn btn-secondary" onClick={() => onOpenEmp(open.empId)}>
                  Открыть карточку сотрудника
                </button>
              </div>
            </div>
            <div className="playbook">
              <h4>📖 Playbook действий</h4>
              <ol>
                {(open.playbook || ['Свяжитесь с сотрудником.', 'Зафиксируйте обстоятельства.', 'Закройте алерт.']).map((p, i) => <li key={i}>{p}</li>)}
              </ol>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const active = window.PULSE_ALERTS.filter(a => a.status !== 'closed').length;

  return (
    <div className="pulse-content">
      <div className="pulse-content-inner">
        <PulseHeader title="Алерты" sub={`${active} активных · 14 закрытых за месяц`}/>

        <div className="pulse-filters">
          <div className="filter-group">
            <span className="filter-label">Уровень</span>
            <div className="seg-sm">
              <button className={level==='all' ? 'active' : ''} onClick={() => setLevel('all')}>Все</button>
              <button className={level==='crit' ? 'active' : ''} onClick={() => setLevel('crit')}>🔴 CRITICAL</button>
              <button className={level==='med' ? 'active' : ''} onClick={() => setLevel('med')}>🟡 MEDIUM</button>
            </div>
          </div>
          <div className="filter-group">
            <span className="filter-label">Статус</span>
            <div className="seg-sm">
              <button className={status==='active' ? 'active' : ''} onClick={() => setStatus('active')}>Активные</button>
              <button className={status==='work' ? 'active' : ''} onClick={() => setStatus('work')}>В работе</button>
              <button className={status==='all' ? 'active' : ''} onClick={() => setStatus('all')}>Все</button>
            </div>
          </div>
        </div>

        <div className="alert-tbl">
          <div className="alert-thead">
            <div>Уровень</div>
            <div>Сотрудник</div>
            <div>Что произошло</div>
            <div>Дата</div>
            <div>SLA</div>
            <div>Статус</div>
            <div>Действия</div>
          </div>
          {filtered.map(a => (
            <div key={a.id} className="alert-trow">
              <div><span className={`lvl-pill ${a.level}`}>{a.level === 'crit' ? '🔴' : '🟡'}</span></div>
              <div>
                <div style={{display:'flex', alignItems:'center', gap:8}}>
                  <Avatar name={a.empName} size="sm"/>
                  <div style={{minWidth:0}}>
                    <div style={{fontSize:13, fontWeight:600, cursor:'pointer'}} onClick={() => onOpenEmp(a.empId)}>{a.empName}</div>
                    <div style={{fontSize:11, color:'var(--fg-3)'}}>{a.empRole}</div>
                  </div>
                </div>
              </div>
              <div style={{fontSize:13}}>{a.text}</div>
              <div className="t-mono" style={{fontSize:12, color:'var(--fg-2)'}}>{a.date}</div>
              <div><span className={`sla-tag ${a.sla.state}`}>{a.sla.text}</span></div>
              <div>
                <span className={`status-tag ${a.status}`}>
                  <span className="dot"/>
                  {a.status === 'open' ? 'Открыт' : a.status === 'work' ? `В работе · ${a.by}` : 'Закрыт'}
                </span>
              </div>
              <div style={{display:'flex', gap:6}}>
                <button className="btn btn-secondary btn-sm" onClick={() => setOpenId(a.id)}>Открыть</button>
                {a.status === 'open' && <button className="btn btn-primary btn-sm">Взять</button>}
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{padding:40, textAlign:'center', color:'var(--fg-3)', fontSize:13}}>
              Нет алертов по выбранным фильтрам 🎉
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   SURVEYS CONFIG
   ============================================================ */

function ScalePreview({ scale, options }) {
  if (scale === 'emoji5') return <span className="q-scale">😡 😞 😐 🙂 😄</span>;
  if (scale === 'num5')   return <span className="q-scale">1 · 2 · 3 · 4 · 5</span>;
  if (scale === 'binary') return <span className="q-scale">Да / Нет</span>;
  if (scale === 'binary4')return <span className="q-scale">{(options || []).join(' / ')}</span>;
  if (scale === 'enps')   return <span className="q-scale">0–10 · eNPS</span>;
  if (scale === 'text')   return <span className="q-scale">📝 open-text</span>;
  return null;
}

function SurveyQuestion({ q, idx, segment, onSegment }) {
  if (q.segmented) {
    const isMass = segment === 'mass';
    return (
      <div className={`q-row ${q.enabled ? '' : 'disabled'}`}>
        <div className="q-num">{idx}</div>
        <div>
          <div className="q-text">
            <span style={{fontSize:10, fontWeight:700, color:'var(--accent)', letterSpacing:'0.06em', textTransform:'uppercase', marginRight:6}}>сегмент-специфичный</span>
            {isMass ? q.massText : q.officeText}
          </div>
          <div className="q-goal">
            <span className="info-dot">i</span>
            <span>Цель: {isMass ? q.massGoal : q.officeGoal}</span>
          </div>
          <div className="seg-switch">
            <button className={isMass ? 'active' : ''} onClick={() => onSegment('mass')}>🏗 Массовый</button>
            <button className={!isMass ? 'active' : ''} onClick={() => onSegment('office')}>💼 Офис</button>
          </div>
          {!isMass && (
            <div className="seg-question">
              <div className="lbl">Альтернатива для массового</div>
              «{q.massText}»
            </div>
          )}
          {isMass && (
            <div className="seg-question">
              <div className="lbl">Альтернатива для офиса</div>
              «{q.officeText}»
            </div>
          )}
        </div>
        <ScalePreview scale={isMass ? q.massScale : q.officeScale}/>
        <input type="checkbox" className="tg-switch" defaultChecked={q.enabled}/>
      </div>
    );
  }
  return (
    <div className={`q-row ${q.enabled ? '' : 'disabled'}`}>
      <div className="q-num">{idx}</div>
      <div>
        <div className="q-text">
          {q.optional && <span style={{fontSize:10, fontWeight:700, color:'var(--fg-3)', letterSpacing:'0.06em', textTransform:'uppercase', marginRight:6}}>опционально</span>}
          {q.text}
        </div>
        <div className="q-goal">
          <span className="info-dot">i</span>
          <span>Цель: {q.goal}</span>
        </div>
      </div>
      <ScalePreview scale={q.scale} options={q.options}/>
      <input type="checkbox" className="tg-switch" defaultChecked={q.enabled}/>
    </div>
  );
}

function SurveyCard({ s }) {
  const [open, setOpen] = usePD(s.day === 7);
  const [seg, setSeg] = usePD('mass');
  return (
    <div className="survey-card">
      <div className={`survey-head ${open ? 'open' : ''}`} onClick={() => setOpen(!open)}>
        <div className="badge-day">
          <div className="num">{s.day}</div>
          <div className="lbl">день</div>
        </div>
        <div>
          <div className="stitle">📋 «{s.name}»</div>
          <div className="smeta">
            {s.questions.length} вопросов · {s.duration} · отправляется во вторник 10:00 локального ·
            <span className="ok"> {s.responseRate}% completion</span>
          </div>
        </div>
        <div style={{display:'flex', alignItems:'center', gap:12}}>
          <input type="checkbox" className="tg-switch" defaultChecked={s.enabled} onClick={e => e.stopPropagation()}/>
          <Icon name="chevD" size={18} className="schev"/>
        </div>
      </div>
      {open && (
        <div className="survey-body">
          {s.questions.map((q, i) => (
            <SurveyQuestion key={q.id} q={q} idx={i + 1} segment={seg} onSegment={setSeg}/>
          ))}
          <button className="q-add-btn" onClick={e => e.stopPropagation()}>
            <Icon name="plus" size={14}/> Добавить вопрос
          </button>
        </div>
      )}
    </div>
  );
}

function PulseSurveys() {
  return (
    <div className="pulse-content">
      <div className="pulse-content-inner">
        <PulseHeader
          title="Опросы"
          sub="Три точки замера: день 7 · 30 · 90. Вопросы зашиты системой — можно включать/выключать и переключать сегмент."
        />

        {window.PULSE_SURVEYS.map(s => <SurveyCard key={s.id} s={s}/>)}

        {/* Schedule + trigger words */}
        <div className="cfg-grid" style={{marginTop:14}}>
          <div className="cfg-block">
            <h3>⏰ Время и расписание</h3>
            <div className="cfg-row">
              <span className="lbl">День недели</span>
              <span className="val"><span className="em">Вторник</span> · пик response rate</span>
            </div>
            <div className="cfg-row">
              <span className="lbl">Время отправки</span>
              <span className="val"><span className="em">10:00</span> локального для сотрудника</span>
            </div>
            <div className="cfg-row">
              <span className="lbl">Reminder через 24 часа, если не ответил</span>
              <input type="checkbox" className="tg-switch" defaultChecked/>
            </div>
            <div className="cfg-row">
              <span className="lbl">Второй reminder через 48 часов</span>
              <input type="checkbox" className="tg-switch"/>
            </div>
            <div className="cfg-row">
              <span className="lbl">Тон бота</span>
              <div className="seg-sm">
                <button className="active">Авто по сегменту</button>
                <button>«Ты»</button>
                <button>«Вы»</button>
              </div>
            </div>
          </div>

          <div className="cfg-block">
            <h3>🚨 Триггер-слова для CRITICAL-алертов</h3>
            <div style={{fontSize:12, color:'var(--fg-3)', marginBottom:6}}>
              При появлении этих слов в open-text создаётся CRITICAL-алерт. Поиск регистронезависимый, по нормализованной форме.
            </div>
            <div className="trigger-words">
              {window.PULSE_TRIGGER_WORDS.map(w => (
                <span key={w} className="trig-chip">{w}<span className="x">×</span></span>
              ))}
              <button className="trig-add"><Icon name="plus" size={11}/> Добавить</button>
            </div>
          </div>
        </div>

        {/* Risk weights + thresholds */}
        <div className="cfg-grid" style={{marginTop:14}}>
          <div className="cfg-block">
            <h3>🤖 Промпт risk-score для Claude<span style={{fontWeight:400, fontSize:12, color:'var(--fg-3)', marginLeft:8}}>системный промпт оценки</span></h3>
            <div style={{fontSize:12, color:'var(--fg-3)', marginBottom:8}}>
              Claude читает все ответы сотрудника за период адаптации и возвращает risk-score 0–100 + список конкретных сигналов с весами. Промпт можно править — изменения применятся со следующего расчёта.
            </div>
            <textarea className="ai-prompt" defaultValue={`Ты — HR-аналитик в найме линейного и офисного персонала. На входе получишь профиль сотрудника (день адаптации, сегмент: массовый/офис, руководитель) и все ответы из пульс-опросов день 7 / 30 / 90, плюс открытые комментарии и метаданные (пропустил ли опрос, время ответа).

Верни JSON: { "risk": 0..100, "bucket": "green|yellow|red", "signals": [{ "text": "...", "severity": "high|med|low", "weight": N }], "summary": "1–2 предложения для HR" }.

Логика:
— зарплата обещана непонятно или не вовремя → +30, severity=high
— manager_rating ≤ 2 (плохие отношения с руководителем) → +25, severity=high
— overall_satisfaction ≤ 2 → +20, severity=med
— пропустил ≥ 2 опросов подряд без причины → +15, severity=med
— eNPS ≤ 6 → +10, severity=low
— триггер-слова в open-text («увольняюсь», «достали», «обманули» и т.п.) → severity=high, создать CRITICAL-алерт
— базовый риск 3 пункта по умолчанию

Если данных мало (день < 7 или нет ответов) — bucket=green, risk=base, signals=[]. Не выдумывай сигналы. Цитируй сотрудника дословно в signals[].text, когда есть open-text.`}/>
            <div style={{display:'flex', gap:8, marginTop:10}}>
              <button className="btn btn-primary btn-sm">Сохранить промпт</button>
              <button className="btn btn-secondary btn-sm">Сбросить к дефолту</button>
              <span style={{marginLeft:'auto', fontSize:11, color:'var(--fg-3)', fontFamily:'var(--font-mono)', alignSelf:'center'}}>claude-sonnet-4.5 · 0.4k tokens</span>
            </div>
          </div>
          <div className="cfg-block">
            <h3>🎨 Пороги цветов</h3>
            <div style={{fontSize:12, color:'var(--fg-3)', marginBottom:8}}>Можно подвинуть, чтобы калибровать чувствительность светофора под вашу выборку.</div>
            <div className="thresh-row">
              <span className="thresh-tag green">🟢 0–30</span>
              <span style={{color:'var(--fg-3)'}}>норма</span>
            </div>
            <div className="thresh-row">
              <span className="thresh-tag yellow">🟡 31–60</span>
              <span style={{color:'var(--fg-3)'}}>средний — 1-on-1 на этой неделе</span>
            </div>
            <div className="thresh-row">
              <span className="thresh-tag red">🔴 61–100</span>
              <span style={{color:'var(--fg-3)'}}>высокий — вмешаться сегодня</span>
            </div>
          </div>
        </div>

        {/* Telegram preview */}
        <div className="cfg-block" style={{marginTop:14}}>
          <h3>📱 Что видит сотрудник в Telegram<span className="helper" style={{fontWeight:400, fontSize:12, color:'var(--fg-3)', marginLeft:8}}>превью бота Глафиры</span></h3>
          <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:14}}>
            <div className="tg-preview">
              <div className="tg-bubble">
                <div className="tg-author">Глафира 💃</div>
                Привет, Иван! Это Глафира. Я уже помогала тебе устраиваться — теперь буду спрашивать, как идёт адаптация. Твои ответы видит только HR, твой руководитель не получит индивидуальные ответы.
              </div>
              <div className="tg-bubble">
                <div className="tg-author">Глафира 💃</div>
                Прошла первая неделя 🎉 Как ты себя чувствуешь?
                <div className="tg-emoji-row">😡 😞 😐 🙂 😄</div>
              </div>
            </div>
            <div className="tg-preview">
              <div className="tg-bubble">
                <div className="tg-author">Глафира 💃</div>
                Зарплата за смены обещана понятным способом и в понятный срок?
                <div className="tg-buttons">
                  <button className="tg-btn">✅ Да</button>
                  <button className="tg-btn">❌ Нет</button>
                </div>
              </div>
              <div className="tg-bubble">
                <div className="tg-author">Глафира 💃</div>
                Что сделало бы первую неделю лучше? (можно пропустить)
                <div className="tg-buttons">
                  <button className="tg-btn">⏭ Пропустить</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.PulseEmployeeCard = PulseEmployeeCard;
window.PulseAlerts = PulseAlerts;
window.PulseSurveys = PulseSurveys;
