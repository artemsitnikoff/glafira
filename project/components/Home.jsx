// Home — Главный экран
const { useState: useStateHome } = React;

function Home({ tweaks }) {
  const [period, setPeriod] = useStateHome('month');
  const periods = [
    { id: 'week', label: 'Неделя' },
    { id: 'month', label: 'Месяц' },
    { id: 'quarter', label: 'Квартал' },
    { id: 'year', label: 'Год' },
    { id: 'all', label: 'Всё время' },
  ];

  // KPIs vary slightly by period — for visual realism
  const data = {
    week:    { open: 23, openD: '+2', closed: 4,  closedDsuc: 3, closedDfail: 1, time: 28, timeD: -8, churn: 4.1, active: 142, activeNew: 12, conv: 11.8, convD: 0.4, cph: 38400, speed: 3.2 },
    month:   { open: 23, openD: '+3', closed: 18, closedDsuc: 14, closedDfail: 4, time: 31, timeD: -12, churn: 6.2, active: 412, activeNew: 47, conv: 12.4, convD: 1.8, cph: 41200, speed: 4.1 },
    quarter: { open: 23, openD: '+8', closed: 47, closedDsuc: 38, closedDfail: 9, time: 33, timeD: -6, churn: 7.0, active: 1180, activeNew: 102, conv: 11.9, convD: 0.6, cph: 43800, speed: 4.4 },
    year:    { open: 23, openD: '+18', closed: 184, closedDsuc: 148, closedDfail: 36, time: 36, timeD: -3, churn: 8.4, active: 4220, activeNew: 320, conv: 11.2, convD: -0.4, cph: 46100, speed: 4.9 },
    all:     { open: 23, openD: '—', closed: 312, closedDsuc: 248, closedDfail: 64, time: 38, timeD: 0, churn: 8.1, active: 6840, activeNew: 0, conv: 10.9, convD: 0, cph: 47800, speed: 5.2 },
  };
  const d = data[period];
  const showExt = tweaks.kpiExtended;

  const fmtNum = n => n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '\u202F');

  const attention = [
    { name: 'Frontend-разработчик (Senior)', reason: 'Топ-3 кандидата без движения 9 дней', flag: 'warn', icon: 'clock' },
    { name: 'Кладовщик · смена 2/2', reason: '12 новых откликов не обработано >24ч', flag: 'urgent', icon: 'alert' },
    { name: 'HR-дженералист', reason: 'Дедлайн закрытия через 4 дня', flag: 'deadline', icon: 'calClock' },
    { name: 'DevOps-инженер', reason: 'Заказчик не отвечает на запрос интервью 3 дня', flag: 'warn', icon: 'clock' },
  ];

  const events = [
    { type: 'qual', icon: 'check', text: <><span className="anatoly">Глафира</span> квалифицировала кандидата <span className="ent">Михаил К.</span> на вакансию <span className="ent">Frontend (Senior)</span></>, time: '5 мин назад' },
    { type: 'new', icon: 'sparkle', text: <>Новый отклик на <span className="ent">Кладовщик · смена 2/2</span> — <span className="ent">Игорь П.</span></>, time: '18 мин назад' },
    { type: 'score', icon: 'star', text: <>Заказчик <span className="ent">«Логос»</span> оставил оценку 5/5 кандидату <span className="ent">Алёна Р.</span></>, time: '42 мин назад' },
    { type: 'offer', icon: 'check', text: <>Кандидат <span className="ent">Сергей Н.</span> принял оффер на <span className="ent">DevOps-инженер</span></>, time: '1 ч назад' },
    { type: 'qual', icon: 'check', text: <><span className="anatoly">Глафира</span> отклонила <span className="ent">Анна В.</span> — не подходит по стажу</>, time: '1 ч назад' },
    { type: 'new', icon: 'sparkle', text: <>3 новых отклика на <span className="ent">HR-дженералист</span></>, time: '2 ч назад' },
    { type: 'move', icon: 'chevR', text: <><span className="ent">Виктор Л.</span> переведён на этап «Интервью с заказчиком»</>, time: '2 ч назад' },
    { type: 'score', icon: 'star', text: <>Заказчик <span className="ent">«Сатурн»</span> запросил замену по <span className="ent">Product Manager</span></>, time: '3 ч назад' },
    { type: 'offer', icon: 'check', text: <>Кандидат <span className="ent">Юлия Б.</span> вышла на испытательный — <span className="ent">QA Lead</span></>, time: '4 ч назад' },
    { type: 'qual', icon: 'check', text: <><span className="anatoly">Глафира</span> запланировала интервью с <span className="ent">Дмитрий К.</span> на завтра 11:00</>, time: '5 ч назад' },
  ];

  const sources = [
    { label: 'hh.ru',         value: 248, color: '#DC4646' },
    { label: 'Авито Работа',  value: 134, color: '#16A34A' },
    { label: 'Telegram-бот Глафиры', value: 98, color: '#2A8AF0' },
    { label: 'Рефералы',      value: 42,  color: '#7E5CF0' },
    { label: 'Прямые отклики',value: 28,  color: '#5B6573' },
  ];
  const sourceMax = Math.max(...sources.map(s => s.value));

  // ===== Адаптация / Пульс-Онбординг =====
  const pulse = {
    total: 24,
    newThisMonth: 7,
    red: 3, yellow: 5, green: 16,
    avgRate: 3.8,           // средняя оценка адаптации (из 5)
    responseRate: 76,        // % ответивших на опросы
    enps: 42,                // eNPS по 90+ дням
    enpsD: '+6',
    noResponse: 2,
    topAlerts: [
      { name: 'Иван Петров',    role: 'Кладовщик',          day: 32, risk: 78, reason: 'Не получил зарплату в срок · день 30', flag: 'urgent', icon: 'alert' },
      { name: 'Мария Орлова',   role: 'Оператор кол-центра',day: 18, risk: 72, reason: 'Триггер «увольняюсь» в ответе на опрос', flag: 'urgent', icon: 'alert' },
      { name: 'Денис Соколов',  role: 'Грузчик',            day: 6,  risk: 65, reason: 'Не отвечает на сообщения Глафиры 7 дней', flag: 'warn',   icon: 'clock' },
    ],
  };
  const riskTotal = pulse.red + pulse.yellow + pulse.green;

  const periodLabelLow = {
    week: 'к прошлой неделе', month: 'к прошлому месяцу', quarter: 'к прошлому кварталу',
    year: 'к прошлому году', all: '',
  }[period];

  return (
    <div className="content-inner">
      {/* Header */}
      <div className="page-header">
        <div className="left">
          <h1>{tweaks.greeting ? 'Привет, Анна' : 'Главная'}</h1>
          <div className="sub">Обновлено 5 мин назад · 14:32</div>
        </div>
        <div className="seg" role="tablist" aria-label="Период">
          {periods.map(p => (
            <button key={p.id}
              className={period === p.id ? 'active' : ''}
              onClick={() => setPeriod(p.id)}>{p.label}</button>
          ))}
        </div>
      </div>

      {/* KPI */}
      <div className="kpi-grid">
        <KPI label="Открытые вакансии" tip="Текущее число активных вакансий"
          value={d.open} sub="всего активных"
          delta={d.openD === '—' ? null : { kind: d.openD.startsWith('+') ? 'up' : 'down', text: d.openD }}/>
        <KPI label="Закрытые вакансии" tip="Сколько закрыто за выбранный период"
          value={d.closed} sub={`${d.closedDsuc} успехом · ${d.closedDfail} без найма`}/>
        <KPI label="Среднее время найма" tip="От создания вакансии до «Принят»"
          value={d.time} unit="дней"
          delta={d.timeD === 0 ? { kind:'flat', text:'— 0%' } : { kind: d.timeD < 0 ? 'down-good' : 'up-bad', text: `${d.timeD < 0 ? '▼' : '▲'} ${Math.abs(d.timeD)}%` }}
          deltaSub={periodLabelLow}/>
        <KPI label="Текучесть (90 дней)" tip="% уволившихся в течение испытательного срока"
          value={d.churn} unit="%"
          delta={{ kind: 'down-good', text: '▼ 0.8 п.п.' }}
          deltaSub={periodLabelLow}/>
        <KPI label="Активных кандидатов" tip="Сколько кандидатов сейчас в воронках"
          value={fmtNum(d.active)} sub={d.activeNew ? `из них ${d.activeNew} новых` : 'весь период'}/>
        <KPI label="Конверсия отклик → найм" tip="% откликов, дошедших до оффера"
          value={d.conv} unit="%"
          delta={d.convD === 0 ? { kind:'flat', text:'— 0' } : { kind: d.convD > 0 ? 'up' : 'down', text: `${d.convD > 0 ? '▲' : '▼'} ${Math.abs(d.convD).toFixed(1)} п.п.` }}
          deltaSub={periodLabelLow}/>
        {showExt && <>
          <KPI label="Стоимость найма (CPH)" tip="Средняя стоимость одного найма"
            value={fmtNum(d.cph)} unit="₽"
            delta={{ kind: 'down-good', text: '▼ 6%' }} deltaSub={periodLabelLow}/>
          <KPI label="Скорость отклика рекрутера" tip="Среднее время от отклика до первого контакта"
            value={d.speed} unit="часа"
            delta={{ kind: 'flat', text: '— 0%' }} deltaSub={periodLabelLow}/>
        </>}
      </div>

      {/* Two widgets */}
      <div className="dash-grid-2">
        <div className="card-block">
          <div className="card-block-head">
            <div className="title">
              Требуют внимания
              <span className="count-pill">{attention.length}</span>
            </div>
            <button className="btn btn-ghost btn-sm">Все вакансии <Icon name="chevR" size={14}/></button>
          </div>
          <div>
            {attention.map((a, i) => (
              <div key={i} className="att-row">
                <div className={`flag-icon ${a.flag}`}><Icon name={a.icon} size={16}/></div>
                <div className="body">
                  <div className="name">{a.name}</div>
                  <div className="reason">{a.reason}</div>
                </div>
                <div className="arrow"><Icon name="chevR" size={16}/></div>
              </div>
            ))}
          </div>
        </div>

        <div className="card-block">
          <div className="card-block-head">
            <div className="title">Лента событий</div>
            <span className="live-dot">live</span>
          </div>
          <div style={{maxHeight: 380, overflowY: 'auto', margin: '0 -4px', padding: '0 4px'}}>
            {events.map((e, i) => (
              <div key={i} className="event-row">
                <div className={`event-icon ${e.type}`}><Icon name={e.icon} size={12}/></div>
                <div className="body">
                  <div className="text">{e.text}</div>
                  <div className="time">{e.time}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Адаптация · Пульс-Онбординг */}
      <div className="card-block ad-card">
        <div className="card-block-head">
          <div className="title">
            Адаптация
            <span className="ad-sub-title">· Пульс-Онбординг</span>
          </div>
          <button className="btn btn-ghost btn-sm">Все сотрудники <Icon name="chevR" size={14}/></button>
        </div>

        <div className="ad-stats">
          <div className="ad-stat ad-stat-total">
            <div className="ad-stat-num">{pulse.total}</div>
            <div className="ad-stat-label">на адаптации</div>
            <div className="ad-stat-sub">+{pulse.newThisMonth} в этом месяце</div>
          </div>

          <div className="ad-stat ad-stat-risk">
            <div className="ad-stat-label-top">Риск ухода</div>
            <div className="ad-risk-bar">
              <span className="seg seg-red"    style={{flex: pulse.red}}/>
              <span className="seg seg-yellow" style={{flex: pulse.yellow}}/>
              <span className="seg seg-green"  style={{flex: pulse.green}}/>
            </div>
            <div className="ad-risk-legend">
              <span><span className="dot dot-red"/>{pulse.red} высокий</span>
              <span><span className="dot dot-yellow"/>{pulse.yellow} средний</span>
              <span><span className="dot dot-green"/>{pulse.green} норма</span>
            </div>
          </div>

          <div className="ad-stat">
            <div className="ad-stat-label-top">Средняя оценка</div>
            <div className="ad-stat-row">
              <span className="ad-stat-num-md">{pulse.avgRate.toFixed(1)}</span>
              <span className="ad-stat-unit">/ 5</span>
            </div>
            <div className="ad-stat-sub">ответили {pulse.responseRate}% · {pulse.noResponse} молчат</div>
          </div>

          <div className="ad-stat">
            <div className="ad-stat-label-top">eNPS <span className="ad-mute">90 дн.</span></div>
            <div className="ad-stat-row">
              <span className="ad-stat-num-md">{pulse.enps}</span>
              <span className="delta up" style={{fontSize:11, marginLeft:6}}>▲ {pulse.enpsD}</span>
            </div>
            <div className="ad-stat-sub">к прошлому периоду</div>
          </div>
        </div>

        <div className="ad-divider"/>

        <div className="ad-attention-head">
          <span className="ad-attn-title">Требуют внимания HR</span>
          <span className="count-pill">{pulse.topAlerts.length}</span>
        </div>
        <div className="ad-attention-list">
          {pulse.topAlerts.map((a, i) => (
            <div key={i} className="att-row ad-att-row">
              <div className={`flag-icon ${a.flag}`}><Icon name={a.icon} size={16}/></div>
              <div className="body">
                <div className="name">
                  {a.name}
                  <span className="ad-role">· {a.role}</span>
                </div>
                <div className="reason">{a.reason}</div>
              </div>
              <div className="ad-att-meta">
                <span className="ad-day t-mono">день {a.day}</span>
                <span className={`ad-risk-pill ${a.risk >= 70 ? 'red' : a.risk >= 50 ? 'yellow' : 'green'}`}>
                  риск <b className="t-mono">{a.risk}</b>
                </span>
              </div>
              <div className="arrow"><Icon name="chevR" size={16}/></div>
            </div>
          ))}
        </div>
      </div>

      {/* Sources */}
      {tweaks.showSources && (
        <div className="card-block">
          <div className="card-block-head">
            <div className="title">Топ-источники кандидатов</div>
            <span className="t-secondary" style={{fontSize:12, color:'var(--fg-3)'}}>{periods.find(p => p.id === period).label.toLowerCase()}</span>
          </div>
          <div>
            {sources.map(s => (
              <div key={s.label} className="sources-row">
                <div className="label">{s.label}</div>
                <div className="bar">
                  <span style={{ width: `${(s.value / sourceMax) * 100}%`, background: s.color }}/>
                </div>
                <div className="num">{s.value}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function KPI({ label, tip, value, unit, sub, delta, deltaSub }) {
  return (
    <div className="kpi" title={tip}>
      <div className="kpi-label">
        {label}
        <span className="info" title={tip}>i</span>
      </div>
      <div className="kpi-value-row">
        <span className="kpi-value">{value}</span>
        {unit && <span className="kpi-unit">{unit}</span>}
      </div>
      <div className="kpi-foot">
        {delta ? <span className={`delta ${delta.kind}`}>{delta.text}</span> : <span/>}
        <span className="kpi-sub">{deltaSub || sub}</span>
      </div>
    </div>
  );
}

window.Home = Home;
