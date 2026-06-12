// Settings — Раздел «Настройки»
// 3-column layout: app sidebar | settings submenu | content
const { useState: useStateSet, useMemo: useMemoSet } = React;

const SET_SECTIONS = [
  { id: 'profile',      label: 'Профиль',                icon: 'user',     adminOnly: false },
  { id: 'general',      label: 'Общие',                  icon: 'settings', adminOnly: true  },
  { id: 'funnel',       label: 'Воронка по умолчанию',   icon: 'funnel',   adminOnly: true  },
  { id: 'access',       label: 'Права доступа',          icon: 'users',    adminOnly: true  },
  { id: 'tags',         label: 'Теги',                   icon: 'pin',      adminOnly: false },
  { id: 'integrations', label: 'Интеграции',             icon: 'antenna',  adminOnly: true  },
  { id: 'ai',           label: 'AI',                     icon: 'sparkle',  adminOnly: true  },
];

function SettingsTopTabs({ active, onChange, isAdmin }) {
  const visible = SET_SECTIONS.filter(s => isAdmin || !s.adminOnly);
  return (
    <div className="set-toptabs">
      {visible.map(s => (
        <button key={s.id}
          className={`set-toptab ${active === s.id ? 'active' : ''}`}
          onClick={() => onChange(s.id)}>
          {s.label}
        </button>
      ))}
    </div>
  );
}

/* ----------------- Reusable form bits ----------------- */
function FormRow({ label, hint, required, children, span }) {
  return (
    <div className={`fld ${span === 2 ? 'fld-span2' : ''}`}>
      {label && (
        <label className="fld-lbl">
          {label}
          {required && <span className="req">*</span>}
        </label>
      )}
      <div className="fld-ctrl">{children}</div>
      {hint && <div className="fld-hint">{hint}</div>}
    </div>
  );
}
function TextInput({ value, placeholder, onChange, type='text', mono, suffix, locked }) {
  return (
    <div className={`txt ${mono ? 'txt-mono' : ''} ${locked ? 'txt-locked' : ''}`}>
      <input type={type} value={value ?? ''} placeholder={placeholder}
        onChange={e => onChange && onChange(e.target.value)} readOnly={locked}/>
      {suffix && <span className="txt-suffix">{suffix}</span>}
    </div>
  );
}
function Textarea({ value, placeholder, rows=3, onChange }) {
  return (
    <textarea className="txt-area" rows={rows} value={value ?? ''} placeholder={placeholder}
      onChange={e => onChange && onChange(e.target.value)}/>
  );
}
function Select({ value, options, onChange, placeholder }) {
  return (
    <div className="sel">
      <select value={value ?? ''} onChange={e => onChange && onChange(e.target.value)}>
        {placeholder && <option value="" disabled>{placeholder}</option>}
        {options.map(o => <option key={o.value ?? o} value={o.value ?? o}>{o.label ?? o}</option>)}
      </select>
      <Icon name="chevD" size={14}/>
    </div>
  );
}
function Switch({ value, onChange, label, desc }) {
  return (
    <label className="sw-row">
      <button type="button" className={`sw ${value ? 'on' : ''}`}
        onClick={() => onChange && onChange(!value)} aria-pressed={!!value}>
        <span className="sw-knob"/>
      </button>
      <div className="sw-text">
        {label && <div className="sw-label">{label}</div>}
        {desc && <div className="sw-desc">{desc}</div>}
      </div>
    </label>
  );
}
function Radio({ checked, onChange, label, desc, right }) {
  return (
    <label className={`rd-row ${checked ? 'on' : ''}`} onClick={() => onChange && onChange()}>
      <span className={`rd ${checked ? 'on' : ''}`}><span/></span>
      <div className="rd-text">
        <div className="rd-label">{label}</div>
        {desc && <div className="rd-desc">{desc}</div>}
      </div>
      {right}
    </label>
  );
}

function PageHead({ title, subtitle, dirty, onSave }) {
  return (
    <div className="set-page-head">
      <div>
        <h1 className="set-h1">{title}</h1>
        {subtitle && <div className="set-sub">{subtitle}</div>}
      </div>
      <div className="set-head-actions">
        {dirty && <span className="dirty-pill">Есть несохранённые изменения</span>}
        <button className={`btn ${dirty ? 'btn-primary' : 'btn-secondary'}`}
          disabled={!dirty} onClick={onSave}>Сохранить изменения</button>
      </div>
    </div>
  );
}

function Card({ title, desc, children, foot }) {
  return (
    <section className="set-card">
      {(title || desc) && (
        <header className="set-card-head">
          {title && <div className="set-card-title">{title}</div>}
          {desc && <div className="set-card-desc">{desc}</div>}
        </header>
      )}
      <div className="set-card-body">{children}</div>
      {foot && <footer className="set-card-foot">{foot}</footer>}
    </section>
  );
}

/* ============================================================
   1. PROFILE
   ============================================================ */
function SettingsProfile() {
  const [dirty, setDirty] = useStateSet(false);
  const [form, setForm] = useStateSet({
    fio: 'Анна Седова',
    role: 'Старший рекрутер',
    email: 'anna.sedova@company.ru',
    phone: '+7 (916) 482-30-15',
    city: 'Москва (UTC+3)',
    lang: 'ru',
  });
  const upd = (k, v) => { setForm({ ...form, [k]: v }); setDirty(true); };

  return (
    <div className="set-content-inner">
      <PageHead title="Мой профиль"
        subtitle="Личные данные, безопасность и уведомления"
        dirty={dirty} onSave={() => setDirty(false)}/>

      <Card title="Аватар и основные данные">
        <div className="profile-avatar-row">
          <div className="big-avatar">
            <Avatar name={form.fio} size="lg"/>
          </div>
          <div className="avatar-actions">
            <button className="btn btn-secondary btn-sm">Загрузить фото</button>
            <button className="btn btn-ghost btn-sm">Удалить</button>
            <div className="t-caption" style={{marginTop:6}}>JPG / PNG, до 4МБ. Квадратное, мин. 200×200.</div>
          </div>
        </div>
        <div className="form-grid form-grid-2">
          <FormRow label="ФИО" required>
            <TextInput value={form.fio} onChange={v => upd('fio', v)}/>
          </FormRow>
          <FormRow label="Должность">
            <TextInput value={form.role} onChange={v => upd('role', v)} placeholder="Например, Senior Recruiter"/>
          </FormRow>
          <FormRow label="Email" required hint="На этот адрес приходят уведомления и приглашения">
            <TextInput value={form.email} type="email" onChange={v => upd('email', v)}/>
          </FormRow>
          <FormRow label="Телефон">
            <TextInput value={form.phone} onChange={v => upd('phone', v)} placeholder="+7 (___) ___-__-__"/>
          </FormRow>
          <FormRow label="Город / часовой пояс">
            <Select value={form.city} onChange={v => upd('city', v)}
              options={['Москва (UTC+3)','Санкт-Петербург (UTC+3)','Екатеринбург (UTC+5)','Новосибирск (UTC+7)','Владивосток (UTC+10)']}/>
          </FormRow>
          <FormRow label="Язык интерфейса">
            <Select value={form.lang} onChange={v => upd('lang', v)}
              options={[{value:'ru', label:'Русский'},{value:'en', label:'English'}]}/>
          </FormRow>
        </div>
      </Card>

      <Card title="Безопасность">
        <div className="action-row">
          <div>
            <div className="ar-title">Пароль</div>
            <div className="ar-desc">Последняя смена: 14 февраля 2026 г.</div>
          </div>
          <button className="btn btn-secondary">Сменить пароль</button>
        </div>
      </Card>

      <Card title="Уведомления" desc="Каналы доставки и события, по которым вам приходят оповещения">
        <div className="notif-table">
          <div className="notif-thead">
            <div>Событие</div>
            <div>Email</div>
            <div>Telegram</div>
            <div>Push</div>
          </div>
          {[
            ['Новый отклик на мою вакансию', true, true, false],
            ['Глафира квалифицировала кандидата', true, true, true],
            ['Кандидат перешёл на этап «Оффер»', true, false, true],
            ['Заказчик оставил оценку', true, true, false],
            ['Ежедневный дайджест по почте', true, false, false],
            ['Еженедельный отчёт', true, false, false],
          ].map((r, i) => (
            <div key={i} className="notif-row">
              <div className="notif-evt">{r[0]}</div>
              <div><Switch value={r[1]} onChange={() => setDirty(true)}/></div>
              <div><Switch value={r[2]} onChange={() => setDirty(true)}/></div>
              <div><Switch value={r[3]} onChange={() => setDirty(true)}/></div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

/* ============================================================
   2. GENERAL
   ============================================================ */
function SettingsGeneral({ hasBitrix }) {
  const [dirty, setDirty] = useStateSet(false);
  const [src, setSrc] = useStateSet(hasBitrix ? 'b24' : 'none');
  const [importOn, setImportOn] = useStateSet(hasBitrix);
  const [autoRole, setAutoRole] = useStateSet(true);
  const dirty2 = (cb) => (...a) => { setDirty(true); cb && cb(...a); };

  return (
    <div className="set-content-inner">
      <PageHead title="Общие настройки"
        subtitle="Системные константы, источник данных о текучке и импорт пользователей"
        dirty={dirty} onSave={() => setDirty(false)}/>

      <Card title="Компания">
        <div className="form-grid form-grid-2">
          <FormRow label="Название компании" required>
            <TextInput value="ООО «Логос-Ритейл»" onChange={dirty2()}/>
          </FormRow>
          <FormRow label="Юридическое название">
            <TextInput value="Общество с ограниченной ответственностью «Логос-Ритейл»" onChange={dirty2()}/>
          </FormRow>
          <FormRow label="ИНН / КПП">
            <TextInput mono value="7701234567 / 770101001" onChange={dirty2()}/>
          </FormRow>
          <FormRow label="Часовой пояс по умолчанию">
            <Select value="msk" onChange={dirty2()}
              options={[{value:'msk',label:'Москва (UTC+3)'},{value:'ekb',label:'Екатеринбург (UTC+5)'},{value:'nsk',label:'Новосибирск (UTC+7)'}]}/>
          </FormRow>
          <FormRow label="Логотип компании" span={2} hint="Используется в подписях писем кандидатам и в шапке экспорта отчётов">
            <div className="logo-uploader">
              <div className="logo-preview"><span>L</span></div>
              <button className="btn btn-secondary btn-sm">Загрузить</button>
              <button className="btn btn-ghost btn-sm">Удалить</button>
            </div>
          </FormRow>
        </div>
      </Card>

      <Card title="Системные константы" desc="Пороги и сроки, которые влияют на «Главный экран», «Аналитику» и автоматизации">
        <div className="form-grid form-grid-2">
          <FormRow label="Порог «новый отклик требует внимания»" hint="Через сколько часов без ответа рекрутера отклик подсветится в «Внимании»">
            <TextInput value="24" type="number" suffix="ч" mono onChange={dirty2()}/>
          </FormRow>
          <FormRow label="Порог «застрял на этапе»" hint="Через сколько дней без движения по воронке">
            <TextInput value="7" type="number" suffix="дн." mono onChange={dirty2()}/>
          </FormRow>
          <FormRow label="Период испытательного срока" hint="Используется для расчёта текучки в Аналитике">
            <TextInput value="90" type="number" suffix="дн." mono onChange={dirty2()}/>
          </FormRow>
          <FormRow label="Авто-архивация закрытой вакансии" hint="Через сколько дней статус «Закрыта» отправляется в Архив">
            <TextInput value="30" type="number" suffix="дн." mono onChange={dirty2()}/>
          </FormRow>
          <FormRow label="Хранение карточек кандидатов" hint="По 152-ФЗ обычно 36 месяцев">
            <TextInput value="36" type="number" suffix="мес." mono onChange={dirty2()}/>
          </FormRow>
          <FormRow label="Удалять резюме с PII по истечении срока">
            <Switch value={true} onChange={dirty2()}
              desc="Карточки полностью обезличиваются: ФИО, контакты и резюме удаляются. Аналитика — сохраняется"/>
          </FormRow>
        </div>
      </Card>

      <Card title="Источник данных о текучке"
        desc="Откуда система берёт сведения о статусе принятого сотрудника — для отчёта «Текучка после найма» в Аналитике">
        <div className="src-radio-list">
          <Radio checked={src==='b24'} onChange={() => { setSrc('b24'); setDirty(true); }}
            label="Битрикс·24"
            desc="Берём данные о статусе сотрудника из CRM/HR Битрикса"
            right={hasBitrix
              ? <span className="conn-pill ok"><Icon name="check" size={12}/>Подключено</span>
              : <span className="conn-pill bad">Не настроено · <a href="#">Перейти к интеграциям</a></span>}/>
          <Radio checked={src==='1c'} onChange={() => { setSrc('1c'); setDirty(true); }}
            label="1С ЗУП"
            desc="Берём данные из кадрового модуля 1С"
            right={<span className="conn-pill bad">Не настроено · <a href="#">Перейти к интеграциям</a></span>}/>
          <Radio checked={src==='none'} onChange={() => { setSrc('none'); setDirty(true); }}
            label="Не использовать"
            desc="Отчёт «Текучка после найма» в Аналитике будет недоступен"/>
        </div>
      </Card>

      <Card title="Импорт пользователей из Битрикс·24"
        desc={hasBitrix
          ? "Автоматически создавать пользователей системы при появлении новых сотрудников в Битрикс·24"
          : "Доступно после подключения Битрикс·24 в разделе «Интеграции»"}>
        <div className={hasBitrix ? '' : 'set-disabled-block'}>
          <Switch value={importOn} onChange={v => { setImportOn(v); setDirty(true); }}
            label="Автоматически импортировать сотрудников"
            desc="Новые сотрудники из Битрикс·24 будут создаваться как пользователи системы каждые 6 часов"/>

          <div className="form-grid form-grid-2" style={{marginTop:14}}>
            <FormRow label="Какие сотрудники импортируются">
              <Select value="depts" onChange={dirty2()}
                options={[
                  {value:'all', label:'Все сотрудники'},
                  {value:'depts', label:'Только из отделов: Производство, Розница'},
                  {value:'pos', label:'Только с должностью «Руководитель»'},
                ]}/>
            </FormRow>
            <FormRow label="Роль по умолчанию">
              <Select value="manager" onChange={dirty2()}
                options={[
                  {value:'manager', label:'Нанимающий менеджер'},
                  {value:'recruiter', label:'Рекрутер'},
                ]}/>
            </FormRow>
            <FormRow span={2}>
              <Switch value={autoRole} onChange={v => { setAutoRole(v); setDirty(true); }}
                label="Автоматически назначать роль"
                desc="Если выключено — импортированные пользователи будут «Без роли» и заблокированы до ручного назначения"/>
            </FormRow>
          </div>

          <div className="import-log">
            <div className="il-row">
              <div className="il-cap">Последний импорт</div>
              <div className="il-val">2 мая 2026, 04:00 · добавлено <b>3</b>, обновлено <b>14</b>, ошибок <b>0</b></div>
            </div>
            <button className="btn btn-secondary btn-sm" disabled={!hasBitrix}>
              <Icon name="refresh" size={14}/> Импортировать сейчас
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}

/* ============================================================
   3. FUNNEL
   ============================================================ */
const FUNNEL_STAGE_TYPES = {
  start:    { label: 'Стартовый',          dot:'#2A8AF0', bg:'#EAF3FE', fg:'#1865BE' },
  system:   { label: 'Системный',          dot:'#7E5CF0', bg:'#F0EAFE', fg:'#5C3FBE' },
  middle:   { label: 'Промежуточный',      dot:'#9AA3AE', bg:'#ECEFF2', fg:'#3A4452' },
  finalOk:  { label: 'Финальный · успех',  dot:'#16A34A', bg:'#DEF5E5', fg:'#128640' },
  finalBad: { label: 'Финальный · отказ',  dot:'#DC4646', bg:'#FCE3E3', fg:'#B83030' },
};

function SettingsFunnel() {
  const [dirty, setDirty] = useStateSet(false);
  const [stages, setStages] = useStateSet([
    { id:1, name:'Отклик',                type:'start',    desc:'Кандидат пришёл с источника. Глафира делает первичный скрининг и зовёт в чат.' },
    { id:3, name:'Добавлен',              type:'system',   desc:'Кандидат добавлен рекрутером вручную из общей базы. Системный этап, не удаляется.' },
    { id:2, name:'Отобран',               type:'middle',   desc:'Глафира посчитала кандидата подходящим — ждём контакта рекрутера.' },
    { id:4, name:'Контакт с рекрутером',  type:'middle',   desc:'Назначен/проведён звонок-знакомство.' },
    { id:5, name:'Интервью',              type:'middle',   desc:'Техническое или профильное интервью.' },
    { id:6, name:'Контакт с менеджером',  type:'middle',   desc:'Финальная встреча с заказчиком.' },
    { id:7, name:'Оффер',                 type:'middle',   desc:'Оффер выслан и согласовывается.' },
    { id:8, name:'Нанят',                 type:'finalOk',  desc:'Кандидат вышел на работу. Стартует Пульс-Онбординг.' },
    { id:9, name:'Отказ',                 type:'finalBad', desc:'Завершение по причине из справочника.' },
  ]);
  const [reasonsCand, setReasonsCand] = useStateSet([
    'Не вышел на связь','Не устроила ЗП','Принял другой оффер','Не устроил график','Слишком далеко от дома',
  ]);
  const [reasonsCo, setReasonsCo] = useStateSet([
    'Несоответствие опыта','Несоответствие навыков','Не прошёл интервью','Не прошёл СБ','Завышенные ожидания по ЗП',
  ]);

  return (
    <div className="set-content-inner">
      <PageHead title="Воронка по умолчанию"
        subtitle="Базовый шаблон, который применяется при создании новой вакансии. Воронку можно изменить в любой вакансии после её создания"
        dirty={dirty} onSave={() => setDirty(false)}/>

      <div className="info-banner">
        <Icon name="sparkle" size={16}/>
        <div>
          <b>Это шаблон.</b> Изменения вступают в силу для <i>новых</i> вакансий.
          Для существующих — используйте тогглы «Применить ко всем активным» при сохранении.
        </div>
      </div>

      <Card title="Этапы воронки" desc="Используйте стрелки ▲▼ чтобы менять порядок. Первый и финальные этапы закреплены.">
        <div className="funnel-editor">
          {stages.map((s, idx) => {
            const t = FUNNEL_STAGE_TYPES[s.type];
            const isFinal = s.type === 'finalOk' || s.type === 'finalBad';
            const isFirst = idx === 0;
            const isSystem = s.type === 'system';
            const locked = isFirst || isFinal || isSystem;
            const move = (dir) => {
              const j = idx + dir;
              if (j < 1 || j > stages.length - 3) return;
              if (locked) return;
              const next = stages.slice();
              [next[idx], next[j]] = [next[j], next[idx]];
              setStages(next); setDirty(true);
            };
            const remove = () => {
              if (locked) return;
              setStages(stages.filter((_, i) => i !== idx));
              setDirty(true);
            };
            return (
              <div key={s.id} className={`fn-stage ${isFinal ? 'fn-final' : ''}`}>
                <div className="nv-fn-arrows">
                  <button className="nv-fn-arr"
                          disabled={locked || idx <= 1}
                          title={locked ? 'Этап зафиксирован' : 'Выше'}
                          onClick={() => move(-1)}>▲</button>
                  <button className="nv-fn-arr"
                          disabled={locked || idx >= stages.length - 3}
                          title={locked ? 'Этап зафиксирован' : 'Ниже'}
                          onClick={() => move(1)}>▼</button>
                </div>
                <div className="fn-num">{idx+1}</div>
                <div className="fn-body">
                  <div className="fn-row1">
                    <input className="fn-name" defaultValue={s.name}
                           onChange={(e) => {
                             const next = stages.slice();
                             next[idx] = {...s, name: e.target.value};
                             setStages(next); setDirty(true);
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
                        onClick={remove}
                        title={locked ? 'Этап нельзя удалить' : 'Удалить этап'}>
                  <Icon name="x" size={14}/>
                </button>
              </div>
            );
          })}
          <button className="fn-add" onClick={() => {
            const newStage = { id: Date.now(), name:'Новый этап', type:'middle', desc:'Опишите, что происходит на этом этапе.' };
            const i = stages.length - 2;
            const next = stages.slice();
            next.splice(i, 0, newStage);
            setStages(next); setDirty(true);
          }}>
            <Icon name="plus" size={14}/> Добавить этап
          </button>
        </div>
      </Card>

      <div className="form-grid form-grid-2 reason-grid">
        <Card title="Причины отказа от кандидата" desc="Видны при нажатии «Отклонить» в карточке кандидата">
          <div className="reason-chips">
            {reasonsCand.map((r,i) => (
              <span key={i} className="reason-chip reason-chip-cand">
                <span className="r-bullet"/>
                <span>{r}</span>
                <button className="reason-chip-x" aria-label="Удалить" onClick={() => { setReasonsCand(reasonsCand.filter((_,j)=>j!==i)); setDirty(true); }}><Icon name="x" size={11}/></button>
              </span>
            ))}
            <button className="reason-chip-add" onClick={() => { setReasonsCand([...reasonsCand,'Новая причина']); setDirty(true); }}><Icon name="plus" size={12}/>Добавить</button>
          </div>
        </Card>
        <Card title="Причины отказа со стороны компании" desc="Используются в Аналитике (отчёт «Причины отказов»)">
          <div className="reason-chips">
            {reasonsCo.map((r,i) => (
              <span key={i} className="reason-chip reason-chip-co">
                <span className="r-bullet co"/>
                <span>{r}</span>
                <button className="reason-chip-x" aria-label="Удалить" onClick={() => { setReasonsCo(reasonsCo.filter((_,j)=>j!==i)); setDirty(true); }}><Icon name="x" size={11}/></button>
              </span>
            ))}
            <button className="reason-chip-add" onClick={() => { setReasonsCo([...reasonsCo,'Новая причина']); setDirty(true); }}><Icon name="plus" size={12}/>Добавить</button>
          </div>
        </Card>
      </div>
    </div>
  );
}

/* ============================================================
   4. ACCESS
   ============================================================ */
const ROLE_INFO = [
  {
    id:'admin', label:'Администратор', tone:'admin',
    sum:'Настраивает систему',
    can:'Всё: интеграции, пользователи, воронка, теги. Полный доступ ко всем вакансиям и аналитике.',
    sees:'Все разделы и все данные.',
  },
  {
    id:'recruiter', label:'Рекрутер', tone:'recruiter',
    sum:'Основной пользователь',
    can:'Создаёт и ведёт вакансии, работает с кандидатами, передаёт по воронке, общается через Глафиру.',
    sees:'Свои вакансии, общую базу кандидатов, Аналитику (без отчёта «Рекрутеры»). Не видит Общие настройки, Воронку, Права, Интеграции.',
  },
  {
    id:'manager', label:'Нанимающий менеджер', tone:'manager',
    sum:'Лёгкий пользователь · заказчик',
    can:'Согласует требования, оценивает кандидатов, проводит интервью на своей стороне. Не двигает кандидатов между этапами (кроме своей зоны).',
    sees:'Только вакансии, где он указан заказчиком. Не видит Аналитику и Настройки (кроме Профиля). Не видит общую базу.',
  },
];

function SettingsAccess() {
  const [search, setSearch] = useStateSet('');
  const [roleFilter, setRoleFilter] = useStateSet('all');
  const [statusFilter, setStatusFilter] = useStateSet('all');

  const users = [
    { fio:'Анна Седова',     email:'anna.sedova@company.ru',     role:'admin',     src:'manual', last:'2 ч назад',    status:'active' },
    { fio:'Иван Петров',     email:'ivan.petrov@company.ru',     role:'recruiter', src:'manual', last:'вчера',         status:'active' },
    { fio:'Мария Кузнецова', email:'maria.k@company.ru',         role:'recruiter', src:'manual', last:'месяц назад',   status:'blocked' },
    { fio:'Сергей Волков',   email:'sergey.volkov@company.ru',   role:'manager',   src:'b24',    last:'5 мин назад',   status:'active' },
    { fio:'Ольга Тимошенко', email:'olga.t@company.ru',          role:'manager',   src:'b24',    last:'3 дня назад',   status:'active' },
    { fio:'Дмитрий Хохлов',  email:'d.khokhlov@company.ru',      role:'manager',   src:'b24',    last:'неделю назад',  status:'active' },
    { fio:'Татьяна Лиховид', email:'t.likhovid@company.ru',      role:'recruiter', src:'manual', last:'12 мин назад',  status:'active' },
    { fio:'Павел Самойлов',  email:'p.samoylov@company.ru',      role:'manager',   src:'b24',    last:'не входил',     status:'invited' },
  ];
  const roleLabel = { admin:'Администратор', recruiter:'Рекрутер', manager:'Нанимающий менеджер' };
  const roleClass = { admin:'admin', recruiter:'recruiter', manager:'manager' };
  const statusLabel = { active:'Активен', blocked:'Заблокирован', invited:'Приглашён' };

  const filtered = users.filter(u => {
    if (search && !(u.fio.toLowerCase().includes(search.toLowerCase()) || u.email.toLowerCase().includes(search.toLowerCase()))) return false;
    if (roleFilter !== 'all' && u.role !== roleFilter) return false;
    if (statusFilter !== 'all' && u.status !== statusFilter) return false;
    return true;
  });

  return (
    <div className="set-content-inner">
      <PageHead title="Права доступа"
        subtitle="Пользователи системы и их роли"/>

      <Card title="Роли в системе">
        <div className="roles-grid">
          {ROLE_INFO.map(r => (
            <div key={r.id} className={`role-card role-${r.tone}`}>
              <div className="role-card-head">
                <div className={`role-pill role-${r.tone}`}>{r.label}</div>
                <div className="role-sum">{r.sum}</div>
              </div>
              <div className="role-block">
                <div className="role-cap">Что может</div>
                <div className="role-text">{r.can}</div>
              </div>
              <div className="role-block">
                <div className="role-cap">Что видит</div>
                <div className="role-text">{r.sees}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Пользователи" desc={`Всего ${users.length}: ${users.filter(u => u.status==='active').length} активных`}>
        <div className="users-toolbar">
          <div className="users-search">
            <Icon name="search" size={14}/>
            <input placeholder="Поиск по ФИО или email…" value={search} onChange={e => setSearch(e.target.value)}/>
          </div>
          <Select value={roleFilter} onChange={setRoleFilter}
            options={[{value:'all',label:'Все роли'},{value:'admin',label:'Администраторы'},{value:'recruiter',label:'Рекрутеры'},{value:'manager',label:'Нанимающие менеджеры'}]}/>
          <Select value={statusFilter} onChange={setStatusFilter}
            options={[{value:'all',label:'Все статусы'},{value:'active',label:'Активные'},{value:'blocked',label:'Заблокированные'},{value:'invited',label:'Приглашённые'}]}/>
          <div style={{flex:1}}/>
          <button className="btn btn-secondary btn-sm"><Icon name="download" size={14}/>Импорт из Б24</button>
          <button className="btn btn-primary btn-sm"><Icon name="plus" size={14}/>Пригласить</button>
        </div>

        <div className="users-table">
          <div className="ut-thead">
            <div>Пользователь</div>
            <div>Роль</div>
            <div>Источник</div>
            <div>Последний вход</div>
            <div>Статус</div>
            <div></div>
          </div>
          {filtered.map((u,i) => (
            <div key={i} className="ut-row">
              <div className="ut-user">
                <Avatar name={u.fio} size="sm"/>
                <div>
                  <div className="ut-fio">{u.fio}</div>
                  <div className="ut-email">{u.email}</div>
                </div>
              </div>
              <div><span className={`role-pill role-${roleClass[u.role]}`}>{roleLabel[u.role]}</span></div>
              <div className="ut-cell">
                {u.src === 'b24'
                  ? <span className="src-pill src-b24"><span className="b24-dot"/>Импорт из Б24</span>
                  : <span className="t-secondary">Создан вручную</span>}
              </div>
              <div className="ut-cell t-mono" style={{fontSize:12}}>{u.last}</div>
              <div>
                <span className={`status-pill status-${u.status}`}>
                  <span className="st-dot"/>{statusLabel[u.status]}
                </span>
              </div>
              <div style={{textAlign:'right'}}>
                <button className="row-icon-btn"><Icon name="more" size={16}/></button>
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="ut-empty">По заданным фильтрам никого не найдено</div>
          )}
        </div>
      </Card>
    </div>
  );
}

/* ============================================================
   5. TAGS
   ============================================================ */
const TAG_PALETTE = [
  {id:'blue',   color:'#2A8AF0', soft:'#EAF3FE'},
  {id:'green',  color:'#16A34A', soft:'#DEF5E5'},
  {id:'yellow', color:'#E0A21A', soft:'#FFF1C8'},
  {id:'red',    color:'#DC4646', soft:'#FCE3E3'},
  {id:'violet', color:'#7E5CF0', soft:'#ECE7FE'},
  {id:'rose',   color:'#E26B7E', soft:'#FBE5EA'},
  {id:'teal',   color:'#3FA3B3', soft:'#DDF1F4'},
  {id:'gray',   color:'#5B6573', soft:'#ECEFF2'},
];

function SettingsTags() {
  const [search, setSearch] = useStateSet('');
  const tags = [
    { name:'Топ-кандидат',     color:'blue',   used:47, when:'12.03.26', by:'Анна С.', desc:'Кандидат, который точно заслуживает оффера' },
    { name:'Готов к выходу',   color:'green',  used:12, when:'28.03.26', by:'Иван П.', desc:'Двухнедельная готовность или меньше' },
    { name:'На испытательном', color:'yellow', used: 8, when:'01.04.26', by:'Анна С.', desc:'' },
    { name:'Чёрный список',    color:'red',    used:23, when:'15.02.26', by:'Анна С.', desc:'Не предлагать на новые вакансии' },
    { name:'Реферал',          color:'violet', used:34, when:'08.01.26', by:'Иван П.', desc:'Пришёл по рекомендации сотрудника' },
    { name:'Релокация',        color:'teal',   used:18, when:'22.02.26', by:'Анна С.', desc:'Готов к переезду' },
    { name:'Junior',           color:'gray',   used: 6, when:'04.04.26', by:'Иван П.', desc:'' },
    { name:'Senior+',          color:'rose',   used:11, when:'04.04.26', by:'Иван П.', desc:'' },
  ];
  const filtered = tags.filter(t => t.name.toLowerCase().includes(search.toLowerCase()));
  const palette = Object.fromEntries(TAG_PALETTE.map(p => [p.id, p]));

  return (
    <div className="set-content-inner">
      <PageHead title="Справочник тегов"
        subtitle="Теги используются для маркировки кандидатов в общей базе. По ним можно фильтровать"/>

      <Card>
        <div className="tags-toolbar">
          <div className="users-search">
            <Icon name="search" size={14}/>
            <input placeholder="Поиск тегов…" value={search} onChange={e => setSearch(e.target.value)}/>
          </div>
          <div style={{flex:1}}/>
          <button className="btn btn-primary btn-sm"><Icon name="plus" size={14}/>Новый тег</button>
        </div>

        <div className="tags-table">
          <div className="tt-thead">
            <div>Тег</div>
            <div>Описание</div>
            <div style={{textAlign:'right'}}>Кандидатов</div>
            <div>Создан</div>
            <div>Создал</div>
            <div></div>
          </div>
          {filtered.map((t,i) => {
            const p = palette[t.color];
            return (
              <div key={i} className="tt-row">
                <div>
                  <span className="tag-chip" style={{background:p.soft, color:p.color}}>
                    <span className="tag-dot" style={{background:p.color}}/>{t.name}
                  </span>
                </div>
                <div className="t-secondary tt-desc">{t.desc || <span className="muted">—</span>}</div>
                <div className="t-mono tt-num" style={{textAlign:'right'}}>{t.used}</div>
                <div className="t-mono" style={{fontSize:12, color:'var(--fg-2)'}}>{t.when}</div>
                <div className="t-secondary">{t.by}</div>
                <div style={{textAlign:'right'}}>
                  <button className="row-icon-btn"><Icon name="more" size={16}/></button>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <Card title="Палитра">
        <div className="palette-row">
          {TAG_PALETTE.map(p => (
            <div key={p.id} className="palette-cell">
              <span className="tag-chip" style={{background:p.soft, color:p.color}}>
                <span className="tag-dot" style={{background:p.color}}/>{p.id}
              </span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

/* ============================================================
   6. INTEGRATIONS
   ============================================================ */
function IntegrationCard({ ico, iconBg, name, desc, status, openByDefault, children }) {
  const [open, setOpen] = useStateSet(!!openByDefault);
  const statusInfo = {
    ok:   { label: 'Подключено',     cls: 'ok' },
    bad:  { label: 'Не настроено',   cls: 'bad' },
    err:  { label: 'Ошибка авторизации', cls: 'err' },
  }[status];
  return (
    <section className={`integ-card ${open ? 'open' : ''}`}>
      <button className="integ-head" onClick={() => setOpen(!open)}>
        <div className="integ-ico" style={{background:iconBg}}>{ico}</div>
        <div className="integ-body">
          <div className="integ-name">{name}</div>
          <div className="integ-desc">{desc}</div>
        </div>
        <div className={`conn-pill ${statusInfo.cls}`}>
          {status==='ok' && <Icon name="check" size={12}/>}
          {status==='err' && <Icon name="alert" size={12}/>}
          {statusInfo.label}
        </div>
        <span className={`integ-chev ${open ? 'open' : ''}`}><Icon name="chevD" size={16}/></span>
      </button>
      {open && <div className="integ-content">{children}</div>}
    </section>
  );
}

function SettingsIntegrations() {
  const [tgBotEnabled, setTgBotEnabled] = useStateSet(true);
  const [tgNotifEnabled, setTgNotifEnabled] = useStateSet(true);
  const [b24Auth, setB24Auth] = useStateSet('oauth');
  const [smtpEnc, setSmtpEnc] = useStateSet('tls');
  const [imapOn, setImapOn] = useStateSet(false);

  return (
    <div className="set-content-inner">
      <PageHead title="Интеграции"
        subtitle="Внешние сервисы, с которыми работает Глафира"/>

      <div className="integ-list">
        {/* TELEGRAM */}
        <IntegrationCard
          ico={<span className="integ-emoji">🤖</span>}
          iconBg="#EAF3FE"
          name="Telegram"
          desc="Бот «Глафира» для общения с кандидатами и уведомления пользователей"
          status="ok"
          openByDefault>
          <div className="integ-section">
            <div className="integ-section-title">Бот «Глафира» — общение с кандидатами</div>
            <div className="form-grid form-grid-2">
              <FormRow label="Bot Token" required>
                <TextInput value="••••••••••••5817:AAFq-pK9b3xN-vN" mono/>
              </FormRow>
              <FormRow label="Bot Username" hint="Определяется автоматически после ввода токена">
                <TextInput value="@glafira_recruit_bot" mono locked/>
              </FormRow>
              <FormRow label="Webhook URL" span={2} hint="Скопируйте URL в настройки бота, если он не привязался автоматически">
                <div className="row-with-action">
                  <TextInput value="https://api.glafira.app/webhook/tg/8f3d2e91-…" mono locked/>
                  <button className="btn btn-secondary btn-sm"><Icon name="copy" size={13}/>Копировать</button>
                </div>
              </FormRow>
              <FormRow label="Приветственное сообщение" span={2}
                hint="Что Глафира пишет кандидату при первом контакте. Поддерживает {{vacancy}} и {{company}}">
                <Textarea rows={3}
                  value="Здравствуйте! Я Глафира — помогаю с подбором в {{company}}. Я задам пару коротких вопросов по вакансии «{{vacancy}}», чтобы понять, насколько она вам подходит. Это займёт 3–5 минут 🙂"/>
              </FormRow>
            </div>
            <div className="integ-actions">
              <Switch value={tgBotEnabled} onChange={setTgBotEnabled}
                label="Включить бота" desc="Если выключено — кандидаты получают сообщение «Бот временно недоступен»"/>
              <button className="btn btn-secondary btn-sm">Проверить подключение</button>
            </div>
          </div>

          <div className="integ-divider"/>

          <div className="integ-section">
            <div className="integ-section-title">Уведомления для пользователей системы</div>
            <div className="form-grid form-grid-2">
              <FormRow label="Bot Token для уведомлений" hint="Можно использовать тот же токен, что и для Глафиры">
                <TextInput value="••••••••••••5817:AAFq-pK9b3xN-vN" mono/>
              </FormRow>
              <FormRow label="Подключённых пользователей" hint="Каждый пользователь привязывает свой Telegram в Профиле">
                <div className="stat-row-inline">
                  <b className="t-mono">14</b> из <span className="t-mono">17</span>
                  <a className="t-link" href="#" style={{marginLeft:8}}>посмотреть</a>
                </div>
              </FormRow>
            </div>
            <Switch value={tgNotifEnabled} onChange={setTgNotifEnabled}
              label="Включить уведомления через Telegram"/>
          </div>

          <details className="integ-advanced">
            <summary>Расширенные настройки</summary>
            <div className="form-grid form-grid-2" style={{marginTop:12}}>
              <FormRow label="Прокси для Telegram API" hint="HTTP/SOCKS5 — если требуется">
                <TextInput placeholder="socks5://user:pass@host:port"/>
              </FormRow>
              <FormRow label="Лимит сообщений в минуту">
                <TextInput value="30" mono suffix="/мин"/>
              </FormRow>
              <FormRow span={2}>
                <Switch value={true} label="Логировать диалоги" desc="Для аудита и улучшения Глафиры. Логи хранятся 90 дней."/>
              </FormRow>
            </div>
          </details>
        </IntegrationCard>

        {/* SMTP */}
        <IntegrationCard
          ico={<Icon name="mail" size={18}/>}
          iconBg="#FFF1C8"
          name="Почтовый сервер (SMTP)"
          desc="Отправка писем кандидатам и системных уведомлений"
          status="bad">
          <div className="integ-section">
            <div className="form-grid form-grid-2">
              <FormRow label="SMTP-сервер" required>
                <TextInput value="smtp.yandex.ru" mono/>
              </FormRow>
              <FormRow label="Порт">
                <TextInput value="587" type="number" mono/>
              </FormRow>
              <FormRow label="Шифрование">
                <Select value={smtpEnc} onChange={setSmtpEnc}
                  options={[{value:'tls',label:'TLS (рекомендуется)'},{value:'ssl',label:'SSL'},{value:'none',label:'Без шифрования'}]}/>
              </FormRow>
              <FormRow label="Reply-to">
                <TextInput placeholder="hr@company.ru"/>
              </FormRow>
              <FormRow label="Email отправителя" required>
                <TextInput value="hr@company.ru" mono/>
              </FormRow>
              <FormRow label="Имя отправителя">
                <TextInput value="HR · ООО Логос"/>
              </FormRow>
              <FormRow label="Логин SMTP">
                <TextInput value="hr@company.ru" mono/>
              </FormRow>
              <FormRow label="Пароль">
                <TextInput value="••••••••••••" type="password" mono/>
              </FormRow>
            </div>
            <div className="info-banner small">
              <Icon name="alert" size={14}/>
              <div>Для лучшей доставляемости настройте <b>DKIM</b> и <b>SPF</b>-записи в DNS вашего домена.</div>
            </div>
            <div className="integ-actions">
              <button className="btn btn-secondary btn-sm">Отправить тестовое письмо</button>
              <button className="btn btn-primary btn-sm">Сохранить и подключить</button>
            </div>
          </div>

          <div className="integ-divider"/>

          <div className="integ-section">
            <div className="integ-section-title">IMAP — получение ответов кандидатов</div>
            <Switch value={imapOn} onChange={setImapOn}
              label="Получать входящие письма от кандидатов в систему"
              desc="Ответы на email-сообщения будут автоматически попадать в чат с кандидатом"/>
            {imapOn && (
              <div className="form-grid form-grid-2" style={{marginTop:12}}>
                <FormRow label="IMAP-сервер"><TextInput value="imap.yandex.ru" mono/></FormRow>
                <FormRow label="Порт"><TextInput value="993" mono/></FormRow>
                <FormRow label="Логин"><TextInput value="hr@company.ru" mono/></FormRow>
                <FormRow label="Пароль"><TextInput value="••••••••••••" type="password" mono/></FormRow>
              </div>
            )}
          </div>
        </IntegrationCard>

        {/* B24 */}
        <IntegrationCard
          ico={<span className="integ-emoji">🔵</span>}
          iconBg="#EAF3FE"
          name="Битрикс·24"
          desc="Импорт пользователей и данные о текучке"
          status="ok">
          <div className="integ-section">
            <div className="form-grid form-grid-2">
              <FormRow label="URL портала Битрикс·24" required span={2}>
                <TextInput value="https://logos.bitrix24.ru" mono/>
              </FormRow>
            </div>

            <div className="integ-section-title" style={{marginTop:8}}>Авторизация · OAuth-приложение</div>
            <div className="form-grid form-grid-2" style={{marginTop:8}}>
              <FormRow label="Client ID"><TextInput placeholder="local.61f8…" mono/></FormRow>
              <FormRow label="Client Secret"><TextInput type="password" placeholder="••••••••••" mono/></FormRow>
              <FormRow span={2}><button className="btn btn-secondary btn-sm">Авторизоваться в Битрикс·24</button></FormRow>
            </div>
          </div>

          <div className="integ-divider"/>

          <div className="integ-section">
            <div className="integ-section-title">Что синхронизируется</div>
            <div className="sync-list">
              <Switch value={true} label="Импортировать пользователей" desc="Настройки в разделе «Общие → Импорт пользователей»"/>
              <Switch value={true} label="Получать данные о текучке" desc="Статусы сотрудников и даты увольнения для отчёта «Текучка»"/>
              <Switch value={false} label="Создавать дело в Б24 при найме кандидата"/>
              <Switch value={true} label="Связывать карточку кандидата с контактом/лидом в Б24" desc="Двусторонняя история: всё, что фиксируется в Глафире, видно в Б24"/>
            </div>
          </div>

          <details className="integ-advanced">
            <summary>Маппинг полей</summary>
            <div className="map-table">
              <div className="map-thead"><div>Поле в Глафире</div><div></div><div>Поле в Битрикс·24</div></div>
              {[
                ['Должность кандидата','UF_CRM_POSITION'],
                ['Источник','UF_CRM_SOURCE'],
                ['Город','UF_CRM_CITY'],
                ['Зарплатные ожидания','UF_CRM_SALARY'],
              ].map(([a,b],i) => (
                <div key={i} className="map-row">
                  <div className="t-mono">{a}</div>
                  <div style={{color:'var(--fg-3)'}}><Icon name="arrowRight" size={14}/></div>
                  <div className="t-mono" style={{color:'var(--fg-2)'}}>{b}</div>
                </div>
              ))}
            </div>
          </details>

          <div className="integ-section">
            <div className="integ-section-title">Лог синхронизаций</div>
            <div className="sync-log">
              {[
                {when:'2 мая, 04:00',  dir:'Импорт',  obj:'17 пользователей', err:0},
                {when:'1 мая, 04:00',  dir:'Импорт',  obj:'17 пользователей', err:0},
                {when:'30 апр, 18:32', dir:'Экспорт', obj:'1 контакт',         err:0},
                {when:'30 апр, 04:00', dir:'Импорт',  obj:'14 пользователей', err:1},
              ].map((r,i) => (
                <div key={i} className="sl-row">
                  <span className="t-mono sl-when">{r.when}</span>
                  <span className={`sl-dir sl-${r.dir==='Импорт'?'in':'out'}`}>{r.dir}</span>
                  <span className="sl-obj">{r.obj}</span>
                  <span className={`sl-err ${r.err>0 ? 'has' : ''}`}>{r.err > 0 ? `${r.err} ошибка` : 'без ошибок'}</span>
                </div>
              ))}
            </div>
            <div className="integ-actions">
              <button className="btn btn-secondary btn-sm"><Icon name="refresh" size={13}/>Запустить сейчас</button>
              <button className="btn btn-secondary btn-sm">Проверить подключение</button>
            </div>
          </div>
        </IntegrationCard>

        {/* 1C */}
        <IntegrationCard
          ico={<span className="integ-emoji">📒</span>}
          iconBg="#FFF1C8"
          name="1С ЗУП"
          desc="Кадровые данные и расчёт текучки"
          status="bad">
          <div className="integ-section">
            <div className="info-banner">
              <Icon name="sparkle" size={14}/>
              <div>
                <b>1С наружу публиковать не нужно.</b> Установите наше расширение для 1С ЗУП — оно само свяжется с Глафирой по защищённому каналу. После установки в настройках расширения внутри 1С нужно указать URL и токен — оба значения возьмите ниже.
                <div style={{marginTop:8, display:'flex', gap:8, flexWrap:'wrap'}}>
                  <a className="btn btn-secondary btn-sm" href="#" download>
                    <Icon name="download" size={13}/>Скачать расширение (.cfe, 2.4 МБ)
                  </a>
                  <a className="t-link" href="#" style={{alignSelf:'center', fontSize:12}}>
                    Инструкция по установке →
                  </a>
                </div>
                <div className="t-caption" style={{marginTop:8}}>
                  Совместимо с 1С:ЗУП 3.1.27+ и 1С:ЗУП КОРП. Поддерживаются файловая и клиент-серверная базы.
                </div>
              </div>
            </div>

            <div className="form-grid form-grid-2" style={{marginTop:14}}>
              <FormRow label="URL для расширения 1С" span={2}
                hint="Скопируйте этот адрес и вставьте в настройках расширения после его установки в 1С">
                <div className="row-with-action">
                  <TextInput value="https://api.glafira.app/1c/in/8f3d2e91-…" mono locked/>
                  <button className="btn btn-secondary btn-sm"><Icon name="copy" size={13}/>Копировать</button>
                </div>
              </FormRow>
              <FormRow label="Токен авторизации" required span={2}
                hint="Сгенерируйте токен здесь и вставьте его в настройки расширения вместе с URL">
                <div className="row-with-action">
                  <TextInput value="glf_1c_••••••••••••••••••••••" mono/>
                  <button className="btn btn-secondary btn-sm"><Icon name="refresh" size={13}/>Сгенерировать новый</button>
                </div>
              </FormRow>
            </div>
            <div className="integ-actions">
              <button className="btn btn-primary btn-sm">Сохранить</button>
            </div>
          </div>

          <div className="integ-divider"/>

          <div className="integ-section">
            <div className="integ-section-title">Что синхронизируется</div>
            <div className="sync-list">
              <Switch value={true} label="Получать данные о сотрудниках и их статусах" desc="Для отчёта «Текучка после найма»"/>
              <Switch value={false} label="Создавать карточку сотрудника в 1С при найме кандидата"/>
            </div>
            <div className="form-grid form-grid-2" style={{marginTop:12}}>
              <FormRow label="Подразделение по умолчанию">
                <Select value="" placeholder="Выберите подразделение"
                  options={['Розница','Производство','Офис · HR','Офис · IT']}/>
              </FormRow>
              <FormRow label="Расписание синхронизации">
                <Select value="6h"
                  options={[
                    {value:'1h', label:'Каждый час'},
                    {value:'6h', label:'Каждые 6 часов'},
                    {value:'24h', label:'Ежедневно (04:00)'},
                    {value:'manual', label:'Только вручную'},
                  ]}/>
              </FormRow>
            </div>
          </div>
        </IntegrationCard>
      </div>

      <div className="info-banner muted">
        <Icon name="sparkle" size={14}/>
        <div>В будущих релизах сюда добавятся карточки <b>hh.ru</b>, <b>Авито Работа</b> и публикация в <b>Telegram-каналы</b>.</div>
      </div>
    </div>
  );
}

/* ============================================================
   7. AI — ИИ
   ============================================================ */
function SettingsAI() {
  const TOTAL = 2847;
  const [indexed, setIndexed] = useStateSet(2731);
  const [reindexing, setReindexing] = useStateSet(false);
  const [llm, setLlm] = useStateSet('claude-sonnet-4-6');
  const [dirty, setDirty] = useStateSet(false);
  const pct = Math.round((indexed / TOTAL) * 100);
  const pending = TOTAL - indexed;

  const reindex = () => {
    if (reindexing) return;
    setReindexing(true);
    setIndexed(0);
    let cur = 0;
    const step = Math.ceil(TOTAL / 36);
    const t = setInterval(() => {
      cur = Math.min(TOTAL, cur + step);
      setIndexed(cur);
      if (cur >= TOTAL) { clearInterval(t); setReindexing(false); }
    }, 55);
  };

  const fmt = (n) => n.toLocaleString('ru-RU');

  return (
    <div className="set-content-inner">
      <PageHead title="Искусственный интеллект"
        subtitle="Семантический поиск по базе и модель, которая анализирует резюме"
        dirty={dirty} onSave={() => setDirty(false)}/>

      {/* --- Semantic search --- */}
      <Card title="Семантический поиск по базе кандидатов"
        desc="Индексация резюме для умного поиска по смыслу, а не только по ключевым словам. Векторы резюме хранятся в системе и используются разделом «Умный подбор».">

        <div className="ai-index">
          <div className="ai-index-stats">
            <div className="ai-stat">
              <div className="ai-stat-num t-mono">{fmt(TOTAL)}</div>
              <div className="ai-stat-cap">Резюме в базе</div>
            </div>
            <div className="ai-stat-arrow"><Icon name="arrowRight" size={16}/></div>
            <div className="ai-stat">
              <div className="ai-stat-num t-mono">{fmt(indexed)}</div>
              <div className="ai-stat-cap">Проиндексировано · векторов</div>
            </div>
            <div className="ai-index-pillwrap">
              {pending === 0
                ? <span className="conn-pill ok"><Icon name="check" size={12}/>Всё проиндексировано</span>
                : <span className="conn-pill bad">{reindexing ? 'Индексируется…' : `${fmt(pending)} в очереди`}</span>}
            </div>
          </div>

          <div className="ai-progress">
            <div className={`ai-progress-fill ${reindexing ? 'busy' : ''}`} style={{width: pct + '%'}}/>
          </div>
          <div className="ai-progress-foot">
            <span className="t-mono">{pct}%</span>
            <span className="t-caption">
              {reindexing
                ? 'Идёт переиндексация базы…'
                : `Последняя индексация: 11 июня 2026, 03:14 · хранилище векторов 412 МБ`}
            </span>
          </div>

          <div className="ai-index-actions">
            <button className="btn btn-primary btn-sm" onClick={reindex} disabled={reindexing}>
              <Icon name="refresh" size={14}/> {reindexing ? 'Переиндексация…' : 'Переиндексировать'}
            </button>
            <span className="t-caption">Новые резюме индексируются автоматически. Полная переиндексация нужна после смены настроек.</span>
          </div>
        </div>

        <div className="ai-divider"/>

        <div className="form-grid">
          <FormRow label="Модель эмбеддингов"
            hint="Преобразует текст резюме в векторы. Многоязычная модель, оптимизированная под русский язык. Зафиксирована.">
            <div className="ai-model-locked">
              <span className="ai-prov-ic" style={{background:'var(--ark-blue-50)', color:'var(--ark-blue-700)'}}><Icon name="database" size={16}/></span>
              <div className="ai-model-id t-mono">sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2</div>
              <span className="ai-soon-pill ai-soon-locked"><Icon name="lock" size={11}/>Зафиксирована</span>
            </div>
          </FormRow>
        </div>
      </Card>

      {/* --- LLM model --- */}
      <Card title="Модель LLM"
        desc="Настройка модели искусственного интеллекта для анализа резюме: квалификация откликов, оценка соответствия вакансии и саммари кандидата.">
        <div className="form-grid">
          <FormRow label="Основная модель"
            hint="Модель, которая оценивает резюме и квалифицирует отклики. Смена влияет на все новые анализы.">
            <div className="ai-model-select">
              <span className="ai-prov-ic" style={{background:'#F3EEE7', color:'#B8551F'}}><Icon name="cpu" size={16}/></span>
              <Select value={llm} onChange={v => { setLlm(v); setDirty(true); }}
                options={[
                  {value:'qwen3-7-max',       label:'Qwen3.7-Max'},
                  {value:'kimi-k2-6',         label:'Kimi K2.6'},
                  {value:'deepseek-v4-flash', label:'DeepSeek V4 Flash'},
                  {value:'claude-sonnet-4-6', label:'Claude Sonnet 4.6'},
                ]}/>
            </div>
          </FormRow>
        </div>
      </Card>
    </div>
  );
}

/* ============================================================
   Root
   ============================================================ */
function Settings({ section, onSectionChange, isAdmin = true, hasBitrix = true }) {
  const safe = SET_SECTIONS.find(s => s.id === section);
  const allowed = !safe || (isAdmin || !safe.adminOnly);
  const active = allowed ? section : 'profile';

  let content;
  if (active === 'profile')           content = <SettingsProfile/>;
  else if (active === 'general')      content = <SettingsGeneral hasBitrix={hasBitrix}/>;
  else if (active === 'funnel')       content = <SettingsFunnel/>;
  else if (active === 'access')       content = <SettingsAccess/>;
  else if (active === 'tags')         content = <SettingsTags/>;
  else if (active === 'ai')           content = <SettingsAI/>;
  else if (active === 'integrations') content = <SettingsIntegrations/>;

  return (
    <div className="settings-shell">
      <div className="set-content" data-screen-label={`Settings / ${active}`}>
        <SettingsTopTabs active={active} onChange={onSectionChange} isAdmin={isAdmin}/>
        {content}
      </div>
    </div>
  );
}

window.Settings = Settings;
window.SET_SECTIONS = SET_SECTIONS;
window.FUNNEL_STAGE_TYPES = FUNNEL_STAGE_TYPES;
