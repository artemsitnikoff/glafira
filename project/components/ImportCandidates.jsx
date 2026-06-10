// ImportCandidates — пошаговый импорт кандидатов в общую базу
// Открывается по кнопке «Импорт кандидатов» на экране «Кандидаты» (общая база).
// Развилка источника: Файл (Excel) или Поток (по API-токену).
//   Файл:  Источник → Загрузка → Колонки → Превью → Готово
//   Поток: Источник → Токен → Превью → Готово
const { useState: useStateIM, useEffect: useEffectIM, useRef: useRefIM, useMemo: useMemoIM } = React;

// ====== Потоки шагов по источнику (для индикатора и навигации) ======
const IMP_FLOWS = {
  file:  ['upload', 'columns', 'preview', 'result'],
  potok: ['token', 'preview', 'result'],
};
const IMP_PHASE_LABEL = { upload:'Загрузка', columns:'Колонки', token:'Токен Потока', preview:'Превью', result:'Готово' };

// ====== Наши поля кандидата (куда маппим колонки файла) ======
const IMP_FIELDS = [
  { id: 'name',       label: 'Имя',            req: true },
  { id: 'phone',      label: 'Телефон',        contact: true },
  { id: 'email',      label: 'Email',          contact: true },
  { id: 'city',       label: 'Город' },
  { id: 'age',        label: 'Возраст' },
  { id: 'salary',     label: 'Зарплата' },
  { id: 'source',     label: 'Источник' },
  { id: 'position',   label: 'Должность' },
  { id: 'company',    label: 'Компания' },
  { id: 'experience', label: 'Опыт' },
  { id: 'comment',    label: 'Комментарий' },
  { id: 'resume',     label: 'Резюме-ссылка' },
];
const FIELD_LABEL = IMP_FIELDS.reduce((m, f) => (m[f.id] = f.label, m), { __skip: 'Не импортировать' });

// ====== Тестовый файл — выгрузка из Потока (potok.io) ======
// Колонки названы «по-потоковски», часть распознаётся автоматически, часть — нет.
const IMP_FILE = {
  name: 'Кандидаты_Поток_2026-06-09.xlsx',
  rows: 5240,
  cols: [
    { id:'c1',  name:'ФИО Кандидата',        samples:['Смирнов Алексей Петрович','Иванова Мария Сергеевна','Кузнецов Д. В.'], auto:'name' },
    { id:'c2',  name:'Моб. телефон',         samples:['+7 916 442-09-13','8 (985) 220-18-04','+7 903 117-44-22'],            auto:'phone' },
    { id:'c3',  name:'E-mail',               samples:['a.smirnov@mail.ru','maria.iv@gmail.com','—'],                          auto:'email' },
    { id:'c4',  name:'Город',                samples:['Москва','Санкт-Петербург','Казань'],                                   auto:'city' },
    { id:'c5',  name:'Возраст',              samples:['28','34','26'],                                                        auto:'age' },
    { id:'c6',  name:'Зарплатные ожидания',  samples:['250 000 ₽','от 300000','180 000'],                                     auto:'salary' },
    { id:'c7',  name:'Источник',             samples:['hh.ru','Авито','Telegram'],                                            auto:'source' },
    { id:'c9',  name:'Желаемая должность',   samples:['Frontend-разработчик','Менеджер по продажам','—'],                     auto:'position' },
    { id:'c10', name:'Комментарий рекрутёра',samples:['Перезвонить после 18:00','Сильный кандидат','—'],                      auto:'comment' },
    { id:'c11', name:'Резюме (ссылка)',      samples:['potok.io/r/88421','potok.io/r/88512','—'],                            auto:'resume', resumeNote:true },
    { id:'c12', name:'ID в Потоке',          samples:['88421','88512','88533'],                                               auto:null },
    { id:'c13', name:'Метка',                samples:['Целевой','Холодный','Резерв'],                                         auto:null },
  ],
};

// ====== Сводка по импорту ======
const IMP_TOTAL  = IMP_FILE.rows;       // 5240
const IMP_DUP    = 198;
const IMP_ERR    = 55;
const IMP_NEW    = IMP_TOTAL - IMP_DUP - IMP_ERR; // 4987

// ====== Строки превью (первые ~22 из файла) ======
function impRow(name, phone, email, city, src, stage, flags = {}) {
  return { name, phone, email, city, src, stage, ...flags };
}
const IMP_PREVIEW = [
  impRow('Смирнов Алексей Петрович','+7 916 442-09-13','a.smirnov@mail.ru','Москва','hh','recruiter', { resumeNote:true }),
  impRow('Иванова Мария Сергеевна','+7 903 117-44-22','maria.iv@gmail.com','СПб','avito','response'),
  impRow('Кузнецов Дмитрий Викторович','+7 985 220-18-04','d.kuznetsov@mail.ru','Казань','hh','offer', { resumeNote:true }),
  impRow('Лебедева Анна Игоревна','+7 911 776-02-99','—','СПб','tg','selected'),
  impRow('Морозов Андрей Сергеевич','+7 910 552-23-44','a.morozov@mail.ru','Москва','hh','interview', { dup:true }),
  impRow('Соколова Екатерина','+7 916 401-22-08','kate.s@gmail.com','Москва','avito','response'),
  impRow('—','+7 999 000-11-22','no.name@mail.ru','Москва','hh','response', { err:'нет имени' }),
  impRow('Берг Юлия Олеговна','+7 916 808-12-77','y.berg@mail.ru','Москва','hh','offer', { resumeNote:true }),
  impRow('Талалаев Олег','+7 985 220-18-04','o.talalaev@mail.ru','Москва','hh','interview', { dup:true }),
  impRow('Романова Алёна','—','—','Москва','avito','response', { err:'нет контакта' }),
  impRow('Шилов Роман Андреевич','+7 903 555-09-21','r.shilov@mail.ru','СПб','tg','selected'),
  impRow('Климова Дарья','+7 916 401-22-08','d.klimova@mail.ru','Москва','tg','response'),
  impRow('Петренко Иван','+7 903 117-44-22','i.petrenko@mail.ru','Москва','hh','recruiter', { dup:true }),
  impRow('Хамбабян Алекс','+7 903 412-66-09','a.h@mail.ru','Москва','hh','interview', { resumeNote:true }),
  impRow('Лазарев Виктор','+7 901 233-44-91','v.lazarev@mail.ru','Москва','hh','recruiter'),
  impRow('Чуликов Артём','+7 999 466-20-16','a.chulikov@mail.ru','Новосибирск','hh','response'),
  impRow('Корнеева Мария','+7 916 442-09-13','m.korneeva@mail.ru','Москва','tg','selected'),
  impRow('Зайцев Никита','+7 916 077-13-88','n.zaitsev@mail.ru','Москва','hh','offer', { resumeNote:true }),
  impRow('Лер Артём','+7 926 504-90-15','a.ler@mail.ru','СПб','tg','recruiter'),
  impRow('Кокурин Максим','+7 903 100-22-33','m.kokurin@mail.ru','Москва','hh','interview'),
  impRow('—','—','—','—','hh','response', { err:'нет имени и контакта' }),
  impRow('Громова Светлана','+7 916 222-33-44','s.gromova@mail.ru','СПб','avito','response'),
];

const SRC_LABEL = { hh:'hh.ru', tg:'Telegram', avito:'Авито' };

// ====== Резюме-профили, «забранные из Потока» (для превью карточки) ======
// Каждой строке превью присваивается архетип по индексу — биография, опыт, навыки.
const IMP_ARCH = {
  fe: {
    title:'Frontend-разработчик', exp:'5 лет опыта',
    bio:'Фронтенд-разработчик с опытом в продуктовых командах. React и TypeScript, проектирование компонентных систем, оптимизация производительности интерфейсов.',
    jobs:[
      { title:'Senior Frontend-разработчик', co:'Яндекс', period:'март 2022 — наст. время', desc:'Развитие интерфейсов поисковых сервисов. Перевёл легаси на TypeScript, внедрил дизайн-систему, ускорил загрузку на 35%.' },
      { title:'Frontend-разработчик', co:'Ozon', period:'июнь 2019 — март 2022', desc:'Личный кабинет продавца: React, Redux, интеграция REST и GraphQL.' },
      { title:'Junior Frontend', co:'Студия Лебедева', period:'2017 — 2019', desc:'Вёрстка лендингов и промо-страниц, поддержка корпоративных сайтов.' },
    ],
    skills:['React','TypeScript','Redux','Next.js','REST API','CI/CD','Jest'],
    edu:{ school:'МГТУ им. Баумана', spec:'Программная инженерия', years:'2013 — 2019' },
    lang:'Русский · English B2',
  },
  sales: {
    title:'Менеджер по продажам B2B', exp:'6 лет опыта',
    bio:'Менеджер по B2B-продажам. Развитие ключевых клиентов, переговоры на уровне C-level, выстраивание воронки от лида до контракта.',
    jobs:[
      { title:'Руководитель отдела продаж', co:'Сбер · Корпоративные клиенты', period:'январь 2021 — наст. время', desc:'Команда 6 человек, годовой план 240 М ₽. Внедрил скоринг лидов, рост конверсии на 22%.' },
      { title:'Менеджер по продажам', co:'Тинькофф', period:'2018 — 2021', desc:'Привлечение корпоративных клиентов, сопровождение сделок, участие в тендерах.' },
    ],
    skills:['B2B-продажи','Переговоры','CRM','Тендеры','Аналитика воронки'],
    edu:{ school:'РЭУ им. Плеханова', spec:'Менеджмент', years:'2011 — 2017' },
    lang:'Русский · English B1',
  },
  pm: {
    title:'Менеджер проектов', exp:'4 года опыта',
    bio:'Проджект-менеджер в IT. Веду продуктовые команды, отвечаю за сроки и приоритеты, работаю с заказчиком и аналитикой.',
    jobs:[
      { title:'Project Manager', co:'VK', period:'2022 — наст. время', desc:'Запуск 3 продуктов с нуля, координация команд 8–12 человек, Agile/Scrum.' },
      { title:'Бизнес-аналитик', co:'X5 Tech', period:'2020 — 2022', desc:'Сбор требований, проектирование процессов в BPMN, постановка задач разработке.' },
    ],
    skills:['Управление проектами','Scrum','Jira','BPMN','Аналитика'],
    edu:{ school:'НИУ ВШЭ', spec:'Бизнес-информатика', years:'2014 — 2020' },
    lang:'Русский · English B2',
  },
  wh: {
    title:'Кладовщик', exp:'8 лет опыта',
    bio:'Кладовщик с опытом на складах FMCG и маркетплейсов. Приёмка, учёт, инвентаризация, работа с WMS, организация смены.',
    jobs:[
      { title:'Старший кладовщик', co:'Wildberries · склад', period:'2020 — наст. время', desc:'Организация смены 2/2, приёмка и отгрузка, контроль остатков в WMS.' },
      { title:'Кладовщик', co:'X5 Retail Group', period:'2016 — 2020', desc:'Складской учёт, комплектация заказов, работа с погрузчиком.' },
    ],
    skills:['Складской учёт','WMS','Инвентаризация','Погрузчик'],
    edu:{ school:'Колледж сервиса', spec:'Логистика', years:'2012 — 2015' },
    lang:'Русский',
  },
  hr: {
    title:'HR-дженералист', exp:'5 лет опыта',
    bio:'HR-специалист полного цикла: подбор, адаптация, кадровое администрирование, развитие бренда работодателя.',
    jobs:[
      { title:'HR-дженералист', co:'Логос', period:'2021 — наст. время', desc:'Массовый и точечный подбор, онбординг, ведение HR-метрик, опросы вовлечённости.' },
      { title:'Рекрутер', co:'Авито', period:'2019 — 2021', desc:'Закрытие вакансий IT и продаж, работа с hh и Авито, проведение интервью.' },
    ],
    skills:['Подбор','Адаптация','КДП','HR-аналитика','Интервью'],
    edu:{ school:'МГУ им. Ломоносова', spec:'Психология', years:'2013 — 2019' },
    lang:'Русский · English B2',
  },
};
const IMP_ARCH_KEYS = ['fe','sales','pm','wh','hr'];
function impArch(i) { return IMP_ARCH[IMP_ARCH_KEYS[i % IMP_ARCH_KEYS.length]]; }

// =====================================================================
// Главный компонент
// =====================================================================
function ImportCandidates({ onClose, onViewBase, preset }) {
  // step: 1..4 ; uploadState: idle | parsing | done | error ; runState: running | result
  const initial = presetToState(preset);
  const [phase, setPhase]             = useStateIM(initial.phase);    // source | upload | columns | token | preview | result
  const [source, setSource]           = useStateIM(initial.source);   // null | 'file' | 'potok'
  const [uploadState, setUploadState] = useStateIM(initial.uploadState);
  const [tokenVal, setTokenVal]       = useStateIM('');
  const [tokenState, setTokenState]   = useStateIM(initial.tokenState || 'idle'); // idle | connecting
  const [runState, setRunState]       = useStateIM(initial.runState);
  const [dragging, setDragging]       = useStateIM(false);
  const [dupMode, setDupMode]         = useStateIM('skip'); // skip | update
  const [imported, setImported]       = useStateIM(0);

  // Маппинг: id колонки файла -> id нашего поля (или '__skip')
  const [mapping, setMapping] = useStateIM(() => {
    const m = {};
    IMP_FILE.cols.forEach(c => { m[c.id] = initial.invalid && c.auto === 'name' ? '__skip' : (c.auto || '__skip'); });
    return m;
  });
  const [openDrop, setOpenDrop] = useStateIM(null); // id колонки с открытым дропдауном
  const fileInputRef = useRefIM(null);
  const runTimers = useRefIM([]);

  // ---- какие поля уже замаплены (для валидации обязательных) ----
  const mappedFields = useMemoIM(() => new Set(Object.values(mapping)), [mapping]);
  const hasName    = mappedFields.has('name');
  const hasContact = mappedFields.has('phone') || mappedFields.has('email');
  const requiredOk = hasName && hasContact;

  const importCount = dupMode === 'update' ? IMP_NEW + IMP_DUP : IMP_NEW;

  // ---- выбор источника (развилка) ----
  function pickSource(s) {
    setSource(s);
    setPhase(s === 'file' ? 'upload' : 'token');
  }
  // ---- подключение к Потоку по токену → сразу на превью ----
  function connectPotok() {
    setTokenState('connecting');
    setTimeout(() => { setTokenState('idle'); setPhase('preview'); }, 1400);
  }

  // ---- запуск парсинга файла ----
  function startParse(errored) {
    setUploadState('parsing');
    setTimeout(() => setUploadState(errored ? 'error' : 'done'), 1300);
  }

  // ---- запуск импорта (шаг 4) ----
  function runImport() {
    setPhase('result');
    setRunState('running');
    setImported(0);
    clearRunTimers();
    const target = importCount;
    const total = 2400; // ms
    const tick = 40;
    const steps = total / tick;
    let i = 0;
    const iv = setInterval(() => {
      i++;
      setImported(Math.min(target, Math.round((i / steps) * target)));
      if (i >= steps) { clearInterval(iv); setImported(target); setTimeout(() => setRunState('result'), 350); }
    }, tick);
    runTimers.current.push(() => clearInterval(iv));
  }
  function clearRunTimers() { runTimers.current.forEach(fn => fn()); runTimers.current = []; }
  useEffectIM(() => () => clearRunTimers(), []);

  // ---- DnD ----
  const onDrop = (e) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    const ok = !f || /\.(xlsx|xls)$/i.test(f.name);
    startParse(!ok);
  };

  return (
    <div className="imp-page" data-screen-label={`Candidates / Import / ${phase}`}>
      {/* ===== Верхняя панель + индикатор шагов ===== */}
      <div className="imp-top">
        <div className="imp-top-row">
          <div className="imp-top-title">
            <Icon name="download" size={17}/>
            <span>Импорт кандидатов</span>
          </div>
          <button className="icon-btn" onClick={onClose} title="Закрыть импорт"><Icon name="x" size={18}/></button>
        </div>
        <ImpStepper source={source} phase={phase}/>
      </div>

      {/* ===== Тело ===== */}
      <div className="imp-body">
        <div className="imp-inner">
          {phase === 'source' && (
            <ImpStepSource onPick={pickSource}/>
          )}
          {phase === 'upload' && (
            <ImpStepUpload
              uploadState={uploadState} dragging={dragging}
              setDragging={setDragging} onDrop={onDrop}
              fileInputRef={fileInputRef}
              onPick={() => startParse(false)}
              onPickError={() => startParse(true)}
              onRetry={() => setUploadState('idle')}
            />
          )}
          {phase === 'token' && (
            <ImpStepToken
              tokenVal={tokenVal} setTokenVal={setTokenVal}
              tokenState={tokenState} onConnect={connectPotok}
            />
          )}
          {phase === 'columns' && (
            <ImpStepColumns
              mapping={mapping} setMapping={setMapping}
              openDrop={openDrop} setOpenDrop={setOpenDrop}
              hasName={hasName} hasContact={hasContact}
            />
          )}
          {phase === 'preview' && (
            <ImpStepPreview dupMode={dupMode} setDupMode={setDupMode} source={source}/>
          )}
          {phase === 'result' && (
            <ImpStepResult
              runState={runState} imported={imported} importCount={importCount}
              dupMode={dupMode} source={source}
              onViewBase={onViewBase}
              onAgain={() => {
                clearRunTimers();
                setPhase('source'); setSource(null);
                setUploadState('idle'); setTokenState('idle'); setTokenVal('');
                setRunState('running'); setImported(0); setDupMode('skip');
              }}
            />
          )}
        </div>
      </div>

      {/* ===== Нижняя панель навигации ===== */}
      {phase === 'upload' && uploadState === 'done' && (
        <div className="imp-foot">
          <button className="btn btn-secondary" onClick={() => { setSource(null); setPhase('source'); setUploadState('idle'); }}>
            <Icon name="chevL" size={14}/> Назад
          </button>
          <div style={{flex:1}}/>
          <button className="btn btn-primary" onClick={() => setPhase('columns')}>
            Далее → Сопоставить колонки
          </button>
        </div>
      )}
      {phase === 'token' && tokenState === 'idle' && (
        <div className="imp-foot">
          <button className="btn btn-secondary" onClick={() => { setSource(null); setPhase('source'); }}>
            <Icon name="chevL" size={14}/> Назад
          </button>
          <div className="imp-foot-hint">
            {tokenVal.trim()
              ? <span className="imp-foot-ok"><Icon name="check" size={13}/> Токен введён</span>
              : <span className="imp-foot-warn"><Icon name="alert" size={13}/> Вставьте API-токен Потока</span>}
          </div>
          <button className="btn btn-primary" disabled={!tokenVal.trim()} onClick={() => tokenVal.trim() && connectPotok()}>
            Подключиться и загрузить →
          </button>
        </div>
      )}
      {phase === 'columns' && (
        <div className="imp-foot">
          <button className="btn btn-secondary" onClick={() => setPhase('upload')}>
            <Icon name="chevL" size={14}/> Назад
          </button>
          <div className="imp-foot-hint">
            {requiredOk
              ? <span className="imp-foot-ok"><Icon name="check" size={13}/> Обязательные поля сопоставлены</span>
              : <span className="imp-foot-warn"><Icon name="alert" size={13}/> Сопоставьте Имя и хотя бы один контакт</span>}
          </div>
          <button className="btn btn-primary" disabled={!requiredOk} onClick={() => requiredOk && setPhase('preview')}>
            Далее → Превью
          </button>
        </div>
      )}
      {phase === 'preview' && (
        <div className="imp-foot">
          <button className="btn btn-secondary" onClick={() => setPhase(source === 'potok' ? 'token' : 'columns')}>
            <Icon name="chevL" size={14}/> Назад{source === 'potok' ? '' : ' к колонкам'}
          </button>
          <div style={{flex:1}}/>
          <button className="btn btn-primary imp-btn-import" onClick={runImport}>
            <Icon name="check" size={15}/> Импортировать {fmtIM(importCount)}&nbsp;кандидатов
          </button>
        </div>
      )}
    </div>
  );
}

// ---- preset → начальное состояние (для ревью всех экранов из Tweaks) ----
function presetToState(preset) {
  const base = { phase:'source', source:null, uploadState:'idle', tokenState:'idle', runState:'running' };
  switch (preset) {
    case 'source':          return { ...base };
    case 'upload-error':    return { ...base, phase:'upload',  source:'file',  uploadState:'error' };
    case 'upload-done':     return { ...base, phase:'upload',  source:'file',  uploadState:'done' };
    case 'token':           return { ...base, phase:'token',   source:'potok' };
    case 'columns':         return { ...base, phase:'columns', source:'file',  uploadState:'done' };
    case 'columns-invalid': return { ...base, phase:'columns', source:'file',  uploadState:'done', invalid:true };
    case 'preview':         return { ...base, phase:'preview', source:'file',  uploadState:'done' };
    case 'preview-potok':   return { ...base, phase:'preview', source:'potok' };
    case 'importing':       return { ...base, phase:'result',  source:'file',  uploadState:'done' };
    case 'result':          return { ...base, phase:'result',  source:'file',  uploadState:'done', runState:'result' };
    default:                return { ...base };
  }
}

function fmtIM(n) { return n.toLocaleString('ru-RU').replace(/,/g, '\u202F'); }

// =====================================================================
// Индикатор шагов
// =====================================================================
function ImpStepper({ source, phase }) {
  const flow = source ? IMP_FLOWS[source] : IMP_FLOWS.file;
  const phases = ['source', ...flow];
  const labels = ['Источник', ...flow.map(p => IMP_PHASE_LABEL[p])];
  const activeIdx = phases.indexOf(phase);
  return (
    <div className="imp-stepper">
      {labels.map((s, i) => {
        const state = activeIdx > i ? 'done' : activeIdx === i ? 'current' : 'upcoming';
        return (
          <React.Fragment key={s}>
            <div className={`imp-step ${state}`}>
              <span className="imp-step-dot">{activeIdx > i ? <Icon name="check" size={14}/> : i + 1}</span>
              <span className="imp-step-label">{s}</span>
            </div>
            {i < labels.length - 1 && <span className={`imp-step-line ${activeIdx > i ? 'done' : ''}`}/>}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// =====================================================================
// ШАГ «Источник» — развилка: Файл или Поток
// =====================================================================
function ImpStepSource({ onPick }) {
  return (
    <div className="imp-source">
      <h2 className="imp-h2">Откуда импортировать кандидатов?</h2>
      <div className="imp-glafira-note">
        <span className="imp-em">💃</span>
        Выберите источник — Глафира заберёт кандидатов в общую базу.
      </div>
      <div className="imp-source-grid">
        <button className="imp-source-card" onClick={() => onPick('file')}>
          <div className="imp-source-ic file"><Icon name="download" size={26}/></div>
          <div className="imp-source-name">Импорт из файла</div>
          <div className="imp-source-desc">Excel-выгрузка из любой системы — hh, Хантфлоу, таблица. Сопоставите колонки вручную.</div>
          <div className="imp-source-tags">
            <span className="imp-source-tag">.xlsx</span>
            <span className="imp-source-tag">.xls</span>
            <span className="imp-source-tag">маппинг</span>
          </div>
          <span className="imp-source-go">Выбрать файл <Icon name="chevR" size={14}/></span>
        </button>
        <button className="imp-source-card" onClick={() => onPick('potok')}>
          <div className="imp-source-ic potok"><span className="imp-source-em">💃</span></div>
          <div className="imp-source-name">Импорт из Потока</div>
          <div className="imp-source-desc">Подключение по API-токену. Глафира сама заберёт кандидатов и резюме — без файла и маппинга.</div>
          <div className="imp-source-tags">
            <span className="imp-source-tag">API-токен</span>
            <span className="imp-source-tag">резюме</span>
            <span className="imp-source-tag">без маппинга</span>
          </div>
          <span className="imp-source-go">Подключить Поток <Icon name="chevR" size={14}/></span>
        </button>
        <div className="imp-source-card soon" aria-disabled="true">
          <span className="imp-source-soon">Скоро</span>
          <div className="imp-source-ic talantix">T</div>
          <div className="imp-source-name">Импорт из Talantix</div>
          <div className="imp-source-desc">Подключение по API-токену — как Поток. Глафира заберёт кандидатов и резюме без файла.</div>
          <div className="imp-source-tags">
            <span className="imp-source-tag">API-токен</span>
            <span className="imp-source-tag">резюме</span>
          </div>
          <span className="imp-source-go muted">В разработке</span>
        </div>
        <div className="imp-source-card soon" aria-disabled="true">
          <span className="imp-source-soon">Скоро</span>
          <div className="imp-source-ic huntflow"><Icon name="briefcase" size={24}/></div>
          <div className="imp-source-name">Импорт из Хантфлоу</div>
          <div className="imp-source-desc">Подключение по API-токену — как Поток. Глафира заберёт кандидатов и резюме без файла.</div>
          <div className="imp-source-tags">
            <span className="imp-source-tag">API-токен</span>
            <span className="imp-source-tag">резюме</span>
          </div>
          <span className="imp-source-go muted">В разработке</span>
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// ШАГ «Токен» — подключение к Потоку по API-токену (→ сразу превью)
// =====================================================================
function ImpStepToken({ tokenVal, setTokenVal, tokenState, onConnect }) {
  if (tokenState === 'connecting') {
    return (
      <div className="imp-parse">
        <div className="imp-parse-dancer">💃</div>
        <div className="imp-parse-text">Глафира подключается к Потоку<span className="cd-load-dots"></span></div>
        <div className="imp-parse-sub">Забираем кандидатов и резюме по API</div>
      </div>
    );
  }
  return (
    <div className="imp-token">
      <h2 className="imp-h2">Подключение к Потоку</h2>
      <div className="imp-glafira-note">
        <span className="imp-em">💃</span>
        Вставьте API-токен из Потока — Глафира подключится и сразу покажет превью кандидатов.
      </div>

      <div className="imp-token-card">
        <label className="imp-token-label" htmlFor="imp-token-input">API-токен Потока</label>
        <div className="imp-token-input-row">
          <Icon name="key" size={16}/>
          <input id="imp-token-input" className="imp-token-input" type="text"
                 placeholder="pk_live_••••••••••••••••••••••••" value={tokenVal}
                 onChange={e => setTokenVal(e.target.value)}
                 onKeyDown={e => { if (e.key === 'Enter' && tokenVal.trim()) onConnect(); }}/>
          <button className="imp-token-demo" onClick={() => setTokenVal('pk_live_9f2c8a4b7e1d6035a2c9')}>
            Вставить демо-токен
          </button>
        </div>
        <div className="imp-token-help">
          <Icon name="alert" size={13}/>
          Токен можно создать в Потоке: <b>Настройки → API → Создать токен</b>. Достаточно доступа на чтение кандидатов.
        </div>
      </div>

      <div className="imp-token-steps">
        <div className="imp-token-step"><span className="imp-token-step-n">1</span> Глафира подключится к вашему аккаунту Потока</div>
        <div className="imp-token-step"><span className="imp-token-step-n">2</span> Заберёт кандидатов и их резюме</div>
        <div className="imp-token-step"><span className="imp-token-step-n">3</span> Покажет превью перед заливкой в базу</div>
      </div>
    </div>
  );
}

// =====================================================================
// ШАГ 1 — Загрузка файла
// =====================================================================
function ImpStepUpload({ uploadState, dragging, setDragging, onDrop, fileInputRef, onPick, onPickError, onRetry, onNext }) {
  if (uploadState === 'parsing') {
    return (
      <div className="imp-parse">
        <div className="imp-parse-dancer">💃</div>
        <div className="imp-parse-text">Глафира читает файл<span className="cd-load-dots"></span></div>
        <div className="imp-parse-sub">Распознаём строки и колонки</div>
      </div>
    );
  }

  if (uploadState === 'error') {
    return (
      <div className="imp-stage-wrap">
        <div className="imp-drop imp-drop-error">
          <div className="imp-drop-ic imp-drop-ic-error"><Icon name="alert" size={30}/></div>
          <div className="imp-drop-title">Не удалось прочитать файл</div>
          <div className="imp-drop-sub">Поддерживаются только таблицы Excel — <b>.xlsx</b> и <b>.xls</b>. Проверьте формат и попробуйте ещё раз.</div>
          <div className="imp-drop-actions">
            <button className="btn btn-primary" onClick={onRetry}><Icon name="refresh" size={14}/> Выбрать другой файл</button>
          </div>
        </div>
      </div>
    );
  }

  if (uploadState === 'done') {
    return (
      <div className="imp-stage-wrap">
        {/* Карточка-итог файла */}
        <div className="imp-file-card">
          <div className="imp-file-head">
            <div className="imp-file-ic"><Icon name="download" size={20}/></div>
            <div className="imp-file-main">
              <div className="imp-file-name">{IMP_FILE.name}</div>
              <div className="imp-file-meta">
                Найдено <b className="t-mono">{fmtIM(IMP_FILE.rows)}</b> строк ·
                <b className="t-mono"> {IMP_FILE.cols.length}</b> колонок
              </div>
            </div>
            <span className="imp-file-ok"><Icon name="check" size={13}/> Файл прочитан</span>
            <button className="imp-file-replace" onClick={onRetry} title="Заменить файл"><Icon name="refresh" size={14}/></button>
          </div>
          <div className="imp-file-cols">
            <div className="imp-file-cols-label">Распознанные колонки</div>
            <div className="imp-chip-row">
              {IMP_FILE.cols.map(c => (
                <span key={c.id} className="imp-col-chip">{c.name}</span>
              ))}
            </div>
          </div>
        </div>
        <div className="imp-next-hint">
          Глафира уже сопоставила колонки автоматически — на следующем шаге проверьте и поправьте маппинг.
        </div>
      </div>
    );
  }

  // idle
  return (
    <div className="imp-stage-wrap">
      <div
        className={`imp-drop ${dragging ? 'dragging' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => onPick()}
      >
        <input ref={fileInputRef} type="file" accept=".xlsx,.xls" style={{display:'none'}}
               onChange={() => onPick()}/>
        <div className="imp-drop-ic"><Icon name="download" size={30}/></div>
        <div className="imp-drop-title">Перетащите Excel-файл с кандидатами<br/>или нажмите для выбора</div>
        <div className="imp-drop-sub">Поддерживаются выгрузки из hh, Потока, Хантфлоу и других систем · форматы <b>.xlsx</b>, <b>.xls</b></div>
        <button className="btn btn-primary imp-drop-btn" onClick={(e) => { e.stopPropagation(); onPick(); }}>
          <Icon name="download" size={14}/> Выбрать файл
        </button>
      </div>
      <button className="imp-demo-link" onClick={onPickError}>
        Что будет, если файл не Excel? →
      </button>
    </div>
  );
}

// =====================================================================
// ШАГ 2 — Сопоставление колонок (главный экран)
// =====================================================================
function ImpStepColumns({ mapping, setMapping, openDrop, setOpenDrop, hasName, hasContact }) {
  return (
    <div className="imp-cols">
      <h2 className="imp-h2">Сопоставьте колонки</h2>
      <div className="imp-glafira-note">
        <span className="imp-em">💃</span>
        Глафира распознала колонки автоматически — проверьте и поправьте, если нужно.
      </div>

      {/* индикатор обязательных полей */}
      <div className="imp-req-row">
        <span className="imp-req-label">Обязательные поля:</span>
        <span className={`imp-req-chip ${hasName ? 'ok' : 'bad'}`}>
          <Icon name={hasName ? 'check' : 'x'} size={12}/> Имя
        </span>
        <span className={`imp-req-chip ${hasContact ? 'ok' : 'bad'}`}>
          <Icon name={hasContact ? 'check' : 'x'} size={12}/> Контакт (телефон / email)
        </span>
      </div>

      {/* таблица сопоставления */}
      <div className="imp-map-table">
        <div className="imp-map-thead">
          <div className="imp-mt-col">Колонка из файла</div>
          <div className="imp-mt-arrow"/>
          <div className="imp-mt-field">Поле кандидата</div>
        </div>
        {IMP_FILE.cols.map(c => {
          const val = mapping[c.id];
          const auto = c.auto && val === c.auto;
          const unmapped = val === '__skip';
          const needsManual = !c.auto && unmapped;
          return (
            <div key={c.id} className={`imp-map-row ${needsManual ? 'needs' : ''}`}>
              <div className="imp-mt-col">
                <div className="imp-col-name">
                  {c.name}
                  {auto && <span className="imp-auto-tag"><Icon name="check" size={11}/> распознано</span>}
                  {needsManual && <span className="imp-manual-tag">выберите вручную</span>}
                </div>
                <div className="imp-col-samples">
                  {c.samples.map((s, i) => <span key={i} className="imp-sample">{s}</span>)}
                </div>
              </div>
              <div className="imp-mt-arrow"><Icon name="arrowRight" size={16}/></div>
              <div className="imp-mt-field">
                <ImpFieldSelect
                  colId={c.id} value={val}
                  open={openDrop === c.id}
                  onToggle={() => setOpenDrop(openDrop === c.id ? null : c.id)}
                  onPick={(fid) => { setMapping({ ...mapping, [c.id]: fid }); setOpenDrop(null); }}
                  usedFields={Object.entries(mapping).filter(([k]) => k !== c.id).map(([, v]) => v)}
                />
                {c.resumeNote && val === 'resume' && (
                  <div className="imp-field-note" title="Ссылка из Потока сохранится в карточке, но сам файл резюме недоступен вне Потока">
                    <Icon name="alert" size={11}/> ссылка сохранится, файл резюме недоступен вне Потока
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// дропдаун выбора поля
function ImpFieldSelect({ colId, value, open, onToggle, onPick, usedFields }) {
  const isSkip = value === '__skip';
  return (
    <div className={`imp-sel-wrap ${open ? 'open' : ''}`}>
      <button className={`imp-sel ${isSkip ? 'skip' : ''}`} onClick={onToggle}>
        <span className="imp-sel-val">{FIELD_LABEL[value]}</span>
        <Icon name="chevD" size={14} className="imp-sel-chev"/>
      </button>
      {open && (
        <>
          <div className="imp-sel-backdrop" onClick={onToggle}/>
          <div className="imp-sel-menu">
            {IMP_FIELDS.map(f => {
              const used = usedFields.includes(f.id) && f.id !== value;
              return (
                <button key={f.id}
                        className={`imp-sel-opt ${value === f.id ? 'sel' : ''} ${used ? 'used' : ''}`}
                        onClick={() => onPick(f.id)}>
                  <span className="imp-sel-opt-label">
                    {f.label}
                    {f.req && <span className="imp-sel-opt-req">обяз.</span>}
                  </span>
                  {used && <span className="imp-sel-opt-used">занято</span>}
                  {value === f.id && <Icon name="check" size={14}/>}
                </button>
              );
            })}
            <div className="imp-sel-sep"/>
            <button className={`imp-sel-opt imp-sel-skip ${value === '__skip' ? 'sel' : ''}`}
                    onClick={() => onPick('__skip')}>
              <span className="imp-sel-opt-label">Не импортировать</span>
              {value === '__skip' && <Icon name="check" size={14}/>}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// мини-блок сопоставления этапов

// =====================================================================
// ШАГ 3 — Превью импорта
// =====================================================================
function ImpStepPreview({ dupMode, setDupMode, source }) {
  const shown = IMP_PREVIEW.length;
  const rest = IMP_TOTAL - shown;
  const [openRow, setOpenRow] = useStateIM(null);
  const fromPotok = source === 'potok';
  return (
    <div className="imp-preview">
      <h2 className="imp-h2">Превью импорта</h2>
      <div className="imp-preview-from">
        {fromPotok
          ? <><span className="imp-em">💃</span> Глафира забрала кандидатов из <b>Потока</b> по API — проверьте перед заливкой в базу.</>
          : <><Icon name="download" size={14}/> Кандидаты из файла <b className="t-mono">{IMP_FILE.name}</b> — проверьте перед заливкой в базу.</>}
      </div>

      {/* сводка-полоса */}
      <div className="imp-stat-row">
        <div className="imp-stat">
          <div className="imp-stat-num t-mono">{fmtIM(IMP_TOTAL)}</div>
          <div className="imp-stat-lbl">Всего строк</div>
        </div>
        <div className="imp-stat is-new">
          <div className="imp-stat-num t-mono">{fmtIM(IMP_NEW)}</div>
          <div className="imp-stat-lbl">Новых кандидатов</div>
        </div>
        <div className="imp-stat is-dup">
          <div className="imp-stat-num t-mono">{fmtIM(IMP_DUP)}</div>
          <div className="imp-stat-lbl">Дублей <span className="imp-stat-cap">уже в базе</span></div>
        </div>
        <div className="imp-stat is-err">
          <div className="imp-stat-num t-mono">{fmtIM(IMP_ERR)}</div>
          <div className="imp-stat-lbl">С ошибками <span className="imp-stat-cap">пропустятся</span></div>
        </div>
      </div>

      {/* тумблер дублей */}
      <div className="imp-preview-controls">
        <div className="imp-dup-ctrl">
          <span className="imp-dup-label">Дубли:</span>
          <div className="imp-seg">
            <button className={`imp-seg-btn ${dupMode === 'skip' ? 'active' : ''}`} onClick={() => setDupMode('skip')}>Пропустить</button>
            <button className={`imp-seg-btn ${dupMode === 'update' ? 'active' : ''}`} onClick={() => setDupMode('update')}>Обновить</button>
          </div>
          <span className="imp-dup-hint">
            {dupMode === 'skip' ? 'Совпавшие с базой — не тронем' : 'Совпавшим обновим контакты и поля из файла'}
          </span>
        </div>
        <div className="imp-preview-count">
          Показаны первые <b className="t-mono">{shown}</b> · и ещё <b className="t-mono">{fmtIM(rest)}</b> строк
        </div>
      </div>

      <div className="imp-pv-tip">
        <Icon name="open" size={13}/> Нажмите на кандидата, чтобы посмотреть резюме, забранное из Потока
      </div>

      {/* таблица превью */}
      <div className="imp-pv-table">
        <div className="imp-pv-head">
          <div className="imp-pv-c-name">Кандидат</div>
          <div className="imp-pv-c-phone">Телефон</div>
          <div className="imp-pv-c-email">Email</div>
          <div className="imp-pv-c-city">Город</div>
          <div className="imp-pv-c-src">Источник</div>
        </div>
        <div className="imp-pv-body">
          {IMP_PREVIEW.map((r, i) => {
            const skip = r.err || (r.dup && dupMode === 'skip');
            const clickable = !r.err;
            return (
              <div key={i}
                   className={`imp-pv-row ${r.err ? 'err' : ''} ${r.dup ? 'dup' : ''} ${skip ? 'skip' : ''} ${clickable ? 'clickable' : ''}`}
                   onClick={() => clickable && setOpenRow(i)}>
                <div className="imp-pv-c-name">
                  {r.err && r.name === '—'
                    ? <span className="imp-pv-avatar-x"><Icon name="x" size={13}/></span>
                    : <Avatar name={r.name === '—' ? '?' : r.name} size="sm"/>}
                  <div className="imp-pv-name-wrap">
                    <span className={`imp-pv-name ${r.name === '—' ? 'empty' : ''}`}>{r.name === '—' ? 'нет имени' : r.name}</span>
                    <div className="imp-pv-badges">
                      {r.dup && <span className="imp-badge-dup">дубль</span>}
                      {r.err && <span className="imp-badge-err"><Icon name="alert" size={10}/> {r.err}</span>}
                      {r.resumeNote && !r.err && (
                        <span className="imp-badge-resume" title="Ссылка на резюме из Потока сохранится в карточке, но сам файл недоступен вне Потока">
                          <Icon name="open" size={10}/> резюме-ссылка
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="imp-pv-c-phone t-mono">{r.phone}</div>
                <div className="imp-pv-c-email">{r.email}</div>
                <div className="imp-pv-c-city">{r.city}</div>
                <div className="imp-pv-c-src">
                  <span className={`src-pill src-${r.src}`}>{SRC_LABEL[r.src]}</span>
                </div>
                {clickable && <Icon name="chevR" size={15} className="imp-pv-open"/>}
              </div>
            );
          })}
        </div>
        <div className="imp-pv-more">
          <Icon name="more" size={16}/> и ещё <b className="t-mono">{fmtIM(rest)}</b> строк будут обработаны при импорте
        </div>
      </div>

      {openRow !== null && (
        <ImpResumeModal row={IMP_PREVIEW[openRow]} arch={impArch(openRow)} onClose={() => setOpenRow(null)}/>
      )}
    </div>
  );
}

// ====== Центральный попап резюме (забрано из Потока) ======
function ImpResumeModal({ row, arch, onClose }) {
  const lastCo = arch.jobs[0].co;
  const stazh = arch.exp.replace(/\s*опыта$/, '');
  return (
    <div className="imp-modal-overlay" onClick={onClose}>
      <div className="imp-modal" role="dialog" aria-label="Резюме кандидата" onClick={e => e.stopPropagation()}>
        <button className="icon-btn imp-modal-close" onClick={onClose} title="Закрыть"><Icon name="x" size={18}/></button>

        <div className="imp-modal-head">
          <div className="imp-modal-id">
            <Avatar name={row.name} size="md"/>
            <h2 className="imp-modal-name">{row.name}</h2>
          </div>
          <div className="imp-modal-chips">
            <span className="imp-resume-from"><span className="imp-resume-from-dot"/> Резюме из Потока</span>
            <span className={`src-pill src-${row.src}`}>{SRC_LABEL[row.src]}</span>
            <span className="imp-modal-role">{arch.title}</span>
          </div>
        </div>

        <div className="imp-modal-body">
          <div className="imp-modal-seclabel">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>
            </svg>
            Резюме
          </div>

          <div className="imp-resume-card">
            <div className="imp-rcard-title">{arch.title}</div>
            <div className="imp-rcard-meta">
              <span>Общий стаж: <b>{stazh}</b></span>
              <span className="imp-rcard-sep">·</span>
              <span>Город: <b>{row.city}</b></span>
              <span className="imp-rcard-sep">·</span>
              <span>Посл. место: <b>{lastCo}</b></span>
            </div>

            <div className="imp-resume-contacts">
              <div className="imp-rc-row"><Icon name="phone" size={14}/><span className="t-mono">{row.phone}</span></div>
              <div className="imp-rc-row"><Icon name="mail" size={14}/><span>{row.email}</span></div>
            </div>

            <div className="imp-resume-note">
              <Icon name="alert" size={13}/>
              Резюме и биография забраны из Потока. Ссылка на исходный файл сохранится в карточке, но сам PDF-файл резюме недоступен вне Потока.
            </div>

            <h3 className="imp-resume-sec">О кандидате</h3>
            <p className="imp-resume-bio">{arch.bio}</p>

            <h3 className="imp-resume-sec">Опыт работы</h3>
            {arch.jobs.map((j, k) => (
              <div key={k} className="job">
                <div className="job-header">
                  <div>
                    <div className="job-title">{j.title}</div>
                    <div className="job-co">{j.co}</div>
                  </div>
                  <div className="job-period">{j.period}</div>
                </div>
                <div className="job-desc">{j.desc}</div>
              </div>
            ))}

            <h3 className="imp-resume-sec">Навыки</h3>
            <div className="skill-row">
              {arch.skills.map(s => <span key={s} className="skill-chip">{s}</span>)}
            </div>

            <h3 className="imp-resume-sec">Образование</h3>
            <div className="edu-row">
              <div>
                <div className="job-title">{arch.edu.school}</div>
                <div className="job-co">{arch.edu.spec}</div>
              </div>
              <div className="job-period">{arch.edu.years}</div>
            </div>

            <h3 className="imp-resume-sec">Дополнительно</h3>
            <div className="imp-resume-extra">
              <div><span className="imp-re-k">Языки:</span> {arch.lang}</div>
              <div><span className="imp-re-k">Источник резюме:</span> {SRC_LABEL[row.src]} (через Поток)</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// ШАГ 4 — Импорт и результат
// =====================================================================
function ImpStepResult({ runState, imported, importCount, dupMode, source, onViewBase, onAgain }) {
  const fromPotok = source === 'potok';
  if (runState === 'running') {
    const pct = importCount ? Math.round((imported / importCount) * 100) : 0;
    return (
      <div className="imp-run">
        <div className="imp-run-dancer">💃</div>
        <div className="imp-run-phase">Импортируем кандидатов в базу…</div>
        <div className="imp-run-detail">
          Импортировано <b className="t-mono">{fmtIM(imported)}</b> из <b className="t-mono">{fmtIM(importCount)}</b>
        </div>
        <div className="imp-run-bar"><span style={{width: `${pct}%`}}/></div>
        <div className="imp-run-pct t-mono">{pct}%</div>
      </div>
    );
  }

  // result
  const created = importCount;
  const skipped = dupMode === 'update' ? 0 : IMP_DUP;
  return (
    <div className="imp-result">
      <div className="imp-result-check"><Icon name="check" size={28}/></div>
      <h2 className="imp-result-title">Импорт завершён</h2>
      <div className="imp-result-sub">{fromPotok ? 'Кандидаты из Потока добавлены в общую базу' : 'Кандидаты из файла добавлены в общую базу'}</div>

      <div className="imp-result-stats">
        <div className="imp-rstat is-new">
          <div className="num t-mono">{fmtIM(created)}</div>
          <div className="lbl">Создано кандидатов</div>
        </div>
        <div className="imp-rstat is-dup">
          <div className="num t-mono">{fmtIM(skipped)}</div>
          <div className="lbl">{dupMode === 'update' ? 'Дублей обновлено' : 'Пропущено дублей'}</div>
        </div>
        <div className="imp-rstat is-err">
          <div className="num t-mono">{fmtIM(IMP_ERR)}</div>
          <div className="lbl">Ошибок (пропущены)</div>
        </div>
      </div>

      <div className="imp-result-actions">
        <button className="btn btn-primary" onClick={onViewBase}>
          <Icon name="users" size={15}/> Смотреть в базе
        </button>
        <button className="btn btn-secondary" onClick={onAgain}>
          <Icon name="refresh" size={14}/> Импортировать ещё
        </button>
      </div>

      {dupMode !== 'update' && (
        <div className="imp-result-note">
          <Icon name="alert" size={13}/>
          {fmtIM(IMP_ERR)} строк пропущено из-за отсутствия имени или контакта — {fromPotok ? 'их можно поправить в Потоке и подключиться повторно.' : 'их можно поправить в файле и загрузить повторно.'}
        </div>
      )}
    </div>
  );
}

Object.assign(window, { ImportCandidates });
