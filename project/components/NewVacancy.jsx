// NewVacancy — создание новой вакансии в 4 шага
// Steps (chips): Описание · Воронка · Команда · Автоматизация
const { useState: useStateNV, useMemo: useMemoNV } = React;

const NV_STEPS = [
  { id: 'desc',  label: 'Описание вакансии', icon: 'briefcase' },
  { id: 'fun',   label: 'Воронка',           icon: 'funnel' },
  { id: 'team',  label: 'Команда',           icon: 'users' },
  { id: 'auto',  label: 'Автоматизация',     icon: 'sparkle' },
];

const NV_DEFAULT_STAGES = [
  { id:1, name:'Отклик',                type:'start',    desc:'Кандидат пришёл с источника. Глафира делает первичный скрининг и зовёт в чат.' },
  { id:3, name:'Добавлен',              type:'system',   desc:'Кандидат добавлен рекрутером вручную из общей базы. Системный этап, не удаляется.' },
  { id:2, name:'Отобран',               type:'middle',   desc:'Глафира посчитала кандидата подходящим — ждём контакта рекрутера.' },
  { id:4, name:'Контакт с рекрутером',  type:'middle',   desc:'Назначен/проведён звонок-знакомство.' },
  { id:5, name:'Интервью',              type:'middle',   desc:'Техническое или профильное интервью.' },
  { id:6, name:'Контакт с менеджером',  type:'middle',   desc:'Финальная встреча с заказчиком.' },
  { id:7, name:'Оффер',                 type:'middle',   desc:'Оффер выслан и согласовывается.' },
  { id:8, name:'Нанят',                 type:'finalOk',  desc:'Кандидат вышел на работу. Стартует Пульс-Онбординг.' },
  { id:9, name:'Отказ',                 type:'finalBad', desc:'Завершение по причине из справочника.' },
];

const NV_USERS = [
  { id:'u1', name:'Анна Седова',      role:'Рекрутер',             dept:'HR',          email:'a.sedova@glafira.ru' },
  { id:'u2', name:'Иван Корнев',      role:'Рекрутер',             dept:'HR',          email:'i.kornev@glafira.ru' },
  { id:'u3', name:'Мария Лосева',     role:'Нанимающий менеджер',  dept:'Engineering', email:'m.loseva@glafira.ru' },
  { id:'u4', name:'Сергей Жигалов',   role:'Нанимающий менеджер',  dept:'Engineering', email:'s.zhigalov@glafira.ru' },
  { id:'u5', name:'Ольга Кравчук',    role:'Нанимающий менеджер',  dept:'Product',     email:'o.kravchuk@glafira.ru' },
  { id:'u6', name:'Дмитрий Беляев',   role:'Нанимающий менеджер',  dept:'Marketing',   email:'d.belyaev@glafira.ru' },
  { id:'u7', name:'Екатерина Громова',role:'Тимлид',               dept:'Engineering', email:'e.gromova@glafira.ru' },
  { id:'u8', name:'Павел Орлов',      role:'Директор',             dept:'Operations',  email:'p.orlov@glafira.ru' },
];

const NV_FUNNELS = [
  { id:'def',  name:'По умолчанию' },
  { id:'mass', name:'Массовый подбор · короткая' },
  { id:'tech', name:'Техническая · с тестовым' },
  { id:'sales',name:'Продажи · 4 этапа' },
];

/* ------------ Шаг 1: Описание ------------ */
function NVStepDesc({ data, onChange }) {
  return (
    <div className="nv-step-body">
      <div className="nv-h1">Описание вакансии</div>
      <div className="nv-h2">Базовая информация — название, локация, дата закрытия. Текст требований и обязанностей.</div>

      <div className="nv-field">
        <label className="nv-label">Название вакансии <span className="nv-req">*</span></label>
        <input className="nv-input" placeholder="Например, Frontend-разработчик (Senior)"
               value={data.title} onChange={e => onChange({title: e.target.value})}/>
      </div>

      <div className="nv-field nv-field-sort">
        <label className="nv-label" title="Чем меньше число — тем выше вакансия в списке слева. По умолчанию 500.">
          Сортировка
          <span className="nv-mute" style={{fontWeight:400, marginLeft:6}}>(порядок в списке)</span>
        </label>
        <input className="nv-input t-mono" type="number" step="10" min="0"
               placeholder="500"
               value={data.sortOrder}
               onChange={e => onChange({sortOrder: e.target.value === '' ? '' : Number(e.target.value)})}/>
      </div>

      <div className="nv-grid-3">
        <div className="nv-field">
          <label className="nv-label">Город</label>
          <div className="nv-select">
            <span className={data.city ? '' : 'nv-ph'}>{data.city || 'Начните вводить город…'}</span>
            <Icon name="chevD" size={14}/>
          </div>
        </div>
        <div className="nv-field">
          <label className="nv-label">Ожидаемая дата закрытия</label>
          <div className="nv-select">
            <span className={data.deadline ? '' : 'nv-ph'}>{data.deadline || 'дд.мм.гггг'}</span>
            <Icon name="calClock" size={14}/>
          </div>
        </div>
        <div className="nv-field">
          <label className="nv-label">Кол-во позиций</label>
          <input className="nv-input" type="number" min="1" value={data.positions}
                 onChange={e => onChange({positions: Number(e.target.value)})}/>
        </div>
      </div>

      <div className="nv-grid-2">
        <div className="nv-field">
          <label className="nv-label">Отдел</label>
          <div className="nv-select">
            <span className={data.dept ? '' : 'nv-ph'}>{data.dept || 'Выберите отдел…'}</span>
            <Icon name="chevD" size={14}/>
          </div>
        </div>
        <div className="nv-field">
          <label className="nv-label">Тип занятости</label>
          <div className="nv-segmented">
            {[
              {id:'full', l:'Полная'},
              {id:'part', l:'Частичная'},
              {id:'proj', l:'Проектная'},
            ].map(o => (
              <button key={o.id}
                className={data.empType === o.id ? 'active' : ''}
                onClick={() => onChange({empType: o.id})}>{o.l}</button>
            ))}
          </div>
        </div>
      </div>

      <div className="nv-field">
        <label className="nv-toggle-row">
          <span className={`nv-switch ${data.confidential ? 'on' : ''}`}>
            <span className="nv-switch-knob"/>
          </span>
          <span>
            <b>Конфиденциальная вакансия</b>
            <span className="nv-mute"> · видна только участникам команды</span>
          </span>
        </label>
        <button className="nv-toggle-btn"
                onClick={() => onChange({confidential: !data.confidential})}
                style={{display:'none'}} aria-hidden="true"/>
      </div>

      <div className="nv-field">
        <label className="nv-label">Зарплатная вилка</label>
        <div className="nv-grid-2-tight">
          <div className="nv-input-wrap">
            <input className="nv-input" placeholder="от" value={data.salaryFrom}
                   onChange={e => onChange({salaryFrom: e.target.value})}/>
            <span className="nv-suffix">₽</span>
          </div>
          <div className="nv-input-wrap">
            <input className="nv-input" placeholder="до" value={data.salaryTo}
                   onChange={e => onChange({salaryTo: e.target.value})}/>
            <span className="nv-suffix">₽</span>
          </div>
        </div>
      </div>

      <div className="nv-field">
        <label className="nv-label">Требования, обязанности, условия</label>
        <div className="nv-editor">
          <div className="nv-toolbar">
            {['B','I','U'].map(t => <button key={t} className="nv-tb-btn" style={{fontWeight:t==='B'?700:500, fontStyle:t==='I'?'italic':'normal', textDecoration:t==='U'?'underline':'none'}}>{t}</button>)}
            <span className="nv-tb-sep"/>
            <button className="nv-tb-btn"><Icon name="sort" size={14}/></button>
            <button className="nv-tb-btn">•</button>
            <button className="nv-tb-btn">1.</button>
            <span className="nv-tb-sep"/>
            <button className="nv-tb-btn">link</button>
          </div>
          <textarea className="nv-textarea"
            placeholder="Требования:&#10;Обязанности:&#10;Условия работы:"
            value={data.body} onChange={e => onChange({body: e.target.value})}/>
        </div>
      </div>
    </div>
  );
}

/* ------------ Шаг 2: Воронка ------------ */
function NVStepFunnel({ stages, onChange }) {
  const move = (idx, dir) => {
    const next = stages.slice();
    const j = idx + dir;
    if (j < 1 || j > next.length - 2) return; // нельзя двигать в зоны 1-го и 2 последних
    if (idx === 0 || idx >= next.length - 2) return;
    [next[idx], next[j]] = [next[j], next[idx]];
    onChange(next);
  };

  const remove = (idx) => {
    const s = stages[idx];
    if (idx === 0 || s.type === 'finalOk' || s.type === 'finalBad') return;
    onChange(stages.filter((_, i) => i !== idx));
  };

  const add = () => {
    const newStage = {
      id: Date.now(),
      name: 'Новый этап',
      type: 'middle',
      desc: 'Опишите, что происходит на этом этапе.',
    };
    // вставляем перед двумя последними финальными
    const idx = stages.length - 2;
    const next = stages.slice();
    next.splice(idx, 0, newStage);
    onChange(next);
  };

  return (
    <div className="nv-step-body">
      <div className="nv-h1">Воронка подбора</div>
      <div className="nv-h2">Этапы, по которым пойдёт кандидат. По умолчанию — шаблон из настроек. Можно переставлять и добавлять — кроме первого и двух последних финальных этапов.</div>

      <div className="nv-banner">
        <Icon name="sparkle" size={16}/>
        <div>
          <b>Совет.</b> Чем короче воронка, тем быстрее закрытие. Для массового подбора достаточно 3-4 этапов.
        </div>
      </div>

      <div className="funnel-editor">
        {stages.map((s, idx) => {
          const t = FUNNEL_STAGE_TYPES[s.type] || { label: 'Промежуточный', dot:'#9AA3AE', bg:'#ECEFF2', fg:'#3A4452' };
          const isFinal = s.type === 'finalOk' || s.type === 'finalBad';
          const isFirst = idx === 0;
          const isSystem = s.type === 'system';
          const locked = isFirst || isFinal || isSystem;
          return (
            <div key={s.id} className={`fn-stage ${isFinal ? 'fn-final' : ''}`}>
              <div className="nv-fn-arrows">
                <button className="nv-fn-arr"
                        disabled={locked || idx <= 1}
                        title={locked ? 'Этап зафиксирован' : 'Выше'}
                        onClick={() => move(idx, -1)}>▲</button>
                <button className="nv-fn-arr"
                        disabled={locked || idx >= stages.length - 3}
                        title={locked ? 'Этап зафиксирован' : 'Ниже'}
                        onClick={() => move(idx, 1)}>▼</button>
              </div>
              <div className="fn-num">{idx+1}</div>
              <div className="fn-body">
                <div className="fn-row1">
                  <input className="fn-name" defaultValue={s.name}
                         onChange={(e) => {
                           const next = stages.slice();
                           next[idx] = {...s, name: e.target.value};
                           onChange(next);
                         }}/>
                  <span className="stage-type-pill" style={{background:t.bg, color:t.fg}}>
                    <span className="st-dot" style={{background:t.dot}}/>{t.label}
                  </span>
                  {locked && (
                    <span className="nv-locked-pill" title="Зафиксирован">
                      <Icon name="pin" size={11}/> закреплён
                    </span>
                  )}
                </div>
                <div className="fn-desc">{s.desc}</div>
              </div>
              <button className="row-icon-btn"
                      disabled={locked}
                      onClick={() => remove(idx)}
                      title={locked ? 'Этап нельзя удалить' : 'Удалить этап'}>
                <Icon name="x" size={14}/>
              </button>
            </div>
          );
        })}
        <button className="fn-add" onClick={add}>
          <Icon name="plus" size={14}/> Добавить этап
        </button>
      </div>
    </div>
  );
}

/* ------------ Шаг 3: Команда ------------ */
function NVStepTeam({ team, onChange }) {
  const [query, setQuery] = useStateNV('');
  const [roleFilter, setRoleFilter] = useStateNV('all');

  const filtered = useMemoNV(() => NV_USERS.filter(u => {
    if (roleFilter === 'rec' && !u.role.toLowerCase().includes('рекрут')) return false;
    if (roleFilter === 'mgr' && !u.role.toLowerCase().includes('менеджер')) return false;
    if (query && !`${u.name} ${u.email} ${u.dept}`.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  }), [query, roleFilter]);

  const toggle = (uid) => {
    if (team.includes(uid)) onChange(team.filter(x => x !== uid));
    else onChange([...team, uid]);
  };

  const owner = team[0];

  return (
    <div className="nv-step-body">
      <div className="nv-h1">Команда вакансии</div>
      <div className="nv-h2">Кто видит вакансию, ведёт кандидатов и принимает решения. Первый добавленный — ответственный рекрутер.</div>

      <div className="nv-team-toolbar">
        <div className="nv-search">
          <Icon name="search" size={14} style={{color:'var(--fg-3)'}}/>
          <input placeholder="Поиск по имени, email или отделу…"
                 value={query} onChange={e => setQuery(e.target.value)}/>
        </div>
        <div className="seg-sm">
          <button className={roleFilter==='all'?'active':''} onClick={() => setRoleFilter('all')}>Все</button>
          <button className={roleFilter==='rec'?'active':''} onClick={() => setRoleFilter('rec')}>Рекрутеры</button>
          <button className={roleFilter==='mgr'?'active':''} onClick={() => setRoleFilter('mgr')}>Менеджеры</button>
        </div>
      </div>

      {team.length > 0 && (
        <div className="nv-team-selected">
          <div className="nv-team-selhead">Выбраны · {team.length}</div>
          <div className="nv-team-chips">
            {team.map(uid => {
              const u = NV_USERS.find(x => x.id === uid);
              if (!u) return null;
              return (
                <div key={uid} className={`nv-team-chip ${uid === owner ? 'owner' : ''}`}>
                  <Avatar name={u.name} size="sm"/>
                  <div className="nv-tc-text">
                    <div className="nv-tc-name">{u.name}{uid === owner && <span className="nv-owner-badge">владелец</span>}</div>
                    <div className="nv-tc-role">{u.role}</div>
                  </div>
                  <button className="nv-tc-x" onClick={() => toggle(uid)}><Icon name="x" size={12}/></button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="nv-user-list">
        {filtered.length === 0 ? (
          <div className="nv-empty">Никого не найдено по запросу «{query}».</div>
        ) : filtered.map(u => {
          const on = team.includes(u.id);
          return (
            <div key={u.id} className={`nv-user-row ${on ? 'on' : ''}`} onClick={() => toggle(u.id)}>
              <span className={`nv-check ${on ? 'on' : ''}`}>{on && <Icon name="check" size={11}/>}</span>
              <Avatar name={u.name} size="md"/>
              <div className="nv-ur-text">
                <div className="nv-ur-name">{u.name}</div>
                <div className="nv-ur-meta">{u.role} <span className="sep">·</span> {u.dept}</div>
              </div>
              <div className="nv-ur-email">{u.email}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ------------ Шаг 4: Автоматизация ------------ */
function NVStepAuto({ data, onChange, stages }) {
  // Этапы воронки вакансии (берутся со шага 2). Исключаем стартовый и финальные для логики "из/в".
  const stageOpts = (stages || NV_DEFAULT_STAGES);
  const [openSel, setOpenSel] = useStateNV(null); // id текущего открытого селекта

  // Утилита: рендер плашки с переключателем. Контент серый и заблокирован, пока не активен.
  const Block = ({ keyOn, title, children }) => (
    <div className={`nv-auto-block ${data[keyOn] ? '' : 'off'}`}>
      <div className="nv-auto-head" onClick={() => onChange({[keyOn]: !data[keyOn]})}>
        <span className={`nv-cb ${data[keyOn] ? 'on' : ''}`}>
          {data[keyOn] && <Icon name="check" size={12}/>}
        </span>
        <span className="nv-auto-title">{title}</span>
      </div>
      <div className="nv-auto-body" onClick={e => e.stopPropagation()}>{children}</div>
    </div>
  );

  // Dropdown селект этапа воронки вакансии
  const StageSelect = ({ id, value, onChange: oc, options }) => {
    const list = options || stageOpts;
    const cur = list.find(s => s.id === value) || list[0];
    const isOpen = openSel === id;
    return (
      <div className={`nv-stage-select ${isOpen ? 'open' : ''}`}>
        <button type="button" className="nv-stage-trigger"
                onClick={() => setOpenSel(isOpen ? null : id)}>
          <span className={`nv-stage-dot t-${cur?.type || 'middle'}`}/>
          <span className="nv-stage-name">{cur?.name || '—'}</span>
          <Icon name="chevD" size={12}/>
        </button>
        {isOpen && (
          <>
            <div className="nv-stage-backdrop" onClick={() => setOpenSel(null)}/>
            <div className="nv-stage-menu">
              {list.map(s => (
                <button key={s.id} type="button"
                        className={`nv-stage-opt ${s.id === value ? 'sel' : ''}`}
                        onClick={() => { oc && oc(s.id); setOpenSel(null); }}>
                  <span className={`nv-stage-dot t-${s.type}`}/>
                  <span className="nv-stage-name">{s.name}</span>
                  {s.id === value && <Icon name="check" size={12} className="nv-stage-check"/>}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="nv-step-body">
      <div className="nv-h1">Автоматизация</div>
      <div className="nv-h2">Глафира будет действовать сама — переводить кандидатов, задавать уточняющие вопросы и закрывать карточки. Включайте по необходимости.</div>

      <Block keyOn="autoMove" title="Автоматический перевод по AI-скорингу">
        <div className="nv-auto-inline">
          <span>Автоматически переводить на этап</span>
          <StageSelect id="autoMoveStage" value={data.autoMoveStage}
                       onChange={v => onChange({autoMoveStage: v})}/>
          <span>при скоринге AI &gt;</span>
          <input className="nv-num-input" type="number" min="0" max="100"
                 value={data.autoMoveThreshold}
                 onChange={e => onChange({autoMoveThreshold: Math.max(0, Math.min(100, Number(e.target.value)))})}/>
          <span className="nv-mute">из 100</span>
        </div>
        <div className="nv-auto-hint">
          <Icon name="sparkle" size={12}/>
          Сейчас порог <b>{data.autoMoveThreshold}</b> — это «сильное совпадение». Глафира двигает только уверенных кандидатов.
        </div>
      </Block>

      <Block keyOn="autoQA" title="Уточняющие вопросы и автоперевод">
        <div className="nv-auto-inline">
          <span>Если карточка на этапе</span>
          <StageSelect id="autoQAFrom" value={data.autoQAFromStage}
                       onChange={v => onChange({autoQAFromStage: v})}/>
          <span>— Глафира задаёт уточняющие вопросы.</span>
        </div>
        <div className="nv-auto-inline">
          <span>При получении ответов переводит на этап</span>
          <StageSelect id="autoQATo" value={data.autoQAToStage}
                       onChange={v => onChange({autoQAToStage: v})}/>
        </div>
        <div className="nv-auto-hint">
          <Icon name="sparkle" size={12}/>
          Полезно, когда в отклике мало данных — например, нет опыта или зарплаты.
        </div>
      </Block>

      <Block keyOn="autoReject" title="Автоматический отказ при неинтересе">
        <div className="nv-auto-text">
          Если LLM по диалогу понимает, что вакансия кандидату <b>не интересна</b> или он <b>принял другой оффер</b>, Глафира сама переведёт его в «Отказ» с соответствующей причиной.
        </div>
        <div className="nv-reasons-row">
          <span className="nv-reason-pill"><span className="nv-rp-dot grey"/>Не интересно</span>
          <span className="nv-reason-pill"><span className="nv-rp-dot grey"/>Принял оффер</span>
        </div>
      </Block>
    </div>
  );
}

/* ------------ Главный экран ------------ */
function NewVacancy({ onClose, onCreated, initial, editMode }) {
  const [active, setActive] = useStateNV('desc');
  const idx = NV_STEPS.findIndex(s => s.id === active);

  const init = initial || {};
  const [desc, setDesc] = useStateNV({
    title:'', sortOrder:500, city:'', deadline:'', positions:1, dept:'', empType:'full',
    confidential:false, salaryFrom:'', salaryTo:'', body:'',
    ...(init.desc || {}),
  });
  const [stages, setStages] = useStateNV(init.stages || NV_DEFAULT_STAGES);
  const [team, setTeam] = useStateNV(init.team || ['u1']);
  const [auto, setAuto] = useStateNV({
    autoMove:false, autoMoveStage:3, autoMoveThreshold:80,
    autoQA:false, autoQAFromStage:1, autoQAToStage:2,
    autoReject:false,
    ...(init.auto || {}),
  });

  const goNext = () => {
    if (idx < NV_STEPS.length - 1) setActive(NV_STEPS[idx+1].id);
    else onCreated && onCreated();
  };
  const goPrev = () => {
    if (idx > 0) setActive(NV_STEPS[idx-1].id);
    else onClose && onClose();
  };

  let body;
  if (active === 'desc')   body = <NVStepDesc data={desc} onChange={p => setDesc({...desc, ...p})}/>;
  else if (active === 'fun')  body = <NVStepFunnel stages={stages} onChange={setStages}/>;
  else if (active === 'team') body = <NVStepTeam team={team} onChange={setTeam}/>;
  else if (active === 'auto') body = <NVStepAuto data={auto} onChange={p => setAuto({...auto, ...p})} stages={stages}/>;

  // прогресс-чипсы (правая колонка)
  const completion = {
    desc: desc.title.trim().length > 0,
    fun:  stages.length >= 3,
    team: team.length > 0,
    auto: true,
  };

  return (
    <div className="nv-wrap">
      <div className="nv-topbar">
        <div className="nv-crumbs">
          <span className="nv-crumb-home" onClick={onClose}>
            <Icon name="chevL" size={14}/> Вакансии
          </span>
          <span className="nv-crumb-sep">/</span>
          <span className="nv-crumb-cur">{editMode ? 'Редактирование вакансии' : 'Создание вакансии'}</span>
        </div>
        <div className="nv-top-actions">
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            <Icon name="x" size={13}/> Отмена
          </button>
          <button className="btn btn-secondary btn-sm">Сохранить черновик</button>
        </div>
      </div>

      {/* Чипсы шагов — 1:1 как воронка в списке вакансий, только индикация (без кликов) */}
      <div className="funnel-row nv-funnel-row">
        {NV_STEPS.map((s, i) => {
          const isActive = s.id === active;
          const isDone = completion[s.id] && !isActive && i < idx;
          return (
            <React.Fragment key={s.id}>
              <div className={`funnel-chip nv-chip-readonly ${isActive ? 'active' : ''} ${isDone ? 'funnel-hired' : ''}`}>
                {isDone
                  ? <Icon name="check" size={12}/>
                  : <span className="nv-step-num">{i+1}</span>}
                {s.label}
              </div>
              {i < NV_STEPS.length - 1 && <Icon name="chevR" size={12} className="funnel-arrow"/>}
            </React.Fragment>
          );
        })}
      </div>

      {/* Форма на всю ширину — кнопки внутри карточки */}
      <div className="nv-grid">
        <div className="nv-card nv-card-full">
          {body}

          <div className="nv-card-foot">
            {idx > 0 ? (
              <button className="btn btn-secondary btn-sm" onClick={goPrev}>
                <Icon name="chevL" size={13}/> Назад
              </button>
            ) : <div/>}
            <div className="nv-foot-progress">
              Шаг <b>{idx+1}</b> из <b>{NV_STEPS.length}</b>
            </div>
            <button className="btn btn-primary btn-sm" onClick={goNext}>
              <Icon name="arrowRight" size={14}/>
              {idx === NV_STEPS.length - 1 ? (editMode ? 'Сохранить' : 'Создать вакансию') : 'Далее'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { NewVacancy, NV_STEPS, NV_DEFAULT_STAGES, NV_USERS, NV_FUNNELS });
