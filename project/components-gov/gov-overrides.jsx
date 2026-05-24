// GOV-ветка — оверрайды компонентов
// Загружается ПОСЛЕ всех обычных компонентов, ПЕРЕД главным <App>.
// Переопределяет глобальные window.Sidebar / window.CandidatesPool /
// window.CandidateFullPage / window.CandidatesList на гос-версии.

const { useState: useStateG, useMemo: useMemoG, useEffect: useEffectG, useRef: useRefG } = React;

// =====================================================================
// 1. SIDEBAR — переименовать «Кандидаты» → «Кадровый резерв»
// =====================================================================
const _OrigSidebar = window.Sidebar;
function GovSidebar(props) {
  useEffectG(() => {
    // Точечно патчим текст пункта меню после рендера. Иконка `users` остаётся.
    const rows = document.querySelectorAll('.sidebar-wide .nav-row-label');
    rows.forEach(el => {
      if (el.textContent.trim() === 'Кандидаты') el.textContent = 'Кадровый резерв';
    });
  });
  return <_OrigSidebar {...props} />;
}
window.Sidebar = GovSidebar;

// =====================================================================
// 2. Утилиты gov
// =====================================================================
function govOrgShort(id) {
  const o = GOV_ORGS.find(x => x.id === id);
  return o ? o.short : id;
}
function govOrgFull(id) {
  const o = GOV_ORGS.find(x => x.id === id);
  return o ? o.full : id;
}

function ReadinessBadge({ kind, size = 'md' }) {
  const cfg = {
    ready: { label: 'Готов к назначению', short: 'Готов',         dot: '#16A34A', bg: '#DEF5E5', fg: '#128640' },
    needs: { label: 'Нужна актуализация', short: 'Актуализация', dot: '#E0A21A', bg: '#FFF1C8', fg: '#8C6710' },
    risk:  { label: 'Есть риски',         short: 'Риски',        dot: '#DC4646', bg: '#FCE3E3', fg: '#9C2424' },
  }[kind] || { label: '—', short: '—', dot: '#9AA3AE', bg: '#F4F6F8', fg: '#5B6573' };
  return (
    <span className={`gov-ready gov-ready-${size} gov-ready-${kind}`} title={cfg.label}
          style={{background: cfg.bg, color: cfg.fg}}>
      <span className="gov-ready-dot" style={{background: cfg.dot}}/>
      {size === 'sm' ? cfg.short : cfg.label}
    </span>
  );
}

function ClearancePill({ level }) {
  const isNone = level === 'Без допуска';
  return (
    <span className={`gov-clear ${isNone ? 'gov-clear-none' : 'gov-clear-on'}`}>
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="11" width="16" height="10" rx="2"/>
        <path d="M8 11V8a4 4 0 0 1 8 0v3"/>
      </svg>
      {level}
    </span>
  );
}

function GovOrgChip({ orgId, size = 'sm' }) {
  return (
    <span className={`gov-org-chip gov-org-${size}`} title={govOrgFull(orgId)}>
      <span className="gov-org-icon" aria-hidden="true">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 21h18M5 21V10l7-4 7 4v11M9 21v-6M15 21v-6M12 12.5v.01"/>
        </svg>
      </span>
      {govOrgShort(orgId)}
    </span>
  );
}

function GovMessDot({ kind }) {
  const cfg = {
    tg:  { bg:'#229ED9', label:'TG' },
    wa:  { bg:'#25D366', label:'WA' },
    vb:  { bg:'#7360F2', label:'V'  },
    max: { bg:'#0077FF', label:'M'  },
  }[kind] || { bg:'#9AA3AE', label:'?' };
  const titles = { tg:'Telegram', wa:'WhatsApp', vb:'Viber', max:'Max' };
  return (
    <span title={titles[kind] || kind}
      style={{
        width:18, height:18, borderRadius:'50%',
        background: cfg.bg, color:'#fff',
        display:'inline-flex', alignItems:'center', justifyContent:'center',
        fontSize:9, fontWeight:700, letterSpacing:'-0.02em', flex:'none'
      }}>{cfg.label}</span>
  );
}

function MiniDocStatus({ kind, ok, label }) {
  return (
    <span className={`gov-mini ${ok ? 'on' : 'off'}`} title={label}>
      {ok ? (
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l5 5 9-11"/></svg>
      ) : (
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.01"/></svg>
      )}
      {label}
    </span>
  );
}

// =====================================================================
// 3. РАЗДЕЛ «КАДРОВЫЙ РЕЗЕРВ» — замена CandidatesPool
// =====================================================================
function GovCandidatesPool({ onOpen, onAddCandidate }) {
  const [query, setQuery] = useStateG('');
  const [sort, setSort] = useStateG('date');
  const [openSort, setOpenSort] = useStateG(false);
  const [filtersOpen, setFiltersOpen] = useStateG(false);
  const [openFilterSections, setOpenFilterSections] = useStateG(
    new Set(['group','category','org','clearance'])
  );
  const toggleFilterSection = (id) => {
    const next = new Set(openFilterSections);
    if (next.has(id)) next.delete(id); else next.add(id);
    setOpenFilterSections(next);
  };

  const [filters, setFilters] = useStateG({
    groups: new Set(),
    categories: new Set(),
    orgs: new Set(),
    clearances: new Set(),
    expBands: new Set(),     // '<1' | '1-3' | '3-5' | '5+'
    reserveLeft: new Set(),  // '3m' | '6m' | '12m' | 'expired'
    decl: new Set(),         // 'ok' | 'expired' | 'na'
    statuses: new Set(),     // 'active' | 'paused' | 'excluded'
    cities: new Set(),
    period: 'all',
  });
  const toggleSet = (key, val) => {
    const next = new Set(filters[key]);
    if (next.has(val)) next.delete(val); else next.add(val);
    setFilters({ ...filters, [key]: next });
  };
  const resetFilters = () => setFilters({
    groups: new Set(), categories: new Set(), orgs: new Set(), clearances: new Set(),
    expBands: new Set(), reserveLeft: new Set(), decl: new Set(), statuses: new Set(),
    cities: new Set(), period: 'all',
  });
  const activeFilterCount =
    filters.groups.size + filters.categories.size + filters.orgs.size + filters.clearances.size +
    filters.expBands.size + filters.reserveLeft.size + filters.decl.size + filters.statuses.size +
    filters.cities.size + (filters.period !== 'all' ? 1 : 0);

  const expBand = (n) => n < 1 ? '<1' : (n < 3 ? '1-3' : (n < 5 ? '3-5' : '5+'));
  const leftBand = (untilDate) => {
    const m = monthsLeft(untilDate);
    if (m <= 0) return 'expired';
    if (m <= 3) return '3m';
    if (m <= 6) return '6m';
    if (m <= 12) return '12m';
    return null;
  };

  const filtered = useMemoG(() => {
    let list = [...RESERVISTS];
    if (query) list = list.filter(r =>
      r.name.toLowerCase().includes(query.toLowerCase()) ||
      r.position.toLowerCase().includes(query.toLowerCase()));
    if (filters.groups.size)     list = list.filter(r => filters.groups.has(r.group));
    if (filters.categories.size) list = list.filter(r => filters.categories.has(r.category));
    if (filters.orgs.size)       list = list.filter(r => filters.orgs.has(r.govOrg));
    if (filters.clearances.size) list = list.filter(r => filters.clearances.has(r.clearance));
    if (filters.expBands.size)   list = list.filter(r => filters.expBands.has(expBand(r.govExp)));
    if (filters.reserveLeft.size) list = list.filter(r => filters.reserveLeft.has(leftBand(r.reserveUntil)));
    if (filters.decl.size)       list = list.filter(r => filters.decl.has(r.declaration));
    if (filters.statuses.size)   list = list.filter(r => filters.statuses.has(r.status));
    if (filters.cities.size)     list = list.filter(r => filters.cities.has(r.city));

    list.sort((a, b) => {
      if (sort === 'date')      return (b.reserveSince || '').localeCompare(a.reserveSince || '');
      if (sort === 'readiness') {
        const order = { ready: 0, needs: 1, risk: 2 };
        return order[a.readiness] - order[b.readiness];
      }
      if (sort === 'name')      return a.name.localeCompare(b.name);
      if (sort === 'leftAsc')   return monthsLeft(a.reserveUntil) - monthsLeft(b.reserveUntil);
      return 0;
    });
    return list;
  }, [query, sort, filters]);

  const SORT_LABELS = {
    date:      'По дате включения (новые сверху)',
    readiness: 'По индексу готовности',
    leftAsc:   'По сроку резерва (истекают первыми)',
    name:      'По ФИО А–Я',
  };

  return (
    <div className="cp-page" data-screen-label="Кадровый резерв / Список">
      {/* Шапка */}
      <div className="cp-header">
        <div className="cp-header-left">
          <h1 className="cp-title">Кадровый резерв</h1>
          <div className="cp-counter">
            {activeFilterCount > 0 || query
              ? <>Показано <span className="t-mono">{filtered.length}</span> из <span className="t-mono">{RESERVISTS.length}</span> резервистов</>
              : <><span className="t-mono">247</span> резервистов в базе</>}
          </div>
        </div>
        <div className="cp-header-actions">
          <button className="btn btn-secondary btn-sm">
            <Icon name="download" size={14}/> Импорт из Excel
          </button>
          <button className="btn btn-primary btn-sm" onClick={onAddCandidate}>
            <Icon name="plus" size={14}/> Добавить резервиста
          </button>
        </div>
      </div>

      {/* Управление */}
      <div className="cp-controls">
        <div className="cp-search">
          <Icon name="search" size={14} style={{color:'var(--fg-3)', flex:'none'}}/>
          <input
            placeholder="Поиск по ФИО, должности, гос. органу…"
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
        </div>
        <div style={{flex:1}}/>
        <div className={`cp-sort ${openSort ? 'open' : ''}`}>
          <button className="btn btn-secondary btn-sm" onClick={() => setOpenSort(o => !o)}>
            <Icon name="sort" size={14}/> {SORT_LABELS[sort]} <Icon name="chevD" size={12}/>
          </button>
          {openSort && (
            <div className="cp-sort-menu" onMouseLeave={() => setOpenSort(false)}>
              {Object.entries(SORT_LABELS).map(([k, l]) => (
                <button key={k}
                  className={`cp-sort-opt ${sort === k ? 'active' : ''}`}
                  onClick={() => { setSort(k); setOpenSort(false); }}>
                  {l}
                  {sort === k && <Icon name="check" size={14}/>}
                </button>
              ))}
            </div>
          )}
        </div>
        <button className={`btn btn-secondary btn-sm ${activeFilterCount > 0 ? 'has-filters' : ''}`}
                onClick={() => setFiltersOpen(true)}>
          <Icon name="filter" size={14}/> Фильтры
          {activeFilterCount > 0 && <span className="filter-badge">{activeFilterCount}</span>}
        </button>
      </div>

      {/* Сетка карточек */}
      <div className="cp-grid gov-grid">
        {filtered.map(r => (
          <GovReservistCard key={r.id} r={r} onOpen={() => onOpen(r.id)}/>
        ))}
        {filtered.length === 0 && (
          <div className="cp-empty">
            <div className="empty-illust"><Icon name="users" size={36}/></div>
            <h3>Никого не найдено по заданным параметрам</h3>
            <p>Попробуйте изменить фильтры или сбросьте их.</p>
            <button className="btn btn-secondary btn-sm" onClick={resetFilters}>Сбросить фильтры</button>
          </div>
        )}
      </div>

      {filtersOpen && (
        <GovFilterDrawer
          filters={filters} setFilters={setFilters} toggleSet={toggleSet}
          resetFilters={resetFilters}
          openSections={openFilterSections} toggleSection={toggleFilterSection}
          filteredCount={filtered.length}
          onClose={() => setFiltersOpen(false)}
          activeCount={activeFilterCount}/>
      )}
    </div>
  );
}

// ====== Карточка резервиста в списке ======
function GovReservistCard({ r, onOpen }) {
  const left = monthsLeft(r.reserveUntil);
  return (
    <div className="pool-card gov-card" onClick={onOpen}>
      <div className="pc-head">
        <Avatar name={r.name} size="sm"/>
        <div className="pc-name-wrap">
          <div className="pc-name" title={r.name}>{r.short}</div>
          <div className="pc-meta-2l">
            <div className="pc-meta-line">Группа: <b>{r.group}</b></div>
            <div className="pc-meta-line t-clip" title={r.position}>{r.position}</div>
          </div>
        </div>
        <ReadinessBadge kind={r.readiness} size="md"/>
      </div>

      <div className="gov-card-row">
        <span>{r.age} лет</span>
        <span className="sep">·</span>
        <span>Стаж г/с <b>{r.govExp} {r.govExp === 1 ? 'год' : (r.govExp < 5 ? 'года' : 'лет')}</b></span>
      </div>
      <div className="gov-card-row">
        <ClearancePill level={r.clearance}/>
      </div>
      <div className="gov-card-row gov-card-row-muted">
        В резерве: {r.group.toLowerCase()}, до <span className="t-mono">{r.reserveUntil.slice(3)}</span>
        {left <= 3 && left > 0 && <span className="gov-pill gov-pill-warn">истекает через {left} мес</span>}
        {left === 0 && <span className="gov-pill gov-pill-red">истёк</span>}
      </div>

      <div className="pc-divider"/>

      <div className="gov-card-bottom">
        <GovOrgChip orgId={r.govOrg}/>
        <div className="gov-card-mini-row">
          <MiniDocStatus ok={r.declaration === 'ok'} label="Декларация"/>
          <MiniDocStatus ok={r.antikor === 'clean'} label="Антикор"/>
        </div>
      </div>

      {r.status === 'paused' && <span className="gov-status-flag">Приостановлен</span>}
    </div>
  );
}

// ====== Drawer фильтров для гос-резерва ======
function GovFilterDrawer({ filters, setFilters, toggleSet, resetFilters,
                           openSections, toggleSection, filteredCount, onClose, activeCount }) {
  const Section = ({ id, title, count, children }) => {
    const open = openSections.has(id);
    return (
      <div className={`fdr-section ${open ? 'open' : ''}`}>
        <button className="fdr-section-head" onClick={() => toggleSection(id)}>
          <span className="fdr-section-title">{title}</span>
          {count > 0 && <span className="fdr-section-count">{count}</span>}
          <Icon name="chevD" size={14} className={`fdr-chev ${open ? 'rot' : ''}`}/>
        </button>
        {open && <div className="fdr-section-body">{children}</div>}
      </div>
    );
  };

  return (
    <>
      <div className="fdr-overlay" onClick={onClose}/>
      <aside className="fdr">
        <div className="fdr-head">
          <div className="fdr-title">
            Фильтры
            {activeCount > 0 && <button className="fdr-reset-circle" onClick={resetFilters} title="Сбросить">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/>
              </svg>
            </button>}
          </div>
          <button className="icon-btn" onClick={onClose}><Icon name="x" size={18}/></button>
        </div>

        <div className="fdr-pin-row">
          <button className="fdr-pin-btn" disabled={activeCount === 0}>
            <Icon name="bookmark" size={13}/>
            Сохранить настроенный фильтр
          </button>
        </div>

        <div className="fdr-body">
          <Section id="group" title="Группа должностей" count={filters.groups.size}>
            <div className="fdr-chip-row">
              {GOV_GROUPS.map(g => (
                <button key={g} className={`filter-chip ${filters.groups.has(g) ? 'active' : ''}`}
                        onClick={() => toggleSet('groups', g)}>{g}</button>
              ))}
            </div>
          </Section>

          <Section id="category" title="Категория" count={filters.categories.size}>
            <div className="fdr-chip-row">
              {GOV_CATEGORIES.map(c => (
                <button key={c} className={`filter-chip ${filters.categories.has(c) ? 'active' : ''}`}
                        onClick={() => toggleSet('categories', c)}>{c}</button>
              ))}
            </div>
          </Section>

          <Section id="org" title="Гос. орган-источник" count={filters.orgs.size}>
            <div className="fdr-chip-row">
              {GOV_ORGS.map(o => (
                <button key={o.id} className={`filter-chip ${filters.orgs.has(o.id) ? 'active' : ''}`}
                        onClick={() => toggleSet('orgs', o.id)} title={o.full}>{o.short}</button>
              ))}
            </div>
          </Section>

          <Section id="clearance" title="Допуск к гос. тайне" count={filters.clearances.size}>
            <div className="fdr-chip-row">
              {GOV_CLEARANCES.map(c => (
                <button key={c} className={`filter-chip ${filters.clearances.has(c) ? 'active' : ''}`}
                        onClick={() => toggleSet('clearances', c)}>{c}</button>
              ))}
            </div>
          </Section>

          <Section id="exp" title="Стаж гос. службы" count={filters.expBands.size}>
            <div className="fdr-chip-row">
              {[
                {id:'<1',  label:'до 1 года'},
                {id:'1-3', label:'1–3 года'},
                {id:'3-5', label:'3–5 лет'},
                {id:'5+',  label:'5+ лет'},
              ].map(e => (
                <button key={e.id} className={`filter-chip ${filters.expBands.has(e.id) ? 'active' : ''}`}
                        onClick={() => toggleSet('expBands', e.id)}>{e.label}</button>
              ))}
            </div>
          </Section>

          <Section id="left" title="Срок в резерве" count={filters.reserveLeft.size}>
            <div className="fdr-chip-row">
              {[
                {id:'3m',      label:'истекает в 3 мес'},
                {id:'6m',      label:'в 6 мес'},
                {id:'12m',     label:'в год'},
                {id:'expired', label:'истёк'},
              ].map(p => (
                <button key={p.id} className={`filter-chip ${filters.reserveLeft.has(p.id) ? 'active' : ''}`}
                        onClick={() => toggleSet('reserveLeft', p.id)}>{p.label}</button>
              ))}
            </div>
          </Section>

          <Section id="decl" title="Декларация о доходах" count={filters.decl.size}>
            <div className="fdr-chip-row">
              {[
                {id:'ok',      label:'Актуальна'},
                {id:'expired', label:'Просрочена'},
                {id:'na',      label:'Не требуется'},
              ].map(p => (
                <button key={p.id} className={`filter-chip ${filters.decl.has(p.id) ? 'active' : ''}`}
                        onClick={() => toggleSet('decl', p.id)}>{p.label}</button>
              ))}
            </div>
          </Section>

          <Section id="status" title="Статус в резерве" count={filters.statuses.size}>
            <div className="fdr-chip-row">
              {[
                {id:'active',   label:'Активный'},
                {id:'paused',   label:'Приостановлен'},
                {id:'excluded', label:'Исключён'},
              ].map(p => (
                <button key={p.id} className={`filter-chip ${filters.statuses.has(p.id) ? 'active' : ''}`}
                        onClick={() => toggleSet('statuses', p.id)}>{p.label}</button>
              ))}
            </div>
          </Section>

          <Section id="city" title="Город проживания" count={filters.cities.size}>
            <div className="fdr-chip-row">
              {['Новосибирск','Бердск','Искитим','Кольцово'].map(c => (
                <button key={c} className={`filter-chip ${filters.cities.has(c) ? 'active' : ''}`}
                        onClick={() => toggleSet('cities', c)}>{c}</button>
              ))}
            </div>
          </Section>

          <Section id="period" title="Дата включения в резерв" count={filters.period !== 'all' ? 1 : 0}>
            <div className="fdr-chip-row">
              {[
                {id:'all',   label:'Всё время'},
                {id:'week',  label:'Неделя'},
                {id:'month', label:'Месяц'},
                {id:'q',     label:'Квартал'},
                {id:'year',  label:'Год'},
              ].map(p => (
                <button key={p.id} className={`filter-chip ${filters.period === p.id ? 'active' : ''}`}
                        onClick={() => setFilters({...filters, period: p.id})}>{p.label}</button>
              ))}
            </div>
          </Section>
        </div>

        <div className="fdr-foot">
          <button className="btn btn-secondary btn-sm" onClick={resetFilters}>Сбросить всё</button>
          <button className="btn btn-primary btn-sm" onClick={onClose}>Показать {filteredCount}</button>
        </div>
      </aside>
    </>
  );
}

window.CandidatesPool = GovCandidatesPool;

// =====================================================================
// 4. КАРТОЧКА РЕЗЕРВИСТА (full page)
// =====================================================================
// Адаптер: превращает резервиста в объект «candidate-shape» для
function reservistAsCandidate(r) {
  const decYear = 2026 - r.age;
  return {
    id: r.id,
    num: r.id.replace('rv', '').padStart(3, '0'),
    name: r.name,
    age: r.age,
    city: r.city,
    phone: r.phone,
    mess: r.mess,
    pdn: true, // в гос-секторе согласие ПдН всегда подписано (входит в пакет док-в резервиста)
    score: r.matchScore || 88,
    date: r.reserveSince.slice(0, 6) + r.reserveSince.slice(8),
    source: 'pool',
    salary: 0,
    lastDur: `Гос. служба · ${r.govExp} лет`,
    lastCo: govOrgShort(r.govOrg),
    stage: 'added',
  };
}

function GovCandidateFullPage({ candidateId, onBack }) {
  const r = RESERVISTS.find(x => x.id === candidateId);
  if (!r) return <div className="cp-empty">Резервист не найден</div>;

  const [tab, setTab] = useStateG('anketa');
  const left = monthsLeft(r.reserveUntil);
  const assignments = RESERVIST_ASSIGNMENTS[r.id] || [];

  const TABS = [
    { id: 'anketa',  label: 'Анкета' },
    { id: 'match',   label: 'Соответствие требованиям' },
    { id: 'verify',  label: 'Верификация' },
    { id: 'chat',    label: 'Чат' },
    { id: 'docs',    label: 'Документы' },
    { id: 'history', label: 'История назначений', count: assignments.length },
    { id: 'comments',label: 'Комментарии' },
    { id: 'actions', label: 'Все действия' },
  ];

  return (
    <div className="cfp-page gov-cfp" data-screen-label="Кадровый резерв / Карточка резервиста">
      <div className="cfp-back-row">
        <button className="cfp-back" onClick={onBack}>
          <Icon name="chevL" size={14}/> Назад к кадровому резерву
        </button>
      </div>

      {/* Шапка резервиста */}
      <div className="gov-rh">
        <div className="gov-rh-left">
          <Avatar name={r.name} size="lg"/>
          <div className="gov-rh-id">
            <div className="gov-rh-name">{r.name}</div>
            <div className="gov-rh-sub">
              {r.age} лет · {r.city}
            </div>
            <div className="gov-rh-position">
              <b>{r.group}</b> группа · {r.category}
              <span className="sep">·</span>
              <span className="t-clip">{r.position}</span>
            </div>
            <div className="gov-rh-org-row">
              <GovOrgChip orgId={r.govOrg} size="md"/>
              <span className="gov-rh-decree">Приказ <span className="t-mono">{r.decree}</span></span>
            </div>
          </div>
        </div>
        <div className="gov-rh-right">
          <ReadinessBadge kind={r.readiness} size="lg"/>
          <div className="gov-rh-stat">
            <div className="gov-rh-stat-row">
              <span className="lbl">Допуск к гос. тайне</span>
              <span className="val"><ClearancePill level={r.clearance}/></span>
            </div>
            {r.clearanceDate && (
              <div className="gov-rh-stat-row">
                <span className="lbl">Дата оформления</span>
                <span className="val t-mono">{r.clearanceDate}</span>
              </div>
            )}
            <div className="gov-rh-stat-row">
              <span className="lbl">В резерве с</span>
              <span className="val t-mono">{r.reserveSince}</span>
            </div>
            <div className="gov-rh-stat-row">
              <span className="lbl">Срок резерва до</span>
              <span className="val">
                <span className="t-mono">{r.reserveUntil}</span>
                {' '}<span className="gov-rh-left">
                  {left > 0 ? `(осталось ${left} мес)` : '(истёк)'}
                </span>
              </span>
            </div>
            <div className="gov-rh-stat-row">
              <span className="lbl">Статус</span>
              <span className="val">
                {r.status === 'active' && <span className="gov-pill gov-pill-ok">Активный</span>}
                {r.status === 'paused' && <span className="gov-pill gov-pill-warn">Приостановлен</span>}
                {r.status === 'excluded' && <span className="gov-pill gov-pill-red">Исключён</span>}
                {r.statusNote && <span className="gov-rh-note"> · {r.statusNote}</span>}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Контактная строка */}
      <div className="gov-rh-contacts">
        <span className="gov-rc-item"><Icon name="phone" size={13}/> <span className="t-mono">{r.phone}</span></span>
        <span className="gov-rc-item"><Icon name="mail" size={13}/> {r.email}</span>
        <span className="gov-rc-mess">
          {r.mess.map(m => <GovMessDot key={m} kind={m}/>)}
        </span>
      </div>

      {/* Табы */}
      <div className="cc-tabs gov-tabs">
        {TABS.map(t => (
          <button key={t.id}
            className={`cc-tab ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}>
            {t.label}
            {t.count > 0 && <span className="gov-tab-count">{t.count}</span>}
          </button>
        ))}
      </div>

      {/* Контент таба */}
      <div className="gov-tab-content">
        {tab === 'anketa'   && <AnketaTab r={r}/>}
        {tab === 'match'    && <MatchTab r={r}/>}
        {tab === 'verify'   && <GovVerifyHost r={r}/>}
        {tab === 'chat'     && <GovChatHost r={r}/>}
        {tab === 'docs'     && <GovDocsTab r={r}/>}
        {tab === 'history'  && <HistoryTab r={r} assignments={assignments}/>}
        {tab === 'comments' && <GovCommentsHost r={r}/>}
        {tab === 'actions'  && <GovActionsHost r={r}/>}
      </div>
    </div>
  );
}

// ====== АНКЕТА ======
function AnketaTab({ r }) {
  return (
    <div className="gov-anketa">
      <Block title="Основное">
        <KVRow k="ФИО" v={r.name}/>
        <KVRow k="Дата рождения" v={`14.06.${2026 - r.age}`} mono/>
        <KVRow k="Возраст" v={`${r.age} лет`}/>
        <KVRow k="Город" v={r.city}/>
        <KVRow k="Телефон" v={r.phone} mono/>
        <KVRow k="E-mail" v={r.email}/>
      </Block>

      <Block title="Образование">
        <div className="gov-edu-item">
          <div className="gov-edu-line">{r.education}</div>
        </div>
        {r.eduExtra && (
          <div className="gov-edu-item">
            <div className="gov-edu-line gov-edu-extra">{r.eduExtra}</div>
            <div className="gov-edu-sub">Доп. образование / переподготовка</div>
          </div>
        )}
      </Block>

      <Block title="Опыт гос. службы" subtitle={`Общий стаж г/с — ${r.govExp} ${r.govExp === 1 ? 'год' : (r.govExp < 5 ? 'года' : 'лет')}`}>
        <GovServiceTimeline r={r}/>
      </Block>

      <Block title="Классные чины">
        <div className="gov-rank">
          <span className="gov-rank-current">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2l3 7 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z"/>
            </svg>
            {r.rank}
          </span>
          <div className="gov-rank-meta">присвоен 14.05.2023, приказ № 142-к</div>
        </div>
      </Block>

      <Block title="Допуск и статусы">
        <KVRow k="Группа должностей" v={<b>{r.group}</b>}/>
        <KVRow k="Категория"          v={r.category}/>
        <KVRow k="Гос. орган-источник" v={govOrgFull(r.govOrg)}/>
        <KVRow k="Допуск к гос. тайне" v={<><ClearancePill level={r.clearance}/>{r.clearanceDate && <span className="t-mono"> · оформлен {r.clearanceDate}</span>}</>}/>
        <KVRow k="№ приказа о включении в резерв" v={<span className="t-mono">{r.decree}</span>}/>
        <KVRow k="Срок пребывания в резерве" v={<>с <span className="t-mono">{r.reserveSince}</span> по <span className="t-mono">{r.reserveUntil}</span> {monthsLeft(r.reserveUntil) > 0 && <span className="t-muted">(осталось {monthsLeft(r.reserveUntil)} мес)</span>}</>}/>
      </Block>
    </div>
  );
}

function Block({ title, subtitle, children }) {
  return (
    <section className="gov-block">
      <div className="gov-block-head">
        <h3 className="gov-block-title">{title}</h3>
        {subtitle && <span className="gov-block-sub">{subtitle}</span>}
      </div>
      <div className="gov-block-body">{children}</div>
    </section>
  );
}

function KVRow({ k, v, mono }) {
  return (
    <div className="gov-kv">
      <span className="gov-kv-k">{k}</span>
      <span className={`gov-kv-v ${mono ? 't-mono' : ''}`}>{v}</span>
    </div>
  );
}

function GovServiceTimeline({ r }) {
  // Синтетическая лента: 2–3 места, основанные на текущей позиции
  const items = [
    { years: '2022 — наст. вр.', org: govOrgShort(r.govOrg), level: 'Региональный', pos: r.position },
    { years: '2018 — 2022',     org: 'Мэрия г. Новосибирска', level: 'Муниципальный',
      pos: r.category === 'Руководители' ? 'Начальник отдела' : 'Главный специалист' },
    { years: r.govExp >= 8 ? '2013 — 2018' : null, org: 'Управление Росреестра по НСО', level: 'Федеральный',
      pos: 'Ведущий специалист' },
  ].filter(x => x.years);
  return (
    <div className="gov-svc">
      {items.map((it, i) => (
        <div key={i} className="gov-svc-row">
          <div className="gov-svc-dot" data-level={it.level === 'Федеральный' ? 'f' : (it.level === 'Региональный' ? 'r' : 'm')}/>
          <div className="gov-svc-main">
            <div className="gov-svc-top">
              <span className="gov-svc-years t-mono">{it.years}</span>
              <span className="gov-svc-level" data-level={it.level === 'Федеральный' ? 'f' : (it.level === 'Региональный' ? 'r' : 'm')}>
                {it.level}
              </span>
            </div>
            <div className="gov-svc-org">{it.org}</div>
            <div className="gov-svc-pos">{it.pos}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ====== СООТВЕТСТВИЕ ТРЕБОВАНИЯМ ======
function MatchTab({ r }) {
  // Какие группы должностей формально подходят — на основе стажа, образования, допуска
  const groupOK = {
    'Высшая':   r.govExp >= 6 && (r.clearance !== 'Без допуска'),
    'Главная':  r.govExp >= 4 && (r.category === 'Руководители' || r.category === 'Помощники (советники)'),
    'Ведущая':  r.govExp >= 2,
    'Старшая':  r.govExp >= 1,
    'Младшая':  true,
  };
  const currentGroupIdx = GOV_GROUPS.indexOf(r.group);

  return (
    <div className="gov-match">
      <div className="gov-match-head">
        <div className="gov-match-title">Формальное соответствие группам должностей</div>
        <div className="gov-match-sub">
          Расчёт по требованиям ФЗ-79 и квалификационным критериям (стаж, образование, допуск).
          Это не AI-скоринг и не оценка личных качеств.
        </div>
      </div>

      <div className="gov-match-grid">
        {GOV_GROUPS.map((g, i) => {
          const ok = groupOK[g];
          const isCurrent = i === currentGroupIdx;
          return (
            <div key={g} className={`gov-match-row ${ok ? 'on' : 'off'} ${isCurrent ? 'current' : ''}`}>
              <div className="gov-match-grp">
                {g} группа
                {isCurrent && <span className="gov-match-current">текущая</span>}
              </div>
              <div className="gov-match-status">
                {ok
                  ? <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l5 5 9-11"/></svg> Соответствует</>
                  : <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M6 6l12 12M18 6L6 18"/></svg> Недостаточно стажа / допуска</>}
              </div>
              <div className="gov-match-meta">
                {g === 'Высшая' && 'Требуется стаж г/с от 6 лет + допуск к гос. тайне'}
                {g === 'Главная' && 'Стаж г/с от 4 лет, категория «Руководители» / «Помощники»'}
                {g === 'Ведущая' && 'Стаж г/с от 2 лет, высшее образование'}
                {g === 'Старшая' && 'Стаж г/с от 1 года, высшее или среднее проф.'}
                {g === 'Младшая' && 'Без требований к стажу'}
              </div>
            </div>
          );
        })}
      </div>

      <div className="gov-match-foot">
        <div className="gov-match-foot-title">Подходящие категории должностей</div>
        <div className="gov-match-cats">
          {GOV_CATEGORIES.map(c => {
            const ok = (c === r.category) || (r.category === 'Руководители' && c === 'Помощники (советники)');
            return (
              <span key={c} className={`gov-match-cat ${ok ? 'on' : 'off'}`}>
                {ok && <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l5 5 9-11"/></svg>}
                {c}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ====== ДОКУМЕНТЫ ======
function GovDocsTab({ r }) {
  const docs = [
    { name: 'Приказ о включении в резерв.pdf', type:'PDF', size:'124 КБ', date:r.reserveSince, who:'Отдел кадров', kind: 'order' },
    { name: 'Декларация о доходах за 2025 г.pdf', type:'PDF', size:'2.4 МБ', date:r.declarationDate, who:r.short,
      kind: 'declaration', expired: r.declaration === 'expired' },
    { name: 'Справка о судимости.pdf', type:'PDF', size:'88 КБ', date:'14.03.2026', who:'МВД РФ', kind: 'criminal' },
    { name: 'Диплом о высшем образовании.pdf', type:'PDF', size:'1.8 МБ', date:r.reserveSince, who:r.short, kind: 'diploma' },
    { name: r.clearance !== 'Без допуска' ? `Удостоверение о допуске (${r.clearance}).pdf` : null,
      type:'PDF', size:'320 КБ', date: r.clearanceDate, who:'ФСБ', kind: 'clearance' },
    { name: 'Свидетельство о повышении квалификации.pdf', type:'PDF', size:'640 КБ',
      date: '02.11.2024', who: 'РАНХиГС', kind: 'qual' },
    { name: 'Анкета установленной формы.pdf', type:'PDF', size:'420 КБ', date: r.reserveSince, who: r.short, kind: 'form' },
  ].filter(d => d.name);

  return (
    <div className="gov-docs">
      <div className="gov-docs-controls">
        <button className="btn btn-secondary btn-sm">
          <Icon name="filter" size={13}/> Все типы
        </button>
        <button className="btn btn-secondary btn-sm">
          <Icon name="sort" size={13}/> По дате
        </button>
        <div style={{flex:1}}/>
        <button className="btn btn-primary btn-sm">
          <Icon name="plus" size={13}/> Загрузить документ
        </button>
      </div>
      <div className="gov-docs-list">
        {docs.map((d, i) => (
          <div key={i} className="gov-doc-row">
            <div className="gov-doc-icon" data-kind={d.kind}>
              {d.type}
            </div>
            <div className="gov-doc-main">
              <div className="gov-doc-name">
                {d.name}
                {d.expired && <span className="gov-pill gov-pill-warn">просрочена</span>}
              </div>
              <div className="gov-doc-meta">
                <span className="t-mono">{d.date}</span>
                <span className="sep">·</span>
                <span>{d.who}</span>
                <span className="sep">·</span>
                <span>{d.size}</span>
              </div>
            </div>
            <div className="gov-doc-actions">
              <button className="icon-btn" title="Скачать"><Icon name="download" size={14}/></button>
              <button className="icon-btn" title="Открыть"><Icon name="open" size={14}/></button>
              <button className="icon-btn" title="Ещё"><Icon name="more" size={14}/></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ====== ИСТОРИЯ НАЗНАЧЕНИЙ ======
function HistoryTab({ r, assignments }) {
  const STATUS_CFG = {
    in_progress: { label: 'В работе',     cls: 'gov-h-prog' },
    agreed:      { label: 'Согласился',   cls: 'gov-h-agree' },
    declined:    { label: 'Отказался',    cls: 'gov-h-decl' },
    appointed:   { label: 'Назначен',     cls: 'gov-h-app' },
    not_chosen:  { label: 'Не выбран',    cls: 'gov-h-not' },
  };

  return (
    <div className="gov-history">
      <div className="gov-h-head">
        <div className="gov-h-title">История назначений</div>
        <div className="gov-h-sub">
          На какие вакансии резервиста подбирали и чем закончилось. Резервист остаётся в базе после назначения.
        </div>
      </div>

      {assignments.length === 0 ? (
        <div className="gov-h-empty">
          <Icon name="briefcase" size={28} style={{color:'var(--fg-3)', opacity:.5}}/>
          <h3>Резервиста ещё ни на одну вакансию не подбирали</h3>
          <p>Кнопка «🏛 Подобрать из кадрового резерва» в карточке вакансии добавит его сюда автоматически.</p>
        </div>
      ) : (
        <div className="gov-h-list">
          {assignments.map((a, i) => {
            const s = STATUS_CFG[a.status] || { label:a.status, cls:'' };
            return (
              <div key={i} className={`gov-h-row ${s.cls}`}>
                <div className="gov-h-date t-mono">{a.date}</div>
                <div className="gov-h-main">
                  <div className="gov-h-vac">
                    <Icon name="briefcase" size={13} style={{color:'var(--fg-3)', flex:'none'}}/>
                    <span>{a.vacancy}</span>
                  </div>
                  <div className="gov-h-meta">
                    <GovOrgChip orgId={GOV_ORGS.find(o => o.short === a.org)?.id || 'mincifry'}/>
                    {a.note && <span className="gov-h-note">{a.note}</span>}
                  </div>
                </div>
                <div className="gov-h-status">
                  <span className={`gov-h-pill ${s.cls}`}>{s.label}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ====== Хосты для использования исходных табов коммерческой версии ======
function GovVerifyHost({ r }) {
  const c = reservistAsCandidate(r);
  return (
    <div className="gov-host-frame">
      <div className="gov-host-bar">
        <div className="gov-host-bar-ico">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 21h18M5 21V10l7-4 7 4v11M9 21v-6M15 21v-6"/>
          </svg>
        </div>
        <div>
          <div className="gov-host-bar-title">Гос-верификация резервиста</div>
          <div className="gov-host-bar-sub">
            Используется коммерческий модуль верификации (ЕГРЮЛ, ФССП, ЕФРСБ, реестры, AI-разведка).
            Для гос-ветки докладываются реестр дисквалифицированных и антикоррупционные регистры.
          </div>
        </div>
      </div>
      <VerifyTab c={c}/>
    </div>
  );
}

function GovChatHost({ r }) {
  const c = reservistAsCandidate(r);
  return <ChatTab c={c}/>;
}

function GovCommentsHost({ r }) {
  const c = reservistAsCandidate(r);
  return <CommentsTab c={c}/>;
}

function GovActionsHost({ r }) {
  const c = reservistAsCandidate(r);
  return <ActionsTab c={c}/>;
}

// ====== Заглушка для табов, переиспользующих коммерческий модуль ======
function ReuseModuleStub({ kind }) {
  const cfg = {
    verify: {
      title: 'Верификация',
      desc: 'Используется тот же модуль, что в коммерческой версии: ЕГРЮЛ, ФССП, ЕФРСБ, реестры, AI-разведка по открытым источникам.',
      extra: 'Для гос-ветки активируются дополнительные реестры: дисквалифицированных лиц, реестр уволенных в связи с утратой доверия, антикоррупционные регистры.',
      icon: 'antenna',
    },
    chat: {
      title: 'Чат с резервистом',
      desc: 'Используется тот же мультиканальный чат, что в коммерческой версии: Telegram, e-mail, WhatsApp.',
      extra: 'Для гос-ветки Глафира использует шаблоны уведомлений: «Вам доступна вакансия…», «Срок резерва истекает…».',
      icon: 'message',
    },
    comments: {
      title: 'Комментарии',
      desc: 'Внутренние заметки команды отдела кадров о резервисте. Без изменений относительно коммерческой версии.',
      icon: 'message',
    },
    actions: {
      title: 'Все действия',
      desc: 'Лента событий по резервисту: изменения в анкете, движение по вакансиям, продление срока, документы.',
      icon: 'clock',
    },
  }[kind];
  return (
    <div className="gov-reuse">
      <div className="gov-reuse-icon"><Icon name={cfg.icon} size={28}/></div>
      <h3 className="gov-reuse-title">{cfg.title}</h3>
      <p className="gov-reuse-desc">{cfg.desc}</p>
      {cfg.extra && <p className="gov-reuse-extra">{cfg.extra}</p>}
      <button className="btn btn-secondary btn-sm">Открыть полный модуль</button>
    </div>
  );
}

window.CandidateFullPage = GovCandidateFullPage;

// =====================================================================
// 5. КАРТОЧКА ВАКАНСИИ — добавляем кнопку «Подобрать из кадрового резерва»
// =====================================================================
const _OrigCandidatesList = window.CandidatesList;
function GovCandidatesList(props) {
  const [modalOpen, setModalOpen] = useStateG(false);
  const [portalNode, setPortalNode] = useStateG(null);
  const [reserveAdded, setReserveAdded] = useStateG([]);

  useEffectG(() => {
    // Найти .vh-actions после рендера CandidatesList и встроить gov-кнопку
    const tick = () => {
      const node = document.querySelector('.vh-actions');
      if (node && !node.querySelector('.gov-reserve-btn-host')) {
        const host = document.createElement('div');
        host.className = 'gov-reserve-btn-host';
        node.insertBefore(host, node.lastElementChild); // перед "Добавить кандидата"
        setPortalNode(host);
      } else if (node) {
        setPortalNode(node.querySelector('.gov-reserve-btn-host'));
      }
    };
    tick();
    const id = setInterval(tick, 200);
    return () => clearInterval(id);
  }, [props.vacancyId]);

  const onAddReservists = (ids) => {
    setReserveAdded(prev => [...new Set([...prev, ...ids])]);
    setModalOpen(false);
  };

  return (
    <>
      <_OrigCandidatesList {...props} />
      {portalNode && ReactDOM.createPortal(
        <button className="btn btn-gov btn-sm gov-reserve-btn"
                onClick={() => setModalOpen(true)}>
          <span className="gov-btn-ico">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 21h18M5 21V10l7-4 7 4v11M9 21v-6M15 21v-6M12 12v.01"/>
            </svg>
          </span>
          Подобрать из кадрового резерва
        </button>,
        portalNode
      )}
      {modalOpen && (
        <ReserveMatchModal
          vacancyId={props.vacancyId}
          onClose={() => setModalOpen(false)}
          onAdd={onAddReservists}
          alreadyAdded={reserveAdded}/>
      )}
    </>
  );
}
window.CandidatesList = GovCandidatesList;

// =====================================================================
// 6. МОДАЛ ПОДБОРА ИЗ РЕЗЕРВА
// =====================================================================
function ReserveMatchModal({ vacancyId, onClose, onAdd, alreadyAdded }) {
  const [phase, setPhase] = useStateG('loading'); // loading | results | added
  const [selected, setSelected] = useStateG(new Set());
  const [progress, setProgress] = useStateG(0);
  const [filterGroup, setFilterGroup] = useStateG('all');

  // Имитируем работу Глафиры: подбор за 1.6 сек
  useEffectG(() => {
    if (phase !== 'loading') return;
    const start = Date.now();
    const dur = 1600;
    const id = setInterval(() => {
      const t = Math.min(1, (Date.now() - start) / dur);
      setProgress(Math.floor(t * 100));
      if (t >= 1) {
        clearInterval(id);
        setTimeout(() => setPhase('results'), 100);
      }
    }, 60);
    return () => clearInterval(id);
  }, [phase]);

  // Матчинг — берём резервистов с любым matchedFor, плюс пара дополнительных
  const matched = useMemoG(() => {
    const primary = RESERVISTS
      .filter(r => r.matchedFor.length > 0 && r.status === 'active')
      .map(r => ({
        ...r,
        matchScore: r.matchedFor.includes('mincifry-frontend-lead') ? 92 :
                    r.matchedFor.includes('mincifry-it-arch') ? 78 : 65,
        matchReasons: buildMatchReasons(r),
      }));
    const sorted = primary.sort((a, b) => b.matchScore - a.matchScore);
    return sorted;
  }, []);

  const filtered = useMemoG(() => {
    if (filterGroup === 'all') return matched;
    return matched.filter(r => r.group === filterGroup);
  }, [matched, filterGroup]);

  const toggleSel = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const onAddSelected = () => {
    onAdd([...selected]);
    setPhase('added');
    setTimeout(onClose, 1200);
  };

  return (
    <>
      <div className="gov-modal-backdrop" onClick={onClose}/>
      <div className="gov-modal" role="dialog" aria-modal="true">
        <div className="gov-modal-head">
          <div>
            <div className="gov-modal-title">
              <span className="gov-modal-ico">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 21h18M5 21V10l7-4 7 4v11M9 21v-6M15 21v-6"/>
                </svg>
              </span>
              Подбор из кадрового резерва
            </div>
            <div className="gov-modal-sub">
              Для вакансии: <b>Frontend-разработчик (Senior)</b> · Минцифры НСО
            </div>
          </div>
          <button className="icon-btn" onClick={onClose}><Icon name="x" size={18}/></button>
        </div>

        {phase === 'loading' && (
          <div className="gov-modal-loading">
            <div className="gov-loader-orb">
              <div className="gov-loader-pulse"/>
              <Icon name="sparkle" size={26}/>
            </div>
            <div className="gov-loader-text">
              <div className="gov-loader-title">Глафира подбирает кандидатов…</div>
              <div className="gov-loader-sub">Проверяю 247 резервистов по требованиям вакансии</div>
            </div>
            <div className="gov-loader-bar">
              <div className="gov-loader-bar-fill" style={{width: `${progress}%`}}/>
            </div>
            <div className="gov-loader-criteria">
              <div className="gov-loader-crit-item">✓ Соответствие группе должностей</div>
              <div className="gov-loader-crit-item">✓ Стаж и образование</div>
              <div className="gov-loader-crit-item">{progress > 40 ? '✓' : '·'} Допуск к гос. тайне</div>
              <div className="gov-loader-crit-item">{progress > 60 ? '✓' : '·'} Свежесть документов</div>
              <div className="gov-loader-crit-item">{progress > 80 ? '✓' : '·'} Антикоррупционные флаги</div>
            </div>
          </div>
        )}

        {phase === 'results' && (
          <>
            <div className="gov-modal-glaf">
              <div className="gov-modal-glaf-ico">
                <span style={{fontSize:18}}>👩🏻</span>
              </div>
              <div className="gov-modal-glaf-text">
                Нашла <b>{matched.length} резервистов</b>, формально соответствующих вакансии.
                Топ-{Math.min(3, matched.length)} — с допуском {matched[0]?.clearance.toLowerCase()} и опытом гос. службы более 5 лет.
                Отметьте подходящих — добавлю их в воронку с источником «🏛 Из резерва».
              </div>
            </div>

            <div className="gov-modal-filter">
              <span className="gov-modal-filter-lbl">Группа:</span>
              {['all', ...GOV_GROUPS].map(g => (
                <button key={g}
                  className={`filter-chip ${filterGroup === g ? 'active' : ''}`}
                  onClick={() => setFilterGroup(g)}>
                  {g === 'all' ? 'Все' : g}
                </button>
              ))}
            </div>

            <div className="gov-modal-list">
              {filtered.map(r => {
                const isAdded = alreadyAdded.includes(r.id);
                const isSel = selected.has(r.id);
                return (
                  <div key={r.id}
                    className={`gov-match-card ${isSel ? 'sel' : ''} ${isAdded ? 'added' : ''}`}
                    onClick={() => !isAdded && toggleSel(r.id)}>
                    <div className="gov-mc-check">
                      <input type="checkbox" checked={isSel || isAdded} disabled={isAdded} onChange={() => {}}/>
                    </div>
                    <Avatar name={r.name} size="md"/>
                    <div className="gov-mc-main">
                      <div className="gov-mc-top">
                        <div className="gov-mc-name">{r.name}</div>
                        <ReadinessBadge kind={r.readiness} size="sm"/>
                        <span className="gov-mc-score">{r.matchScore}%</span>
                      </div>
                      <div className="gov-mc-sub">
                        {r.age} лет · Стаж г/с {r.govExp} лет · <b>{r.group}</b> группа · {r.category}
                      </div>
                      <div className="gov-mc-org">
                        <GovOrgChip orgId={r.govOrg}/>
                        <ClearancePill level={r.clearance}/>
                        <span className="gov-mc-pos t-clip">{r.position}</span>
                      </div>
                      <div className="gov-mc-reasons">
                        {r.matchReasons.map((rs, i) => (
                          <span key={i} className={`gov-mc-reason ${rs.kind}`}>
                            {rs.kind === 'plus' && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l5 5 9-11"/></svg>}
                            {rs.kind === 'warn' && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.01"/></svg>}
                            {rs.text}
                          </span>
                        ))}
                      </div>
                    </div>
                    {isAdded && <span className="gov-mc-added">Уже в воронке</span>}
                  </div>
                );
              })}
            </div>

            <div className="gov-modal-foot">
              <div className="gov-modal-foot-info">
                {selected.size > 0
                  ? <>Выбрано: <b>{selected.size}</b>. Они появятся в воронке вакансии на этапе «Отобран».</>
                  : <>Отметьте резервистов, которых хотите добавить в воронку.</>}
              </div>
              <div className="gov-modal-foot-actions">
                <button className="btn btn-secondary btn-sm" onClick={onClose}>Отмена</button>
                <button className="btn btn-primary btn-sm"
                  disabled={selected.size === 0}
                  onClick={onAddSelected}>
                  Добавить выбранных {selected.size > 0 && `(${selected.size})`}
                </button>
              </div>
            </div>
          </>
        )}

        {phase === 'added' && (
          <div className="gov-modal-loading">
            <div className="gov-loader-orb" style={{background:'#DEF5E5', borderColor:'#16A34A'}}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#16A34A" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l5 5 9-11"/></svg>
            </div>
            <div className="gov-loader-text">
              <div className="gov-loader-title">Готово</div>
              <div className="gov-loader-sub">
                {selected.size} резервистов добавлены в воронку.
                Я отправлю им предложение через подключённые каналы и зафиксирую в истории назначений.
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function buildMatchReasons(r) {
  const reasons = [];
  if (r.govExp >= 5) reasons.push({ kind:'plus', text: `Стаж г/с ${r.govExp} лет` });
  else reasons.push({ kind:'warn', text: `Стаж г/с всего ${r.govExp} лет` });

  if (r.clearance !== 'Без допуска') reasons.push({ kind:'plus', text: `Допуск ${r.clearance}` });

  if (r.declaration === 'ok') reasons.push({ kind:'plus', text: 'Декларация актуальна' });
  else if (r.declaration === 'expired') reasons.push({ kind:'warn', text: 'Декларация просрочена' });

  if (r.antikor === 'clean') reasons.push({ kind:'plus', text: 'Антикор без флагов' });
  else reasons.push({ kind:'warn', text: 'Антикор-флаг (проверяется)' });

  if (monthsLeft(r.reserveUntil) <= 3) reasons.push({ kind:'warn', text: `Резерв истекает через ${monthsLeft(r.reserveUntil)} мес` });

  return reasons.slice(0, 4);
}
