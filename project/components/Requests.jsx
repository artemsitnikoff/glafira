// Заявки на подбор — экран в дизайне «Кандидатов»: воронка-чипы, таблица, панель заявки, перевод по этапам
const { useState: useStateRq, useMemo: useMemoRq } = React;

const REQUESTS_DATA = [
  { id:'r1', num:21, title:'Менеджер по продажам B2B', dept:'Отдел продаж', author:'Марина Ковалёва', role:'Руководитель отдела продаж', positions:2, city:'Москва', deadline:'до 30 августа', deadlineISO:'2026-08-30', deadlineDate:'30.08.2026', salaryFrom:'120000', salaryTo:'180000', priority:'high', created:'сегодня', createdDate:'18.07.2026', status:'new',
    desc:'Нужны 2 менеджера активных продаж в B2B-направление (SaaS). Обязателен опыт холодных продаж от 2 лет, желательно в IT. База тёплых лидов есть, CRM — Битрикс24. Оклад + % с первых сделок.',
    comments:[], history:[{t:'Сегодня, 10:24', label:'Заявка подана · Марина Ковалёва'}] },
  { id:'r2', num:20, title:'Оператор склада (ночная смена)', dept:'Логистика', author:'Дмитрий Ершов', role:'Начальник склада', positions:4, city:'Подольск', deadline:'до 15 августа', deadlineISO:'2026-08-15', deadlineDate:'15.08.2026', priority:'normal', created:'вчера', createdDate:'17.07.2026', status:'new', via:'form',
    desc:'Смена 20:00–08:00, график 2/2. Погрузка, сборка заказов, работа с ТСД. Без опыта — обучим, важна ответственность. Есть развозка от станции.',
    comments:[], history:[{t:'Вчера, 18:05', label:'Заявка подана по ссылке-форме · Дмитрий Ершов'}] },
  { id:'r3', num:19, title:'Ассистент отдела маркетинга', dept:'Маркетинг', author:'Ольга Митина', role:'Директор по маркетингу', positions:1, city:'Москва (гибрид)', deadline:'не срочно', priority:'normal', created:'вчера', createdDate:'17.07.2026', status:'new',
    desc:'Помощь с организацией съёмок и мероприятий, документооборот, работа с подрядчиками. Подойдёт начинающий специалист, главное — организованность.',
    comments:[], history:[{t:'Вчера, 12:40', label:'Заявка подана · Ольга Митина'}] },
  { id:'r4', num:18, title:'Аналитик данных', dept:'Data', author:'Павел Гусев', role:'Head of Data', positions:1, city:'Москва', deadline:'до 1 сентября', deadlineISO:'2026-09-01', deadlineDate:'01.09.2026', salaryFrom:'180000', salaryTo:'240000', priority:'normal', created:'3 дня назад', createdDate:'15.07.2026', status:'work',
    desc:'Нужен аналитик в продуктовую команду: SQL, Python, построение дашбордов. Основная задача — метрики продукта и регулярная отчётность для топ-менеджмента.',
    comments:[
      {side:'recruiter', author:'Анна Седова', time:'Позавчера, 15:02', text:'Павел, уточните, пожалуйста: BI-инструмент принципиален? Superset, Power BI?'},
      {side:'manager', author:'Павел Гусев', time:'Позавчера, 16:40', text:'У нас Superset, но переучим с любого. Главное — крепкий SQL.'},
    ],
    history:[{t:'15 июля', label:'Заявка подана · Павел Гусев'},{t:'16 июля', label:'Взята в работу · Анна Седова'}] },
  { id:'r5', num:17, title:'Frontend-разработчик (Senior)', dept:'Engineering', author:'Игорь Савельев', role:'CTO', positions:2, city:'Москва', deadline:'до 31 июля', deadlineDate:'31.07.2026', priority:'high', created:'23 дня назад', createdDate:'25.06.2026', status:'sourcing', vacancyId:'fe', hired:0,
    desc:'Усиление продуктовой команды: React/TypeScript, senior-уровень. Ожидаем участие в ревью и менторинг мидлов.',
    comments:[], history:[{t:'25 июня', label:'Заявка подана · Игорь Савельев'},{t:'25 июня', label:'Взята в работу · Анна Седова'},{t:'26 июня', label:'Создана вакансия «Frontend-разработчик (Senior)»'}] },
  { id:'r6', num:16, title:'QA-инженер (автоматизация)', dept:'Engineering', author:'Игорь Савельев', role:'CTO', positions:1, city:'Москва', deadline:'до 15 августа', deadlineDate:'15.08.2026', priority:'normal', created:'месяц назад', createdDate:'18.06.2026', status:'sourcing', vacancyId:'qa', hired:0,
    desc:'Автоматизация регресса: Python + pytest или JS + Playwright. Настроить пайплайн прогонов в CI.',
    comments:[], history:[{t:'18 июня', label:'Заявка подана · Игорь Савельев'},{t:'19 июня', label:'Взята в работу · Иван Корнев'},{t:'20 июня', label:'Создана вакансия «QA-инженер (автоматизация)»'}] },
  { id:'r7', num:12, title:'Data Engineer', dept:'Data', author:'Павел Гусев', role:'Head of Data', positions:1, city:'Москва', deadline:'до 30 апреля', deadlineDate:'30.04.2026', priority:'normal', created:'19 марта', createdDate:'19.03.2026', status:'done', hired:1, closedNote:'Нанят Сергей Аверин · найм занял 27 дней',
    desc:'Инженер данных: витрины, Airflow, ClickHouse. Поддержка пайплайнов аналитики.',
    comments:[], history:[{t:'19 марта', label:'Заявка подана · Павел Гусев'},{t:'19 марта', label:'Взята в работу · Анна Седова'},{t:'20 марта', label:'Создана вакансия «Data Engineer»'},{t:'15 апреля', label:'Нанят 1 из 1 — заявка закрыта автоматически'}] },
  { id:'r8', num:9, title:'Офис-менеджер (второй)', dept:'Административный отдел', author:'Ирина Волкова', role:'Операционный директор', positions:1, city:'Москва', deadline:'не срочно', priority:'normal', created:'2 июля', createdDate:'02.07.2026', status:'rejected', rejectReason:'Бюджет на вторую ставку не согласован на Q3. Вернёмся к заявке в октябре.',
    desc:'Второй офис-менеджер в пару к текущему: ресепшн, закупки, командировки.',
    comments:[], history:[{t:'2 июля', label:'Заявка подана · Ирина Волкова'},{t:'3 июля', label:'Отклонена · Анна Седова'}] },
];

const REQ_STAGES = [
  { id:'new',      label:'Новая',     color:'#2A8AF0' },
  { id:'work',     label:'В работе',  color:'#D9A514' },
  { id:'sourcing', label:'В подборе', color:'#7E5CF0' },
  { id:'done',     label:'Закрыта',   color:'#16A34A', terminal:true },
  { id:'rejected', label:'Отклонена', color:'#DC4646', terminal:true },
];
const REQ_STATUS = Object.fromEntries(REQ_STAGES.map(s => [s.id, { label: s.label, cls: s.id, color: s.color }]));
const reqStage = (id) => REQ_STAGES.find(s => s.id === id);
const reqPlural = (n, f) => f[ n%10===1 && n%100!==11 ? 0 : (n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2) ];
const posLabel = (n) => `${n} ${reqPlural(n, ['позиция','позиции','позиций'])}`;

function ReqBadge({ status }) {
  const s = REQ_STATUS[status];
  return <span className={`req-badge ${s.cls}`}><span className="stage-dot" style={{background:s.color, marginRight:5}}/>{s.label}</span>;
}
const ReqUrgent = () => <span className="req-urgent"><Icon name="flame" size={11}/> Срочно</span>;

/* ---------- Перевод по воронке: общий обработчик ---------- */
function useReqMove(onUpdate, onCreateVacancy) {
  return (req, target) => {
    if (target === req.status) return;
    if (target === 'sourcing' && !req.vacancyId) { onCreateVacancy(req); return; }
    const label = reqStage(target).label;
    onUpdate(rs => rs.map(r => r.id === req.id ? {
      ...r, status: target,
      closedNote: target === 'done' ? (r.closedNote || `Закрыта вручную · нанято ${r.hired || 0} из ${r.positions}`) : r.closedNote,
      history: [...r.history, { t:'Сегодня', label:`Переведена на этап «${label}» · Анна Седова` }],
    } : r));
  };
}

/* ---------- B24-полоса этапов (как у кандидата) ---------- */
function ReqStageStrip({ req, onMove, onReject }) {
  const flow = REQ_STAGES.filter(s => s.id !== 'rejected');
  const currentIdx = flow.findIndex(s => s.id === req.status);
  return (
    <div className="stage-strip">
      {flow.map((s, i) => {
        const passed = i < currentIdx, active = i === currentIdx;
        return (
          <button key={s.id}
            className={`ss-step ${passed ? 'passed' : ''} ${active ? 'active' : ''} ${i > currentIdx ? 'upcoming' : ''}`}
            style={passed || active ? {'--ss-color': s.color} : {}}
            title={s.label} onClick={() => onMove(req, s.id)}>
            <span className="ss-label">{s.label}</span>
          </button>
        );
      })}
      <button className="ss-step ss-final" title="Отклонить заявку" onClick={onReject}>
        <span className="ss-label">{req.status === 'rejected' ? 'Отклонена' : 'Отклонить'}</span>
      </button>
    </div>
  );
}

/* ---------- Попап отклонения (в тулбаре) ---------- */
function ReqRejectPop({ onClose, onConfirm }) {
  const [reason, setReason] = useStateRq('');
  return (
    <>
      <div className="cd-pop-backdrop" onClick={onClose}/>
      <div className="cd-move-pop req-reject-pop" role="menu">
        <div className="cd-pop-head">Причина отклонения — увидит менеджер</div>
        <textarea rows="3" autoFocus value={reason} onChange={e => setReason(e.target.value)} placeholder="Например: бюджет не согласован, позиция дублируется…"/>
        <div className="req-pop-foot">
          <button className="btn btn-ghost btn-sm" onClick={onClose}>Отмена</button>
          <button className="btn btn-primary btn-sm req-btn-danger" disabled={!reason.trim()} onClick={() => onConfirm(reason.trim())}>Отклонить</button>
        </div>
      </div>
    </>
  );
}

/* ---------- Панель заявки (как карточка кандидата) ---------- */
function RequestDetailPanel({ req, onUpdate, onClose, onCreateVacancy, onOpenVacancy, readOnly, managerName }) {
  const [moveOpen, setMoveOpen] = useStateRq(false);
  const [rejectOpen, setRejectOpen] = useStateRq(false);
  const [msg, setMsg] = useStateRq('');
  const moveTo = useReqMove(onUpdate, onCreateVacancy);
  const patch = (fn) => onUpdate(rs => rs.map(r => r.id === req.id ? fn(r) : r));
  const reject = (reason) => { setRejectOpen(false); patch(r => ({ ...r, status:'rejected', rejectReason:reason, history:[...r.history, { t:'Сегодня', label:'Отклонена · Анна Седова' }] })); };
  const restore = () => patch(r => ({ ...r, status:'work', rejectReason:undefined, history:[...r.history, { t:'Сегодня', label:'Возвращена в работу · Анна Седова' }] }));
  const send = () => {
    const text = msg.trim();
    if (!text) return;
    setMsg('');
    patch(r => ({
      ...r,
      status: (!readOnly && r.status === 'new') ? 'work' : r.status,
      comments: [...r.comments, { side: readOnly ? 'manager' : 'recruiter', author: readOnly ? managerName : 'Анна Седова', time:'Только что', text }],
      history: (!readOnly && r.status === 'new') ? [...r.history, { t:'Сегодня', label:'Взята в работу (задан вопрос) · Анна Седова' }] : r.history,
    }));
  };
  const v = req.vacancyId && VACANCIES.find(x => x.id === req.vacancyId);
  const stageOptions = REQ_STAGES.filter(s => s.id !== 'rejected');
  const curIdx = stageOptions.findIndex(s => s.id === req.status);
  const showThread = req.status === 'new' || req.status === 'work' || req.comments.length > 0;
  return (
    <div className="cand-detail req-panel">
      {readOnly ? (
        <div className="cd-toolbar">
          <span className="req-ro-hint"><Icon name="lock" size={13}/> Заявка у рекрутинга — статус обновляется здесь автоматически</span>
          <div style={{flex:1}}/>
          <button className="icon-btn" onClick={onClose} title="Закрыть"><Icon name="x" size={18}/></button>
        </div>
      ) : (
      <div className="cd-toolbar">
        <div className="cd-move-wrap">
          <button className="btn btn-success btn-sm" onClick={() => setMoveOpen(o => !o)}>
            <Icon name="arrowRight" size={14}/> Перевести <Icon name="chevD" size={12}/>
          </button>
          {moveOpen && (
            <>
              <div className="cd-pop-backdrop" onClick={() => setMoveOpen(false)}/>
              <div className="cd-move-pop" role="menu">
                <div className="cd-pop-head">На какой этап?</div>
                {stageOptions.map((s, i) => (
                  <button key={s.id}
                    className={`cd-pop-item ${s.id === req.status ? 'cur' : ''} ${i === curIdx + 1 ? 'next' : ''}`}
                    onClick={() => { setMoveOpen(false); moveTo(req, s.id); }}>
                    <span className="stage-dot" style={{background: s.color}}/>
                    <span className="cd-pop-label">{s.label}{s.id === 'sourcing' && !req.vacancyId ? ' — создать вакансию' : ''}</span>
                    {s.id === req.status && <span className="cd-pop-tag">сейчас</span>}
                    {i === curIdx + 1 && <span className="cd-pop-tag cd-pop-tag-next">далее</span>}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
        <div className="cd-move-wrap">
          <button className="btn btn-secondary btn-sm" onClick={() => setRejectOpen(o => !o)}>
            <Icon name="x" size={14}/> Отклонить <Icon name="chevD" size={12}/>
          </button>
          {rejectOpen && <ReqRejectPop onClose={() => setRejectOpen(false)} onConfirm={reject}/>}
        </div>
        {(req.status === 'new' || req.status === 'work') && (
          <button className="btn btn-primary btn-sm" onClick={() => onCreateVacancy(req)}><Icon name="briefcase" size={14}/> Создать вакансию</button>
        )}
        {req.status === 'sourcing' && v && (
          <button className="btn btn-secondary btn-sm" onClick={() => onOpenVacancy(req.vacancyId)}><Icon name="open" size={14}/> Открыть вакансию</button>
        )}
        {req.status === 'rejected' && (
          <button className="btn btn-secondary btn-sm" onClick={restore}><Icon name="refresh" size={14}/> Вернуть в работу</button>
        )}
        <div style={{flex:1}}/>
        <button className="icon-btn" onClick={onClose} title="Закрыть"><Icon name="x" size={18}/></button>
      </div>
      )}

      <div className={`req-strip-row ${readOnly ? 'req-strip-ro' : ''}`}>
        <ReqStageStrip req={req} onMove={moveTo} onReject={() => setRejectOpen(true)}/>
      </div>

      <div className="req-p-head">
        <div className="cd-context">
          <span className="src-pill">Заявка №{req.num}</span>
          {req.via === 'form' && <span className="src-pill req-pill-form"><Icon name="link" size={11}/> по ссылке-форме</span>}
          <span>{req.author} · {req.role}</span>
          <span className="sep">·</span>
          <span>подана {req.created}</span>
          <span className="sep">·</span>
          <span>срок: {req.deadline}</span>
        </div>
        <div className="req-p-title">
          <h1>{req.title}</h1>
          <ReqBadge status={req.status}/>
          {req.priority === 'high' && req.status !== 'done' && req.status !== 'rejected' && <ReqUrgent/>}
        </div>
      </div>

      <div className="req-panel-body">
        <div className="req-grid">
          <div className="req-col">
            <div className="req-card">
              <div className="req-card-title">Описание от менеджера</div>
              <p className="req-desc">{req.desc}</p>
            </div>
            {showThread && (
              <div className="req-card">
                <div className="req-card-title">Уточнения с заказчиком</div>
                {req.comments.length === 0 && <div className="req-thread-empty">{readOnly ? 'Вопросов от рекрутера пока нет. Напишите, если хотите что-то добавить к заявке.' : <>Пока вопросов не было. {req.status === 'new' ? 'Если что-то неясно — спросите: заявка перейдёт «В работу».' : 'Задайте вопрос менеджеру, если что-то неясно.'}</>}</div>}
                {req.comments.map((c, i) => (
                  <div key={i} className={`req-msg ${c.side}`}>
                    <Avatar name={c.author} size="sm"/>
                    <div className="req-msg-body">
                      <div className="req-msg-head">{c.author} <span>{c.time}</span></div>
                      <div className="req-msg-text">{c.text}</div>
                    </div>
                  </div>
                ))}
                {(req.status === 'new' || req.status === 'work' || req.status === 'sourcing') && (
                  <div className="req-thread-input">
                    <input value={msg} onChange={e => setMsg(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} placeholder={readOnly ? 'Написать рекрутеру…' : 'Вопрос менеджеру…'}/>
                    <button className="btn btn-secondary btn-sm" disabled={!msg.trim()} onClick={send}><Icon name="telegram" size={14}/> Отправить</button>
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="req-col req-col-side">
            <div className="req-card">
              <div className="req-card-title">Параметры</div>
              <div className="req-params">
                <div><span>Позиции</span><b>{posLabel(req.positions)}</b></div>
                <div><span>Город</span><b>{req.city}</b></div>
                <div><span>Отдел</span><b>{req.dept}</b></div>
                <div><span>Срок</span><b>{req.deadline}</b></div>
                {req.salaryFrom && <div><span>Вилка</span><b>{(+req.salaryFrom).toLocaleString('ru-RU')} – {(+req.salaryTo).toLocaleString('ru-RU')} ₽</b></div>}
                <div><span>Приоритет</span><b>{req.priority === 'high' ? '🔥 Срочно' : 'Обычный'}</b></div>
              </div>
            </div>
            {req.status === 'sourcing' && v && (
              <div className="req-card req-card-vac">
                <div className="req-card-title">Вакансия по заявке</div>
                <div className="req-vac-name" style={readOnly ? {cursor:'default'} : null} onClick={() => !readOnly && onOpenVacancy(req.vacancyId)}>{v.name} {!readOnly && <Icon name="chevR" size={14}/>}</div>
                <div className="req-vac-stats">
                  <div><b>{v.count}</b><span>кандидатов</span></div>
                  <div><b>+{v.newCount}</b><span>новых</span></div>
                  <div><b>{req.hired || 0} из {req.positions}</b><span>нанято</span></div>
                </div>
                <div className="req-vac-note"><Icon name="sparkle" size={13}/> Заявка закроется сама, когда нанятых станет {req.positions} из {req.positions}.</div>
              </div>
            )}
            {req.status === 'done' && (
              <div className="req-card req-card-done">
                <div className="req-card-title">Итог</div>
                <div className="req-done-line"><Icon name="check" size={15}/> {req.closedNote}</div>
              </div>
            )}
            {req.status === 'rejected' && req.rejectReason && (
              <div className="req-card req-card-rej">
                <div className="req-card-title">Причина отклонения</div>
                <p className="req-desc">{req.rejectReason}</p>
              </div>
            )}
            <div className="req-card">
              <div className="req-card-title">История</div>
              <div className="req-tl">
                {req.history.map((h, i) => (
                  <div key={i} className="req-tl-row">
                    <span className="req-tl-dot"/>
                    <div><div className="req-tl-label">{h.label}</div><div className="req-tl-time">{h.t}</div></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------- Экран заявок (дизайн «Кандидатов») ---------- */
function RequestsScreen({ requests, onUpdate, requestId, onOpenRequest, onCloseRequest, onCreateVacancy, onOpenVacancy, onNewRequest, onGoFunnelSettings, manager }) {
  const [stage, setStage] = useStateRq('all');
  const [query, setQuery] = useStateRq('');
  const isMgr = !!manager;
  const [copied, setCopied] = useStateRq(false);
  const source = isMgr ? requests.filter(r => r.author === manager.name) : requests;
  const detailMode = !!requestId;
  const activeReq = detailMode ? source.find(r => r.id === requestId) : null;

  const counts = useMemoRq(() => {
    const c = { all: source.length };
    REQ_STAGES.forEach(s => c[s.id] = source.filter(r => r.status === s.id).length);
    return c;
  }, [source]);

  const filtered = useMemoRq(() => source.filter(r => {
    if (stage !== 'all' && r.status !== stage) return false;
    if (query && !(`№${r.num} ${r.title} ${r.author}`.toLowerCase().includes(query.toLowerCase()))) return false;
    return true;
  }), [source, stage, query]);

  const toggleSelUnused = null;
  const pickStage = (id) => { setStage(id); onCloseRequest?.(); };

  return (
    <div className="cand-list-wrap">
      <div className="vac-header">
        <div className="vh-left">
          <h1 className="vh-title">{isMgr ? 'Мои заявки' : 'Заявки на подбор'}</h1>
          <div className="vh-meta">
            <span>{counts.new + counts.work + counts.sourcing} активных</span>
            <span className="sep">·</span>
            <span>{isMgr ? 'статусы и уточнения рекрутера — здесь, в реальном времени' : 'менеджеры подают заявки из своего кабинета — роль «Нанимающий менеджер»'}</span>
          </div>
        </div>
        <div className="vh-actions">
          {!isMgr && (
            <button className="btn btn-secondary btn-sm" onClick={() => { setCopied(true); setTimeout(() => setCopied(false), 2000); }} title="Длинная непубличная ссылка — заявки с формы помечаются">
              <Icon name={copied ? 'check' : 'link'} size={14}/> {copied ? 'Скопировано' : 'Ссылка на форму'}
            </button>
          )}
          {!isMgr && (
            <button className="btn btn-secondary btn-sm" onClick={onGoFunnelSettings} title="Этапы воронки заявок настраиваются в Настройках">
              <Icon name="funnel" size={14}/> Воронка
            </button>
          )}
          <button className="btn btn-primary btn-sm" onClick={onNewRequest}><Icon name="plus" size={14}/> Новая заявка</button>
        </div>
      </div>

      <div className="funnel-row">
        <div className={`funnel-chip funnel-all ${stage === 'all' ? 'active' : ''}`} onClick={() => pickStage('all')}>
          Все <span className="fc-count">{counts.all}</span>
        </div>
        {REQ_STAGES.filter(s => !s.terminal).map(s => (
          <React.Fragment key={s.id}>
            <div className={`funnel-chip ${stage === s.id ? 'active' : ''}`} onClick={() => pickStage(s.id)}>
              <span className="stage-dot" style={{background: s.color}}/>
              {s.label} <span className="fc-count">{counts[s.id]}</span>
            </div>
            <Icon name="chevR" size={12} className="funnel-arrow"/>
          </React.Fragment>
        ))}
        <div className={`funnel-chip funnel-hired ${stage === 'done' ? 'active' : ''}`} onClick={() => pickStage('done')}>
          <Icon name="check" size={12}/> Закрыта <span className="fc-count">{counts.done}</span>
        </div>
        <div className="funnel-gap"/>
        <div className={`funnel-chip funnel-rejected ${stage === 'rejected' ? 'active' : ''}`} onClick={() => pickStage('rejected')}>
          <Icon name="x" size={12}/> Отклонена <span className="fc-count">{counts.rejected}</span>
        </div>
      </div>

      <div className="cand-controls">
        <div className="submenu-search" style={{width:280, height:30, background:'#fff', border:'1px solid var(--border-1)'}}>
          <Icon name="search" size={14} style={{color:'var(--fg-3)', flex:'none'}}/>
          <input placeholder="Поиск по заявкам…" value={query} onChange={e => setQuery(e.target.value)}/>
        </div>
        <div style={{flex:1}}/>
      </div>

      <div className="cand-body">
        <div className="cand-table">
          <div className="req-cards">
            {filtered.map(r => {
              const st = reqStage(r.status);
              const v = r.vacancyId && VACANCIES.find(x => x.id === r.vacancyId);
              return (
                <div key={r.id}
                     className="req-cardrow"
                     style={{'--stage-color': st.color}}
                     onClick={() => onOpenRequest(r.id)}>
                  <Avatar name={r.author} size="md"/>
                  <div className="req-cr-main">
                    <div className="req-cr-title">
                      <span className="req-num">№{r.num}</span>
                      <span className="req-name">{r.title}</span>
                      {r.priority === 'high' && r.status !== 'done' && r.status !== 'rejected' && <ReqUrgent/>}
                    </div>
                    <div className="req-cr-sub">{r.author} · {r.role}</div>
                    <div className="req-cr-sub2">{r.dept} · {r.city}</div>
                  </div>
                  <div className="req-cr-facts">
                    <div><span>Позиции</span><b>{r.positions}</b></div>
                    <div><span>Срок</span><b className="t-mono">{r.deadlineDate || '—'}</b></div>
                    <div><span>Подана</span><b className="t-mono">{r.createdDate}</b></div>
                  </div>
                  <div className="req-cr-stage">
                    <ReqBadge status={r.status}/>
                    {r.status === 'sourcing' && v && <span className="req-mini">нанято {r.hired || 0} из {r.positions} · {v.count} канд.</span>}
                    {r.status === 'done' && <span className="req-mini ok">нанято {r.hired} из {r.positions}</span>}
                  </div>
                  <Icon name="chevR" size={16} style={{color:'var(--fg-3)', flex:'none'}}/>
                </div>
              );
            })}
            {filtered.length === 0 && (
              <div className="empty-pane" style={{height:280}}>
                <div className="empty-illust"><Icon name="inbox" size={36}/></div>
                <h3>{query ? 'Ничего не найдено' : `На этапе «${stage === 'all' ? 'Все' : reqStage(stage)?.label}» пусто`}</h3>
                <p>{query ? 'Попробуйте изменить запрос.' : (isMgr ? 'Нажмите «Новая заявка», чтобы описать, кто вам нужен.' : 'Заявки появятся, когда менеджер подаст новую или вы переведёте существующую.')}</p>
              </div>
            )}
          </div>

          {detailMode && activeReq && (
            <RequestDetailPanel
              key={activeReq.id}
              req={activeReq}
              onUpdate={onUpdate}
              onClose={onCloseRequest}
              onCreateVacancy={onCreateVacancy}
              onOpenVacancy={onOpenVacancy}
              readOnly={isMgr}
              managerName={isMgr ? manager.name : null}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------- Новая заявка — страница, как создание вакансии ---------- */
function NewRequestPage({ onClose, onCreated, nextNum, manager }) {
  const [f, setF] = useStateRq({ title:'', author:'Марина Ковалёва · Руководитель отдела продаж', dept: manager ? manager.dept : '', positions:1, city:'', fmt:'Офис', deadline:'', noRush:false, salaryFrom:'', salaryTo:'', priority:'normal', desc:'' });
  const set = (k, v) => setF(s => ({ ...s, [k]: v }));
  const ok = f.title.trim() && f.desc.trim();
  const fmtDate = (iso) => iso ? iso.split('-').reverse().join('.') : '';
  const submit = () => {
    const [author, role] = manager ? [manager.name, manager.role] : f.author.split(' · ');
    const dd = f.noRush ? '' : fmtDate(f.deadline);
    const citySuffix = f.fmt === 'Офис' ? '' : ` (${f.fmt.toLowerCase()})`;
    onCreated({
      id: 'r' + Date.now(), num: nextNum, title: f.title.trim(), dept: f.dept.trim() || '—',
      author, role: role || 'Менеджер', positions: +f.positions || 1, city: (f.city.trim() || '—') + (f.city.trim() ? citySuffix : ''),
      deadline: dd ? `до ${dd}` : 'не срочно', deadlineDate: dd, createdDate: '18.07.2026', salaryFrom: f.salaryFrom.trim(), salaryTo: f.salaryTo.trim(),
      priority: f.priority, created: 'только что', status: 'new', via: manager ? 'cabinet' : 'manual',
      desc: f.desc.trim(), comments: [],
      history: [{ t: 'Сегодня', label: manager ? `Заявка подана · ${author}` : `Заявка внесена вручную · Анна Седова (со слов: ${author})` }],
    });
  };
  return (
    <div className="nv-wrap">
      <div className="nv-topbar">
        <div className="nv-crumbs">
          <span className="nv-crumb-home" onClick={onClose}><Icon name="inbox" size={13}/> Заявки</span>
          <span className="nv-crumb-sep">/</span>
          <span className="nv-crumb-cur">Новая заявка</span>
        </div>
        <div className="nv-top-actions">
          <button className="btn btn-ghost btn-sm" onClick={onClose}><Icon name="x" size={13}/> Отмена</button>
          <button className="btn btn-primary btn-sm" disabled={!ok} onClick={submit}><Icon name="check" size={13}/> Создать заявку</button>
        </div>
      </div>
      <div className="req-fp-scroll">
        <div className="req-fp-card">
          <div className="req-fp-h1">Заявка на подбор</div>
          <p className="req-fp-sub">{manager
            ? 'Опишите, кто вам нужен, — рекрутинг возьмёт заявку в работу и вернётся с уточнениями. Обязательны только два поля — остальное можно уточнить в переписке.'
            : 'Обычно менеджер подаёт заявку сам — из своего кабинета или по ссылке-форме.'}</p>
          {!manager && <p className="req-fp-sub2">Эта форма — если заявка пришла голосом или в мессенджере: внесите её со слов заказчика.</p>}
          <div className="req-fp-row2">
            <label className="req-fp-field"><span>Заказчик</span>
              {manager ? (
                <input className="nv-input" value={`${manager.name} · ${manager.role}`} disabled/>
              ) : (
                <select className="nv-input" value={f.author} onChange={e => set('author', e.target.value)}>
                  {['Марина Ковалёва · Руководитель отдела продаж','Игорь Савельев · CTO','Павел Гусев · Head of Data','Ольга Митина · Директор по маркетингу','Дмитрий Ершов · Начальник склада','Ирина Волкова · Операционный директор'].map(o => <option key={o}>{o}</option>)}
                </select>
              )}
            </label>
            <label className="req-fp-field"><span>Отдел</span><input className="nv-input" placeholder="Отдел продаж" value={f.dept} onChange={e => set('dept', e.target.value)}/></label>
          </div>
          <label className="req-fp-field"><span>Кто нужен <b className="req-fp-req">*</b></span>
            <input className="nv-input" placeholder="Например: Менеджер по продажам B2B" value={f.title} onChange={e => set('title', e.target.value)}/>
          </label>
          <div className="req-fp-row3">
            <label className="req-fp-field"><span>Сколько человек</span><input className="nv-input" type="number" min="1" value={f.positions} onChange={e => set('positions', e.target.value)}/></label>
            <label className="req-fp-field"><span>Город</span><input className="nv-input" placeholder="Москва" value={f.city} onChange={e => set('city', e.target.value)}/></label>
            <label className="req-fp-field"><span>Формат</span>
              <select className="nv-input" value={f.fmt} onChange={e => set('fmt', e.target.value)}>
                {['Офис','Гибрид','Удалённо'].map(o => <option key={o}>{o}</option>)}
              </select>
            </label>
          </div>
          <div className="req-fp-row2">
            <div className="req-fp-field"><span>К какому сроку</span>
              <div className="req-fp-inline">
                <input className="nv-input" type="date" style={{flex:1}} disabled={f.noRush} value={f.deadline} onChange={e => set('deadline', e.target.value)}/>
                <label className="req-fp-check"><input type="checkbox" checked={f.noRush} onChange={e => set('noRush', e.target.checked)}/> не срочно</label>
              </div>
            </div>
            <div className="req-fp-field"><span>Приоритет</span>
              <div className="req-fp-seg">
                <button className={f.priority === 'normal' ? 'on' : ''} onClick={() => set('priority', 'normal')}>Обычный</button>
                <button className={f.priority === 'high' ? 'on' : ''} onClick={() => set('priority', 'high')}>🔥 Срочно</button>
              </div>
            </div>
          </div>
          <div className="req-fp-field"><span>Зарплатная вилка <span className="req-fp-hint">— если не знаете, оставьте пустым: подскажем по рынку</span></span>
            <div className="req-fp-salary">
              <span className="req-fp-suf"><input className="nv-input" placeholder="от" inputMode="numeric" value={f.salaryFrom} onChange={e => set('salaryFrom', e.target.value)}/><i>₽</i></span>
              <span className="req-fp-suf"><input className="nv-input" placeholder="до" inputMode="numeric" value={f.salaryTo} onChange={e => set('salaryTo', e.target.value)}/><i>₽</i></span>
            </div>
          </div>
          <label className="req-fp-field"><span>Кратко: кто нужен и зачем <b className="req-fp-req">*</b></span>
            <textarea className="nv-input req-page-ta" rows="5" placeholder="Задачи, обязательный опыт и навыки, условия. Например: нужны два менеджера активных продаж в B2B, опыт холодных продаж от 2 лет, база лидов есть, оклад + %." value={f.desc} onChange={e => set('desc', e.target.value)}/>
          </label>
          <button className="req-fp-submit" disabled={!ok} onClick={submit}>Создать заявку</button>
          <p className="req-fp-note">{manager ? 'Рекрутер увидит заявку сразу — уточнения придут сюда и в Telegram.' : 'Заявка будет создана со статусом «Новая» от имени выбранного заказчика.'}</p>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { RequestsScreen, NewRequestPage, REQUESTS_DATA, REQ_STATUS, REQ_STAGES });
