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

  // ===== Последние сообщения / Чаты =====
  const channelMeta = {
    telegram: { abbr: 'TG', color: '#2A8AF0', name: 'Telegram' },
    whatsapp: { abbr: 'WA', color: '#1FA855', name: 'WhatsApp' },
    hh:       { abbr: 'HH', color: '#DC4646', name: 'hh.ru' },
    avito:    { abbr: 'AV', color: '#0AB1C7', name: 'Авито' },
    sms:      { abbr: 'СМ', color: '#5B6573', name: 'СМС' },
  };
  const messages = [
    { id: 'm1', channel: 'whatsapp', name: 'Ольга С.', vacancy: 'Кладовщик · 2/2',
      preview: 'Здравствуйте! Видела объявление про кладовщика 2/2, ещё актуально? Могу выйти уже на этой неделе',
      time: '2 мин', unread: true },
    { id: 'm2', channel: 'telegram', name: 'Михаил К.', vacancy: 'Frontend (Senior)',
      preview: 'Спасибо за приглашение — подтверждаю собеседование на завтра в 11:00', time: '14 мин', unread: true },
    { id: 'm3', channel: 'hh', name: 'Павел Д.', vacancy: 'Кладовщик · 2/2',
      preview: 'Готов приступить хоть завтра. Подскажите, какой график и есть ли оформление по ТК?',
      time: '38 мин', unread: true },
    { id: 'm4', channel: 'avito', name: 'Игорь П.', vacancy: 'Кладовщик · 2/2',
      preview: 'А можно подъехать к 10 утра вместо 9? Дорога от меня неблизкая', time: '1 ч', unread: false },
    { id: 'm5', channel: 'telegram', name: 'Александр Т.', vacancy: 'Оператор call-центра',
      preview: 'Это по поводу работы оператором, мне ваш номер дали в чате', time: '2 ч', unread: true },
    { id: 'm6', channel: 'whatsapp', name: 'Алёна Р.', vacancy: 'HR-дженералист',
      preview: 'Отправила выполненное тестовое задание вам на почту, посмотрите пожалуйста', time: '3 ч', unread: false },
  ];
  const unread = messages.filter(m => m.unread).length;

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

      {/* Последние сообщения · Чаты Глафиры */}
      <div className="card-block msg-card">
        <div className="card-block-head">
          <div className="title">
            Последние сообщения
            <span className="ad-sub-title">· все каналы в одном чате</span>
          </div>
          <button className="btn btn-ghost btn-sm">Все чаты <Icon name="chevR" size={14}/></button>
        </div>

        <div className="msg-summary">
          <span className="msg-sum-item">
            <span className="msg-sum-num t-mono">{unread}</span> непрочитанных
          </span>
          <span className="msg-sum-sep"/>
          <span className="msg-sum-item">
            <span className="msg-sum-num t-mono">{messages.length}</span> активных диалогов
          </span>
        </div>

        <div className="msg-list">
          {messages.map((m) => {
            const ch = channelMeta[m.channel];
            const initials = m.name.split(' ').map(s => s[0]).join('').slice(0, 2);
            return (
              <div key={m.id} className={`msg-row${m.unread ? ' unread' : ''}`}>
                <div className="msg-ava-wrap">
                  <div className="msg-ava">{initials}</div>
                  <span className="msg-ch-badge t-mono" style={{ background: ch.color }}>{ch.abbr}</span>
                </div>
                <div className="msg-body">
                  <div className="msg-top">
                    <span className="msg-name">{m.name}</span>
                    <span className="msg-vac">{m.vacancy}</span>
                    <span className="msg-ch-name" style={{ color: ch.color }}>
                      <span className="msg-ch-dot" style={{ background: ch.color }}/>
                      {ch.name}
                    </span>
                  </div>
                  <div className="msg-text">{m.preview}</div>
                  <div className="msg-actions">
                    <button className="msg-goto">Перейти к кандидату <Icon name="chevR" size={13}/></button>
                  </div>
                </div>
                <div className="msg-meta">
                  {m.unread && <span className="msg-unread-dot"/>}
                  <span className="msg-time t-mono">{m.time}</span>
                </div>
              </div>
            );
          })}
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
