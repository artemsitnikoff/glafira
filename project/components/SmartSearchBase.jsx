// SmartSearchBase — ветка «Умный подбор по своей базе кандидатов».
// Два режима ввода:
//   1) Промт (аля ChatGPT) — «напишите, кто вам нужен» → найдём релевантных в базе.
//   2) Галочка «Искать по открытой вакансии» → выбор вакансии + автофильтры (как на hh) → поиск по базе.
// Состояния: build → running → done (результаты — карточки кандидатов из базы).
const { useState: useStateSB, useMemo: useMemoSB, useEffect: useEffectSB, useRef: useRefSB } = React;

// ====== Доменные наборы навыков (для правдоподобных тегов и матчинга) ======
const SB_DOMAINS = {
  fe:    { label:'Frontend',  tags:['React','TypeScript','Redux','JavaScript','REST API','CSS'] },
  sales: { label:'Продажи',   tags:['B2B-продажи','CRM','Переговоры','Холодные звонки','Воронка'] },
  devops:{ label:'DevOps',    tags:['Kubernetes','Docker','Terraform','CI/CD','Linux','Ansible'] },
  qa:    { label:'QA',        tags:['Python','Selenium','Pytest','API-тесты','SQL'] },
  hr:    { label:'HR',        tags:['Подбор','Адаптация','HR-бренд','1С:ЗУП','Кадровый учёт'] },
};
const SB_ORDER = ['fe','sales','devops','qa','hr'];

const SB_STOP = new Set(['на','по','и','с','в','во','для','от','до','лет','год','года','опыт','опытом',
  'нужен','нужна','нужны','нужно','ищу','ищем','найти','нам','уровня','уровень','или','а','со','же','от']);

function sbParseYears(dur) {
  const m = (dur || '').match(/(\d+)\s*(год|лет|года)/);
  return m ? +m[1] : 1;
}
function sbTokens(str) {
  return (str || '').toLowerCase().replace(/ё/g, 'е')
    .split(/[^a-zа-я0-9+]+/i)
    .filter(t => t.length >= 2 && !SB_STOP.has(t));
}

// База кандидатов = CANDIDATES, обогащённые доменом / тегами / опытом
const SB_POOL = (typeof CANDIDATES !== 'undefined' ? CANDIDATES : []).map(c => {
  const domKey = SB_ORDER[(c.id - 1) % SB_ORDER.length];
  const dom = SB_DOMAINS[domKey];
  const start = c.id % dom.tags.length;
  const rotated = [...dom.tags.slice(start), ...dom.tags.slice(0, start)];
  const tags = rotated.slice(0, 3 + (c.id % 2));
  return {
    ...c,
    domain: domKey,
    domainLabel: dom.label,
    tags,
    years: sbParseYears(c.lastDur),
  };
});

function sbRelColor(p) {
  if (p >= 80) return 'green';
  if (p >= 60) return 'blue';
  return 'gray';
}

// Ранжирование базы под набор «искомых» токенов + доменных тегов вакансии
function sbRank({ tokens = [], wantTags = [], wantCity = '' }) {
  const wantTagsL = wantTags.map(t => t.toLowerCase());
  const ranked = SB_POOL.map(c => {
    const tagsL = c.tags.map(t => t.toLowerCase());
    // совпадения тегов с искомыми тегами (вакансия) ИЛИ токенами промта
    const matched = c.tags.filter(tag => {
      const tl = tag.toLowerCase();
      const byWant = wantTagsL.some(w => w === tl || w.includes(tl) || tl.includes(w));
      const byTok  = tokens.some(t => tl.includes(t) || t.includes(tl.split(/[ -]/)[0]));
      return byWant || byTok;
    });
    const domHit = tokens.some(t => c.domainLabel.toLowerCase().includes(t)) ? 1 : 0;
    const cityHit = (wantCity && c.city === wantCity) ||
                    tokens.some(t => c.city.toLowerCase().includes(t)) ? 1 : 0;
    const hits = matched.length + domHit;
    let rel;
    if (hits === 0 && !cityHit) {
      rel = Math.max(34, c.score - 44);            // нет совпадений — близость по AI-баллу
    } else {
      rel = Math.min(98, 56 + hits * 12 + cityHit * 7 + Math.round((c.score - 70) / 6));
    }
    return { ...c, _matched: matched, _hits: hits, _cityHit: !!cityHit, _rel: Math.max(30, rel) };
  });
  ranked.sort((a, b) => (b._hits - a._hits) || (b._rel - a._rel) || (b.score - a.score));
  const anyHits = ranked.some(r => r._hits > 0 || r._cityHit);
  const list = anyHits ? ranked.filter(r => r._hits > 0 || r._cityHit) : ranked;
  return { list: list.slice(0, 8), exact: anyHits };
}

const SB_EXAMPLES = [
  'Senior Frontend на React, от 5 лет, Москва',
  'Менеджер по продажам B2B с опытом холодных звонков',
  'DevOps-инженер: Kubernetes, Docker, CI/CD',
  'QA-автоматизатор на Python',
];

// История поиска по своей базе (отдельная от истории hh)
const SB_HISTORY = [
  { id:1, kind:'prompt',  text:'Senior Frontend на React, от 5 лет',  date:'6 апреля 2026',  found:8, added:3 },
  { id:2, kind:'vacancy', vacId:'sl', text:'Менеджер по продажам B2B', date:'2 апреля 2026',  found:5, added:2 },
  { id:3, kind:'prompt',  text:'DevOps: Kubernetes, Docker, CI/CD',    date:'28 марта 2026',  found:6, added:1 },
];

// ====== Главный компонент ветки ======
function SSBaseFlow({ vacancies = [], onBack, onOpenCandidate, onGoFunnel }) {
  const [byVacancy, setByVacancy] = useStateSB(false);   // галочка «искать по открытой вакансии»
  const [prompt, setPrompt] = useStateSB('');
  const [phase, setPhase] = useStateSB('build');         // build | running | done

  // режим вакансии
  const [vacId, setVacId] = useStateSB(null);
  const [selOpen, setSelOpen] = useStateSB(false);
  const [skills, setSkills] = useStateSB([]);
  const [area, setArea] = useStateSB('');
  const [role, setRole] = useStateSB('');
  const [exp, setExp] = useStateSB('');

  // результаты + выполнение
  const [results, setResults] = useStateSB([]);
  const [exact, setExact] = useStateSB(true);
  const [criteria, setCriteria] = useStateSB(null);      // {kind:'prompt'|'vacancy', text, tags}
  const [seen, setSeen] = useStateSB(0);
  const [added, setAdded] = useStateSB(() => new Set());
  const timers = useRefSB([]);
  const seenInt = useRefSB(null);

  const vac = useMemoSB(() => vacancies.find(v => v.id === vacId) || null, [vacId, vacancies]);

  useEffectSB(() => () => { timers.current.forEach(clearTimeout); clearInterval(seenInt.current); }, []);

  function selectVacancy(id) {
    const v = vacancies.find(x => x.id === id);
    if (!v) return;
    setVacId(id); setSelOpen(false);
    setSkills([...v.skills]); setArea(v.area); setRole(v.role); setExp(v.exp);
  }

  const canSearch = byVacancy ? !!vac : prompt.trim().length > 2;

  function runSearch() {
    if (!canSearch) return;
    let ranked, crit;
    if (byVacancy && vac) {
      ranked = sbRank({ tokens: sbTokens(role + ' ' + area), wantTags: skills });
      crit = { kind:'vacancy', text: vac.title, tags: skills };
    } else {
      const toks = sbTokens(prompt);
      ranked = sbRank({ tokens: toks });
      crit = { kind:'prompt', text: prompt.trim(), tags: [] };
    }
    setResults(ranked.list); setExact(ranked.exact); setCriteria(crit);

    // короткая анимация «чтения базы»
    setPhase('running'); setSeen(0);
    const target = SB_POOL.length;
    let c = 0;
    seenInt.current = setInterval(() => {
      c = Math.min(target, c + Math.max(1, Math.round(target / 16)));
      setSeen(c);
      if (c >= target) clearInterval(seenInt.current);
    }, 70);
    timers.current.push(setTimeout(() => setPhase('done'), 1700));
  }

  function resetSearch() {
    timers.current.forEach(clearTimeout); clearInterval(seenInt.current);
    setPhase('build'); setResults([]); setCriteria(null); setSeen(0);
  }

  // повтор поиска из истории — заполняет соответствующий метод
  function pickHistory(h) {
    if (h.kind === 'vacancy') { setByVacancy(true); selectVacancy(h.vacId); }
    else { setByVacancy(false); setVacId(null); setSelOpen(false); setPrompt(h.text); }
  }

  // ====== ВЫПОЛНЕНИЕ ======
  if (phase === 'running') {
    return (
      <div className="ss-page" data-screen-label="Smart Search / Base / Running">
        <SSHeader onBack={onBack} sub={baseSub}/>
        <div className="ss-run">
          <div className="ss-run-dancer">💃</div>
          <div className="ss-run-phase">Глафира читает вашу базу…</div>
          <div className="ss-run-detail">
            сопоставляет <span className="t-mono">{ssFmt(seen)}</span> из <span className="t-mono">{ssFmt(SB_POOL.length)}</span> кандидатов
          </div>
          <div className="ss-run-bar"><span style={{width: `${12 + (seen / SB_POOL.length) * 88}%`}}/></div>
        </div>
      </div>
    );
  }

  // ====== РЕЗУЛЬТАТЫ ======
  if (phase === 'done') {
    return (
      <div className="ss-page" data-screen-label="Smart Search / Base / Results">
        <SSHeader onBack={onBack} sub={baseSub}/>
        <SSBaseResults
          results={results} exact={exact} criteria={criteria}
          added={added}
          onToggleAdd={(id) => {
            const next = new Set(added);
            next.has(id) ? next.delete(id) : next.add(id);
            setAdded(next);
          }}
          onOpen={onOpenCandidate}
          onReset={resetSearch}
          onGoFunnel={onGoFunnel}
        />
      </div>
    );
  }

  // ====== КОНСТРУКТОР ВВОДА ======
  return (
    <div className="ss-page" data-screen-label="Smart Search / Base / Build">
      <SSHeader onBack={onBack} sub={baseSub}/>

      {/* ── Метод 1: поиск промтом (аля ChatGPT) ── */}
      <div className={`ssb-method ${byVacancy ? 'is-dim' : 'is-active'}`}>
        <div className="ssb-method-head">
          <span className="ssb-method-ic prompt">💬</span>
          <div className="ssb-method-titles">
            <div className="ssb-method-title">Поиск промтом</div>
            <div className="ssb-method-desc">Опишите обычными словами, кто вам нужен — Глафира найдёт релевантных в базе.</div>
          </div>
        </div>
        <div className="ssb-prompt-box">
          <textarea
            className="ssb-textarea"
            placeholder="Например: Senior Frontend на React и TypeScript, от 5 лет опыта, Москва, готов выйти быстро…"
            value={prompt}
            rows={3}
            onFocus={() => { if (byVacancy) setByVacancy(false); }}
            onChange={e => { if (byVacancy) setByVacancy(false); setPrompt(e.target.value); }}
            onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') runSearch(); }}
          />
        </div>
        <div className="ssb-examples">
          <span className="ssb-ex-label">Примеры:</span>
          {SB_EXAMPLES.map((ex, i) => (
            <button key={i} className="ssb-ex-chip"
              onClick={() => { setByVacancy(false); setPrompt(ex); }}>{ex}</button>
          ))}
        </div>
      </div>

      {/* ── разделитель ── */}
      <div className="ssb-or"><span>или</span></div>

      {/* ── Метод 2: по открытой вакансии (отдельный блок) ── */}
      <div className={`ssb-method ${byVacancy ? 'is-active' : 'is-dim'}`}>
        <label className="ssb-method-head ssb-method-toggle">
          <input type="checkbox" checked={byVacancy}
            onChange={e => { setByVacancy(e.target.checked); setVacId(null); setSelOpen(false); }}/>
          <span className="ssb-check-box">
            <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
              <rect x="1" y="1" width="20" height="20" rx="6"
                fill={byVacancy ? '#7E5CF0' : '#fff'}
                stroke={byVacancy ? '#7E5CF0' : '#C9CFD6'} strokeWidth="1.5"/>
              {byVacancy && <path d="M6 11.2l3 3 6.5-7" fill="none"
                stroke="#fff" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round"/>}
            </svg>
          </span>
          <div className="ssb-method-titles">
            <div className="ssb-method-title">Искать по открытой вакансии</div>
            <div className="ssb-method-desc">Выберите вакансию — Глафира соберёт автофильтры как на hh и найдёт совпадения в базе.</div>
          </div>
        </label>

        {byVacancy && (
          <div className="ssb-vac-body">
            <div className="ssb-field-label">Открытая вакансия</div>
            <div className="ss-select-wrap">
              <button className={`ss-select ${selOpen ? 'open' : ''}`} onClick={() => setSelOpen(o => !o)}>
                <Icon name="briefcase" size={16} style={{color:'var(--fg-3)', flex:'none'}}/>
                {vac
                  ? <span className="ss-select-val">{vac.title}</span>
                  : <span className="ss-select-ph">Выберите вакансию компании…</span>}
                <Icon name="chevD" size={16} className="ss-chev"/>
              </button>
              {selOpen && (
                <div className="ss-select-menu">
                  {vacancies.map(v => (
                    <div key={v.id}
                      className={`ss-select-opt ${vacId === v.id ? 'sel' : ''}`}
                      onClick={() => selectVacancy(v.id)}>
                      <Icon name="briefcase" size={15} className="ss-opt-ic"/>
                      <div className="ss-opt-main">
                        <div className="ss-opt-title">{v.title}</div>
                        <div className="ss-opt-meta">{v.city} · {ssFmt(v.salFrom)}–{ssFmt(v.salTo)} ₽</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {vac && (
              <div className="ssb-autofilters">
                <div className="ss-glafira-note">
                  <span className="em">💃</span> Глафира собрала автофильтры из вакансии — поправьте при необходимости
                </div>

                <div className="ss-field-row" style={{marginBottom:14}}>
                  <div className="ss-field">
                    <div className="ss-field-label">Область / профобласть</div>
                    <input className="ss-input" value={area} onChange={e => setArea(e.target.value)}/>
                  </div>
                  <div className="ss-field">
                    <div className="ss-field-label">Проф-роль</div>
                    <input className="ss-input" value={role} onChange={e => setRole(e.target.value)}/>
                  </div>
                  <div className="ss-field" style={{maxWidth:160}}>
                    <div className="ss-field-label">Опыт</div>
                    <input className="ss-input" value={exp} onChange={e => setExp(e.target.value)}/>
                  </div>
                </div>

                <div className="ss-filter-group">
                  <div className="ss-fg-label">Ключевые навыки</div>
                  <div className="ss-chip-row">
                    {skills.map((sk, i) => (
                      <span key={i} className="ss-chip">
                        {sk}
                        <button className="ss-chip-x" onClick={() => setSkills(skills.filter((_, j) => j !== i))} aria-label="Убрать">
                          <Icon name="x" size={11}/>
                        </button>
                      </span>
                    ))}
                    <button className="ss-chip-add" onClick={() => {
                      const extra = ['Git','Agile','English B2','SQL','Code review'].find(x => !skills.includes(x));
                      if (extra) setSkills([...skills, extra]);
                    }}>
                      <Icon name="plus" size={12}/> навык
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── кнопка поиска ── */}
      <div className="ssb-actions">
        <button className="ssb-search-btn" disabled={!canSearch} onClick={runSearch}>
          <Icon name="search" size={16}/> Найти в базе
        </button>
        <span className="ssb-actions-hint">
          <Icon name="users" size={13} className="ssb-hint-ic"/>
          Поиск только по вашей базе — {ssFmt(SB_POOL.length)} кандидатов. Доступ к hh.ru не требуется.
        </span>
      </div>

      <SSBaseHistory onPick={pickHistory}/>
    </div>
  );
}

const baseSub = (
  <>Поиск среди ваших кандидатов: опишите промтом, кто нужен, — или включите поиск под открытую вакансию с автофильтрами.</>
);

// ====== Результаты по базе ======
function SSBaseResults({ results, exact, criteria, added, onToggleAdd, onOpen, onReset, onGoFunnel }) {
  return (
    <div>
      <div className="ssb-res-head">
        <div className="ssb-res-check"><Icon name="check" size={22}/></div>
        <div className="ssb-res-head-text">
          <h2>Нашлось {results.length} {plural(results.length, 'кандидат','кандидата','кандидатов')} в базе</h2>
          <div className="ssb-res-sub">
            {criteria && criteria.kind === 'vacancy'
              ? <>под вакансию «{criteria.text}»</>
              : <>по запросу «{criteria ? criteria.text : ''}»</>}
            {!exact && <span className="ssb-res-flag"> · точных совпадений нет — показаны ближайшие по AI-баллу</span>}
          </div>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={onReset}>
          <Icon name="refresh" size={14}/> Новый поиск
        </button>
      </div>

      <div className="ssb-res-list">
        {results.map(c => {
          const isAdded = added.has(c.id);
          return (
            <div key={c.id} className="ssb-row">
              <Avatar name={c.name} size="md"/>
              <div className="ssb-row-main">
                <div className="ssb-row-name-line">
                  <span className="ssb-row-name">{c.name}</span>
                  <span className={`ssb-rel ssb-rel-${sbRelColor(c._rel)}`}>{c._rel}% совпадение</span>
                </div>
                <div className="ssb-row-meta">{c.age} лет · {c.lastDur} · {c.lastCo} · {c.city}</div>
                <div className="ssb-row-chips">
                  {c.tags.map((t, i) => {
                    const hit = c._matched.includes(t);
                    return (
                      <span key={i} className={`ssb-tag ${hit ? 'hit' : ''}`}>
                        {hit && <Icon name="check" size={10}/>}{t}
                      </span>
                    );
                  })}
                </div>
              </div>
              <ScoreBadge score={c.score} size="md" tip="AI-балл кандидата"/>
              <div className="ssb-row-actions">
                <button className="ssb-act open" onClick={() => onOpen && onOpen(c.id)}>
                  <Icon name="open" size={14}/> Открыть
                </button>
                <button className={`ssb-act add ${isAdded ? 'is-added' : ''}`} onClick={() => onToggleAdd(c.id)}>
                  <Icon name={isAdded ? 'check' : 'plus'} size={14}/> {isAdded ? 'В вакансии' : 'В вакансию'}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {added.size > 0 && (
        <div className="ssb-res-bar">
          <span><b className="t-mono">{added.size}</b> {plural(added.size,'кандидат','кандидата','кандидатов')} добавлено в воронку</span>
          <button className="btn btn-primary btn-sm" onClick={onGoFunnel}>
            <Icon name="funnel" size={14}/> Смотреть в воронке
          </button>
        </div>
      )}
    </div>
  );
}

function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

// ====== История поиска по базе (отдельная от истории hh) ======
function SSBaseHistory({ onPick }) {
  return (
    <div className="ss-history ssb-history">
      <div className="ss-history-head">
        <Icon name="clock" size={15} style={{color:'var(--fg-3)'}}/>
        <span className="title">История поиска по базе</span>
        <span className="count">{SB_HISTORY.length}</span>
      </div>
      <div className="ss-hist-list">
        {SB_HISTORY.map(h => (
          <div key={h.id} className="ss-hist-row" onClick={() => onPick && onPick(h)} title="Повторить — заполнит поиск">
            <span className={`ssb-hist-kind ${h.kind}`}>
              <Icon name={h.kind === 'vacancy' ? 'briefcase' : 'message'} size={11}/>
              {h.kind === 'vacancy' ? 'по вакансии' : 'промт'}
            </span>
            <div className="ss-hist-main">
              <div className="ss-hist-vac">{h.text}</div>
              <div className="ss-hist-date">{h.date}</div>
            </div>
            <div className="ss-hist-stats">
              <div className="ss-hist-stat">
                <div className="hv">{h.found}</div>
                <div className="hl">найдено</div>
              </div>
              <div className="ss-hist-stat invite">
                <div className="hv">{h.added}</div>
                <div className="hl">в воронку</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { SSBaseFlow });
