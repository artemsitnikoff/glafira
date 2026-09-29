// SmartSearchAuto — ветка «Автоподбор» (сохранённые автопоиски hh.ru).
// Идея: фильтры настроены и подписаны на hh → новые подходящие резюме приходят в поток.
// Глафира забирает их, оценивает AI-матчингом и даёт забрать контакт / в воронку / в пул.
// Состояния: список автопоисков → кандидаты выбранного автопоиска → карточка кандидата (низ).
const { useState: useStateSA, useMemo: useMemoSA, useEffect: useEffectSA, useRef: useRefSA } = React;

// ====== Доменные наборы (правдоподобные резюме на бесплатных полях) ======
const SA_DOMAINS = {
  devops: {
    titles: ['DevOps-инженер','Системный инженер','SRE-инженер','Инженер по эксплуатации'],
    skills: ['Kubernetes','Docker','Terraform','Ansible','CI/CD','GitLab CI','Linux','Prometheus','Helm','Bash','PostgreSQL','Nginx'],
    companies: ['2ГИС','Тинькофф','Сбер','X5 Tech','Авито','Ростелеком','Контур','Yandex Cloud','МТС Диджитал'],
    edu: ['НГТУ · Автоматизированные системы обработки информации','СибГУТИ · Инфокоммуникационные технологии','НГУ · Информатика и вычислительная техника'],
    salary: [180000, 330000],
    bullets: [
      ['поддержка и развитие Kubernetes-кластеров (50+ нод)','миграция CI/CD на GitLab CI — пайплайны быстрее на 40%','инфраструктура как код: Terraform-модули и review','мониторинг Prometheus + Grafana, настройка алертинга','дежурства on-call, разбор и постмортемы инцидентов'],
      ['автоматизация деплоя через Helm и ArgoCD','перенос инфраструктуры в Yandex Cloud','написание Ansible-ролей для типовых сервисов','контейнеризация legacy-приложений','поддержка SLA 99.95%, снижение downtime'],
    ],
  },
  analyst: {
    titles: ['Системный аналитик','Бизнес-аналитик','Системный / бизнес-аналитик','Аналитик (1С)'],
    skills: ['SQL','BPMN','UML','REST API','OpenAPI','Confluence','Jira','Postman','Анализ требований','User Story','PostgreSQL'],
    companies: ['Сбер','Альфа-Банк','2ГИС','Тензор','Контур','ЦФТ','Ростелеком','Райффайзен'],
    edu: ['НГУЭУ · Бизнес-информатика','НГТУ · Прикладная информатика','НГУ · Экономика'],
    salary: [130000, 260000],
    bullets: [
      ['сбор и формализация требований (BRD, SRS)','проектирование REST API, описание контрактов в OpenAPI','работа с командой разработки по Scrum','моделирование процессов в BPMN, схемы интеграций','подготовка ТЗ и пользовательских историй'],
      ['описание структуры БД, ER-диаграммы','ведение документации в Confluence','постановка и декомпозиция задач в Jira','анализ интеграций между смежными системами','участие в приёмочном тестировании'],
    ],
  },
  sales: {
    titles: ['Менеджер по продажам','Руководитель отдела продаж','Менеджер по развитию бизнеса','Sales-менеджер B2B'],
    skills: ['B2B-продажи','CRM Битрикс24','Холодные звонки','Переговоры с ЛПР','Воронка продаж','Тендеры','amoCRM','Активные продажи'],
    companies: ['СёрчИнформ','Softline','Ростелеком','МегаФон Бизнес','1С-Рарус','КОРУС Консалтинг','Контур'],
    edu: ['НГУЭУ · Менеджмент организации','СибГУ · Маркетинг','НГТУ · Бизнес-информатика'],
    salary: [80000, 210000],
    bullets: [
      ['активный поиск и привлечение B2B-клиентов','ведение воронки в CRM (Битрикс24)','переговоры с ЛПР, заключение договоров','выполнение плана продаж 110–130%','развитие партнёрской сети в регионе'],
      ['холодные звонки и обработка входящих лидов','подготовка коммерческих предложений','сопровождение сделки от лида до оплаты','участие в отраслевых выставках','рост среднего чека на 18%'],
    ],
  },
  php: {
    titles: ['PHP-разработчик','Backend-разработчик (PHP)','Web-разработчик','Fullstack PHP-разработчик'],
    skills: ['PHP 8','Laravel','Symfony','MySQL','REST API','Redis','Docker','PHPUnit','RabbitMQ','JavaScript','Vue'],
    companies: ['2ГИС','Тензор','веб-студия «Сибирикс»','Контур','Audiqo','FL.ru','Студия Лебедева'],
    edu: ['НГТУ · Программная инженерия','СибГУТИ · Прикладная математика','НГУ · Информатика'],
    salary: [120000, 240000],
    bullets: [
      ['разработка backend на PHP 8 / Laravel','проектирование и оптимизация MySQL-запросов','интеграция платёжных шлюзов и внешних API','покрытие кода тестами (PHPUnit)','code review и менторинг junior-разработчиков'],
      ['поддержка и рефакторинг legacy-кода','разработка на Symfony, очереди RabbitMQ','кэширование Redis, оптимизация под нагрузку','REST API для мобильных приложений','работа с Docker в команде'],
    ],
  },
};

// ====== Сохранённые автопоиски (как «папки» автопоиска на hh) ======
const SA_SEARCHES = [
  { id:'devops', name:'DevOps',               domain:'devops',  region:'Новосибирск',           period:'неделю', total:650, newCount:36, subscribed:true,  autoEval:true,  relocate:true,  noSalary:false, updated:'12 июня' },
  { id:'sysan',  name:'системный аналитик',   domain:'analyst', region:'Новосибирск',           period:'неделю', total:128, newCount:14, subscribed:true,  autoEval:true,  relocate:true,  noSalary:true,  updated:'11 июня' },
  { id:'biz',    name:'Business upgrade',     domain:'sales',   region:'Новосибирск',           period:'месяц',  total:11,  newCount:9,  subscribed:true,  autoEval:false, relocate:true,  noSalary:true,  updated:'12 июня' },
  { id:'php',    name:'PHP-программист',       domain:'php',     region:'Новосибирская область', period:'неделю', total:75,  newCount:0,  subscribed:false, autoEval:false, relocate:true,  noSalary:true,  updated:'13 мая'  },
  { id:'laravel',name:'Laravel',              domain:'php',     region:'Новосибирская область', period:'неделю', total:43,  newCount:5,  subscribed:true,  autoEval:false, relocate:false, noSalary:true,  updated:'13 мая'  },
];

const SA_NAMES_M = { first:['Александр','Дмитрий','Максим','Сергей','Андрей','Алексей','Артём','Илья','Кирилл','Михаил','Никита','Роман','Егор','Денис','Павел','Владимир','Антон','Евгений'],
  last:['Иванов','Петров','Смирнов','Кузнецов','Соколов','Попов','Лебедев','Козлов','Новиков','Морозов','Волков','Зайцев','Павлов','Семёнов','Голубев','Виноградов','Богданов','Тарасов'] };
const SA_NAMES_F = { first:['Анна','Мария','Елена','Ольга','Наталья','Екатерина','Юлия','Татьяна','Ирина','Дарья','Светлана','Виктория','Полина','Ксения'],
  last:['Иванова','Петрова','Смирнова','Кузнецова','Соколова','Попова','Лебедева','Козлова','Новикова','Морозова','Волкова','Зайцева','Семёнова','Голубева'] };
const SA_CITIES = ['Новосибирск','Новосибирск','Новосибирск','Бердск','Академгородок','Кольцово','Новосибирск'];
const SA_UPDATED_NEW = ['сегодня','сегодня','вчера','вчера','2 дня назад'];
const SA_UPDATED_OLD = ['3 дня назад','неделю назад','2 недели назад','10 июня','5 июня','28 мая'];

function saPrng(seed) {
  let s = (seed >>> 0) || 1;
  return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
}
function saHash(str) { let h = 0; for (let i = 0; i < str.length; i++) h = (Math.imul(h, 31) + str.charCodeAt(i)) | 0; return Math.abs(h); }
function saPick(rnd, arr) { return arr[Math.floor(rnd() * arr.length)]; }
function saInt(rnd, a, b) { return a + Math.floor(rnd() * (b - a + 1)); }
function saPlural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}
function saExpStr(years) {
  const m = Math.floor(((years * 10) % 10) / 10 * 11);
  const yPart = years > 0 ? `${years} ${saPlural(years,'год','года','лет')}` : '';
  return yPart || 'менее года';
}

// ====== Генерация кандидатов автопоиска (бесплатные поля; контакты закрыты) ======
// Ленивая генерация по глобальному индексу gi — под пагинацию (как страницы выдачи hh).
const SA_CACHE = {};            // candId → candidate
const SA_PER_PAGE = 10;
function saMaxDepth(search) { return Math.min(search.total, 2000); } // глубина выдачи hh ≤ 2000

function saMakeCandidate(search, gi) {
  const id = `${search.id}-${gi}`;
  if (SA_CACHE[id]) return SA_CACHE[id];
  const dom = SA_DOMAINS[search.domain];
  const rnd = saPrng(saHash(search.id) * 131 + gi * 977 + 7);
  const isNew = gi < search.newCount;
  const gender = rnd() < (search.domain === 'sales' ? 0.5 : 0.72) ? 'm' : 'f';
  const npool = gender === 'm' ? SA_NAMES_M : SA_NAMES_F;
  const first = saPick(rnd, npool.first);
  const last = saPick(rnd, npool.last);
  const title = saPick(rnd, dom.titles);
  const age = saInt(rnd, 24, 44);
  const city = saPick(rnd, SA_CITIES);
  const totalYears = saInt(rnd, 2, 14);
  const hasSalary = search.noSalary ? rnd() > 0.42 : true;
  const sMin = dom.salary[0], sMax = dom.salary[1];
  const salary = hasSalary ? Math.round((sMin + rnd() * (sMax - sMin)) / 5000) * 5000 : null;
  const anonymous = rnd() < 0.14;
  const skn = saInt(rnd, 4, 6);
  const sstart = saInt(rnd, 0, dom.skills.length - 1);
  const skills = [];
  for (let k = 0; k < skn; k++) skills.push(dom.skills[(sstart + k) % dom.skills.length]);
  const jobs = [];
  let endYear = 2026;
  for (let j = 0; j < 3; j++) {
    const dur = j === 0 ? saInt(rnd, 1, 4) : saInt(rnd, 1, 3);
    const startYear = endYear - dur;
    const period = j === 0 ? `${startYear} — наст. время` : `${startYear} — ${endYear}`;
    jobs.push({
      pos: saPick(rnd, dom.titles),
      co: saPick(rnd, dom.companies),
      period,
      dur: `${dur} ${saPlural(dur,'год','года','лет')}`,
      bullets: dom.bullets[(gi + j) % dom.bullets.length],
    });
    endYear = startYear;
  }
  const baseScore = 58 + (saHash(search.id + gi) % 38); // 58–95
  const obj = {
    id,
    searchId: search.id,
    title, age, city, gender, anonymous,
    salary, totalYears,
    expStr: saExpStr(totalYears),
    skills,
    edu: saPick(rnd, dom.edu),
    lastPos: jobs[0].pos, lastCo: jobs[0].co, lastPeriod: jobs[0].period,
    jobs,
    updated: isNew ? saPick(rnd, SA_UPDATED_NEW) : saPick(rnd, SA_UPDATED_OLD),
    isNew,
    baseScore,
    realName: `${last} ${first[0]}.`,
    fullName: `${first} ${last}`,
    realPhone: `+7 (913) ${saInt(rnd,100,999)}-${saInt(rnd,10,99)}-${saInt(rnd,10,99)}`,
    langs: rnd() > 0.5 ? 'Русский · English B1' : 'Русский · English A2',
    relocate: search.relocate && rnd() > 0.4,
  };
  SA_CACHE[id] = obj;
  return obj;
}
function saGetCandidateById(id) { return SA_CACHE[id] || null; }
function saGetPage(search, onlyNew, page, perPage) {
  const total = onlyNew ? search.newCount : saMaxDepth(search);
  const start = (page - 1) * perPage;
  const out = [];
  for (let gi = start; gi < Math.min(total, start + perPage); gi++) out.push(saMakeCandidate(search, gi));
  return out;
}
// windowed список страниц: [1, '…', 4, 5, 6, '…', 65]
function saPager(cur, count) {
  const out = [];
  for (let p = 1; p <= count; p++) {
    if (p === 1 || p === count || (p >= cur - 1 && p <= cur + 1)) out.push(p);
    else if (out[out.length - 1] !== '…') out.push('…');
  }
  return out;
}

function saScoreVerdict(score) {
  if (score >= 80) return 'Хорошо подходит — релевантный опыт и ключевые навыки совпадают с требованиями.';
  if (score >= 60) return 'Подходит частично — есть релевантный опыт, но не хватает части навыков.';
  return 'Слабое совпадение — опыт частично расходится с требованиями вакансии.';
}

// Оценка ОТНОСИТЕЛЬНА → для неё нужна основа: вакансия или промт.
// Основа по умолчанию для предвключённых автопоисков:
const SA_BASIS_DEFAULTS = {
  devops: { kind:'vacancy', vacId:'do', label:'DevOps-инженер' },
  sysan:  { kind:'vacancy', vacId:'sa', label:'Системный аналитик' },
};
function saBasisLabel(b) {
  if (!b) return null;
  if (b.kind === 'vacancy') return b.label;
  const t = b.text || '';
  return t.length > 46 ? t.slice(0, 46) + '…' : t;
}

// ====== Главный компонент ветки ======
function SSAutoFlow({ onBack, onGoFunnel, onGoPool }) {
  const [searchId, setSearchId] = useStateSA(null);     // null → список автопоисков
  const [onlyNew, setOnlyNew] = useStateSA(false);
  const [openId, setOpenId] = useStateSA(null);         // кандидат в нижней карточке
  const [sort, setSort] = useStateSA('updated');        // updated | score
  // авто-оценка по автопоискам
  const [autoEval, setAutoEval] = useStateSA(() => {
    const m = {}; SA_SEARCHES.forEach(s => m[s.id] = s.autoEval); return m;
  });
  const [scored, setScored] = useStateSA(() => {
    const set = new Set(); SA_SEARCHES.forEach(s => { if (s.autoEval) set.add(s.id); }); return set;
  });
  const [scoringId, setScoringId] = useStateSA(null);
  const [subs, setSubs] = useStateSA(() => {
    const m = {}; SA_SEARCHES.forEach(s => m[s.id] = s.subscribed); return m;
  });
  // основа оценки (вакансия/промт) по автопоискам + диалог выбора основы
  const [basis, setBasis] = useStateSA(() => ({ ...SA_BASIS_DEFAULTS }));
  const [basisDialog, setBasisDialog] = useStateSA(null); // { id, then:'enable'|'score' }
  // пул контактов + забранные кандидаты
  const [pool, setPool] = useStateSA(47);
  const [taken, setTaken] = useStateSA({});             // candId → { contact:true, dest:'pool'|vacId }
  const [toast, setToast] = useStateSA(null);
  const scoreTimer = useRefSA(null);

  useEffectSA(() => () => clearTimeout(scoreTimer.current), []);
  useEffectSA(() => { if (!toast) return; const t = setTimeout(() => setToast(null), 4200); return () => clearTimeout(t); }, [toast]);

  function openSearch(s, newMode) {
    setSearchId(s.id); setOnlyNew(!!newMode); setOpenId(null);
    setSort(scored.has(s.id) ? 'score' : 'updated');
  }
  function backToList() { setSearchId(null); setOpenId(null); }

  function doScore(id) {
    if (scored.has(id)) return;
    setScoringId(id);
    clearTimeout(scoreTimer.current);
    scoreTimer.current = setTimeout(() => {
      setScored(prev => new Set(prev).add(id));
      setScoringId(null);
    }, 1500);
  }
  // Нет основы оценки → сперва спросить вакансию/промт.
  function requestScore(id) {
    if (scored.has(id) || scoringId === id) return;
    if (basis[id]) doScore(id); else setBasisDialog({ id, then: 'score' });
  }
  function requestEnableEval(id) {
    if (basis[id]) { setAutoEval(p => ({ ...p, [id]: true })); doScore(id); }
    else setBasisDialog({ id, then: 'enable' });
  }
  function toggleAutoEval(id) {
    if (autoEval[id]) setAutoEval(p => ({ ...p, [id]: false }));
    else requestEnableEval(id);
  }
  function confirmBasis(b) {
    if (!basisDialog) return;
    const { id, then } = basisDialog;
    setBasis(prev => ({ ...prev, [id]: b }));
    if (then === 'enable') setAutoEval(p => ({ ...p, [id]: true }));
    setBasisDialog(null);
    setTimeout(() => doScore(id), 0);
  }
  function editBasis(id) { setBasisDialog({ id, then: scored.has(id) ? 'score' : (autoEval[id] ? 'enable' : 'score') }); }

  function takeContact(c) {
    if (taken[c.id]?.contact) return;
    if (pool <= 0) { setToast({ kind:'err', text:'Пул контактов исчерпан. Пополните в кабинете hh.' }); return; }
    setPool(p => p - 1);
    setTaken(prev => ({ ...prev, [c.id]: { ...(prev[c.id] || {}), contact: true } }));
    setToast({ kind:'ok', text: c.anonymous
      ? `Контакт списан. Резюме анонимное — часть полей могла не открыться.`
      : `Контакт открыт. Осталось ${pool - 1} в пуле.` });
  }
  function routeCandidate(c, dest, destLabel) {
    const hadContact = !!taken[c.id]?.contact;
    let nextPool = pool;
    if (!hadContact) {
      if (pool <= 0) { setToast({ kind:'err', text:'Пул контактов исчерпан. Пополните в кабинете hh.' }); return; }
      nextPool = pool - 1; setPool(nextPool);
    }
    setTaken(prev => ({ ...prev, [c.id]: { contact: true, dest } }));
    setToast({
      kind:'ok',
      text: `${c.realName} — ${destLabel}.`,
      action: dest === 'pool' ? { label:'Открыть базу', fn: onGoPool } : { label:'Открыть воронку', fn: onGoFunnel },
    });
  }

  const search = SA_SEARCHES.find(s => s.id === searchId) || null;
  const dialogSearch = basisDialog ? SA_SEARCHES.find(s => s.id === basisDialog.id) : null;

  return (
    <div className="ss-page ssa-page" data-screen-label={search ? 'Smart Search / Auto / Candidates' : 'Smart Search / Auto / Searches'}>
      <SSAutoHeader onBack={onBack} pool={pool}/>

      {!search ? (
        <SSAutoSearchesView
          autoEval={autoEval} scored={scored} scoringId={scoringId} subs={subs} basis={basis}
          onToggleAutoEval={toggleAutoEval}
          onEditBasis={editBasis}
          onToggleSub={(id) => setSubs(p => ({ ...p, [id]: !p[id] }))}
          onOpen={openSearch}
        />
      ) : (
        <SSAutoCandidatesView
          search={search}
          onlyNew={onlyNew} setOnlyNew={setOnlyNew}
          sort={sort} setSort={setSort}
          isScored={scored.has(search.id)} scoring={scoringId === search.id}
          autoEval={!!autoEval[search.id]} onToggleAutoEval={() => toggleAutoEval(search.id)}
          basis={basis[search.id]} onEditBasis={() => editBasis(search.id)}
          onRunScoring={() => requestScore(search.id)}
          taken={taken}
          onBackToList={backToList}
          onOpenCand={setOpenId}
        />
      )}

      {openId && search && (
        <SSAutoSheet
          c={saGetCandidateById(openId)}
          search={search}
          isScored={scored.has(search.id)} scoring={scoringId === search.id}
          basis={basis[search.id]}
          taken={taken[openId]}
          pool={pool}
          onRunScoring={() => requestScore(search.id)}
          onTakeContact={takeContact}
          onRoute={routeCandidate}
          onClose={() => setOpenId(null)}
        />
      )}

      {basisDialog && dialogSearch && (
        <SSAutoBasisDialog
          search={dialogSearch}
          mode={basisDialog.then}
          current={basis[basisDialog.id]}
          onCancel={() => setBasisDialog(null)}
          onConfirm={confirmBasis}
        />
      )}

      {toast && (
        <div className={`ssa-toast ssa-toast-${toast.kind}`}>
          <Icon name={toast.kind === 'ok' ? 'check' : 'alert'} size={15}/>
          <span>{toast.text}</span>
          {toast.action && <button className="ssa-toast-act" onClick={() => { toast.action.fn && toast.action.fn(); setToast(null); }}>{toast.action.label}</button>}
        </div>
      )}
    </div>
  );
}

// ====== Шапка ветки ======
function SSAutoHeader({ onBack, pool }) {
  return (
    <div>
      <button className="ss-back" onClick={onBack}>
        <Icon name="chevL" size={14}/> Выбор источника
      </button>
      <div className="ss-head">
        <div className="ss-head-mark ssa-mark">💃</div>
        <div className="ss-head-text">
          <h1>
            Автоподбор <span className="ss-beta">beta</span>
            <span className="ssa-hh-pill"><Icon name="antenna" size={12}/> пока через hh</span>
          </h1>
          <div className="ss-sub">
            Ваши <b>автопоиски на hh.ru</b>: фильтры настроены и подписаны — новые подходящие резюме
            приходят в поток. Глафира забирает их, оценивает AI-матчингом и даёт открыть контакт.
          </div>
        </div>
        <div className="ssa-pool" title="Остаток контактов в пуле hh">
          <div className="ssa-pool-num t-mono">{pool}</div>
          <div className="ssa-pool-cap">контактов<br/>в пуле</div>
        </div>
      </div>
    </div>
  );
}

// ====== Вид: список автопоисков ======
function SSAutoSearchesView({ autoEval, scored, scoringId, subs, basis, onToggleAutoEval, onEditBasis, onToggleSub, onOpen }) {
  const totalNew = SA_SEARCHES.reduce((s, x) => s + x.newCount, 0);
  return (
    <div className="ssa-searches">
      <div className="ssa-searches-bar">
        <div className="ssa-sb-left">
          <span className="ssa-sb-title">Автопоиски</span>
          <span className="ssa-sb-count t-mono">{SA_SEARCHES.length}</span>
          {totalNew > 0 && <span className="ssa-sb-new">+{totalNew} новых</span>}
        </div>
        <div className="ssa-sb-sync">
          <span className="ssa-sync-dot"/> синхронизировано с hh · обновляется раз в час
        </div>
      </div>

      <div className="ssa-search-list">
        {SA_SEARCHES.map(s => {
          const isScored = scored.has(s.id);
          const isScoring = scoringId === s.id;
          return (
            <div key={s.id} className="ssa-search-card">
              <div className="ssa-sc-main">
                <div className="ssa-sc-head">
                  <span className="ssa-sc-name">«{s.name}»</span>
                  <button className="ssa-sc-edit" title="Изменить автопоиск на hh"><Icon name="open" size={13}/></button>
                  <span className="ssa-sc-region"><Icon name="pin" size={12}/> {s.region}</span>
                  <div style={{flex:1}}/>
                  <span className="ssa-sc-date t-mono">{s.updated}</span>
                </div>

                <div className="ssa-sc-filters">
                  <span className="ssa-filter-chip">{s.relocate ? 'с переездом' : 'без переезда'}</span>
                  <span className="ssa-filter-chip">{s.noSalary ? 'вкл. без ЗП' : 'только с ЗП'}</span>
                  <span className="ssa-filter-chip">за {s.period}</span>
                  <span className={`ssa-sub ${subs[s.id] ? 'on' : 'off'}`} onClick={() => onToggleSub(s.id)} title="Подписка на новые резюме">
                    <span className="ssa-sub-dot"/>{subs[s.id] ? 'подписка активна' : 'подписка выключена'}
                  </span>
                </div>

                <div className="ssa-sc-foot">
                  <button className="ssa-sc-link all" onClick={() => onOpen(s, false)}>
                    Показать соискателей <span className="t-mono">{ssFmt(s.total)}</span>
                  </button>
                  {s.newCount > 0 ? (
                    <button className="ssa-sc-link new" onClick={() => onOpen(s, true)}>
                      <span className="ssa-new-dot"/> Новые <span className="t-mono">+{s.newCount}</span>
                    </button>
                  ) : (
                    <span className="ssa-sc-nonew">новых нет</span>
                  )}
                </div>
              </div>

              <div className="ssa-sc-aside">
                <div className="ssa-autoeval">
                  <div className="ssa-ae-text">
                    <div className="ssa-ae-title">Авто-оценка новых</div>
                    <div className="ssa-ae-sub">
                      {isScoring ? 'Глафира оценивает…'
                        : autoEval[s.id] ? 'новые приходят с AI-баллом'
                        : 'оценивать вручную'}
                    </div>
                  </div>
                  <button className={`ss-switch ${autoEval[s.id] ? 'on' : ''}`} onClick={() => onToggleAutoEval(s.id)} aria-label="Авто-оценка"/>
                </div>
                {(autoEval[s.id] || scored.has(s.id)) && basis[s.id] && (
                  <button className="ssa-basis" onClick={() => onEditBasis(s.id)} title="Изменить основу оценки">
                    <Icon name={basis[s.id].kind === 'vacancy' ? 'briefcase' : 'message'} size={12}/>
                    <span className="ssa-basis-text">
                      <span className="ssa-basis-k">{basis[s.id].kind === 'vacancy' ? 'против вакансии' : 'по промту'}</span>
                      <span className="ssa-basis-v">{saBasisLabel(basis[s.id])}</span>
                    </span>
                    <Icon name="open" size={11} className="ssa-basis-edit"/>
                  </button>
                )}
                {isScoring && <div className="ssa-ae-flag scoring"><span className="ssa-spin"/> оцениваю новых…</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ====== Вид: кандидаты выбранного автопоиска ======
function SSAutoCandidatesView({ search, onlyNew, setOnlyNew, sort, setSort, isScored, scoring,
                                autoEval, onToggleAutoEval, basis, onEditBasis, onRunScoring, taken, onBackToList, onOpenCand }) {
  const PER = SA_PER_PAGE;
  const [page, setPage] = useStateSA(1);
  const candsRef = useRefSA(null);
  useEffectSA(() => { setPage(1); }, [search.id, onlyNew, sort]);
  const totalItems = onlyNew ? search.newCount : saMaxDepth(search);
  const pageCount = Math.max(1, Math.ceil(totalItems / PER));
  const curPage = Math.min(page, pageCount);
  const pageItems = useMemoSA(() => {
    let items = saGetPage(search, onlyNew, curPage, PER);
    if (sort === 'score') items = [...items].sort((a, b) => b.baseScore - a.baseScore);
    return items;
  }, [search.id, onlyNew, sort, curPage]);
  const rangeStart = totalItems === 0 ? 0 : (curPage - 1) * PER + 1;
  const rangeEnd = (curPage - 1) * PER + pageItems.length;
  function goPage(p) {
    const np = Math.max(1, Math.min(pageCount, p));
    setPage(np);
    requestAnimationFrame(() => {
      const cont = candsRef.current && candsRef.current.closest('.content');
      if (cont && candsRef.current) {
        const delta = candsRef.current.getBoundingClientRect().top - cont.getBoundingClientRect().top;
        cont.scrollTop += delta - 14;
      }
    });
  }

  return (
    <div className="ssa-cands" ref={candsRef}>
      <div className="ssa-cands-head">
        <button className="ssa-crumb" onClick={onBackToList}>
          <Icon name="chevL" size={13}/> Автопоиски
        </button>
        <span className="ssa-crumb-sep">/</span>
        <span className="ssa-crumb-cur">«{search.name}»</span>
        <span className="ssa-crumb-region">{search.region}</span>
        <div style={{flex:1}}/>
        {(isScored || autoEval) && basis && (
          <button className="ssa-basis ssa-basis-inline" onClick={onEditBasis} title="Изменить основу оценки">
            <Icon name={basis.kind === 'vacancy' ? 'briefcase' : 'message'} size={12}/>
            <span className="ssa-basis-text">
              <span className="ssa-basis-k">{basis.kind === 'vacancy' ? 'оценка против вакансии' : 'оценка по промту'}</span>
              <span className="ssa-basis-v">{saBasisLabel(basis)}</span>
            </span>
            <Icon name="open" size={11} className="ssa-basis-edit"/>
          </button>
        )}
      </div>

      <div className="ssa-cands-bar">
        <div className="ssa-seg">
          <button className={`ssa-seg-btn ${!onlyNew ? 'active' : ''}`} onClick={() => setOnlyNew(false)}>
            Все <span className="t-mono">{ssFmt(search.total)}</span>
          </button>
          <button className={`ssa-seg-btn new ${onlyNew ? 'active' : ''}`} onClick={() => setOnlyNew(true)} disabled={search.newCount === 0}>
            <span className="ssa-new-dot"/> Новые <span className="t-mono">{search.newCount}</span>
          </button>
        </div>

        <div style={{flex:1}}/>

        <label className="ssa-sort">
          <span>Сортировка</span>
          <select value={sort} onChange={e => setSort(e.target.value)}>
            <option value="updated">по обновлению</option>
            <option value="score" disabled={!isScored}>по AI-баллу</option>
          </select>
        </label>

        <div className="ssa-ae-inline">
          <span className="ssa-ae-inline-label">Авто-оценка новых</span>
          <button className={`ss-switch ${autoEval ? 'on' : ''}`} onClick={onToggleAutoEval} aria-label="Авто-оценка"/>
        </div>

        {!isScored && (
          <button className="btn btn-primary btn-sm ssa-eval-btn" onClick={onRunScoring} disabled={scoring}>
            {scoring ? <><span className="ssa-spin dark"/> Оцениваю…</> : <><Icon name="sparkle" size={14}/> Оценить {onlyNew ? search.newCount : ssFmt(search.total)}</>}
          </button>
        )}
      </div>

      {onlyNew && (
        <div className="ssa-newnote">
          <Icon name="alert" size={14}/>
          Показаны только новые с момента последнего просмотра. Открытие списка сбрасывает счётчик «+{search.newCount}» на hh.
        </div>
      )}

      <div className="ssa-rows">
        {pageItems.map(c => {
          const t = taken[c.id];
          return (
            <div key={c.id} className={`ssa-row ${c.isNew ? 'is-new' : ''} ${t?.dest ? 'is-taken' : ''}`} onClick={() => onOpenCand(c.id)}>
              <div className="ssa-row-av">
                <SSAAnonAvatar c={c} revealed={!!t?.contact}/>
                {c.isNew && <span className="ssa-row-newpip" title="Новое резюме"/>}
              </div>
              <div className="ssa-row-main">
                <div className="ssa-row-title-line">
                  <span className="ssa-row-title">{c.title}</span>
                  <span className="ssa-row-meta">{c.age} {saPlural(c.age,'год','года','лет')} · {c.city}</span>
                  {c.anonymous && <span className="ssa-anon-tag" title="Анонимное резюме (скрытые поля)"><Icon name="lock" size={10}/> аноним</span>}
                </div>
                <div className="ssa-row-job">{c.lastPos} · {c.lastCo} · опыт {c.expStr}</div>
                <div className="ssa-row-chips">
                  {c.skills.slice(0, 5).map((s, i) => <span key={i} className="ssa-skill">{s}</span>)}
                  {c.skills.length > 5 && <span className="ssa-skill more">+{c.skills.length - 5}</span>}
                </div>
              </div>
              <div className="ssa-row-right">
                <div className="ssa-row-salary t-mono">{c.salary ? `${ssFmt(c.salary)} ₽` : <span className="ssa-nosal">з/п не указана</span>}</div>
                <div className="ssa-row-upd">обновлено {c.updated}</div>
              </div>
              <div className="ssa-row-score">
                {isScored
                  ? <ScoreBadge score={c.baseScore} size="lg" tip="AI-балл против вакансии"/>
                  : <span className="ssa-score-empty" title="Не оценён">—</span>}
              </div>
              {t?.dest && <span className="ssa-row-taken-flag"><Icon name="check" size={11}/> {t.dest === 'pool' ? 'в пуле' : 'в воронке'}</span>}
            </div>
          );
        })}
      </div>

      {pageItems.length === 0 ? (
        <div className="ssa-rows-empty">Здесь пока пусто.</div>
      ) : (
        <div className="ssa-pager">
          <div className="ssa-pager-info">
            Показано <b>{rangeStart}–{rangeEnd}</b> из <b className="t-mono">{onlyNew ? search.newCount : ssFmt(search.total)}</b>
          </div>
          {pageCount > 1 && (
            <div className="ssa-pager-ctrls">
              <button className="ssa-pg-nav" disabled={curPage <= 1} onClick={() => goPage(curPage - 1)} aria-label="Назад">
                <Icon name="chevL" size={15}/>
              </button>
              {saPager(curPage, pageCount).map((p, i) => p === '…'
                ? <span key={'e' + i} className="ssa-pg-ell">…</span>
                : <button key={p} className={`ssa-pg ${p === curPage ? 'active' : ''}`} onClick={() => goPage(p)}>{p}</button>)}
              <button className="ssa-pg-nav" disabled={curPage >= pageCount} onClick={() => goPage(curPage + 1)} aria-label="Вперёд">
                <Icon name="chevR" size={15}/>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Анонимный аватар (закрытое резюме) / раскрытый после списания контакта
function SSAAnonAvatar({ c, revealed, size = 'md' }) {
  if (revealed) return <Avatar name={c.fullName} size={size}/>;
  const px = { sm: 28, md: 38, lg: 44 }[size] || 38;
  return (
    <div className="ssa-anon-av" style={{ width: px, height: px }} title="Контакты закрыты">
      <Icon name="user" size={px * 0.5}/>
    </div>
  );
}

// ====== Нижняя карточка кандидата — 1:1 как карточка соискателя в «Кандидатах» ======
// Контейнер выезжает снизу; внутри — существующий .cand-detail (те же классы/верстка).
function SSAutoSheet({ c, search, isScored, scoring, basis, taken, pool, onRunScoring, onTakeContact, onRoute, onClose }) {
  const [tab, setTab] = useStateSA('resume');
  const [moveOpen, setMoveOpen] = useStateSA(false);
  const [shown, setShown] = useStateSA(false);
  const VACS = (typeof VACANCIES !== 'undefined' ? VACANCIES : []);
  useEffectSA(() => {
    const t = setTimeout(() => setShown(true), 16);
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => { clearTimeout(t); window.removeEventListener('keydown', onKey); };
  }, []);
  if (!c) return null;
  const hasContact = !!taken?.contact;
  const routed = taken?.dest;
  const first = c.fullName.split(' ')[0], last = c.fullName.split(' ')[1] || '';
  const email = `${first}.${last}`.toLowerCase().replace(/[^a-zа-я.]/gi, '') + '@mail.ru';

  return (
    <>
      <div className={`ssa-sheet-backdrop ${shown ? 'is-open' : ''}`} onClick={onClose}/>
      <div className={`ssa-sheet ${shown ? 'is-open' : ''}`} role="dialog" aria-label={`Резюме · ${c.title}`}>
        <div className="ssa-sheet-grip"/>
        <div className="cand-detail ssa-cd">
          {/* Тулбар — действия Автоподбора, кнопки из общей системы */}
          <div className="cd-toolbar">
            {!hasContact && (
              <button className="btn btn-primary btn-sm" onClick={() => onTakeContact(c)} title="Списать 1 контакт из пула hh">
                <Icon name="open" size={14}/> Забрать контакт
              </button>
            )}
            <div className="cd-move-wrap">
              <button className={`btn btn-sm ${routed ? 'btn-secondary' : 'btn-success'}`} onClick={() => setMoveOpen(o => !o)}>
                <Icon name="arrowRight" size={14}/> {routed ? (routed === 'pool' ? 'В пуле' : 'В воронке') : 'Перевести'} <Icon name="chevD" size={12}/>
              </button>
              {moveOpen && (
                <>
                  <div className="cd-pop-backdrop" onClick={() => setMoveOpen(false)}/>
                  <div className="cd-move-pop" role="menu">
                    <div className="cd-pop-head">Куда перенести кандидата?</div>
                    <button className="cd-pop-item" onClick={() => { onRoute(c, 'pool', 'в пул кандидатов'); setMoveOpen(false); }}>
                      <span className="cd-pop-num"><Icon name="users" size={14}/></span>
                      <span className="cd-pop-label">В пул кандидатов</span>
                      {routed === 'pool' && <span className="cd-pop-tag">сейчас</span>}
                    </button>
                    <div className="cd-pop-group">В воронку вакансии</div>
                    {VACS.map(v => (
                      <button key={v.id} className="cd-pop-item" onClick={() => { onRoute(c, v.id, `в воронку «${v.name}»`); setMoveOpen(false); }}>
                        <span className="cd-pop-num t-mono">{v.count}</span>
                        <span className="cd-pop-label">{v.name}</span>
                        {routed === v.id && <span className="cd-pop-tag">сейчас</span>}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
            {hasContact && (
              <span className="cd-pdn-confirmed" title="Контакт списан из пула hh">
                Контакт открыт
                <svg width="13" height="13" viewBox="0 0 12 12" fill="none">
                  <path d="M2.5 6.2l2.4 2.4L9.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </span>
            )}
            <div style={{flex:1}}/>
            <button className="icon-btn" onClick={onClose} title="Закрыть (Esc)"><Icon name="x" size={18}/></button>
          </div>

          {/* Шапка — те же классы, что и в карточке соискателя */}
          <div className="cd-header">
            <div className="cd-context">
              <span className="src-pill src-hh">hh · Автопоиск «{search.name}»</span>
              <span>обновлено {c.updated}</span>
              <span className="sep">·</span>
              <span>{search.region}</span>
            </div>

            <div className="cd-h-main">
              <div className="cd-h-left">
                <div className="cd-name-row">
                  <h1 className="cd-name">{hasContact ? c.fullName : c.title}</h1>
                  {isScored && <ScoreBadge score={c.baseScore} size="lg"/>}
                  {c.isNew && <span className="ssa-newpill"><span className="ssa-new-dot"/> новое</span>}
                </div>
                <div className="cd-exp-line">
                  {hasContact && <>{c.title} · </>}{c.lastPos} · {c.lastCo} · опыт {c.expStr}
                </div>
                <div className="cd-salary-line">
                  <span className="cd-salary t-mono">{c.salary ? `${fmtSalary(c.salary)} ₽` : '—'}</span>
                  <span className="cd-salary-label">{c.salary ? 'ожидания' : 'з/п не указана'}</span>
                </div>
                <div className="cd-tags-row">
                  {c.skills.slice(0, 4).map((s, i) => <span key={i} className="skill-chip skill-chip-sm">{s}</span>)}
                </div>
              </div>

              {hasContact ? (
                <div className="cd-contact-box">
                  <div className="cb-row">
                    <span className="cb-label">Телефон:</span>
                    <span className="t-mono cb-strong">{c.realPhone}</span>
                    <div className="mess-icons-row"><MessIconRound kind="tg"/><MessIconRound kind="wa"/></div>
                  </div>
                  <div className="cb-row"><span className="cb-label">Город:</span><span>{c.city}</span></div>
                  <div className="cb-row"><span className="cb-label">E-mail:</span><span>{c.anonymous ? '—' : email}</span></div>
                </div>
              ) : (
                <div className="cd-contact-box ssa-cb-locked">
                  <div className="cb-row"><span className="cb-label">Контакты:</span><span className="ssa-locked"><Icon name="lock" size={12}/> закрыты на hh</span></div>
                  <div className="cb-row"><span className="cb-label">Телефон:</span><span className="ssa-mask">+7 ••• ••• •• ••</span></div>
                  <div className="cb-row"><span className="cb-label">Город:</span><span>{c.city}</span></div>
                  <div className="ssa-cb-note">
                    Откроется после списания 1 контакта из пула (осталось <span className="t-mono">{pool}</span>).
                    {c.anonymous && <span className="ssa-cb-warn"> Резюме анонимное — ФИО и телефон могут не прийти.</span>}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Табы — те же классы cc-tabs/cc-tab */}
          <div className="cc-tabs">
            <button className={`cc-tab ${tab === 'resume' ? 'active' : ''}`} onClick={() => setTab('resume')}>Резюме</button>
            <button className={`cc-tab ${tab === 'ai' ? 'active' : ''}`} onClick={() => setTab('ai')}>Оценка AI</button>
          </div>

          <div className="cc-content">
            {tab === 'resume'
              ? <SSAutoResume c={c} isScored={isScored} basis={basis} onOpenAI={() => setTab('ai')}/>
              : <SSAutoAI c={c} isScored={isScored} scoring={scoring} basis={basis} onRunScoring={onRunScoring}/>}
          </div>
        </div>
      </div>
    </>
  );
}

// Мини-карточка вердикта Глафиры — те же классы filo-card, что и в карточке соискателя
function SSAVerdict({ c, basis, screening }) {
  const short = saScoreVerdict(c.baseScore);
  const bl = saBasisLabel(basis);
  return (
    <div className={`filo-card filo-card-compact${screening ? '' : ' filo-card-mini'}`}>
      <div className="filo-head">
        <div className="filo-ai-mark filo-glafira" aria-label="Глафира"><span className="glafira-emoji">👩🏻</span></div>
        <div className="filo-head-body">
          <div className="filo-title-row"><span className="filo-title">Оценка от Глафиры</span></div>
          <div className="filo-sub">{short}</div>
          {screening && (
            <div className="filo-screening">
              {bl ? <>Сравнила резюме {basis.kind === 'vacancy' ? <>с вакансией <b>«{bl}»</b></> : <>с запросом <b>«{bl}»</b></>}. </> : null}
              Совпадение с требованиями — {c.baseScore}%. Опыт {c.expStr}{c.salary ? `, ожидания ${fmtSalary(c.salary)} ₽` : ', зарплата не указана'}.
            </div>
          )}
        </div>
        <ScoreBadge score={c.baseScore} size={screening ? 'xl' : 'lg'}/>
      </div>
    </div>
  );
}

// Резюме — те же классы (resume-single, cc-sec-title, job, skill-chip, extra-grid)
function SSAutoResume({ c, isScored, basis, onOpenAI }) {
  return (
    <div className="resume-single">
      {isScored
        ? <SSAVerdict c={c} basis={basis}/>
        : <div className="ssa-unscored-note"><Icon name="sparkle" size={15}/> Резюме ещё не оценено — откройте вкладку «Оценка AI», чтобы сравнить с вакансией или промтом.</div>}

      <h3 className="cc-sec-title">Опыт работы</h3>
      {c.jobs.map((j, i) => (
        <div className="job" key={i}>
          <div className="job-when">
            <div className="job-period">{j.period}</div>
            <div className="job-dur">{j.dur}</div>
          </div>
          <div className="job-main">
            <div className="job-co">{j.co}</div>
            <div className="job-title">{j.pos}</div>
            <ul className="job-bullets">
              {j.bullets.map((b, k) => <li key={k}>{b}</li>)}
            </ul>
          </div>
        </div>
      ))}

      <h3 className="cc-sec-title">Навыки</h3>
      <div className="skill-row">
        {c.skills.map((s, i) => <span key={i} className="skill-chip">{s}</span>)}
      </div>

      <h3 className="cc-sec-title">Образование</h3>
      <div className="job">
        <div className="job-when"></div>
        <div className="job-main">
          <div className="job-co">{c.edu.split(' · ')[0]}</div>
          <div className="job-title">{c.edu.split(' · ')[1] || ''} · {c.city}</div>
        </div>
      </div>

      <h3 className="cc-sec-title">Дополнительно</h3>
      <div className="extra-grid">
        <div><span className="extra-k">Языки:</span> {c.langs}</div>
        <div><span className="extra-k">Переезд:</span> {c.relocate ? 'готов' : 'не готов'}</div>
        <div><span className="extra-k">Город:</span> {c.city}</div>
        <div><span className="extra-k">Источник:</span> hh.ru · автопоиск</div>
      </div>
    </div>
  );
}

// Оценка AI — те же классы (ai-single, msg ai-msg, crit-list)
function SSAutoAI({ c, isScored, scoring, basis, onRunScoring }) {
  if (!isScored) {
    return (
      <div className="ai-single">
        <div className="ssa-ai-empty">
          <div className="ssa-ai-empty-ic"><Icon name="sparkle" size={26}/></div>
          <h3>Резюме ещё не оценено</h3>
          <p>Оценка относительна: Глафира сравнивает резюме с конкретной вакансией или с описанием идеального кандидата. Выберите основу — и она выставит балл.</p>
          <button className="btn btn-primary btn-sm" onClick={onRunScoring} disabled={scoring}>
            {scoring ? <><span className="ssa-spin dark"/> Оцениваю…</> : <><Icon name="sparkle" size={14}/> Оценить относительно…</>}
          </button>
        </div>
      </div>
    );
  }
  const inRegion = ['Новосибирск','Бердск','Кольцово','Академгородок'].some(x => c.city.includes(x));
  const pluses = [
    `Релевантная позиция: ${c.lastPos}`,
    `Опыт ${c.expStr} в профильных компаниях (${c.jobs.map(j => j.co).slice(0, 2).join(', ')})`,
    `Ключевые навыки совпадают: ${c.skills.slice(0, 3).join(', ')}`,
    inRegion ? `Проживает в нужном регионе (${c.city})` : `Город: ${c.city}`,
  ];
  const minuses = [
    c.salary ? `Зарплатные ожидания ${fmtSalary(c.salary)} ₽ — проверить вилку` : 'Зарплатные ожидания не указаны — уточнить',
    c.anonymous ? 'Резюме анонимное — контакты могут не открыться' : 'Не хватает части ключевых навыков из требований',
    'Нет данных о ключевых достижениях в цифрах',
  ];
  const questions = [
    `${c.fullName.split(' ')[0]}, какие зарплатные ожидания и готовы ли рассмотреть оффер сейчас?`,
    `Расскажите про самый показательный проект с ${c.skills[0]} — какая была роль и результат?`,
    'Что ищете на новом месте и насколько срочно готовы выйти?',
  ];
  const criteria = [
    { label:'Релевантность позиции', pts: Math.min(20, Math.round(c.baseScore / 5)), max:20, comment:`Последняя позиция — ${c.lastPos}; профиль совпадает с основой оценки.` },
    { label:'Опыт и стаж',           pts: Math.min(20, c.totalYears + 6),            max:20, comment:`Суммарный опыт ${c.expStr}, последнее место — ${c.lastCo}.` },
    { label:'Совпадение навыков',    pts: Math.min(25, c.skills.length * 4),          max:25, comment:`Совпали: ${c.skills.slice(0, 4).join(', ')}.` },
    { label:'Регион / переезд',      pts: inRegion ? 15 : (c.relocate ? 12 : 8),      max:15, comment: inRegion ? `Проживает в ${c.city}.` : (c.relocate ? 'Готов к переезду.' : 'Другой регион, переезд не указан.') },
    { label:'Зарплатные ожидания',   pts: c.salary ? 14 : 6,                          max:20, comment: c.salary ? `Указаны: ${fmtSalary(c.salary)} ₽ — в рамках вилки.` : 'Не указаны — требуется уточнение.' },
  ];
  const totalPts = criteria.reduce((s, x) => s + x.pts, 0);
  const totalMax = criteria.reduce((s, x) => s + x.max, 0);
  return (
    <div className="ai-single">
      <SSAVerdict c={c} basis={basis} screening/>

      <h3 className="cc-sec-title">Анализ AI</h3>
      <div className="msg ai-msg ai-msg-good" style={{maxWidth:'100%'}}>
        <div className="ai-name ai-name-good"><span className="cc-sec-emoji">✅</span> Сильные стороны</div>
        <ul className="ai-msg-list">{pluses.map((p, i) => <li key={i}>{p}</li>)}</ul>
      </div>
      <div className="msg ai-msg ai-msg-warn" style={{maxWidth:'100%', marginTop:8}}>
        <div className="ai-name ai-name-warn"><span className="cc-sec-emoji">⚠️</span> Слабые стороны</div>
        <ul className="ai-msg-list">{minuses.map((m, i) => <li key={i}>{m}</li>)}</ul>
      </div>
      <div className="msg ai-msg ai-msg-q" style={{maxWidth:'100%', marginTop:8}}>
        <div className="ai-name ai-name-q"><span className="cc-sec-emoji">💬</span> Вопросы для первого контакта</div>
        <ol className="ai-msg-list ai-msg-list-num">{questions.map((q, i) => <li key={i}>{q}</li>)}</ol>
      </div>

      <h3 className="cc-sec-title">
        Разбор по критериям
        <span className="crit-total"><span className="t-mono">{totalPts}</span> / <span className="t-mono">{totalMax}</span></span>
      </h3>
      <div className="crit-list">
        {criteria.map((cr, i) => {
          const pct = cr.max ? Math.round((cr.pts / cr.max) * 100) : 0;
          const color = pct >= 80 ? 'green' : pct >= 40 ? 'yellow' : 'red';
          return (
            <div key={i} className={`crit-row crit-${color}`}>
              <div className="crit-head">
                <span className="crit-label">{cr.label}</span>
                <span className="crit-pts t-mono">{cr.pts}<span className="crit-pts-max"> / {cr.max}</span></span>
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

// ====== Диалог: относительно чего оценивать (вакансия или промт) ======
function SSAutoBasisDialog({ search, mode, current, onCancel, onConfirm }) {
  const VACS = (typeof VACANCIES !== 'undefined' ? VACANCIES : []);
  const [kind, setKind] = useStateSA(current?.kind || 'vacancy');
  const [vacId, setVacId] = useStateSA(current?.kind === 'vacancy' ? current.vacId : null);
  const [text, setText] = useStateSA(current?.kind === 'prompt' ? current.text : '');
  useEffectSA(() => {
    const onKey = (e) => { if (e.key === 'Escape') onCancel(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const canConfirm = kind === 'vacancy' ? !!vacId : text.trim().length > 2;
  function confirm() {
    if (!canConfirm) return;
    if (kind === 'vacancy') {
      const v = VACS.find(x => x.id === vacId);
      onConfirm({ kind:'vacancy', vacId, label: v ? v.name : 'вакансия' });
    } else {
      onConfirm({ kind:'prompt', text: text.trim(), label: text.trim() });
    }
  }
  return (
    <>
      <div className="ssa-modal-backdrop" onClick={onCancel}/>
      <div className="ssa-modal" role="dialog" aria-label="Основа оценки">
        <div className="ssa-modal-head">
          <div>
            <div className="ssa-modal-title">Относительно чего оценивать?</div>
            <div className="ssa-modal-sub">Оценка кандидата — относительная. Глафира сравнит резюме из автопоиска «{search.name}» с вашей вакансией или с описанием идеального кандидата.</div>
          </div>
          <button className="icon-btn" onClick={onCancel} title="Закрыть"><Icon name="x" size={18}/></button>
        </div>

        <div className="ssa-modal-body">
          {/* Метод 1 — вакансия */}
          <div className={`ssb-method ${kind === 'vacancy' ? 'is-active' : 'is-dim'}`}>
            <div className="ssb-method-head ssb-method-toggle" onClick={() => setKind('vacancy')}>
              <span className="ssb-radio" data-on={kind === 'vacancy'}/>
              <div className="ssb-method-titles">
                <div className="ssb-method-title">По открытой вакансии</div>
                <div className="ssb-method-desc">Глафира возьмёт требования вакансии как эталон.</div>
              </div>
            </div>
            {kind === 'vacancy' && (
              <div className="ssa-vac-list">
                {VACS.map(v => (
                  <button key={v.id} className={`ssa-vac-opt ${vacId === v.id ? 'sel' : ''}`} onClick={() => setVacId(v.id)}>
                    <Icon name="briefcase" size={15} className="ssa-vac-ic"/>
                    <span className="ssa-vac-name">{v.name}</span>
                    <span className="ssa-vac-count t-mono">{v.count}</span>
                    {vacId === v.id && <Icon name="check" size={15} className="ssa-vac-check"/>}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="ssb-or"><span>или</span></div>

          {/* Метод 2 — промт */}
          <div className={`ssb-method ${kind === 'prompt' ? 'is-active' : 'is-dim'}`}>
            <div className="ssb-method-head ssb-method-toggle" onClick={() => setKind('prompt')}>
              <span className="ssb-radio" data-on={kind === 'prompt'}/>
              <div className="ssb-method-titles">
                <div className="ssb-method-title">По описанию (промт)</div>
                <div className="ssb-method-desc">Опишите словами, кто вам нужен — это станет эталоном оценки.</div>
              </div>
            </div>
            {kind === 'prompt' && (
              <textarea
                className="ssb-textarea ssa-basis-textarea"
                placeholder="Например: DevOps с Kubernetes и CI/CD, от 3 лет, опыт on-call, готов выйти быстро…"
                value={text}
                rows={3}
                onChange={e => setText(e.target.value)}
                autoFocus
              />
            )}
          </div>
        </div>

        <div className="ssa-modal-foot">
          <button className="btn btn-secondary" onClick={onCancel}>Отмена</button>
          <button className="btn btn-primary" onClick={confirm} disabled={!canConfirm}>
            <Icon name="sparkle" size={15}/> {mode === 'enable' ? 'Включить авто-оценку' : 'Оценить'}
          </button>
        </div>
      </div>
    </>
  );
}

Object.assign(window, { SSAutoFlow, SA_SEARCHES });
