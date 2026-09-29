// Sidebar — single panel with labels; "Вакансии" expands inline
function Sidebar({ active, onNavigate, vacanciesOpen, onToggleVacancies, vacancyId, onSelectVacancy, archiveActive, onArchive,
                   analyticsOpen, onToggleAnalytics, analyticsReportId, onSelectAnalyticsReport, onCreateVacancy,
                   requestsActive, onRequests, newRequestsCount, requestsCount, managerMode, managerUser,
                   allVacanciesActive, onAllVacancies, chatUnread, chatOpen, onToggleChat }) {
  const nav = [
    { id: 'home',     label: 'Главная',   icon: 'home' },
    { id: 'vacancies',label: 'Вакансии',  icon: 'briefcase', expandable: 'vacancies', pip: newRequestsCount || 0 },
    { id: 'candidates',label:'Кандидаты', icon: 'users' },
    { id: 'smart',    label: 'Умный подбор', icon: 'sparkle' },
    { id: 'analytics',label: 'Аналитика', icon: 'chart',     expandable: 'analytics' },
    { id: 'pulse',    label: 'Пульс-Онбординг', icon: 'heart', pip: 2 },
    { id: 'settings', label: 'Настройки', icon: 'settings' },
  ];

  const [query, setQuery] = React.useState('');
  const [othersOpen, setOthersOpen] = React.useState(false);
  const filtered = React.useMemo(
    () => VACANCIES.filter(v => v.name.toLowerCase().includes(query.toLowerCase())),
    [query]
  );
  const mine = filtered.filter(v => v.owner === ME);
  const others = filtered.filter(v => v.owner !== ME);
  const showOthers = othersOpen || query.length > 0;

  const vacRow = (v) => (
    <div key={v.id}
      className={`sub-row ${vacancyId === v.id && !archiveActive && !requestsActive && !allVacanciesActive ? 'selected' : ''}`}
      onClick={() => onSelectVacancy(v.id)}>
      <span className={`unread-dot ${v.unread ? '' : 'invisible'}`}/>
      <span className="sub-name">{v.name}</span>
      <span className="sub-count">{v.count}</span>
      {v.newCount > 0 && <span className="sub-new">+{v.newCount}</span>}
    </div>
  );

  const renderVacanciesSub = () => (
    <div className="sub-block">
      <div className={`sub-archive sub-requests ${requestsActive ? 'selected' : ''}`} onClick={onRequests}>
        <Icon name="inbox" size={15}/>
        <span>Заявки</span>
        {newRequestsCount > 0 && <span className="sub-new">+{newRequestsCount}</span>}
        <span className="sub-count">{requestsCount}</span>
      </div>
      <div className="sub-divider"/>
      <div className={`sub-archive sub-all ${allVacanciesActive ? 'selected' : ''}`} onClick={onAllVacancies}>
        <Icon name="grid" size={15}/>
        <span>Все вакансии</span>
        <span className="sub-count">{VACANCIES.length}</span>
      </div>
      <button className="sub-add" onClick={onCreateVacancy}><Icon name="plus" size={14}/> Новая вакансия</button>
      <div className="sub-search">
        <Icon name="search" size={13} style={{color:'var(--fg-3)', flex:'none'}}/>
        <input placeholder="Поиск…" value={query} onChange={e => setQuery(e.target.value)}/>
      </div>
      <div className="sub-list">
        {filtered.length === 0 ? (
          <div className="sub-empty">Ничего не найдено</div>
        ) : (
          <>
            <div className="sub-group-label">Мои <span>{mine.length}</span></div>
            {mine.length === 0 ? <div className="sub-empty">У вас нет вакансий в работе</div> : mine.map(vacRow)}
            <div className="sub-divider"/>
            <button className="sub-group-toggle" onClick={() => setOthersOpen(o => !o)}>
              <Icon name="chevD" size={12} className={showOthers ? 'open' : ''}/>
              Остальные <span>{others.length}</span>
            </button>
            {showOthers && others.map(vacRow)}
          </>
        )}
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
        <span className="brand-ver">v1.2.4</span>
        <span className="brand-dancer">💃</span>
      </div>
      {managerMode ? (
        <div className="nav-wide">
          <button className="nav-row active">
            <Icon name="inbox" size={18} className="nav-row-icon"/>
            <span className="nav-row-label">Мои заявки</span>
          </button>
        </div>
      ) : (
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
      )}

      <div className="user-card-wide">
        <Avatar name={managerMode ? managerUser.name : 'Анна Седова'} size="sm"/>
        <div style={{flex:1, minWidth:0}}>
          <div className="uc-name">{managerMode ? managerUser.name : 'Анна Седова'}</div>
          <div className="uc-role">{managerMode ? 'Нанимающий менеджер' : 'Старший рекрутер'}</div>
        </div>
        <div className="ucw-actions">
          {!managerMode && (
            <button className={`icon-btn ${chatOpen ? 'active' : ''}`} aria-label="Чаты" title="Чаты с кандидатами" onClick={onToggleChat}>
              <Icon name="message" size={16}/>
              {chatUnread > 0 && <span className="badge">{chatUnread}</span>}
            </button>
          )}
          <button className="icon-btn" aria-label="Уведомления" title="Уведомления">
            <Icon name="bell" size={16}/>
            <span className="pip"/>
          </button>
          <button className="icon-btn" aria-label="Выход" title="Выход">
            <Icon name="logout" size={16}/>
          </button>
        </div>
      </div>
    </aside>
  );
}

window.Sidebar = Sidebar;
