// CandidatesPool — раздел «Кандидаты» (общая база)
// 4A — список карточек по всей базе, 4B — карточка кандидата на весь экран
const { useState: useStateCP, useMemo: useMemoCP } = React;

// ====== Тестовая база ======
// Расширяем имеющийся CANDIDATES «привязанным» опытом по нескольким вакансиям,
// чтобы показать историю участия. Если CANDIDATES (из Candidates.jsx) загружен — берём из него.
const POOL_BASE = (typeof CANDIDATES !== 'undefined' ? CANDIDATES : []).map(c => ({...c}));

// id вакансий совпадают с тем, что в Vacancies.jsx
const POOL_VACS = {
  fe: { id:'fe', title: 'Frontend-разработчик (Senior)', client: 'Atlas',  recruiter: 'А. Седова', status:'active' },
  wh: { id:'wh', title: 'Кладовщик · смена 2/2',         client: 'Север',  recruiter: 'И. Корнев', status:'active' },
  hr: { id:'hr', title: 'HR-дженералист',                client: 'Логос',  recruiter: 'А. Седова', status:'active' },
  do: { id:'do', title: 'DevOps-инженер',                client: 'Atlas',  recruiter: 'И. Корнев', status:'active' },
  rm: { id:'rm', title: 'Региональный менеджер по продажам', client: 'Атлант', recruiter: 'А. Седова', status:'active' },
  qa: { id:'qa', title: 'QA-инженер (закрыта)',          client: 'Сатурн', recruiter: 'И. Корнев', status:'archived' },
};

// Обогащаем кандидатов историей участия + источником / последней активностью.
// Логика: каждый кандидат уже имеет stage и date — это его «текущая» вакансия.
// Добавим 0–2 прошлых участия чтобы показать «+N».
const POOL = POOL_BASE.map((c, i) => {
  const primaryVacancyId = ['fe','rm','wh','hr','do'][i % 5];
  const history = [{
    vacancyId: primaryVacancyId,
    stage: c.stage,
    date: c.date,
    score: c.score,
    rejectReason: c.stage === 'rejected' ? 'Несоответствие стека' : null,
  }];
  // Несколько кандидатов «засветились» в других вакансиях
  if (i % 3 === 0) {
    history.push({
      vacancyId: 'qa',
      stage: 'rejected',
      date: '12.02.26', closedDate: '28.02.26',
      score: Math.max(30, c.score - 22),
      rejectReason: 'Не прошёл тестовое',
    });
  }
  if (i % 4 === 1) {
    history.push({
      vacancyId: 'do',
      stage: 'hired',
      date: '04.01.26', closedDate: '20.01.26',
      score: Math.min(99, c.score + 4),
    });
  }
  // 2 кандидата — без вакансий, чисто в базе
  const inPoolOnly = (i === 6);
  return {
    ...c,
    addedAt: c.date,
    source: c.source,
    history: inPoolOnly ? [] : history,
    poolOnly: inPoolOnly,
    duplicate: i === 4,
  };
});

// ====== utils ======
function fmtSalaryCP(n) {
  return n.toLocaleString('ru-RU').replace(/,/g, '\u202F');
}
function StageDot({ stage, size = 8 }) {
  const s = STAGES.find(x => x.id === stage);
  if (!s) return null;
  return <span style={{
    display:'inline-block', width:size, height:size, borderRadius:'50%',
    background: s.color, flex:'none'
  }}/>;
}
function StageLabel({ stage }) {
  const s = STAGES.find(x => x.id === stage);
  if (!s) return null;
  let cls = 'sl-neutral';
  if (s.id === 'hired') cls = 'sl-hired';
  else if (s.id === 'rejected') cls = 'sl-rejected';
  return (
    <span className={`stage-label ${cls}`}>
      <StageDot stage={stage}/>
      <span>{s.label}</span>
    </span>
  );
}

// ====== 4A. Список ======
function CandidatesPool({ onOpen, onAddCandidate }) {
  const [query, setQuery] = useStateCP('');
  const [sort, setSort] = useStateCP('date');
  const [openSort, setOpenSort] = useStateCP(false);
  const [filtersOpen, setFiltersOpen] = useStateCP(false);
  const [openFilterSections, setOpenFilterSections] = useStateCP(new Set(['ai','source','vacancy']));
  const toggleFilterSection = (id) => {
    const next = new Set(openFilterSections);
    if (next.has(id)) next.delete(id); else next.add(id);
    setOpenFilterSections(next);
  };

  const [filters, setFilters] = useStateCP({
    aiMin: 0,
    cities: new Set(),
    exp: new Set(),       // '<1' | '1-3' | '3-5' | '5+'
    sources: new Set(),
    vacancies: new Set(),
    stages: new Set(),    // включая 'pool'
    period: 'all',
  });
  const toggleSetFilter = (key, val) => {
    const next = new Set(filters[key]);
    if (next.has(val)) next.delete(val); else next.add(val);
    setFilters({ ...filters, [key]: next });
  };
  const resetFilters = () => setFilters({
    aiMin: 0, cities: new Set(), exp: new Set(),
    sources: new Set(), vacancies: new Set(), stages: new Set(),
    period: 'all',
  });
  const activeFilterCount =
    (filters.aiMin > 0 ? 1 : 0) +
    filters.cities.size +
    filters.exp.size +
    filters.sources.size +
    filters.vacancies.size +
    filters.stages.size +
    (filters.period !== 'all' ? 1 : 0);

  const filtered = useMemoCP(() => {
    let list = [...POOL];
    if (query) list = list.filter(c => c.name.toLowerCase().includes(query.toLowerCase()));
    if (filters.aiMin > 0) list = list.filter(c => c.score >= filters.aiMin);
    if (filters.cities.size) list = list.filter(c => filters.cities.has(c.city));
    if (filters.sources.size) list = list.filter(c => filters.sources.has(c.source));
    if (filters.vacancies.size) list = list.filter(c => c.history.some(h => filters.vacancies.has(h.vacancyId)));
    if (filters.stages.size) {
      list = list.filter(c => {
        if (filters.stages.has('pool') && c.poolOnly) return true;
        return c.history.some(h => filters.stages.has(h.stage));
      });
    }
    list.sort((a, b) => {
      if (sort === 'date')  return (b.addedAt || '').localeCompare(a.addedAt || '');
      if (sort === 'score') return b.score - a.score;
      if (sort === 'name')  return a.name.localeCompare(b.name);
      if (sort === 'activity') return (b.addedAt || '').localeCompare(a.addedAt || '');
      return 0;
    });
    return list;
  }, [query, sort, filters]);

  const SORT_LABELS = {
    date: 'По дате добавления',
    score: 'По AI-скорингу',
    name: 'По ФИО А–Я',
    activity: 'По последней активности',
  };

  return (
    <div className="cp-page" data-screen-label="Candidates / Pool list">
      {/* ====== Шапка раздела (sticky) ====== */}
      <div className="cp-header">
        <div className="cp-header-left">
          <h1 className="cp-title">Кандидаты</h1>
          <div className="cp-counter">
            {activeFilterCount > 0 || query
              ? <>Показано <span className="t-mono">{filtered.length}</span> из <span className="t-mono">{POOL.length}</span></>
              : <><span className="t-mono">{POOL.length}</span> кандидатов в базе</>}
          </div>
        </div>
        <div className="cp-header-actions">
          <button className="btn btn-secondary btn-sm">
            <Icon name="download" size={14}/> Импорт из файла
          </button>
          <button className="btn btn-primary btn-sm" onClick={onAddCandidate}>
            <Icon name="plus" size={14}/> Добавить кандидата
          </button>
        </div>
      </div>

      {/* ====== Панель управления (sticky) ====== */}
      <div className="cp-controls">
        <div className="cp-search">
          <Icon name="search" size={14} style={{color:'var(--fg-3)', flex:'none'}}/>
          <input
            placeholder="Поиск по ФИО, телефону, email…"
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

      {/* ====== Сетка карточек ====== */}
      <div className="cp-grid">
        {filtered.map(c => (
          <PoolCard key={c.id} c={c} onOpen={() => onOpen(c.id)}/>
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
        <PoolFilterDrawer
          filters={filters} setFilters={setFilters}
          toggleSetFilter={toggleSetFilter}
          resetFilters={resetFilters}
          openSections={openFilterSections}
          toggleSection={toggleFilterSection}
          filteredCount={filtered.length}
          onClose={() => setFiltersOpen(false)}
          activeCount={activeFilterCount}
        />
      )}
    </div>
  );
}

// ====== Drawer с фильтрами (как в Вакансиях) ======
function PoolFilterDrawer({ filters, setFilters, toggleSetFilter, resetFilters,
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
                <path d="M3 12a9 9 0 1 0 3-6.7"/>
                <path d="M3 4v5h5"/>
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
          <Section id="ai" title="AI-скоринг" count={filters.aiMin > 0 ? 1 : 0}>
            <div className="fdr-slider-row">
              <input type="range" min="0" max="100" step="5"
                     value={filters.aiMin}
                     onChange={e => setFilters({...filters, aiMin: +e.target.value})}/>
              <span className="fdr-slider-val t-mono">от {filters.aiMin}</span>
            </div>
            <div className="fdr-tick-row">
              <span>0</span><span>50</span><span>100</span>
            </div>
          </Section>

          <Section id="source" title="Источник" count={filters.sources.size}>
            <div className="fdr-chip-row">
              {[
                {id:'hh',     label:'hh.ru'},
                {id:'avito',  label:'Авито'},
                {id:'tg',     label:'Глафира · Telegram'},
                {id:'import', label:'Импорт'},
                {id:'manual', label:'Ручной ввод'},
              ].map(s => (
                <button key={s.id}
                        className={`filter-chip ${filters.sources.has(s.id) ? 'active' : ''}`}
                        onClick={() => toggleSetFilter('sources', s.id)}>
                  {s.label}
                </button>
              ))}
            </div>
          </Section>

          <Section id="vacancy" title="Вакансия" count={filters.vacancies.size}>
            <div className="fdr-chip-row">
              {Object.values(POOL_VACS).map(v => (
                <button key={v.id}
                        className={`filter-chip ${filters.vacancies.has(v.id) ? 'active' : ''}`}
                        onClick={() => toggleSetFilter('vacancies', v.id)}>
                  {v.title}
                </button>
              ))}
            </div>
          </Section>

          <Section id="stage" title="Этап воронки" count={filters.stages.size}>
            <div className="fdr-chip-row">
              {STAGES.filter(s => !s.separated).map(s => (
                <button key={s.id}
                        className={`filter-chip ${filters.stages.has(s.id) ? 'active' : ''}`}
                        onClick={() => toggleSetFilter('stages', s.id)}>
                  <span className="stage-dot" style={{background: s.color, marginRight: 6}}/>
                  {s.label}
                </button>
              ))}
              <button className={`filter-chip ${filters.stages.has('pool') ? 'active' : ''}`}
                      onClick={() => toggleSetFilter('stages', 'pool')}>
                В базе (без вакансии)
              </button>
            </div>
          </Section>

          <Section id="city" title="Город проживания" count={filters.cities.size}>
            <div className="fdr-chip-row">
              {['Москва','СПб','Новосибирск'].map(c => (
                <button key={c}
                        className={`filter-chip ${filters.cities.has(c) ? 'active' : ''}`}
                        onClick={() => toggleSetFilter('cities', c)}>
                  {c}
                </button>
              ))}
            </div>
          </Section>

          <Section id="exp" title="Опыт работы" count={filters.exp.size}>
            <div className="fdr-chip-row">
              {[
                {id:'<1',  label:'до 1 года'},
                {id:'1-3', label:'1–3 года'},
                {id:'3-5', label:'3–5 лет'},
                {id:'5+',  label:'5+ лет'},
              ].map(e => (
                <button key={e.id}
                        className={`filter-chip ${filters.exp.has(e.id) ? 'active' : ''}`}
                        onClick={() => toggleSetFilter('exp', e.id)}>
                  {e.label}
                </button>
              ))}
            </div>
          </Section>

          <Section id="period" title="Период добавления" count={filters.period !== 'all' ? 1 : 0}>
            <div className="fdr-chip-row">
              {[
                {id:'all',   label:'Всё время'},
                {id:'week',  label:'Неделя'},
                {id:'month', label:'Месяц'},
                {id:'q',     label:'Квартал'},
                {id:'year',  label:'Год'},
              ].map(p => (
                <button key={p.id}
                        className={`filter-chip ${filters.period === p.id ? 'active' : ''}`}
                        onClick={() => setFilters({...filters, period: p.id})}>
                  {p.label}
                </button>
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

// ====== Карточка кандидата в сетке ======
function PoolCard({ c, onOpen }) {
  const lastVac = c.history.length > 0
    ? c.history.slice().sort((a,b) => (b.date||'').localeCompare(a.date||''))[0]
    : null;
  const otherCount = c.history.length - 1;
  const v = lastVac ? POOL_VACS[lastVac.vacancyId] : null;

  return (
    <div className="pool-card" onClick={onOpen}>
      <div className="pc-head">
        <Avatar name={c.name} size="sm"/>
        <div className="pc-name-wrap">
          <div className="pc-name" title={c.name}>{c.name}</div>
          <div className="pc-meta-2l">
            <div className="pc-meta-line">{c.age} лет</div>
            <div className="pc-meta-line t-clip" title={`${c.lastDur} · ${c.lastCo}`}>
              {c.lastDur} · {c.lastCo}
            </div>
          </div>
        </div>
        <ScoreBadge score={c.score} size="lg"/>
      </div>

      {c.duplicate && <span className="pc-dup-flag">Дубль</span>}

      <div className="pc-divider"/>

      {lastVac && v ? (
        <div className="pc-vac">
          <div className="pc-vac-head">
            <Icon name="briefcase" size={13} className="pc-vac-icon"/>
            <span className="pc-vac-title" title={v.title}>{v.title}</span>
            {otherCount > 0 && (
              <span className="pc-vac-more" title={`Ещё в ${otherCount} вакансиях`}>+{otherCount}</span>
            )}
          </div>
          <StageLabel stage={lastVac.stage}/>
        </div>
      ) : (
        <div className="pc-vac pc-vac-empty">
          <span className="pc-vac-empty-dot"/>
          В базе · не привязан к вакансии
        </div>
      )}
    </div>
  );
}

// ====== 4B. Карточка кандидата на весь экран ======
// Использует CandidateDetail из Candidates.jsx 1-в-1, добавляет «Назад» и блок «История участия».
function CandidateFullPage({ candidateId, onBack }) {
  const c = POOL.find(x => x.id === candidateId);
  if (!c) return <div className="cp-empty">Кандидат не найден</div>;

  // Сортируем историю: активные сверху, дальше по дате убывания
  const history = c.history.slice().sort((a, b) => {
    const va = POOL_VACS[a.vacancyId], vb = POOL_VACS[b.vacancyId];
    if (va?.status !== vb?.status) return va?.status === 'active' ? -1 : 1;
    return (b.date || '').localeCompare(a.date || '');
  });

  // Контекстная вакансия для CandidateDetail — самая свежая активная или любая первая.
  const ctxHist = history.find(h => POOL_VACS[h.vacancyId]?.status === 'active') || history[0];
  const ctxVac = ctxHist
    ? { title: POOL_VACS[ctxHist.vacancyId].title }
    : { title: '— без привязки к вакансии —' };

  return (
    <div className="cfp-page" data-screen-label="Candidates / Candidate Page">
      {/* Назад */}
      <div className="cfp-back-row">
        <button className="cfp-back" onClick={onBack}>
          <Icon name="chevL" size={14}/> Назад к кандидатам
        </button>
      </div>

      {/* История участия в вакансиях */}
      <div className="cfp-history">
        <div className="cfp-section-head">
          <h2 className="cfp-section-title">История участия в вакансиях</h2>
          <span className="cfp-section-count">{history.length}</span>
        </div>
        {history.length === 0 ? (
          <div className="cfp-history-empty">
            <span>Кандидат пока ни в одной вакансии</span>
            <button className="btn btn-secondary btn-sm">
              <Icon name="briefcase" size={14}/> Назначить на вакансию
            </button>
          </div>
        ) : (
          <div className="cfp-history-list">
            {history.map((h, i) => {
              const v = POOL_VACS[h.vacancyId];
              if (!v) return null;
              return (
                <div key={i} className="cfp-h-row">
                  <div className="cfp-h-row-main">
                    <div className="cfp-h-vac">
                      <Icon name="briefcase" size={14} style={{color:'var(--fg-3)', flex:'none'}}/>
                      <span className="cfp-h-vac-title">{v.title}</span>
                      <span className={`cfp-vac-status ${v.status === 'active' ? 'on' : 'off'}`}>
                        {v.status === 'active' ? 'Активна' : 'В архиве'}
                      </span>
                    </div>
                    <div className="cfp-h-stage">
                      <StageLabel stage={h.stage}/>
                    </div>
                  </div>
                  <div className="cfp-h-row-meta">
                    <span>Заказчик: <b>{v.client}</b></span>
                    <span className="sep">·</span>
                    <span>Рекрутер: {v.recruiter}</span>
                    <span className="sep">·</span>
                    <span className="t-mono">
                      Отбор: {h.date}
                      {h.closedDate && ` → ${h.stage === 'hired' ? 'Нанят' : 'Отказ'}: ${h.closedDate}`}
                    </span>
                    <span className="sep">·</span>
                    <span>Скоринг: <ScoreBadge score={h.score} size="sm"/></span>
                  </div>
                  {h.rejectReason && (
                    <div className="cfp-h-reject">Причина отказа: {h.rejectReason}</div>
                  )}
                  <button className="cfp-h-go" title="Перейти к карточке внутри вакансии">
                    <Icon name="arrowRight" size={14}/>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Карточка соискателя — точь-в-точь такая же, как в вакансиях, но во весь экран */}
      <div className="cfp-detail-host">
        <CandidateDetail candidate={c} vacancy={ctxVac} onClose={onBack} fromPool={true}/>
      </div>
    </div>
  );
}

Object.assign(window, { CandidatesPool, CandidateFullPage, POOL, POOL_VACS });
