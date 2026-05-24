// Sidebar — single panel with labels; "Вакансии" expands inline
function Sidebar({ active, onNavigate, vacanciesOpen, onToggleVacancies, vacancyId, onSelectVacancy, archiveActive, onArchive,
                   analyticsOpen, onToggleAnalytics, analyticsReportId, onSelectAnalyticsReport, onCreateVacancy }) {
  const nav = [
    { id: 'home',     label: 'Главная',   icon: 'home' },
    { id: 'vacancies',label: 'Вакансии',  icon: 'briefcase', expandable: 'vacancies' },
    { id: 'candidates',label:'Кандидаты', icon: 'users' },
    { id: 'analytics',label: 'Аналитика', icon: 'chart',     expandable: 'analytics' },
    { id: 'pulse',    label: 'Пульс-Онбординг', icon: 'heart', pip: 2 },
    { id: 'settings', label: 'Настройки', icon: 'settings' },
  ];

  const [query, setQuery] = React.useState('');
  const filtered = React.useMemo(
    () => VACANCIES.filter(v => v.name.toLowerCase().includes(query.toLowerCase())),
    [query]
  );

  const renderVacanciesSub = () => (
    <div className="sub-block">
      <button className="sub-add" onClick={onCreateVacancy}><Icon name="plus" size={14}/> Новая вакансия</button>
      <div className="sub-search">
        <Icon name="search" size={13} style={{color:'var(--fg-3)', flex:'none'}}/>
        <input placeholder="Поиск…" value={query} onChange={e => setQuery(e.target.value)}/>
      </div>
      <div className="sub-list">
        {filtered.length === 0 ? (
          <div className="sub-empty">Ничего не найдено</div>
        ) : filtered.map(v => (
          <div key={v.id}
            className={`sub-row ${vacancyId === v.id && !archiveActive ? 'selected' : ''}`}
            onClick={() => onSelectVacancy(v.id)}>
            <span className={`unread-dot ${v.unread ? '' : 'invisible'}`}/>
            <span className="sub-name">{v.name}</span>
            <span className="sub-count">{v.count}</span>
            {v.newCount > 0 && <span className="sub-new">+{v.newCount}</span>}
          </div>
        ))}
        <div className="sub-divider"/>
        <div className={`sub-archive ${archiveActive ? 'selected' : ''}`} onClick={onArchive}>
          <Icon name="archive" size={15}/>
          <span>Архив</span>
          <span className="sub-count">{ARCHIVE_DATA.length * 10 + 4}</span>
        </div>
      </div>
    </div>
  );

  const renderAnalyticsSub = () => (
    <div className="sub-block">
      <div className="sub-list">
        {window.AN_REPORTS && window.AN_REPORTS.map(r => (
          <div key={r.id}
            className={`sub-row sub-row-an ${analyticsReportId === r.id ? 'selected' : ''}`}
            onClick={() => onSelectAnalyticsReport && onSelectAnalyticsReport(r.id)}>
            <Icon name={r.icon} size={14} style={{flex:'none', color:'var(--fg-2)'}}/>
            <span className="sub-name">{r.label}</span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <aside className="sidebar-wide">
      <div className="brand-wide">
        <div className="brand-mark">
          <span className="brand-emoji">👩🏻</span>
        </div>
        <span className="brand-name">Глафира</span>
        <span className="brand-dancer">💃</span>
      </div>
      <div className="nav-wide">
        {nav.map(n => {
          const isActive = active === n.id;
          const isExpanded = (n.expandable === 'vacancies' && vacanciesOpen) ||
                             (n.expandable === 'analytics' && analyticsOpen);
          return (
            <React.Fragment key={n.id}>
              <button
                className={`nav-row ${isActive ? 'active' : ''}`}
                onClick={() => {
                  if (n.expandable === 'vacancies') onToggleVacancies();
                  else if (n.expandable === 'analytics') onToggleAnalytics && onToggleAnalytics();
                  else onNavigate(n.id);
                }}>
                <Icon name={n.icon} size={18} className="nav-row-icon"/>
                <span className="nav-row-label">{n.label}</span>
                {n.pip ? <span className="nav-row-pip">{n.pip}</span> : null}
                {n.expandable && (
                  <span className={`nav-chev ${isExpanded ? 'open' : ''}`}>
                    <Icon name="chevD" size={14}/>
                  </span>
                )}
              </button>
              {n.expandable === 'vacancies' && isExpanded && renderVacanciesSub()}
              {n.expandable === 'analytics' && isExpanded && renderAnalyticsSub()}
            </React.Fragment>
          );
        })}
      </div>

      <div className="user-card-wide">
        <Avatar name="Анна Седова" size="sm"/>
        <div style={{flex:1, minWidth:0}}>
          <div className="uc-name">Анна Седова</div>
          <div className="uc-role">Старший рекрутер</div>
        </div>
        <button className="icon-btn" aria-label="Уведомления">
          <Icon name="bell" size={16}/>
          <span className="pip"/>
        </button>
      </div>
    </aside>
  );
}

window.Sidebar = Sidebar;
