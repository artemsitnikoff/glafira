// Candidates — list + inline candidate detail panel (Поток-style)
const { useState: useStateC, useMemo: useMemoC, useEffect: useEffectC } = React;

const STAGES = [
  { id: 'response',   label: 'Отклик',                color: '#5B6573' },
  { id: 'added',      label: 'Добавлен',              color: '#7E5CF0', system: true },
  { id: 'selected',   label: 'Отобран',               color: '#9AA3AE' },
  { id: 'recruiter',  label: 'Контакт с рекрутером',  color: '#7AB4F5' },
  { id: 'interview',  label: 'Интервью',              color: '#2A8AF0' },
  { id: 'manager',    label: 'Контакт с менеджером',  color: '#5778E8' },
  { id: 'offer',      label: 'Оффер',                 color: '#E0A21A' },
  { id: 'hired',      label: 'Нанят',                 color: '#16A34A', terminal: true },
  { id: 'rejected',   label: 'Отказ',                 color: '#DC4646', terminal: true, separated: true },
];

const CANDIDATES = [
  { id: 1,  num:'029', name: 'Артём Чуликов',   age: 28, lastDur: '2 года 3 мес', lastCo: 'ЭЛСИ Стальконструкция', score: 87, ai2: 84, phone: '+7 (999) 466-20-16', mess:['tg','wa'], salary: 220000, city: 'Новосибирск',     date: '08.04.26', stage: 'response',  source:'hh' },
  { id: 2,  num:'080', name: 'Иван Петренко',   age: 32, lastDur: '4 года',       lastCo: 'Сбер',                  score: 92, ai2: 88, phone: '+7 (903) 117-44-22', mess:['tg','max'],          salary: 280000, city: 'Москва',           date: '08.04.26', stage: 'response',  source:'hh', pdn:true },
  { id: 3,  num:'066', name: 'Мария Корнеева',  age: 26, lastDur: '1 год 8 мес',  lastCo: 'Яндекс',                score: 78, ai2: 71, phone: '+7 (916) 442-09-13', mess:['tg','wa'],     salary: 200000, city: 'Москва',           date: '07.04.26', stage: 'response',  source:'tg' },
  { id: 4,  num:'062', name: 'Олег Талалаев',   age: 35, lastDur: '6 лет',        lastCo: 'Альфа-Банк',            score: 94, ai2: 91, phone: '+7 (985) 220-18-04', mess:['tg','wa'],     salary: 320000, city: 'Москва',           date: '07.04.26', stage: 'selected',  source:'hh', pdn:true },
  { id: 5,  num:'041', name: 'Анна Лебедева',   age: 29, lastDur: '3 года',       lastCo: 'Ozon',                  score: 81, ai2: 79, phone: '+7 (911) 776-02-99', mess:['wa','max'],          salary: 240000, city: 'СПб',              date: '06.04.26', stage: 'selected',  source:'avito' },
  { id: 6,  num:'017', name: 'Максим Кокурин',  age: 31, lastDur: '2 года',       lastCo: 'Тинькофф',              score: 65, ai2: 62, phone: '+7 (903) 100-22-33', mess:['tg'],          salary: 250000, city: 'Москва',           date: '06.04.26', stage: 'recruiter', source:'hh', pdn:true },
  { id: 7,  num:'046', name: 'Артём Лер',       age: 27, lastDur: '1 год',        lastCo: 'Wildberries',           score: 73, ai2: 70, phone: '+7 (926) 504-90-15', mess:['tg','wa'],     salary: 210000, city: 'СПб',              date: '05.04.26', stage: 'recruiter', source:'tg' },
  { id: 8,  num:'072', name: 'Никита Зайцев',   age: 33, lastDur: '8 лет',        lastCo: 'CBDO Media Direction',  score: 96, ai2: 94, phone: '+7 (916) 077-13-88', mess:['tg','wa','max'],     salary: 380000, city: 'Москва',           date: '04.04.26', stage: 'interview', source:'hh', pdn:true },
  { id: 9,  num:'075', name: 'Алекс Хамбабян',  age: 28, lastDur: '3 года 6 мес', lastCo: 'Vanta AI',              score: 84, ai2: 82, phone: '+7 (903) 412-66-09', mess:['tg'],          salary: 270000, city: 'Москва',           date: '04.04.26', stage: 'interview', source:'hh', pdn:true },
  { id: 10, num:'034', name: 'Виктор Лазарев',  age: 30, lastDur: '2 года 8 мес', lastCo: 'X5 Tech',               score: 88, ai2: 86, phone: '+7 (901) 233-44-91', mess:['tg','wa'],     salary: 290000, city: 'Москва',           date: '03.04.26', stage: 'manager',   source:'hh', pdn:true },
  { id: 11, num:'058', name: 'Юлия Берг',       age: 34, lastDur: '5 лет',        lastCo: 'Yandex Cloud',          score: 91, ai2: 89, phone: '+7 (916) 808-12-77', mess:['tg','wa','max'],     salary: 340000, city: 'Москва',           date: '02.04.26', stage: 'offer',     source:'hh', pdn:true },
  { id: 12, num:'012', name: 'Андрей Морозов',  age: 36, lastDur: '4 года',       lastCo: 'Райффайзен',            score: 89, ai2: 90, phone: '+7 (910) 552-23-44', mess:['tg'],          salary: 310000, city: 'Москва',           date: '28.03.26', stage: 'hired',     source:'hh', pdn:true },
  { id: 13, num:'089', name: 'Игорь Соколов',   age: 41, lastDur: '12 лет',       lastCo: 'IBM',                   score: 42, ai2: 38, phone: '+7 (903) 301-18-72', mess:['tg'],          salary: 450000, city: 'Москва',           date: '27.03.26', stage: 'rejected',  source:'hh' },
  { id: 14, num:'054', name: 'Алёна Романова',  age: 25, lastDur: '11 мес',       lastCo: 'Студия Лебедева',       score: 56, ai2: 52, phone: '+7 (916) 999-04-11', mess:['tg','wa'],     salary: 180000, city: 'Москва',           date: '03.04.26', stage: 'rejected',  source:'avito' },
  { id: 15, num:'091', name: 'Дарья Климова',   age: 27, lastDur: '2 года',       lastCo: 'Авито',                 score: 86, ai2: 84, phone: '+7 (916) 401-22-08', mess:['tg','wa'],     salary: 230000, city: 'Москва',           date: '08.04.26', stage: 'added',     source:'pool' },
  { id: 16, num:'038', name: 'Роман Шилов',     age: 30, lastDur: '4 года',       lastCo: 'VK',                    score: 79, ai2: 77, phone: '+7 (903) 555-09-21', mess:['tg'],          salary: 260000, city: 'СПб',              date: '07.04.26', stage: 'added',     source:'pool' },
];

const REJECT_REASONS_CAND = ['Не вышел на связь','Не устроила ЗП','Принял другой оффер','Не устроил график','Слишком далеко от дома'];
const REJECT_REASONS_CO = ['Несоответствие опыта','Несоответствие навыков','Не прошёл интервью','Не прошёл СБ','Завышенные ожидания по ЗП'];

const VACANCY_INFO = {
  fe: { title: 'Frontend-разработчик (Senior)', client: 'Atlas',  recruiter: 'А. Седова', city: 'Москва', created: '15 марта 2026' },
  wh: { title: 'Кладовщик · смена 2/2',         client: 'Север',  recruiter: 'И. Корнев', city: 'Москва', created: '20 марта 2026' },
  hr: { title: 'HR-дженералист',                client: 'Логос',  recruiter: 'А. Седова', city: 'Москва', created: '25 марта 2026' },
  do: { title: 'DevOps-инженер',                client: 'Atlas',  recruiter: 'И. Корнев', city: 'Москва', created: '10 марта 2026' },
};

function scoreColor(s) {
  if (s == null) return null;
  if (s >= 80) return 'green';
  if (s >= 50) return 'yellow';
  return 'red';
}

function ScoreBadge({ score, size = 'md', tip }) {
  return (
    <span className={`score-badge score-${scoreColor(score)} score-${size}`} title={tip}>
      {score == null ? '—' : score}
    </span>
  );
}

// ПдН badge — индикатор «кандидат подписал согласие на обработку персональных данных»
function PdnBadge({ size = 'md' }) {
  return (
    <span className={`pdn-badge pdn-${size}`} title="Согласие на обработку персональных данных подписано">
      <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
        <path d="M2.5 6.2l2.4 2.4L9.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
      ПдН
    </span>
  );
}

function StageChip({ stage, size = 'md' }) {
  const s = STAGES.find(x => x.id === stage);
  if (!s) return null;
  return (
    <span className={`stage-pill stage-${stage} ${size === 'sm' ? 'stage-sm' : ''}`}>
      <span className="stage-dot" style={{background: s.color}}/>
      {s.label}
    </span>
  );
}

// Round colored messenger icons (Поток-style)
function MessIconRound({ kind, size = 22 }) {
  const cfg = {
    tg: { bg: '#229ED9', glyph: (
      <svg width={size*0.62} height={size*0.62} viewBox="0 0 24 24" fill="#fff">
        <path d="M9.5 16.7l-.3 4.2c.5 0 .7-.2 1-.5l2.4-2.3 5 3.6c.9.5 1.6.2 1.8-.8L22.7 4c.3-1.3-.5-1.8-1.4-1.5L1.7 10c-1.3.5-1.3 1.2-.2 1.5l5 1.6L18.4 6.4c.5-.4 1-.2.6.2"/>
      </svg>
    )},
    wa: { bg: '#25D366', glyph: (
      <svg width={size*0.62} height={size*0.62} viewBox="0 0 24 24" fill="#fff">
        <path d="M12 2C6.48 2 2 6.48 2 12c0 1.85.5 3.58 1.36 5.07L2 22l5.07-1.32A9.95 9.95 0 0 0 12 22c5.52 0 10-4.48 10-10S17.52 2 12 2zm5.07 14.07c-.21.6-1.05 1.13-1.71 1.27-.46.1-1.07.18-3.1-.66-2.6-1.08-4.27-3.7-4.4-3.87-.13-.17-1.05-1.4-1.05-2.67 0-1.27.66-1.9.9-2.16.2-.22.45-.27.6-.27.15 0 .3 0 .43.01.14.01.32-.05.5.38.2.46.66 1.6.72 1.72.06.12.1.26.02.42-.08.16-.12.26-.24.4-.12.14-.25.32-.36.42-.12.12-.24.25-.1.49.13.24.6 1 1.3 1.62.9.8 1.66 1.05 1.9 1.17.25.12.4.1.55-.06.15-.16.63-.74.8-.99.16-.25.33-.21.55-.13.22.08 1.4.66 1.64.78.24.12.4.18.46.28.06.1.06.6-.15 1.18z"/>
      </svg>
    )},
    vb: { bg: '#7360F2', glyph: (
      <svg width={size*0.62} height={size*0.62} viewBox="0 0 24 24" fill="#fff">
        <path d="M12 2C6.48 2 2 6.36 2 12c0 2.24.74 4.32 2 6L3 22l4.36-1.04A9.78 9.78 0 0 0 12 22c5.52 0 10-4.36 10-10S17.52 2 12 2zm.55 4.6c2.32.05 4.21 1.59 4.45 3.9.04.4-.5.55-.7.16-.2-.4-.42-1-.92-1.45-.5-.45-1.2-.66-2-.7-.4 0-.55-.5-.16-.7l.33-.04zm-.22 1.5c1.56.04 2.65 1.07 2.85 2.55.06.4-.5.5-.7.13-.13-.4-.32-.78-.7-1.1-.36-.32-.85-.5-1.42-.55-.4 0-.5-.5-.16-.7l.13-.04zm-.06 1.5c.96.07 1.6.66 1.78 1.6.07.4-.5.5-.7.16-.06-.36-.2-.5-.45-.7-.25-.2-.55-.27-.85-.3-.4 0-.5-.5-.16-.7l.38-.04zm-3.6.62c.36.05.7.45.97.96.27.5.5 1.05.66 1.18.16.13.32.2.5.06l.96-.6c.13-.07.27-.07.4.02.36.27 1.5 1.18 1.96 1.6.46.4.5.7.32.99-.18.32-.7 1.04-1.5 1.27-.78.22-2.2-.27-3.4-1.27-1.18-1-2.32-2.55-2.96-3.78-.62-1.22-.5-1.96-.18-2.27.32-.32.78-.32 1.27-.16z"/>
      </svg>
    )},
    max: { bg: '#0077FF', glyph: (
      <span style={{
        color:'#fff',
        fontFamily:'var(--font-sans)',
        fontWeight:800,
        fontSize: size*0.46,
        letterSpacing:'-0.02em',
        lineHeight:1
      }}>M</span>
    )},
  };
  const c = cfg[kind] || cfg.tg;
  const titles = { tg:'Telegram', wa:'WhatsApp', vb:'Viber', max:'Max' };
  return (
    <span className="mess-round" style={{background: c.bg, width: size, height: size}} title={titles[kind] || kind}>
      {c.glyph}
    </span>
  );
}

// Small mono-letter badge (used in narrow contexts e.g. card pulled list)
function MessLetter({ kind }) {
  const map = {
    tg: { bg:'#229ED9', l:'TG' },
    wa: { bg:'#25D366', l:'WA' },
    vb: { bg:'#7360F2', l:'V' },
  };
  const m = map[kind] || map.tg;
  return <span className="mess-letter" style={{background:m.bg}}>{m.l}</span>;
}

function fmtSalary(n) {
  return n.toLocaleString('ru-RU').replace(/,/g, '\u202F');
}

function SortHead({ label, id, w, sortField, sortDir, onSort }) {
  const active = sortField === id;
  return (
    <div className={`ct-col ct-sort-head ${active ? 'on' : ''}`}
         style={{width: w}}
         onClick={() => onSort(id)}>
      <span>{label}</span>
      <span className={`ct-sort ${active ? 'on' : ''}`}>
        <span className={`ct-sort-arr ${active && sortDir==='asc' ? 'active' : ''}`}>▲</span>
        <span className={`ct-sort-arr ${active && sortDir==='desc' ? 'active' : ''}`}>▼</span>
      </span>
    </div>
  );
}

// =====================================================================
// FilterDrawer — full-height right-side drawer with collapsible sections
// =====================================================================
function FilterDrawer({ filters, setFilters, toggleSetFilter, resetFilters,
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

          <Section id="salary" title="Зарплата, тыс ₽" count={filters.salaryMax < 500 ? 1 : 0}>
            <div className="fdr-slider-row">
              <input type="range" min="100" max="500" step="10"
                     value={filters.salaryMax}
                     onChange={e => setFilters({...filters, salaryMax: +e.target.value})}/>
              <span className="fdr-slider-val t-mono">до {filters.salaryMax}</span>
            </div>
          </Section>

          <Section id="source" title="Источник" count={filters.sources.size}>
            <div className="fdr-chip-row">
              {[
                {id:'hh', label:'HeadHunter'},
                {id:'tg', label:'Глафира · Telegram'},
                {id:'avito', label:'Авито'},
              ].map(s => (
                <button key={s.id}
                        className={`filter-chip ${filters.sources.has(s.id) ? 'active' : ''}`}
                        onClick={() => toggleSetFilter('sources', s.id)}>
                  {s.label}
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

          <Section id="mess" title="Мессенджер" count={filters.messengers.size}>
            <div className="fdr-chip-row">
              {[
                {id:'tg', label:'Telegram'},
                {id:'wa', label:'WhatsApp'},
                {id:'max', label:'Max'},
              ].map(m => (
                <button key={m.id}
                        className={`filter-chip ${filters.messengers.has(m.id) ? 'active' : ''}`}
                        onClick={() => toggleSetFilter('messengers', m.id)}>
                  {m.label}
                </button>
              ))}
            </div>
          </Section>

          <Section id="ready" title="Готовность" count={filters.relocate ? 1 : 0}>
            <label className="fdr-check">
              <input type="checkbox" checked={filters.relocate}
                     onChange={e => setFilters({...filters, relocate: e.target.checked})}/>
              <span>Готов к переезду</span>
            </label>
          </Section>

          <Section id="period" title="Период отбора на вакансию" count={0}>
            <div className="fdr-chip-row">
              {['Сегодня','Неделя','Месяц','Квартал','Всё время'].map(p => (
                <button key={p} className="filter-chip">{p}</button>
              ))}
            </div>
          </Section>

          <Section id="repeat" title="Повторный отклик" count={0}>
            <label className="fdr-check">
              <input type="checkbox"/>
              <span>Только повторно откликнувшиеся</span>
            </label>
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

// =====================================================================
// CandidatesList — handles both list mode and detail panel mode
// =====================================================================
function CandidatesList({ vacancyId, candidateId, onOpenCandidate, onCloseCandidate, onBack, onAddCandidate, onEditVacancy }) {
  const v = VACANCY_INFO[vacancyId] || VACANCY_INFO.fe;
  const [stage, setStage] = useStateC('response');
  const [query, setQuery] = useStateC('');
  const [sortField, setSortField] = useStateC('score');
  const [sortDir, setSortDir] = useStateC('desc'); // 'asc' | 'desc'
  const [sortOpen, setSortOpen] = useStateC(false);
  const [selected, setSelected] = useStateC(new Set());
  const [bulkRejectOpen, setBulkRejectOpen] = useStateC(false);
  const [filtersOpen, setFiltersOpen] = useStateC(false);
  const [openFilterSections, setOpenFilterSections] = useStateC(new Set(['ai','salary','source']));
  const toggleFilterSection = (id) => {
    const next = new Set(openFilterSections);
    if (next.has(id)) next.delete(id); else next.add(id);
    setOpenFilterSections(next);
  };
  const [filters, setFilters] = useStateC({
    aiMin: 0,
    salaryMax: 500,        // ₽ ×1000
    sources: new Set(),    // hh/tg/avito
    cities: new Set(),
    stages: new Set(),
    messengers: new Set(), // tg/wa/vb
    relocate: false,
  });
  const activeFilterCount =
    (filters.aiMin > 0 ? 1 : 0) +
    (filters.salaryMax < 500 ? 1 : 0) +
    filters.sources.size +
    filters.cities.size +
    filters.stages.size +
    filters.messengers.size +
    (filters.relocate ? 1 : 0);
  const toggleSetFilter = (key, val) => {
    const next = new Set(filters[key]);
    if (next.has(val)) next.delete(val); else next.add(val);
    setFilters({ ...filters, [key]: next });
  };
  const resetFilters = () => setFilters({
    aiMin: 0, salaryMax: 500,
    sources: new Set(), cities: new Set(), stages: new Set(), messengers: new Set(),
    relocate: false,
  });

  const SORT_OPTIONS = [
    { id: 'name',   label: 'ФИО' },
    { id: 'score',  label: 'AI-скоринг' },
    { id: 'phone',  label: 'Телефон' },
    { id: 'salary', label: 'Зарплата' },
    { id: 'city',   label: 'Город' },
    { id: 'date',   label: 'Дата отбора' },
    { id: 'stage',  label: 'Этап' },
    { id: 'age',    label: 'Возраст' },
  ];
  const sortLabel = SORT_OPTIONS.find(s => s.id === sortField)?.label || '';

  const setSort = (field) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const detailMode = !!candidateId;

  const counts = useMemoC(() => {
    const c = {};
    STAGES.forEach(s => c[s.id] = 0);
    CANDIDATES.forEach(x => { c[x.stage] = (c[x.stage]||0) + 1; });
    c.all = CANDIDATES.filter(x => x.stage !== 'rejected').length;
    return c;
  }, []);

  // In detail mode show all candidates of vacancy (so user can scroll all without filter)
  const filtered = useMemoC(() => {
    let list;
    if (detailMode) {
      list = [...CANDIDATES];
    } else {
      list = stage === 'all' ? CANDIDATES.filter(x => x.stage !== 'rejected') : CANDIDATES.filter(x => x.stage === stage);
    }
    if (query) list = list.filter(x => x.name.toLowerCase().includes(query.toLowerCase()));
    if (filters.aiMin > 0) list = list.filter(x => x.score >= filters.aiMin);
    if (filters.salaryMax < 500) list = list.filter(x => x.salary <= filters.salaryMax * 1000);
    if (filters.sources.size > 0) list = list.filter(x => filters.sources.has(x.source));
    if (filters.cities.size > 0) list = list.filter(x => filters.cities.has(x.city));
    if (filters.stages.size > 0) list = list.filter(x => filters.stages.has(x.stage));
    if (filters.messengers.size > 0) list = list.filter(x => x.mess.some(m => filters.messengers.has(m)));
    const dir = sortDir === 'asc' ? 1 : -1;
    const STAGE_ORDER = STAGES.reduce((m, s, i) => (m[s.id] = i, m), {});
    list = [...list].sort((a, b) => {
      let av, bv;
      if (sortField === 'score')      { av = a.score;  bv = b.score;  }
      else if (sortField === 'date')  { av = a.date;   bv = b.date;   }
      else if (sortField === 'name')  { av = a.name;   bv = b.name;   }
      else if (sortField === 'salary'){ av = a.salary; bv = b.salary; }
      else if (sortField === 'age')   { av = a.age;    bv = b.age;    }
      else if (sortField === 'city')  { av = a.city;   bv = b.city;   }
      else if (sortField === 'stage') { av = STAGE_ORDER[a.stage]; bv = STAGE_ORDER[b.stage]; }
      else if (sortField === 'phone') { av = a.phone; bv = b.phone; }
      if (av == null && bv == null) return 0;
      if (typeof av === 'string') return av.localeCompare(bv) * dir;
      return (av - bv) * dir;
    });
    return list;
  }, [stage, query, sortField, sortDir, detailMode, filters]);

  const toggleSel = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const activeCandidate = detailMode ? CANDIDATES.find(c => c.id === candidateId) : null;

  return (
    <div className={`cand-list-wrap ${detailMode ? 'detail-mode' : ''}`}>
      {/* Vacancy header */}
      <div className="vac-header">
        <div className="vh-left">
          <h1 className="vh-title">{v.title}</h1>
          <div className="vh-meta">
            <span>{v.client}</span>
            <span className="sep">·</span>
            <span>{v.recruiter}</span>
            <span className="sep">·</span>
            <span>{v.city}</span>
            <span className="sep">·</span>
            <span>создана {v.created}</span>
          </div>
        </div>
        <div className="vh-actions">
          <button className="btn btn-secondary btn-sm"><Icon name="open" size={14}/> Поделиться</button>
          <button className="btn btn-secondary btn-sm"><Icon name="open" size={14}/> Перейти на hh</button>
          <button className="btn btn-secondary btn-sm" onClick={onEditVacancy}>Редактировать</button>
          <button className="btn btn-primary btn-sm" onClick={onAddCandidate}><Icon name="plus" size={14}/> Добавить кандидата</button>
        </div>
      </div>

      {/* Funnel chips — hidden in detail mode to give room */}
      {/* Funnel chips — always visible. Clicking a chip exits detail and shows the filtered list */}
      <div className="funnel-row">
        <div className={`funnel-chip funnel-all ${stage === 'all' ? 'active' : ''}`} onClick={() => { setStage('all'); onCloseCandidate?.(); }}>
          Все <span className="fc-count">{counts.all}</span>
        </div>
        {STAGES.filter(s => !s.separated && !s.terminal).map(s => (
          <React.Fragment key={s.id}>
            <div className={`funnel-chip ${stage === s.id ? 'active' : ''}`} onClick={() => { setStage(s.id); onCloseCandidate?.(); }}>
              <span className="stage-dot" style={{background: s.color}}/>
              {s.label} <span className="fc-count">{counts[s.id]}</span>
            </div>
            <Icon name="chevR" size={12} className="funnel-arrow"/>
          </React.Fragment>
        ))}
        <div className={`funnel-chip funnel-hired ${stage === 'hired' ? 'active' : ''}`} onClick={() => { setStage('hired'); onCloseCandidate?.(); }}>
          <Icon name="check" size={12}/> Нанят <span className="fc-count">{counts.hired}</span>
        </div>
        <div className="funnel-gap"/>
        <div className={`funnel-chip funnel-rejected ${stage === 'rejected' ? 'active' : ''}`} onClick={() => { setStage('rejected'); onCloseCandidate?.(); }}>
          <Icon name="x" size={12}/> Отказ <span className="fc-count">{counts.rejected}</span>
        </div>
      </div>

      {/* Controls — search, sort, filters (always visible) */}
      <div className="cand-controls">
          <div className="submenu-search" style={{width:280, height:30, background:'#fff', border:'1px solid var(--border-1)'}}>
            <Icon name="search" size={14} style={{color:'var(--fg-3)', flex:'none'}}/>
            <input placeholder="Поиск по ФИО…" value={query} onChange={e => setQuery(e.target.value)}/>
          </div>
          {selected.size > 0 && (
            <div className="bulk-bar">
              <span className="bulk-count">{selected.size} выбрано</span>
              <button className="btn btn-secondary btn-sm">Перевести</button>
              <div className="cd-move-wrap" style={{display:'inline-block', position:'relative'}}>
                <button className="btn btn-secondary btn-sm" onClick={() => setBulkRejectOpen(o => !o)}>Отклонить ▾</button>
                {bulkRejectOpen && (
                  <>
                    <div className="cd-pop-backdrop" onClick={() => setBulkRejectOpen(false)}/>
                    <div className="cd-move-pop cd-reject-pop" role="menu">
                      <div className="cd-pop-head">Причина отказа</div>
                      <div className="cd-pop-group">От кандидата</div>
                      {REJECT_REASONS_CAND.map((r,i) => (
                        <button key={'bc'+i} className="cd-pop-item cd-reject-item" onClick={() => setBulkRejectOpen(false)}>
                          <span className="r-bullet"/><span className="cd-pop-label">{r}</span>
                        </button>
                      ))}
                      <div className="cd-pop-group">Со стороны компании</div>
                      {REJECT_REASONS_CO.map((r,i) => (
                        <button key={'bo'+i} className="cd-pop-item cd-reject-item" onClick={() => setBulkRejectOpen(false)}>
                          <span className="r-bullet co"/><span className="cd-pop-label">{r}</span>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              <button className="btn btn-secondary btn-sm">Сообщение</button>
            </div>
          )}
          <div style={{flex:1}}/>
          <button className={`btn btn-secondary btn-sm ${activeFilterCount > 0 ? 'has-filters' : ''}`}
                  onClick={() => setFiltersOpen(true)}>
            <Icon name="filter" size={14}/> Фильтры
            {activeFilterCount > 0 && <span className="filter-badge">{activeFilterCount}</span>}
          </button>
          {filtersOpen && (
            <FilterDrawer
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

      {/* Body: list (always full layout) + optional detail overlay over the rest-columns */}
      <div className="cand-body">
        <div className="cand-table">
          <div className="cand-scroll">
            <div className="cand-thead">
              <div className="ct-profile">
                <div className="ct-prof-label">Профиль</div>
                <div className="ct-prof-sorts">
                  <div className="ct-prof-head ct-prof-name" onClick={() => setSort('name')}>
                    <span>ФИО</span>
                    <span className={`ct-sort ${sortField === 'name' ? 'on' : ''}`}>
                      <span className={`ct-sort-arr ${sortField==='name' && sortDir==='asc' ? 'active' : ''}`}>▲</span>
                      <span className={`ct-sort-arr ${sortField==='name' && sortDir==='desc' ? 'active' : ''}`}>▼</span>
                    </span>
                  </div>
                  <div className="ct-prof-head ct-prof-ai" onClick={() => setSort('score')}>
                    <span>AI</span>
                    <span className={`ct-sort ${sortField === 'score' ? 'on' : ''}`}>
                      <span className={`ct-sort-arr ${sortField==='score' && sortDir==='asc' ? 'active' : ''}`}>▲</span>
                      <span className={`ct-sort-arr ${sortField==='score' && sortDir==='desc' ? 'active' : ''}`}>▼</span>
                    </span>
                  </div>
                </div>
              </div>
              {!detailMode && (
                <div className="ct-rest">
                  <SortHead label="Телефон" id="phone" w={200} sortField={sortField} sortDir={sortDir} onSort={setSort}/>
                  <SortHead label="ЗП" id="salary" w={120} sortField={sortField} sortDir={sortDir} onSort={setSort}/>
                  <SortHead label="Город" id="city" w={140} sortField={sortField} sortDir={sortDir} onSort={setSort}/>
                  <SortHead label="Дата отбора" id="date" w={120} sortField={sortField} sortDir={sortDir} onSort={setSort}/>
                  <SortHead label="Этап" id="stage" w={200} sortField={sortField} sortDir={sortDir} onSort={setSort}/>
                </div>
              )}
              {detailMode && activeCandidate && (
                <div className="ct-rest cd-thead-spacer"/>
              )}
            </div>
            <div className="cand-tbody">
            {filtered.map(c => (
              <div key={c.id}
                   className={`cand-row ${selected.has(c.id) ? 'selected' : ''} ${candidateId === c.id ? 'open' : ''}`}
                   style={{'--stage-color': STAGES.find(s => s.id === c.stage)?.color}}
                   onClick={() => onOpenCandidate(c.id)}>
                <div className="ct-profile">
                  <input type="checkbox" className="row-check" checked={selected.has(c.id)}
                         onChange={() => toggleSel(c.id)} onClick={e => e.stopPropagation()}/>
                  <Avatar name={c.name} size="sm"/>
                  <div className="prof-text">
                    <div className="prof-name">
                      <span className="prof-num">{c.num}</span>
                      <span>{c.name}</span>
                      {c.pdn && <PdnBadge size="sm"/>}
                      {c.stage !== 'response' && <span className="stage-pip" style={{background: STAGES.find(s => s.id === c.stage)?.color}}/>}
                    </div>
                    <div className="prof-meta-2l">
                      <div className="prof-meta-line">{c.age} лет</div>
                      <div className="prof-meta-line">{c.lastDur} · {c.lastCo}</div>
                    </div>
                  </div>
                  <ScoreBadge score={c.score} size="lg" tip="Почему такая оценка"/>
                </div>
                {!detailMode && (
                  <div className="ct-rest">
                    <div className="ct-col" style={{width:200}}>
                      <div className="phone-cell">
                        <span className="t-mono">{c.phone}</span>
                        <div className="mess-row">
                          {c.mess.map(m => <MessIconRound key={m} kind={m} size={18}/>)}
                        </div>
                      </div>
                    </div>
                    <div className="ct-col t-mono" style={{width:120}}>{fmtSalary(c.salary)} ₽</div>
                    <div className="ct-col" style={{width:140}}>{c.city}</div>
                    <div className="ct-col t-mono" style={{width:120, color:'var(--fg-2)'}}>{c.date}</div>
                    <div className="ct-col" style={{width:200}}><StageChip stage={c.stage} size="sm"/></div>
                  </div>
                )}
              </div>
            ))}
            {filtered.length === 0 && (
              <div className="empty-pane" style={{height: 280}}>
                <div className="empty-illust"><Icon name="users" size={36}/></div>
                <h3>На этапе «{STAGES.find(s => s.id === stage)?.label || 'выбранном'}» пока никого</h3>
                <p>Кандидаты появятся, как только Глафира продвинет их по воронке.</p>
              </div>
            )}
            </div>
          </div>

          {/* Detail panel — overlays the rest-columns area in detail mode */}
          {detailMode && activeCandidate && (
            <CandidateDetail
              key={activeCandidate.id}
              candidate={activeCandidate}
              vacancy={v}
              onClose={onCloseCandidate}/>
          )}
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// StageStrip — B24-style funnel arrows for quick stage transitions
// =====================================================================
function StageStrip({ current }) {
  // ordered active funnel: response → screening → interview → offer → hired
  const flow = STAGES.filter(s => !s.separated && s.id !== 'rejected');
  const currentIdx = flow.findIndex(s => s.id === current);
  return (
    <div className="stage-strip">
      {flow.map((s, i) => {
        const passed = i < currentIdx;
        const active = i === currentIdx;
        const upcoming = i > currentIdx;
        return (
          <button key={s.id}
                  className={`ss-step ${passed ? 'passed' : ''} ${active ? 'active' : ''} ${upcoming ? 'upcoming' : ''}`}
                  style={passed || active ? {'--ss-color': s.color} : {}}
                  title={s.label}>
            <span className="ss-label">{s.label}</span>
          </button>
        );
      })}
      <button className="ss-step ss-final" title="Завершить обработку">
        <span className="ss-label">Завершить обработку</span>
      </button>
    </div>
  );
}

// =====================================================================
// CandidateDetail — right-side panel
// =====================================================================
function CandidateDetail({ candidate: c, vacancy: v, onClose, fromPool }) {
  const [tab, setTab] = useStateC('resume');
  const [loading, setLoading] = useStateC(true);
  const [moveOpen, setMoveOpen] = useStateC(false);
  const [rejectOpen, setRejectOpen] = useStateC(false);
  const composeRef = React.useRef(null);
  const openComments = () => {
    setTab('comments');
    setTimeout(() => {
      const ta = document.querySelector('.cmt-compose textarea');
      if (ta) { ta.focus(); ta.scrollIntoView({block:'nearest', behavior:'smooth'}); }
    }, 60);
  };
  const stageOptions = STAGES.filter(s => !s.terminal);
  const curStageIdx = stageOptions.findIndex(s => s.id === c.stage);

  useEffectC(() => {
    setLoading(true);
    const t = setTimeout(() => setLoading(false), 850);
    return () => clearTimeout(t);
  }, [c.id]);

  return (
    <div className="cand-detail">
      {loading && (
        <div className="cd-loading">
          <div className="cd-dancer" role="img" aria-label="loading">💃</div>
          <div className="cd-load-text">
            Глафира собирает профиль<span className="cd-load-dots"></span>
          </div>
        </div>
      )}
      {/* Top toolbar — primary actions */}
      <div className="cd-toolbar">
        <div className="cd-move-wrap">
          <button className="btn btn-success btn-sm" onClick={() => setMoveOpen(o => !o)}>
            <Icon name="arrowRight" size={14}/> Перевести <Icon name="chevD" size={12}/>
          </button>
          {moveOpen && (
            <>
              <div className="cd-pop-backdrop" onClick={() => setMoveOpen(false)}/>
              <div className="cd-move-pop" role="menu">
                <div className="cd-pop-head">
                  {fromPool ? 'Выберите вакансию' : 'На какой этап?'}
                </div>
                {fromPool ? (
                  VACANCIES.map(vac => (
                    <button key={vac.id} className="cd-pop-item" onClick={() => setMoveOpen(false)}>
                      <span className="cd-pop-num t-mono">{vac.count}</span>
                      <span className="cd-pop-label">{vac.name}</span>
                    </button>
                  ))
                ) : (
                  stageOptions.map((s, i) => (
                    <button key={s.id}
                      className={`cd-pop-item ${s.id === c.stage ? 'cur' : ''} ${i === curStageIdx + 1 ? 'next' : ''}`}
                      onClick={() => setMoveOpen(false)}>
                      <span className="stage-dot" style={{background: s.color}}/>
                      <span className="cd-pop-label">{s.label}</span>
                      {s.id === c.stage && <span className="cd-pop-tag">сейчас</span>}
                      {i === curStageIdx + 1 && <span className="cd-pop-tag cd-pop-tag-next">далее</span>}
                    </button>
                  ))
                )}
              </div>
            </>
          )}
        </div>
        <div className="cd-move-wrap">
          <button className="btn btn-secondary btn-sm" onClick={() => setRejectOpen(o => !o)}>
            <Icon name="x" size={14}/> Отклонить <Icon name="chevD" size={12}/>
          </button>
          {rejectOpen && (
            <>
              <div className="cd-pop-backdrop" onClick={() => setRejectOpen(false)}/>
              <div className="cd-move-pop cd-reject-pop" role="menu">
                <div className="cd-pop-head">Причина отказа</div>
                <div className="cd-pop-group">От кандидата</div>
                {REJECT_REASONS_CAND.map((r,i) => (
                  <button key={'c'+i} className="cd-pop-item cd-reject-item" onClick={() => setRejectOpen(false)}>
                    <span className="r-bullet"/>
                    <span className="cd-pop-label">{r}</span>
                  </button>
                ))}
                <div className="cd-pop-group">Со стороны компании</div>
                {REJECT_REASONS_CO.map((r,i) => (
                  <button key={'o'+i} className="cd-pop-item cd-reject-item" onClick={() => setRejectOpen(false)}>
                    <span className="r-bullet co"/>
                    <span className="cd-pop-label">{r}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
        <button className="btn btn-secondary btn-sm" onClick={openComments}><Icon name="open" size={14}/> Комментарий</button>
        {!c.pdn && (
          <button className="btn btn-secondary btn-sm cd-pdn-btn" title="Запросить согласие на обработку персональных данных">
            <Icon name="open" size={14}/> ПдН
          </button>
        )}
        {c.pdn && (
          <span className="cd-pdn-confirmed" title="Согласие на обработку персональных данных подписано">
            ПдН
            <svg width="13" height="13" viewBox="0 0 12 12" fill="none">
              <path d="M2.5 6.2l2.4 2.4L9.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </span>
        )}
        <div style={{flex:1}}/>
        <button className="icon-btn" onClick={onClose} title="Закрыть"><Icon name="x" size={18}/></button>
      </div>

      {/* Header — compact, single column */}
      <div className="cd-header">
        <div className="cd-context">
          <span className={`src-pill src-${c.source}`}>
            {c.source === 'hh' ? 'Отклик с HeadHunter' : c.source === 'tg' ? 'Глафира · Telegram' : 'Авито'}
          </span>
          <span>от {c.date}</span>
          <span className="sep">·</span>
          <span>{v.title}</span>
        </div>

        <div className="cd-h-main">
          <div className="cd-h-left">
            <div className="cd-name-row">
              <h1 className="cd-name">{c.name}</h1>
              {c.pdn && <PdnBadge size="md"/>}
              <ScoreBadge score={c.score} size="lg"/>
            </div>
            <div className="cd-exp-line">
              {c.lastDur} · {c.lastCo} · апрель 2024 — наст. время
            </div>
            <div className="cd-salary-line">
              <span className="cd-salary t-mono">{fmtSalary(c.salary)} ₽</span>
              <span className="cd-salary-label">ожидания</span>
            </div>
            <div className="cd-tags-row">
              <button className="tag-add">+ Добавить тег</button>
            </div>
          </div>

          <div className="cd-contact-box">
            <div className="cb-row">
              <span className="cb-label">Телефон:</span>
              <span className="t-mono cb-strong">{c.phone}</span>
              <div className="mess-icons-row">
                {c.mess.map(m => <MessIconRound key={m} kind={m}/>)}
              </div>
            </div>
            <div className="cb-row">
              <span className="cb-label">Город:</span>
              <span>{c.city}</span>
            </div>
            <div className="cb-row">
              <span className="cb-label">E-mail:</span>
              <span>{c.name.split(' ')[0].toLowerCase()}.{c.name.split(' ')[1].toLowerCase()}@mail.ru</span>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="cc-tabs">
        {[
          { id: 'resume', label: 'Резюме' },
          { id: 'ai', label: 'Оценка AI' },
          { id: 'verify', label: 'Верификация' },
          { id: 'chat', label: 'Чат' },
          { id: 'calls', label: 'Звонки' },
          { id: 'docs', label: 'Документы' },
          { id: 'comments', label: 'Комментарии' },
          { id: 'actions', label: 'Все действия' },
        ].map(t => (
          <button key={t.id} className={`cc-tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="cc-content">
        {tab === 'resume' && <ResumeTab c={c} onOpenAI={() => setTab('ai')}/>}
        {tab === 'chat' && <ChatTab c={c}/>}
        {tab === 'calls' && <CallsTab c={c}/>}
        {tab === 'actions' && <ActionsTab c={c}/>}
        {tab === 'docs' && <DocsTab/>}
        {tab === 'ai' && <AITab c={c}/>}
        {tab === 'verify' && <VerifyTab c={c}/>}
        {tab === 'comments' && <CommentsTab c={c}/>}
      </div>
    </div>
  );
}

// ============ AI verdict card — compact (resume tab) ============
function AIVerdictCard({ c, hideLink, onOpenAI, showScreening }) {
  const verdict = c.score >= 80
    ? 'Хорошо подходит. Релевантный опыт, ключевые навыки совпадают с требованиями вакансии.'
    : c.score >= 50
    ? 'Подходит частично. Есть релевантный опыт, но не хватает части ключевых навыков.'
    : 'Не подходит. Опыт не совпадает с требованиями вакансии.';
  return (
    <div className="filo-card filo-card-compact">
      <div className="filo-head">
        <div className="filo-head-left">
          <div className="filo-ai-mark filo-glafira" aria-label="Глафира">
            <span className="glafira-emoji">👩🏻</span>
          </div>
          <div>
            <div className="filo-title">Оценка от Глафиры</div>
            <div className="filo-sub">{verdict}</div>
            {showScreening && (
              <div className="filo-screening">
                Уточнила ожидания ({fmtSalary(c.salary)} ₽), опыт {c.lastDur}, готовность — {c.city} или удалёнка.
                Резюме совпадает с требованиями на {c.score}%.
              </div>
            )}
          </div>
        </div>
        <ScoreBadge score={c.score} size="xl"/>
      </div>
      <div className="filo-link-row" style={hideLink ? {display:'none'} : null}>
        <a className="filo-link" href="#" onClick={(e)=>{e.preventDefault(); if (onOpenAI) onOpenAI();}}>
          Посмотреть подробную оценку →
        </a>
      </div>
    </div>
  );
}

function ResumeTab({ c, onOpenAI }) {
  const [prefContact, setPrefContact] = useStateC('tg');
  const contactOpts = [
    { id:'tg',    label:'Telegram', icon:'telegram' },
    { id:'mail',  label:'Почта',    icon:'mail' },
    { id:'phone', label:'Телефон',  icon:'phone' },
  ];
  return (
    <div className="resume-single">
      <AIVerdictCard c={c} onOpenAI={onOpenAI}/>

      <h3 className="cc-sec-title">Опыт работы</h3>
      <div className="job">
        <div className="job-header">
          <div>
            <div className="job-title">Менеджер по развитию клиентов (B2B продажи)</div>
            <div className="job-co">{c.lastCo}</div>
          </div>
          <div className="job-period">апрель 2024 — наст. время</div>
        </div>
        <div className="job-desc">
          Работа с ключевыми клиентами в сегменте B2B. Развитие портфеля, переговоры на уровне C-level.
          Внедрил систему скоринга лидов, поднял конверсию на 22%.
        </div>
      </div>
      <div className="job">
        <div className="job-header">
          <div>
            <div className="job-title">Senior Sales Manager</div>
            <div className="job-co">Сбер · Корпоративные клиенты</div>
          </div>
          <div className="job-period">февраль 2022 — март 2024</div>
        </div>
        <div className="job-desc">
          Воронка от первичного контакта до контракта. Среднегодовой объём — 180 М ₽. Команда 4 человека.
        </div>
      </div>

      <h3 className="cc-sec-title">Навыки</h3>
      <div className="skill-row">
        {['B2B продажи','CRM','Переговоры','Презентации','Тендеры','Аналитика воронки','Excel/PowerBI','Английский B2'].map(s => (
          <span key={s} className="skill-chip">{s}</span>
        ))}
      </div>

      <h3 className="cc-sec-title">Образование</h3>
      <div className="edu-row">
        <div>
          <div className="job-title">МГТУ им. Баумана</div>
          <div className="job-co">Менеджмент</div>
        </div>
        <div className="job-period">2012 — 2018</div>
      </div>

      <h3 className="cc-sec-title">Дополнительно</h3>
      <div className="extra-grid">
        <div><span className="extra-k">Языки:</span> Русский · English B2</div>
        <div><span className="extra-k">Переезд:</span> не готов</div>
        <div><span className="extra-k">Командировки:</span> раз в месяц</div>
        <div><span className="extra-k">Удалёнка:</span> предпочитает</div>
        <div className="extra-pref" style={{gridColumn:'1 / -1'}}>
          <span className="extra-k">Предпочтительный способ связи:</span>
          <span className="pref-chips">
            {contactOpts.map(o => (
              <button key={o.id}
                className={`pref-chip ${prefContact === o.id ? 'active' : ''}`}
                onClick={() => setPrefContact(o.id)}
                type="button">
                <Icon name={o.icon} size={13}/>
                {o.label}
              </button>
            ))}
          </span>
        </div>
      </div>
    </div>
  );
}

function ActionsTab({ c }) {
  const events = [
    { icon:'open',     who:'А. Седова', role:'рекрутер', text:`оставила комментарий: «Согласовала интервью на вторник, 15:00»`, time:`${c.date} · 16:12` },
    { icon:'open',     who:'И. Корнев', role:'нанимающий менеджер', text:`оставил комментарий: «Согласен, давайте посмотрим. Интересны кейсы с крупными клиентами»`, time:`${c.date} · 15:24` },
    { icon:'open',     who:'А. Седова', role:'рекрутер', text:`оставила комментарий: «Кандидат произвёл хорошее впечатление, есть релевантный опыт в B2B»`, time:`${c.date} · 15:02` },
    { icon:'sparkle',  who:'Глафира',  text:`провела скрининг с ${c.name}: уточнила ожидания и опыт`, time:`${c.date} · 14:48`, ai:true },
    { icon:'star',     who:'Глафира',  text:`оценила резюме на ${c.score}/100`, time:`${c.date} · 14:32`, ai:true },
    { icon:'plus',     who:'hh.ru',    text:`Кандидат откликнулся на «Региональный менеджер по продажам»`, time:`${c.date} · 14:15` },
  ];
  return (
    <div className="card-block">
      <div className="actions-feed">
        {events.map((e, i) => (
          <div key={i} className="action-row">
            <div className={`action-icon ${e.ai ? 'ai' : ''}`}><Icon name={e.icon} size={13}/></div>
            <div className="action-body">
              <div className="action-text">
                <span className={`action-who ${e.ai ? 'ai' : ''}`}>{e.who}</span>
                {e.role && <span className="action-role"> · {e.role}</span>} {e.text}
              </div>
              <div className="action-time t-mono">{e.time}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DocsTab() {
  const files = [
    { name: 'Резюме.pdf',          type:'PDF', size:'412 КБ', date:'08.04.26', who:'импорт hh' },
    { name: 'Фото.jpg',            type:'IMG', size:'1.2 МБ', date:'08.04.26', who:'импорт hh' },
    { name: 'Согласие_ОПД.pdf',    type:'PDF', size:'88 КБ',  date:'10.04.26', who:'А. Седова' },
  ];
  return (
    <div className="card-block">
      <div className="docs-grid">
        {files.map((f, i) => (
          <div key={i} className="doc-tile">
            <div className="file-icon">{f.type}</div>
            <div className="file-info">
              <div className="file-name">{f.name}</div>
              <div className="file-meta">{f.size} · {f.date} · {f.who}</div>
            </div>
            <button className="icon-btn"><Icon name="download" size={16}/></button>
          </div>
        ))}
        <div className="doc-tile doc-drop">
          <Icon name="plus" size={20}/>
          <span>Перетащите файл или нажмите</span>
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// VerifyTab — проверка по реестрам и публичным источникам
// =====================================================================
function VerifyTab({ c }) {
  if (!c.pdn) {
    return (
      <div className="verify-locked">
        <div className="verify-locked-ico">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <rect x="4" y="10" width="16" height="11" rx="2"/>
            <path d="M8 10V7a4 4 0 0 1 8 0v3"/>
          </svg>
        </div>
        <h3>Верификация недоступна</h3>
        <p>
          Кандидат пока не подписал согласие на обработку персональных данных (152-ФЗ).
          Запросите ПдН — после подписания Глафира автоматически проверит кандидата
          по всем реестрам и публичным источникам.
        </p>
        <button className="btn btn-primary btn-sm">
          <Icon name="open" size={14}/> Запросить ПдН
        </button>
      </div>
    );
  }

  // -- helpers ----------------------------------------------------------
  const Source = ({ name, kind }) => (
    <span className={`vf-src vf-src-${kind || 'api'}`}>{name}</span>
  );
  const Status = ({ kind, children }) => (
    <span className={`vf-status vf-st-${kind}`}>
      {kind === 'clean' && <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2.5 6.2l2.4 2.4L9.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>}
      {kind === 'warn'  && <span className="vf-dot"/>}
      {kind === 'risk'  && <span className="vf-dot"/>}
      {kind === 'info'  && <span className="vf-dot"/>}
      {children}
    </span>
  );
  const Block = ({ icon, title, sources, status, statusKind, children, footer }) => (
    <section className="vf-block">
      <header className="vf-head">
        <div className="vf-head-left">
          <div className="vf-icon">{icon}</div>
          <div className="vf-head-text">
            <div className="vf-title">{title}</div>
            <div className="vf-sources">{sources}</div>
          </div>
        </div>
        {status && <Status kind={statusKind}>{status}</Status>}
      </header>
      <div className="vf-body">{children}</div>
      {footer && <footer className="vf-foot">{footer}</footer>}
    </section>
  );
  const KV = ({ k, v, mono, copy }) => (
    <div className="vf-kv">
      <span className="vf-k">{k}</span>
      <span className={`vf-v ${mono ? 't-mono' : ''}`}>{v}</span>
      {copy && <button className="vf-copy" title="Скопировать">⧉</button>}
    </div>
  );

  return (
    <div className="verify-tab">
      <div className="vf-meta">
        <span className="vf-meta-glyph">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </span>
        <span>Проверка выполнена <b>{c.date} · 16:42</b> · по согласию №<b className="t-mono">PD-{c.num}/26</b></span>
        <span style={{flex:1}}/>
        <button className="btn btn-secondary btn-sm">Перепроверить</button>
      </div>

      {/* 1. ИНН */}
      <Block
        icon={<span className="vf-icon-letter">№</span>}
        title="ИНН — идентификация"
        sources={<>
          <Source name="ФНС · service.nalog.ru/inn.do" kind="api"/>
          <Source name="DaData" kind="api"/>
        </>}
        status="Найден"
        statusKind="clean">
        <div className="vf-grid">
          <KV k="ФИО (резюме)" v={c.name}/>
          <KV k="Дата рождения" v="14.06.1993"/>
          <KV k="ИНН" v="772 731 824 561" mono copy/>
          <KV k="Совпадение" v="Полное (ФИО + ДР)"/>
        </div>
        <div className="vf-note">
          Если автопоиск не находит — рекрутёр может попросить кандидата ввести ИНН вручную в чате.
          Глафира подставит шаблон запроса.
        </div>
      </Block>

      {/* 2. ФССП */}
      <Block
        icon={<span className="vf-icon-letter">⚖</span>}
        title="Исполнительные производства"
        sources={<Source name="Datanewton · ФССП" kind="api"/>}
        status="Без производств"
        statusKind="clean">
        <div className="vf-note">
          Открытых исполнительных производств не найдено. Последняя проверка по реестру ФССП.
        </div>
      </Block>

      {/* 3. ЕФРСБ + ЕГРЮЛ/ЕГРИП */}
      <Block
        icon={<span className="vf-icon-letter">Ю</span>}
        title="Банкротство и связи с юрлицами"
        sources={<>
          <Source name="ЕФРСБ" kind="reg"/>
          <Source name="ЕГРЮЛ / ЕГРИП · DaData" kind="api"/>
        </>}
        status="1 связь"
        statusKind="info">
        <div className="vf-list">
          <div className="vf-list-row">
            <div className="vf-list-main">
              <div className="vf-list-title">ООО «Альтаир Консалт»</div>
              <div className="vf-list-sub">Учредитель · доля 30% · с 2019 г.</div>
            </div>
            <span className="t-mono vf-list-id">ОГРН 1197746000123</span>
          </div>
          <div className="vf-empty-row">Признаков банкротства не найдено.</div>
        </div>
      </Block>

      {/* 4. Спец-реестры */}
      <Block
        icon={<span className="vf-icon-letter">Р</span>}
        title="Реестры и санкции"
        sources={<>
          <Source name="ФНС · Дисквалифицированные" kind="reg"/>
          <Source name="Массовые директора" kind="reg"/>
          <Source name="Самозанятость" kind="reg"/>
          <Source name="Санкции (РФ / ЕС / OFAC)" kind="reg"/>
          <Source name="kad.arbitr.ru" kind="reg"/>
        </>}
        status="Чисто"
        statusKind="clean">
        <div className="vf-checks">
          <div className="vf-check"><span className="vf-tick"/>Не дисквалифицирован</div>
          <div className="vf-check"><span className="vf-tick"/>Не в списке массовых директоров</div>
          <div className="vf-check"><span className="vf-tick"/>Статус самозанятого: <b>не действует</b></div>
          <div className="vf-check"><span className="vf-tick"/>В санкционных списках не значится</div>
          <div className="vf-check"><span className="vf-tick"/>Арбитражных дел против лица не найдено</div>
        </div>
      </Block>

      {/* 5. Публичная экспертиза */}
      <Block
        icon={<span className="vf-icon-letter">★</span>}
        title="Публичная экспертиза"
        sources={<>
          <Source name="GitHub" kind="pub"/>
          <Source name="Habr Career" kind="pub"/>
          <Source name="Stack Exchange" kind="pub"/>
          <Source name="TGStat" kind="pub"/>
        </>}
        status="Найдены профили"
        statusKind="info">
        <div className="vf-pubs">
          <div className="vf-pub">
            <span className="vf-pub-name">GitHub</span>
            <span className="vf-pub-handle t-mono">@a-chulikov</span>
            <span className="vf-pub-stat">412 ★ · 28 repo · активность 2 г.</span>
          </div>
          <div className="vf-pub">
            <span className="vf-pub-name">Habr Career</span>
            <span className="vf-pub-handle t-mono">/users/{c.num}</span>
            <span className="vf-pub-stat">5 статей · карма +84</span>
          </div>
          <div className="vf-pub">
            <span className="vf-pub-name">Stack Exchange</span>
            <span className="vf-pub-handle t-mono">8 421 rep</span>
            <span className="vf-pub-stat">42 answers · 9 bronze</span>
          </div>
          <div className="vf-pub">
            <span className="vf-pub-name">TGStat</span>
            <span className="vf-pub-handle">Канал «Заметки {c.name.split(' ')[0]}а»</span>
            <span className="vf-pub-stat">1.2k подписчиков · ER 8.4%</span>
          </div>
        </div>
        <div className="vf-note">Глафира искала по ФИО и косвенным признакам — связь с кандидатом подтверждена сходством профилей и контекстом постов.</div>
      </Block>

      {/* 6. AI-разведка */}
      <Block
        icon={<span className="vf-icon-letter ai">✦</span>}
        title="AI-разведка"
        sources={<>
          <Source name="Claude API · web search" kind="ai"/>
          <Source name="PII-firewall · цитата + URL контракт · JSON-schema" kind="ai"/>
        </>}
        status="3 находки"
        statusKind="info">
        <div className="vf-findings">
          <div className="vf-finding">
            <div className="vf-finding-quote">«… {c.name.split(' ')[0]} выступил с докладом о масштабировании B2B-воронки на конференции Sales Hackers 2025…»</div>
            <a className="vf-finding-src" href="#">sales-hackers.ru/2025/programme</a>
          </div>
          <div className="vf-finding">
            <div className="vf-finding-quote">«… интервью с {c.lastCo} о внедрении скоринга лидов и росте конверсии на 22%…»</div>
            <a className="vf-finding-src" href="#">vc.ru/marketing/884211</a>
          </div>
          <div className="vf-finding">
            <div className="vf-finding-quote">«… благодарность от команды за организацию off-site в 2024 г.»</div>
            <a className="vf-finding-src" href="#">linkedin.com/posts/…</a>
          </div>
        </div>
        <div className="vf-note">PII-firewall: персональные данные в запрос к LLM не передавались — только ФИО, город и должность. Каждая находка возвращена с цитатой и URL.</div>
      </Block>

      {/* 7. Алименты */}
      <Block
        icon={<span className="vf-icon-letter">₽</span>}
        title="Алиментные обязательства"
        sources={<Source name="ФССП · реестр должников по алиментам" kind="reg"/>}
        status="Не найдено"
        statusKind="clean">
        <div className="vf-note">Кандидат не значится в реестре должников по алиментным обязательствам.</div>
      </Block>
    </div>
  );
}

function CommentsTab({ c }) {  const items = [
    { who:'Анна Седова', role:'рекрутер', text:`Кандидат произвёл хорошее впечатление, есть релевантный опыт в B2B продажах. Договорились на интервью со мной во вторник в 15:00.`, time:`${c.date} · 15:02`, avatar:'A' },
    { who:'Иван Корнев', role:'нанимающий менеджер', text:'Согласен, давайте посмотрим. Особенно интересны кейсы по работе с крупным клиентами.', time:`${c.date} · 15:24`, avatar:'И' },
    { who:'Анна Седова', role:'рекрутер', text:'Отправила приглашение в календарь. Подключусь к интервью первые 10 минут.', time:`${c.date} · 16:08`, avatar:'A' },
  ];
  return (
    <div className="comments-tab">
      <div className="comments-list">
        {items.map((it, i) => (
          <div className="cmt-item" key={i}>
            <div className="cmt-avatar" data-letter={it.avatar}>{it.avatar}</div>
            <div className="cmt-body">
              <div className="cmt-head">
                <span className="cmt-who">{it.who}</span>
                <span className="cmt-role">· {it.role}</span>
                <span className="cmt-time">{it.time}</span>
              </div>
              <div className="cmt-text">{it.text}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="cmt-compose">
        <textarea placeholder="Напишите комментарий… Используйте @ чтобы упомянуть коллегу." rows={3}></textarea>
        <div className="cmt-compose-actions">
          <span className="cmt-hint">@ упомянуть · Ctrl+Enter — отправить</span>
          <button className="btn btn-primary btn-sm">Отправить</button>
        </div>
      </div>
    </div>
  );
}

function ChatTab({ c }) {
  // Channel options — color logos & labels
  const CHANNELS = [
    { id: 'tg',    label: 'Telegram',   short: 'TG',  color: '#229ED9', icon: 'mail' },
    { id: 'hh',    label: 'hh.ru',      short: 'hh',  color: '#D6001C', icon: 'briefcase' },
    { id: 'max',   label: 'Max',        short: 'MX',  color: '#0077FF', icon: 'sparkle' },
    { id: 'wa',    label: 'WhatsApp',   short: 'WA',  color: '#25D366', icon: 'mail' },
    { id: 'sms',   label: 'SMS',        short: 'SMS', color: '#7A7F87', icon: 'mail' },
    { id: 'email', label: 'E-mail',     short: '@',   color: '#5B6573', icon: 'mail' },
  ];
  // Initial channel = always Telegram (default)
  const initialChannel = 'tg';
  const [activeChannel, setActiveChannel] = useStateC(initialChannel);
  const [draft, setDraft] = useStateC('');
  const [open, setOpen] = useStateC(false);
  const recruiterName = 'Анна Седова';

  const today = c.date || '08.04.26';
  const messages = [
    { id:1, who:'me',     who_name:recruiterName, ch:'tg', text:`Здравствуйте, ${c.name.split(' ')[1]}! Меня зовут Анна, я из «Технологии Будущего». Спасибо за отклик на вакансию «Региональный менеджер по продажам».`, time:`${today} · 14:20` },
    { id:2, who:'me',     who_name:recruiterName, ch:'tg', text:`Резюме посмотрела — выглядит интересно. Можем созвониться завтра в 15:00, чтобы обсудить детали?`, time:`${today} · 14:20` },
    { id:3, who:'them',   who_name:c.name,        ch:'tg', text:`Анна, добрый день! Спасибо за быстрый ответ. Завтра в 15:00 — да, подойдёт.`, time:`${today} · 14:48` },
    { id:4, who:'them',   who_name:c.name,        ch:'tg', text:`Подскажите формат — видео или голос? И на сколько примерно по времени?`, time:`${today} · 14:48` },
    { id:5, who:'me',     who_name:recruiterName, ch:'tg', text:`Отлично! Видеосозвон в Zoom, ~30 минут. Сейчас отправлю приглашение в календарь.`, time:`${today} · 15:02` },
    { id:6, who:'them',   who_name:c.name,        ch:'tg', text:`Принято, жду ссылку 👍`, time:`${today} · 15:04` },
  ];

  const channelMeta = (id) => CHANNELS.find(x => x.id === id) || CHANNELS[0];
  const active = channelMeta(activeChannel);

  const send = () => {
    if (!draft.trim()) return;
    setDraft('');
  };

  return (
    <div className="chat-tab">
      <div className="chat-stream">
        <div className="chat-day-divider"><span>{today}</span></div>
        {messages.map(m => {
          const ch = channelMeta(m.ch);
          const isMe = m.who === 'me';
          return (
            <div key={m.id} className={`chat-row ${isMe ? 'chat-row-me' : 'chat-row-them'}`}>
              {!isMe && <Avatar name={m.who_name} size="sm"/>}
              <div className="chat-bubble-wrap">
                <div className="chat-meta">
                  <span className="chat-who">{isMe ? recruiterName : m.who_name}</span>
                  <span className={`chat-ch chat-ch-${m.ch}`} style={{'--ch-color': ch.color}}>
                    <span className="chat-ch-dot" style={{background: ch.color}}/>
                    {ch.label}
                  </span>
                </div>
                <div className={`chat-bubble ${isMe ? 'chat-bubble-me' : 'chat-bubble-them'}`}>
                  {m.text}
                </div>
                <div className="chat-time t-mono">{m.time.split(' · ')[1]}</div>
              </div>
              {isMe && <Avatar name={recruiterName} size="sm"/>}
            </div>
          );
        })}
      </div>

      <div className="chat-compose">
        <div className="chat-compose-head">
          <span className="chat-compose-label">Канал ответа:</span>
          <div className={`chat-ch-select ${open ? 'open' : ''}`}>
            <button type="button" className="chat-ch-trigger" onClick={() => setOpen(!open)}>
              <span className="chat-ch-dot" style={{background: active.color}}/>
              <span className="chat-ch-trigger-label">{active.label}</span>
              <Icon name="chevD" size={14}/>
            </button>
            {open && (
              <div className="chat-ch-menu">
                {CHANNELS.map(ch => (
                  <button
                    type="button"
                    key={ch.id}
                    className={`chat-ch-opt ${ch.id === activeChannel ? 'active' : ''}`}
                    onClick={() => { setActiveChannel(ch.id); setOpen(false); }}
                  >
                    <span className="chat-ch-dot" style={{background: ch.color}}/>
                    <span className="chat-ch-opt-label">{ch.label}</span>
                    {ch.id === activeChannel && <Icon name="check" size={14}/>}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="chat-compose-body">
          <div className="chat-input-wrap">
            <textarea
              className="chat-input"
              placeholder={`Сообщение в ${active.label}…`}
              rows={2}
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send(); }}
            ></textarea>
            <button
              className="chat-send-btn"
              onClick={send}
              disabled={!draft.trim()}
              type="button"
              title="Отправить (Ctrl+Enter)"
              aria-label="Отправить"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2 11 13"/>
                <path d="M22 2 15 22l-4-9-9-4z"/>
              </svg>
            </button>
          </div>
        </div>
        <div className="chat-compose-hint">Ctrl + Enter — отправить · ответ уйдёт в <b>{active.label}</b></div>
      </div>
    </div>
  );
}

function AITab({ c }) {
  const pluses = [
    `Проживает в ${c.city}`,
    `Более ${c.lastDur} практического опыта с Яндекс.Директ, РСЯ и VK Ads`,
    'Широкий стек инструментов: Метрика, GA, GTM, веб-аналитика',
    'Опыт построения маркетинговых стратегий и медиапланов',
    'Конкретные количественные достижения (50 000+ ключевых фраз, 1000+ объявлений)',
    `Опыт работы в ${c.lastCo} — знание экосистемы изнутри`,
    'Образовательный бэкграунд (Нетология) — структурное мышление',
  ];
  const minuses = [
    'Очень частая смена работы в 2022–2024 (8+ мест за ~2 года) — риск нестабильности',
    'Нет упоминаний сквозной аналитики (Roistat, Calltouch)',
    'Не указаны конкретные метрики (CPA, CTR, ROMI) и бюджеты кампаний',
    'Нет опыта A/B-тестирования',
    'Нет упоминаний работы с ИИ/автоматизацией',
    'Не указан уровень английского и зарплатные ожидания',
    'Нет профессиональных сертификатов Яндекса/Google',
  ];
  const questions = [
    `${c.name.split(' ')[1]}, добрый день! Подскажите ваши зарплатные ожидания и готовы ли вы рассматривать офис/гибрид в ${c.city} (вилка 80–110 тыс)?`,
    'Расскажите про ваши самые крупные кейсы по контекстной рекламе: какие были бюджеты, какие KPI (CPA, ROMI, ДРР) ставили и как достигали?',
    'Был ли у вас опыт работы со сквозной аналитикой — Roistat, Calltouch или подобными? На каком уровне?',
    'В резюме вижу частую смену проектов в 2022–2024 — расскажите, с чем это связано и что ищете на новом месте?',
    'Используете ли в работе ИИ-инструменты (ChatGPT, Claude и т.п.) для автоматизации — генерация объявлений, парсинг семантики, аналитика?',
  ];

  // Detailed criteria — for visualization (max → 100% bar)
  const criteria = [
    { label:'Локация (Новосибирск)',                                  pts:15, max:15, comment:'Кандидат проживает в Новосибирске — полное соответствие.' },
    { label:'Опыт работы с контекстной рекламой',                    pts:20, max:20, comment:'Более 2 лет с Яндекс.Директ, РСЯ, VK Ads — настройка кампаний, семантика, оптимизация.' },
    { label:'Системы аналитики (Метрика, GA)',                        pts:10, max:10, comment:'В навыках: Яндекс.Метрика, Google Analytics, веб-аналитика — продвинутый уровень.' },
    { label:'Сквозная аналитика и бюджеты (Roistat, Calltouch)',     pts:0,  max:10, comment:'В резюме нет упоминаний Roistat, Calltouch или иной сквозной аналитики.' },
    { label:'Знание ключевых метрик (CPA, CPC, CTR, ROMI, ДРР)',     pts:5,  max:10, comment:'Метрики явно не упомянуты, но описаны задачи по оптимизации.' },
    { label:'Аудиты кампаний и медиапланы',                          pts:10, max:10, comment:'Указано: разработка медиаплана, формирование стратегии продвижения.' },
    { label:'Работа с формами / чатами / квизами',                   pts:0,  max:5,  comment:'Прямых упоминаний работы с формами, чатами, обратным звонком, квизами нет.' },
    { label:'A/B-тесты',                                              pts:0,  max:5,  comment:'Опыт A/B-тестирования в резюме не упомянут.' },
    { label:'Отчётность и презентация решений',                      pts:2,  max:5,  comment:'Есть упоминания аналитики и обратной связи, но без деталей.' },
    { label:'Грамотность резюме',                                     pts:5,  max:5,  comment:'Резюме структурированное, без ошибок, есть достижения и количественные показатели.' },
    { label:'Зарплатные ожидания',                                    pts:0,  max:0,  comment:'Не указаны — требуется уточнение, баллы не начисляем.' },
    { label:'Работа с ИИ и автоматизацией',                          pts:0,  max:5,  comment:'В резюме нет упоминаний промптов, ИИ-инструментов или автоматизации рутины.' },
    { label:'Графические редакторы (Figma / Photoshop)',             pts:3,  max:5,  comment:'В навыках указан Adobe Photoshop — базовый уровень для креативов.' },
    { label:'Английский язык B1+',                                    pts:0,  max:5,  comment:'Уровень владения английским в резюме не указан.' },
    { label:'Кейсы с крупными бюджетами (500K+)',                    pts:0,  max:5,  comment:'Бюджеты в резюме не указаны, конкретных кейсов с цифрами нет.' },
    { label:'Yandex Tag Manager и e-commerce',                       pts:1,  max:5,  comment:'Указан Google Tag Manager (косвенно близкий навык).' },
    { label:'Профессиональные сертификаты',                          pts:0,  max:5,  comment:'Сертификаты Директ/Метрика в резюме не упомянуты.' },
  ];
  const totalPts = criteria.reduce((s, x) => s + x.pts, 0);
  const totalMax = criteria.reduce((s, x) => s + x.max, 0);

  return (
    <div className="ai-single">
      <AIVerdictCard c={c} hideLink showScreening/>

      <h3 className="cc-sec-title">Анализ AI</h3>
      <div className="msg ai-msg ai-msg-good" style={{maxWidth:'100%'}}>
        <div className="ai-name ai-name-good"><span className="cc-sec-emoji">✅</span> Сильные стороны</div>
        <ul className="ai-msg-list">
          {pluses.map((p, i) => <li key={i}>{p}</li>)}
        </ul>
      </div>

      <div className="msg ai-msg ai-msg-warn" style={{maxWidth:'100%', marginTop: 8}}>
        <div className="ai-name ai-name-warn"><span className="cc-sec-emoji">⚠️</span> Слабые стороны</div>
        <ul className="ai-msg-list">
          {minuses.map((m, i) => <li key={i}>{m}</li>)}
        </ul>
      </div>

      <div className="msg ai-msg ai-msg-q" style={{maxWidth:'100%', marginTop: 8}}>
        <div className="ai-name ai-name-q"><span className="cc-sec-emoji">💬</span> Вопросы для первого контакта</div>
        <ol className="ai-msg-list ai-msg-list-num">
          {questions.map((q, i) => <li key={i}>{q}</li>)}
        </ol>
      </div>

      <h3 className="cc-sec-title">
        Разбор по критериям
        <span className="crit-total">
          <span className="t-mono">{totalPts}</span> / <span className="t-mono">{totalMax}</span>
        </span>
      </h3>
      <div className="crit-list">
        {criteria.map((cr, i) => {
          const pct = cr.max ? Math.round((cr.pts / cr.max) * 100) : 0;
          const color = cr.max === 0 ? 'gray' : pct >= 80 ? 'green' : pct >= 40 ? 'yellow' : 'red';
          return (
            <div key={i} className={`crit-row crit-${color}`}>
              <div className="crit-head">
                <span className="crit-label">{cr.label}</span>
                <span className="crit-pts t-mono">{cr.pts}<span className="crit-pts-max"> / {cr.max || '—'}</span></span>
              </div>
              <div className="crit-bar"><span style={{width: `${pct}%`}}/></div>
              <div className="crit-comment">{cr.comment}</div>
            </div>
          );
        })}
      </div>

    </div>
  );
}

// =====================================================================
// CallsTab — звонки рекрутера через Манго Телеком (amoCRM-style)
// =====================================================================
const CALL_WAVE = [8,14,22,31,19,12,26,38,44,30,18,11,24,40,52,46,33,21,14,28,42,55,48,36,24,16,30,46,58,50,38,26,18,12,22,36,48,40,28,17,11,20,33,44,30,19,12,9];

function fmtClock(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function CallPlayer({ durationSec, color = 'var(--accent)' }) {
  const [playing, setPlaying] = useStateC(false);
  const [pos, setPos] = useStateC(0);
  const [speed, setSpeed] = useStateC(1);
  const trackRef = React.useRef(null);

  useEffectC(() => {
    if (!playing) return;
    const iv = setInterval(() => {
      setPos(p => {
        const np = p + 0.12 * speed;
        if (np >= durationSec) return durationSec;
        return np;
      });
    }, 120);
    return () => clearInterval(iv);
  }, [playing, speed, durationSec]);

  useEffectC(() => {
    if (pos >= durationSec && playing) setPlaying(false);
  }, [pos, durationSec, playing]);

  const pct = Math.min(100, (pos / durationSec) * 100);
  const toggle = () => {
    if (pos >= durationSec) setPos(0);
    setPlaying(p => !p);
  };
  const cycleSpeed = () => setSpeed(s => (s === 1 ? 1.5 : s === 1.5 ? 2 : 1));
  const seek = (e) => {
    const r = trackRef.current.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    setPos(ratio * durationSec);
  };

  return (
    <div className="call-player" style={{'--cp-color': color}}>
      <button className={`cp-play ${playing ? 'playing' : ''}`} onClick={toggle} aria-label={playing ? 'Пауза' : 'Слушать'}>
        {playing ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M7 5.5v13a1 1 0 0 0 1.5.87l11-6.5a1 1 0 0 0 0-1.74l-11-6.5A1 1 0 0 0 7 5.5z"/></svg>
        )}
      </button>
      <div className="cp-wave" ref={trackRef} onClick={seek}>
        {CALL_WAVE.map((h, i) => {
          const barPct = (i / CALL_WAVE.length) * 100;
          return <span key={i} className={`cp-bar ${barPct <= pct ? 'on' : ''}`} style={{height: `${h}%`}}/>;
        })}
      </div>
      <span className="cp-time t-mono">{fmtClock(pos)} / {fmtClock(durationSec)}</span>
      <button className="cp-speed t-mono" onClick={cycleSpeed} title="Скорость воспроизведения">{speed}×</button>
      <button className="cp-dl icon-btn" title="Скачать запись"><Icon name="download" size={15}/></button>
    </div>
  );
}

function CallsTab({ c }) {
  const recruiter = c.recruiter || 'Анна Седова';
  const calls = [
    {
      id: 1, dir: 'out', status: 'answered', durationSec: 252, date: c.date, time: '14:32',
      title: 'Первичный скрининг',
      summary: `Глафира соединила ${recruiter} с кандидатом. Обсудили текущую занятость и причину поиска, кратко прошлись по опыту в ${c.lastCo}. Кандидат подтвердил интерес к вакансии, готов к интервью на следующей неделе.`,
      hint: 'Рекрутёр говорил 68% времени — кандидату почти не дали раскрыться. Не уточнили зарплатные ожидания и формат работы (офис/удалёнка), хотя это ключевые отсеивающие критерии. Дважды перебили кандидата на рассказе про достижения.',
      hintTone: 'warn',
    },
    {
      id: 2, dir: 'out', status: 'missed', durationSec: 0, date: c.date, time: '11:08',
      title: 'Недозвон',
      summary: 'Кандидат не взял трубку. Глафира автоматически отправила сообщение в Telegram с предложением выбрать удобное время для звонка.',
      hint: null,
    },
    {
      id: 3, dir: 'in', status: 'answered', durationSec: 158, date: c.date, time: '15:47',
      title: 'Кандидат перезвонил',
      summary: 'Кандидат перезвонил сам, уточнил детали по графику и оформлению по ТК. Договорились о видеоинтервью во вторник в 15:00, ссылку рекрутёр отправит в Telegram.',
      hint: 'В конце разговора не проговорили следующий шаг явно — кандидат сам спросил, «что дальше». Стоит всегда резюмировать договорённости и сроки голосом, а не только в чате.',
      hintTone: 'warn',
    },
    {
      id: 4, dir: 'out', status: 'answered', durationSec: 365, date: c.date, time: '16:20',
      title: 'Согласование интервью',
      summary: 'Подтвердили дату и время интервью, ответили на вопросы про команду и проект. Кандидат настроен позитивно, прислал подтверждение в календаре.',
      hint: 'Хороший звонок: чёткая структура, договорённости зафиксированы. Можно было заранее предупредить о тестовом задании, чтобы не было сюрприза на интервью.',
      hintTone: 'good',
    },
  ];

  const answered = calls.filter(x => x.status === 'answered');
  const totalSec = answered.reduce((s, x) => s + x.durationSec, 0);

  const dirMeta = {
    out: { label: 'Исходящий', cls: 'out', icon: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M7 17 17 7"/><path d="M8 7h9v9"/></svg>
    )},
    in: { label: 'Входящий', cls: 'in', icon: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 7 7 17"/><path d="M16 17H7V8"/></svg>
    )},
  };

  return (
    <div className="calls-tab">
      {/* Summary strip */}
      <div className="calls-summary">
        <div className="calls-sum-left">
          <span className="calls-sum-item"><span className="calls-sum-num t-mono">{calls.length}</span> звонка</span>
          <span className="calls-sum-sep"/>
          <span className="calls-sum-item"><span className="calls-sum-num t-mono">{fmtClock(totalSec)}</span> разговора</span>
          <span className="calls-sum-sep"/>
          <span className="calls-sum-item calls-sum-missed"><span className="calls-sum-num t-mono">1</span> недозвон</span>
        </div>
        <div className="calls-mango" title="Телефония подключена через Манго Телеком">
          <span className="mango-dot"/>
          Манго Телеком · {c.phone}
        </div>
      </div>

      {/* Call list */}
      <div className="calls-list">
        {calls.map(call => {
          const dm = dirMeta[call.dir];
          const missed = call.status === 'missed';
          return (
            <div key={call.id} className={`call-card ${missed ? 'missed' : ''}`}>
              <div className="call-head">
                <span className={`call-dir call-dir-${dm.cls} ${missed ? 'call-dir-missed' : ''}`}>
                  {missed ? (
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M7 17 17 7"/><path d="M8 7h9v9"/><line x1="2" y1="22" x2="22" y2="2" stroke="currentColor" strokeWidth="2"/></svg>
                  ) : dm.icon}
                </span>
                <span className="call-title">{call.title}</span>
                {missed
                  ? <span className="call-status call-status-missed">Не дозвонился</span>
                  : <span className="call-status call-status-ok">{dm.label} · {fmtClock(call.durationSec)}</span>}
                <span className="call-spacer"/>
                <span className="call-recruiter">{recruiter}</span>
                <span className="call-when t-mono">{call.date} · {call.time}</span>
              </div>

              {!missed && <CallPlayer durationSec={call.durationSec} color={call.dir === 'in' ? '#16A34A' : 'var(--accent)'}/>}

              <div className="call-summary">
                <div className="call-block-label">
                  <span className="glafira-emoji">👩🏻</span> Краткое содержание
                </div>
                <div className="call-summary-text">{call.summary}</div>
              </div>

              {call.hint && (
                <div className={`call-hint call-hint-${call.hintTone}`}>
                  <div className="call-hint-mark">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.79.68-1.4 1.41-2a5 5 0 1 0-7 0c.73.6 1.23 1.21 1.41 2"/></svg>
                  </div>
                  <div className="call-hint-body">
                    <div className="call-hint-title">
                      {call.hintTone === 'good' ? 'AI-разбор звонка' : 'AI-подсказка: что улучшить'}
                    </div>
                    <div className="call-hint-text">{call.hint}</div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

Object.assign(window, { CandidatesList, CANDIDATES, VACANCY_INFO, ChatTab, VerifyTab, CommentsTab, ActionsTab, MessIconRound });
