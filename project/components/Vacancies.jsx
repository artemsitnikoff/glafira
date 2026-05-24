// Vacancies — submenu list + right pane (empty / mode A stub / archive)
const { useState: useStateVac, useMemo: useMemoVac } = React;

const VACANCIES = [
  { id: 'fe',   name: 'Frontend-разработчик (Senior)', count: 47, newCount: 5, unread: true },
  { id: 'wh',   name: 'Кладовщик · смена 2/2',         count: 132, newCount: 12, unread: true },
  { id: 'hr',   name: 'HR-дженералист',                count: 8, newCount: 0, unread: false },
  { id: 'do',   name: 'DevOps-инженер',                count: 23, newCount: 2, unread: true },
  { id: 'pm',   name: 'Product Manager',               count: 19, newCount: 0, unread: false },
  { id: 'qa',   name: 'QA-инженер (автоматизация)',    count: 31, newCount: 4, unread: true },
  { id: 'ux',   name: 'UX/UI Дизайнер',                count: 14, newCount: 0, unread: false },
  { id: 'sa',   name: 'Системный аналитик',            count: 22, newCount: 1, unread: false },
  { id: 'ba',   name: 'Бухгалтер на первичку',         count: 9,  newCount: 0, unread: false },
  { id: 'cs',   name: 'Customer Success Manager',      count: 17, newCount: 3, unread: true },
  { id: 'mk',   name: 'Маркетолог · performance',      count: 11, newCount: 0, unread: false },
  { id: 'sl',   name: 'Менеджер по продажам B2B',      count: 38, newCount: 0, unread: false },
];

const ARCHIVE_DATA = [
  { id: 1, title: 'Senior Backend (Go)',         result: 'success', client: 'Логос', recruiter: 'А. Седова',  days: 23, date: '12 марта 2026',     candidates: 47, hired: 1, period: 'quarter' },
  { id: 2, title: 'Junior QA-инженер',           result: 'success', client: 'Сатурн', recruiter: 'И. Корнев', days: 14, date: '28 февраля 2026',   candidates: 62, hired: 2, period: 'quarter' },
  { id: 3, title: 'Менеджер call-центра',        result: 'fail',    client: 'Логос', recruiter: 'А. Седова',  days: 41, date: '5 февраля 2026',    candidates: 89, hired: 0, period: 'quarter' },
  { id: 4, title: 'Product Designer',            result: 'success', client: 'Atlas',  recruiter: 'А. Седова', days: 19, date: '14 апреля 2026',    candidates: 34, hired: 1, period: 'month' },
  { id: 5, title: 'Курьер-водитель (свой авто)', result: 'success', client: 'Север',  recruiter: 'И. Корнев', days: 9,  date: '22 апреля 2026',    candidates: 154, hired: 4, period: 'month' },
  { id: 6, title: 'Главный бухгалтер',           result: 'frozen',  client: 'Сатурн', recruiter: 'А. Седова', days: 28, date: '18 апреля 2026',    candidates: 12, hired: 0, period: 'month' },
  { id: 7, title: 'iOS-разработчик (Swift)',     result: 'fail',    client: 'Atlas',  recruiter: 'И. Корнев', days: 56, date: '10 января 2026',    candidates: 28, hired: 0, period: 'year' },
  { id: 8, title: 'HR Business Partner',         result: 'success', client: 'Логос',  recruiter: 'А. Седова', days: 35, date: '7 апреля 2026',     candidates: 19, hired: 1, period: 'month' },
  { id: 9, title: 'Data Engineer',               result: 'success', client: 'Atlas',  recruiter: 'А. Седова', days: 27, date: '15 апреля 2026',    candidates: 22, hired: 1, period: 'month' },
  { id: 10, title: 'Менеджер по работе с ключевыми клиентами', result: 'success', client: 'Сатурн', recruiter: 'И. Корнев', days: 18, date: '20 апреля 2026', candidates: 41, hired: 1, period: 'month' },
  { id: 11, title: 'Уборщица в офис',            result: 'success', client: 'Север',  recruiter: 'И. Корнев', days: 6,  date: '24 апреля 2026',    candidates: 38, hired: 1, period: 'month' },
  { id: 12, title: 'Контент-менеджер',           result: 'fail',    client: 'Atlas',  recruiter: 'А. Седова', days: 38, date: '2 марта 2026',      candidates: 24, hired: 0, period: 'quarter' },
];

function VacanciesSubmenu({ selected, onSelect, archiveActive, onArchive }) {
  const [query, setQuery] = useStateVac('');
  const filtered = useMemoVac(
    () => VACANCIES.filter(v => v.name.toLowerCase().includes(query.toLowerCase())),
    [query]
  );
  return (
    <div className="submenu">
      <div className="submenu-header">
        <div className="submenu-title-row">
          <span className="submenu-title">Вакансии</span>
          <button className="btn-icon-pill"><Icon name="plus" size={14}/> Новая</button>
        </div>
        <div className="submenu-search">
          <Icon name="search" size={14} style={{color:'var(--fg-3)', flex:'none'}}/>
          <input placeholder="Поиск по названию…" value={query} onChange={e => setQuery(e.target.value)}/>
          <button className="sort-btn" title="Сортировка"><Icon name="sort" size={14}/></button>
        </div>
      </div>
      <div className="submenu-list">
        {filtered.length === 0 ? (
          <div style={{padding:'24px 16px', fontSize:13, color:'var(--fg-3)', textAlign:'center'}}>
            Ничего не найдено по запросу «{query}»
          </div>
        ) : filtered.map(v => (
          <div key={v.id}
            className={`submenu-row ${selected === v.id && !archiveActive ? 'selected' : ''}`}
            onClick={() => onSelect(v.id)}>
            <span className={`unread-dot ${v.unread ? '' : 'invisible'}`}/>
            <span className="vac-name">{v.name}</span>
            <span className="vac-count">{v.count}</span>
            {v.newCount > 0 && <span className="vac-new">+{v.newCount}</span>}
            <button className="row-more" onClick={e => e.stopPropagation()}><Icon name="more" size={14}/></button>
          </div>
        ))}
        <div className="submenu-divider"/>
        <div className={`submenu-archive ${archiveActive ? 'selected' : ''}`} onClick={onArchive}>
          <Icon name="archive" size={16}/>
          <span>Архив</span>
          <span className="arch-count">{ARCHIVE_DATA.length * 10 + 4}</span>
        </div>
      </div>
    </div>
  );
}

function EmptyVacancyPane() {
  return (
    <div className="empty-pane">
      <div className="empty-illust"><Icon name="briefcase" size={42}/></div>
      <h3>Выберите вакансию слева</h3>
      <p>Здесь откроется канбан кандидатов и дашборд по выбранной вакансии. Или откройте «Архив», чтобы посмотреть закрытые.</p>
    </div>
  );
}

function VacancyDetailStub({ id }) {
  const v = VACANCIES.find(x => x.id === id);
  if (!v) return <EmptyVacancyPane/>;
  return (
    <div className="content-inner">
      <div className="page-header">
        <div className="left">
          <h1 style={{fontSize:22}}>{v.name}</h1>
          <div className="sub">Активная вакансия · 47 кандидатов · открыта 23 дня назад</div>
        </div>
        <div style={{display:'flex', gap:8}}>
          <button className="btn btn-secondary"><Icon name="open" size={14}/> Открыть на hh.ru</button>
          <button className="btn btn-primary"><Icon name="plus" size={14}/> Добавить кандидата</button>
        </div>
      </div>
      <div style={{
        background:'#fff', border:'1px dashed var(--border-strong)', borderRadius:12,
        padding:'48px 32px', textAlign:'center', color:'var(--fg-2)',
      }}>
        <div style={{display:'inline-flex', width:64, height:64, borderRadius:'50%', background:'var(--bg-panel)', alignItems:'center', justifyContent:'center', color:'var(--fg-3)', marginBottom:14}}>
          <Icon name="sparkle" size={28}/>
        </div>
        <div style={{fontSize:15, fontWeight:600, color:'var(--fg-1)', marginBottom:6}}>Канбан и дашборд вакансии</div>
        <div style={{fontSize:13, maxWidth:440, margin:'0 auto'}}>Этот режим спроектируем отдельным экраном — здесь будет воронка кандидатов, переписка с заказчиком и план Глафиры.</div>
      </div>
    </div>
  );
}

function Archive() {
  const [result, setResult] = useStateVac('all');
  const [period, setPeriod] = useStateVac('all');
  const [client, setClient] = useStateVac('all');
  const [recruiter, setRecruiter] = useStateVac('all');
  const [query, setQuery] = useStateVac('');

  const filtered = useMemoVac(() => {
    return ARCHIVE_DATA.filter(a => {
      if (result !== 'all' && a.result !== result) return false;
      if (period !== 'all' && a.period !== period && period !== 'year') return false;
      if (client !== 'all' && a.client !== client) return false;
      if (recruiter !== 'all' && a.recruiter !== recruiter) return false;
      if (query && !a.title.toLowerCase().includes(query.toLowerCase())) return false;
      return true;
    });
  }, [result, period, client, recruiter, query]);

  const hasFilters = result !== 'all' || period !== 'all' || client !== 'all' || recruiter !== 'all' || query !== '';

  const reset = () => {
    setResult('all'); setPeriod('all'); setClient('all'); setRecruiter('all'); setQuery('');
  };

  const resultBadge = (r) => {
    if (r === 'success') return <span className="result-badge success"><Icon name="check" size={11}/> Успех</span>;
    if (r === 'fail')    return <span className="result-badge fail"><Icon name="x" size={11}/> Без найма</span>;
    return <span className="result-badge frozen"><Icon name="pause" size={11}/> Заморожена</span>;
  };

  return (
    <div className="content-inner">
      <div className="archive-head">
        <h1>Архив вакансий</h1>
        <div className="sub">
          {hasFilters
            ? <>Показано <span className="t-mono">{filtered.length}</span> из <span className="t-mono">{ARCHIVE_DATA.length}</span></>
            : <><span className="t-mono">{ARCHIVE_DATA.length}</span> закрытых вакансии</>}
        </div>
      </div>

      <div className="filter-bar">
        <div className="filter-group">
          <span className="filter-label">Результат</span>
          <div className="seg-sm">
            <button className={result === 'all' ? 'active' : ''} onClick={() => setResult('all')}>Все</button>
            <button className={result === 'success' ? 'active' : ''} onClick={() => setResult('success')}>✓ Успех</button>
            <button className={result === 'fail' ? 'active' : ''} onClick={() => setResult('fail')}>✕ Без найма</button>
          </div>
        </div>
        <div className="filter-group">
          <span className="filter-label">Период</span>
          <div className="seg-sm">
            {[
              {id:'week', l:'Неделя'},{id:'month', l:'Месяц'},{id:'quarter', l:'Квартал'},
              {id:'year', l:'Год'},{id:'all', l:'Всё время'}
            ].map(p => (
              <button key={p.id} className={period === p.id ? 'active' : ''} onClick={() => setPeriod(p.id)}>{p.l}</button>
            ))}
          </div>
        </div>
        <div className="filter-group">
          <span className="filter-label">Заказчик</span>
          <button className="dropdown" onClick={() => setClient(client === 'all' ? 'Логос' : 'all')}>
            {client === 'all' ? 'Все' : client} <Icon name="chevD" size={12}/>
          </button>
        </div>
        <div className="filter-group">
          <span className="filter-label">Рекрутер</span>
          <button className="dropdown" onClick={() => setRecruiter(recruiter === 'all' ? 'А. Седова' : 'all')}>
            {recruiter === 'all' ? 'Все' : recruiter} <Icon name="chevD" size={12}/>
          </button>
        </div>
        <div className="filter-spacer"/>
        <div className="submenu-search" style={{width:240, height:28}}>
          <Icon name="search" size={14} style={{color:'var(--fg-3)', flex:'none'}}/>
          <input placeholder="Поиск по архиву…" value={query} onChange={e => setQuery(e.target.value)}/>
        </div>
        {hasFilters && (
          <button className="btn btn-ghost btn-sm" onClick={reset}>
            <Icon name="x" size={14}/> Сбросить
          </button>
        )}
      </div>

      {filtered.length === 0 ? (
        <div className="empty-pane" style={{height:280}}>
          <div className="empty-illust"><Icon name="filter" size={36}/></div>
          <h3>Ничего не найдено</h3>
          <p>По заданным фильтрам ничего не найдено. Попробуйте сбросить часть условий.</p>
          <button className="btn btn-secondary btn-sm" onClick={reset}>Сбросить фильтры</button>
        </div>
      ) : (
        <div className="archive-grid">
          {filtered.map(a => (
            <div key={a.id} className="arch-card">
              <div className="top-row">
                {resultBadge(a.result)}
                <button className="more-btn" onClick={e => e.stopPropagation()}><Icon name="more" size={14}/></button>
              </div>
              <div className="title">{a.title}</div>
              <div className="meta">
                {a.client} <span className="sep">·</span> {a.recruiter}
              </div>
              <div className="meta" style={{display:'flex', gap:10, alignItems:'center'}}>
                <Icon name="clock" size={13} style={{color:'var(--fg-3)'}}/>
                Закрыта за {a.days} {a.days === 1 ? 'день' : (a.days < 5 ? 'дня' : 'дней')}
                <span className="sep">·</span>
                {a.date}
              </div>
              <div className="stats-row">
                <div className="stat-cell">
                  <span className="stat-val">{a.candidates}</span>
                  <span className="stat-lbl">кандидатов</span>
                </div>
                <div className="stat-cell">
                  <span className="stat-val" style={{color: a.hired > 0 ? 'var(--ark-green-600)' : 'var(--fg-3)'}}>{a.hired}</span>
                  <span className="stat-lbl">{a.hired === 1 ? 'нанят' : 'нанято'}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

Object.assign(window, { VacanciesSubmenu, EmptyVacancyPane, VacancyDetailStub, Archive, VACANCIES, ARCHIVE_DATA });
