// NewCandidate — добавление кандидата (full-screen форма в стиле NewVacancy)
const { useState: useStateNC } = React;

const NC_SOURCES = [
  { id:'hh',      name:'HeadHunter' },
  { id:'avito',   name:'Avito Работа' },
  { id:'super',   name:'SuperJob' },
  { id:'tg',      name:'Telegram-канал' },
  { id:'ref',     name:'Реферальная программа' },
  { id:'direct',  name:'Прямой контакт' },
  { id:'agency',  name:'Кадровое агентство' },
  { id:'other',   name:'Другое' },
];

const NC_ADD_TYPES = [
  { id:'manual',  name:'Ручное добавление' },
  { id:'resume',  name:'Из резюме' },
  { id:'pool',    name:'Из общей базы' },
  { id:'hh-link', name:'По ссылке HH' },
];

const NC_SOCIAL_TYPES = [
  { id:'tg',  name:'Telegram',  icon:'send',     prefix:'https://t.me/' },
  { id:'wa',  name:'WhatsApp',  icon:'phone',    prefix:'https://wa.me/' },
  { id:'mx',  name:'Max',       icon:'send',     prefix:'https://max.ru/' },
  { id:'vk',  name:'VK',        icon:'users',    prefix:'https://vk.com/' },
  { id:'in',  name:'LinkedIn',  icon:'open',     prefix:'https://linkedin.com/in/' },
];

const NC_VACANCIES = [
  { id:'fe',   name:'Frontend-разработчик (Senior)' },
  { id:'rm',   name:'Региональный менеджер по продажам' },
  { id:'pm',   name:'Product Manager · CRM' },
  { id:'des',  name:'Дизайнер · Design System' },
  { id:'ds',   name:'Data Scientist · ML' },
];

function NCDropdown({ id, value, onChange, options, placeholder, openId, setOpenId }) {
  const cur = options.find(o => o.id === value);
  const isOpen = openId === id;
  return (
    <div className={`nv-dd ${isOpen ? 'open' : ''}`}>
      <button type="button" className="nv-dd-trigger"
              onClick={() => setOpenId(isOpen ? null : id)}>
        <span className={`nv-dd-name ${cur ? '' : 'ph'}`}>{cur ? cur.name : (placeholder || 'Выберите значение')}</span>
        <Icon name="chevD" size={12}/>
      </button>
      {isOpen && (
        <>
          <div className="nv-dd-backdrop" onClick={() => setOpenId(null)}/>
          <div className="nv-dd-menu">
            {options.map(o => (
              <button key={o.id} type="button"
                      className={`nv-dd-opt ${o.id === value ? 'sel' : ''}`}
                      onClick={() => { onChange(o.id); setOpenId(null); }}>
                <span>{o.name}</span>
                {o.id === value && <Icon name="check" size={12} className="nv-dd-check"/>}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function NewCandidate({ vacancyId, onClose, onCreated }) {
  const [openDD, setOpenDD] = useStateNC(null);
  const [data, setData] = useStateNC({
    last:'', first:'', mid:'',
    phone:'', email:'',
    gender:'unset',
    birth:'',
    city:'',
    salary:'', currency:'rub',
    source:'', addType:'manual',
    socialType:'tg', socialUrl:'',
    targetVacancy: vacancyId || 'rm',
    comment:'',
  });
  const set = (p) => setData({...data, ...p});

  const targetName = NC_VACANCIES.find(v => v.id === data.targetVacancy)?.name || '—';
  const valid = data.last.trim() && data.first.trim() && data.source;

  return (
    <div className="nv-wrap">
      <div className="nv-topbar">
        <div className="nv-crumbs">
          <span className="nv-crumb-home" onClick={onClose}>
            <Icon name="chevL" size={14}/> Назад
          </span>
          <span className="nv-crumb-sep">/</span>
          <span className="nv-crumb-cur">Добавить кандидата</span>
        </div>
        <div className="nv-top-actions">
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            <Icon name="x" size={13}/> Отмена
          </button>
        </div>
      </div>

      <div className="nv-grid">
        <div className="nv-card nv-card-full">
          <div className="nv-step-body">
            <div className="nv-h1">Новый кандидат</div>
            <div className="nv-h2">Заполните основное и приложите резюме. Глафира распарсит документ и подтянет недостающие поля автоматически.</div>

            {/* Шапка: аватар + дроп-зона резюме + импорт Excel */}
            <div className="nc-head">
              <div className="nc-avatar">
                <Icon name="users" size={26}/>
                <div className="nc-avatar-cam"><Icon name="open" size={11}/></div>
              </div>
              <label className="nc-drop">
                <Icon name="open" size={20} className="nc-drop-icon"/>
                <div className="nc-drop-text">
                  <span className="nc-drop-title">
                    Перетащите резюме или <span className="nc-drop-link">загрузите файл</span>
                  </span>
                  <span className="nc-drop-fmt">PDF · DOC · DOCX · RTF — до 10 МБ</span>
                </div>
                <input type="file" accept=".pdf,.doc,.docx,.rtf" hidden/>
              </label>
              <label className="nc-xls">
                <Icon name="chart" size={16} className="nc-xls-icon"/>
                <span className="nc-xls-text">
                  <span className="nc-xls-title">Импорт из Excel</span>
                  <span className="nc-xls-sub">XLSX, до 500 строк</span>
                </span>
                <input type="file" accept=".xlsx,.xls,.csv" hidden/>
              </label>
            </div>

            {/* Привязка к вакансии */}
            <div className="nv-field">
              <label className="nv-label">Добавить в вакансию <span className="nv-req">*</span></label>
              <NCDropdown id="vac" value={data.targetVacancy}
                          onChange={v => set({targetVacancy: v})}
                          options={NC_VACANCIES}
                          openId={openDD} setOpenId={setOpenDD}/>
            </div>

            {/* Источник */}
            <div className="nv-field">
              <label className="nv-label">
                Источник <span className="nv-req">*</span>
                <span className="nv-mute" style={{fontWeight:400, marginLeft:6}}>· откуда узнали о кандидате</span>
              </label>
              <NCDropdown id="src" value={data.source}
                          onChange={v => set({source: v})}
                          options={NC_SOURCES} placeholder="Выберите источник…"
                          openId={openDD} setOpenId={setOpenDD}/>
            </div>

            {/* ФИО */}
            <div className="nv-grid-3">
              <div className="nv-field">
                <label className="nv-label">Фамилия <span className="nv-req">*</span></label>
                <input className="nv-input" value={data.last} onChange={e => set({last:e.target.value})}/>
              </div>
              <div className="nv-field">
                <label className="nv-label">Имя <span className="nv-req">*</span></label>
                <input className="nv-input" value={data.first} onChange={e => set({first:e.target.value})}/>
              </div>
              <div className="nv-field">
                <label className="nv-label">Отчество</label>
                <input className="nv-input" value={data.mid} onChange={e => set({mid:e.target.value})}/>
              </div>
            </div>

            {/* Телефон + email */}
            <div className="nv-grid-2">
              <div className="nv-field">
                <label className="nv-label">Телефон</label>
                <div className="nc-phone">
                  <span className="nc-phone-flag">🇷🇺</span>
                  <input className="nv-input" placeholder="+7 (___) ___-__-__"
                         value={data.phone} onChange={e => set({phone:e.target.value})}/>
                </div>
              </div>
              <div className="nv-field">
                <label className="nv-label">E-mail</label>
                <input className="nv-input" type="email" placeholder="name@example.com"
                       value={data.email} onChange={e => set({email:e.target.value})}/>
              </div>
            </div>

            {/* Пол / ДР / Город */}
            <div className="nv-grid-3">
              <div className="nv-field">
                <label className="nv-label">Пол</label>
                <div className="nv-segmented" style={{display:'flex'}}>
                  <button type="button" className={data.gender === 'f' ? 'active' : ''}
                          onClick={() => set({gender:'f'})}>Жен.</button>
                  <button type="button" className={data.gender === 'm' ? 'active' : ''}
                          onClick={() => set({gender:'m'})}>Муж.</button>
                  <button type="button" className={data.gender === 'unset' ? 'active' : ''}
                          onClick={() => set({gender:'unset'})}>Не указан</button>
                </div>
              </div>
              <div className="nv-field">
                <label className="nv-label">Дата рождения</label>
                <input className="nv-input" placeholder="ДД.ММ.ГГГГ"
                       value={data.birth} onChange={e => set({birth:e.target.value})}/>
              </div>
              <div className="nv-field">
                <label className="nv-label">Город проживания</label>
                <input className="nv-input" placeholder="Введите название"
                       value={data.city} onChange={e => set({city:e.target.value})}/>
              </div>
            </div>

            {/* ЗП / Тип добавления */}
            <div className="nv-grid-2">
              <div className="nv-field">
                <label className="nv-label">Ожидаемая ЗП</label>
                <div className="nc-salary">
                  <input className="nv-input" type="number" placeholder="0"
                         value={data.salary} onChange={e => set({salary:e.target.value})}/>
                  <NCDropdown id="cur" value={data.currency}
                              onChange={v => set({currency: v})}
                              options={[{id:'rub',name:'руб.'},{id:'usd',name:'$'},{id:'eur',name:'€'}]}
                              openId={openDD} setOpenId={setOpenDD}/>
                </div>
              </div>
              <div className="nv-field">
                <label className="nv-label">Тип добавления</label>
                <NCDropdown id="atp" value={data.addType}
                            onChange={v => set({addType: v})}
                            options={NC_ADD_TYPES}
                            openId={openDD} setOpenId={setOpenDD}/>
              </div>
            </div>

            {/* Соц.сети */}
            <div className="nv-field">
              <label className="nv-label">Социальные сети</label>
              <div className="nc-social">
                <NCDropdown id="soc" value={data.socialType}
                            onChange={v => set({socialType: v, socialUrl:''})}
                            options={NC_SOCIAL_TYPES}
                            openId={openDD} setOpenId={setOpenDD}/>
                <input className="nv-input" placeholder={NC_SOCIAL_TYPES.find(s => s.id === data.socialType)?.prefix || ''}
                       value={data.socialUrl} onChange={e => set({socialUrl:e.target.value})}/>
              </div>
            </div>

            {/* Комментарий */}
            <div className="nv-field">
              <label className="nv-label">Комментарий</label>
              <textarea className="nv-textarea" rows="3"
                        placeholder="Заметка для команды — что обсудили, какой стек, причина обращения…"
                        value={data.comment} onChange={e => set({comment:e.target.value})}/>
            </div>
          </div>

          <div className="nv-card-foot">
            <button className="btn btn-secondary btn-sm" onClick={onClose}>
              <Icon name="chevL" size={13}/> Отмена
            </button>
            <div className="nv-foot-progress">
              Кандидат → <b>{targetName}</b>
            </div>
            <button className={`btn btn-primary btn-sm ${valid ? '' : 'is-disabled'}`}
                    disabled={!valid}
                    onClick={() => onCreated && onCreated(data)}>
              <Icon name="plus" size={14}/> Добавить кандидата
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { NewCandidate, NC_SOURCES, NC_ADD_TYPES, NC_SOCIAL_TYPES, NC_VACANCIES });
