// SmartSearch — раздел «Умный подбор» (активный поиск кандидатов через hh.ru)
// Пошаговый конструктор в одном окне (прогрессивное раскрытие) + состояния:
// нет-доступа / начальное / шаги / выполнение / результат / история.
const { useState: useStateSS, useMemo: useMemoSS, useEffect: useEffectSS, useRef: useRefSS } = React;

// ====== Данные вакансий для активного поиска ======
// Привязаны к VACANCIES по id; обогащены превью + предложенными фильтрами + «найдено на hh».
const SMART_VACANCIES = [
  { id:'fe', title:'Frontend-разработчик (Senior)', city:'Москва', salFrom:280000, salTo:380000,
    reqs:['React','TypeScript','5+ лет опыта'],
    area:'Информационные технологии', role:'Программист, разработчик', exp:'3–6 лет',
    skills:['React','TypeScript','Redux','REST API','CI/CD'], found:524 },
  { id:'do', title:'DevOps-инженер', city:'Москва', salFrom:300000, salTo:420000,
    reqs:['Kubernetes','CI/CD','3+ года'],
    area:'Информационные технологии', role:'DevOps-инженер', exp:'3–6 лет',
    skills:['Kubernetes','Docker','Terraform','Ansible','Linux'], found:286 },
  { id:'sl', title:'Менеджер по продажам B2B', city:'Москва', salFrom:120000, salTo:240000,
    reqs:['B2B-продажи','CRM','2+ года'],
    area:'Продажи', role:'Менеджер по продажам', exp:'1–3 года',
    skills:['B2B-продажи','Холодные звонки','CRM','Переговоры'], found:912 },
  { id:'wh', title:'Кладовщик · смена 2/2', city:'Москва', salFrom:65000, salTo:90000,
    reqs:['Опыт склада','Бумажный учёт'],
    area:'Транспорт, логистика', role:'Кладовщик', exp:'не важен',
    skills:['Складской учёт','WMS','Погрузчик'], found:1340 },
  { id:'qa', title:'QA-инженер (автоматизация)', city:'Удалённо', salFrom:200000, salTo:300000,
    reqs:['Python','Selenium','3+ года'],
    area:'Информационные технологии', role:'Тестировщик', exp:'3–6 лет',
    skills:['Python','Selenium','API-тесты','Pytest'], found:198 },
];

// История прошлых запусков
const SMART_HISTORY = [
  { id:1, vacId:'fe', vac:'Frontend-разработчик (Senior)', date:'2 апреля 2026', found:498, evaluated:300, invited:18 },
  { id:2, vacId:'sl', vac:'Менеджер по продажам B2B',      date:'27 марта 2026', found:870, evaluated:400, invited:24 },
  { id:3, vacId:'do', vac:'DevOps-инженер',                 date:'14 марта 2026', found:240, evaluated:200, invited:11 },
];

function ssFmt(n) {
  return n.toLocaleString('ru-RU').replace(/\u00A0/g, '\u202F');
}
function ssThrColor(v) {
  if (v >= 80) return { cls:'green', bg:'var(--ark-green-100)', fg:'var(--ark-green-600)', label:'высокий порог' };
  if (v >= 50) return { cls:'yellow', bg:'var(--ark-yellow-100)', fg:'var(--ark-yellow-600)', label:'средний порог' };
  return { cls:'red', bg:'var(--ark-red-100)', fg:'var(--ark-red-600)', label:'низкий порог' };
}

// ====== Главный компонент ======
function SmartSearch({ hasHhAccess = true, presetView = 'auto', onGoSettings, onGoFunnel }) {
  // phase: 'build' | 'running' | 'done'
  const [phase, setPhase] = useStateSS('build');
  const [vacId, setVacId] = useStateSS(null);
  const [maxStep, setMaxStep] = useStateSS(1);
  const [selOpen, setSelOpen] = useStateSS(false);

  // Step 2 — фильтры
  const [skills, setSkills] = useStateSS([]);
  const [role, setRole] = useStateSS('');
  const [exp, setExp] = useStateSS('');
  const [area, setArea] = useStateSS('');

  // Step 3 — зарплата
  const [salFrom, setSalFrom] = useStateSS(0);
  const [salTo, setSalTo] = useStateSS(0);
  const [inclNoSalary, setInclNoSalary] = useStateSS(true);

  // Step 4 — объём
  const [scanN, setScanN] = useStateSS(300);
  const [inviteM, setInviteM] = useStateSS(20);

  // Step 5 — порог
  const [threshold, setThreshold] = useStateSS(75);

  // Running
  const [runStage, setRunStage] = useStateSS(0); // 0 search, 1 eval, 2 invite
  const [evalCount, setEvalCount] = useStateSS(0);
  const timers = useRefSS([]);

  const vac = useMemoSS(() => SMART_VACANCIES.find(v => v.id === vacId) || null, [vacId]);

  // Применить пресет из тумблера (для удобного превью состояний)
  useEffectSS(() => {
    if (presetView === 'running' || presetView === 'done') {
      selectVacancy('fe', /*silent*/true);
      setMaxStep(5);
      if (presetView === 'done') { setPhase('done'); setRunStage(2); setEvalCount(300); }
      else { startRun(); }
    } else if (presetView === 'constructor') {
      selectVacancy('fe', true);
      setMaxStep(5);
      setPhase('build');
    } else if (presetView === 'initial') {
      resetAll();
    }
    // eslint-disable-line
  }, [presetView]);

  function resetAll() {
    clearTimers();
    setPhase('build'); setVacId(null); setMaxStep(1); setSelOpen(false);
    setSkills([]); setRole(''); setExp(''); setArea('');
    setSalFrom(0); setSalTo(0); setInclNoSalary(true);
    setScanN(300); setInviteM(20); setThreshold(75);
    setRunStage(0); setEvalCount(0);
  }

  function selectVacancy(id, silent) {
    const v = SMART_VACANCIES.find(x => x.id === id);
    if (!v) return;
    setVacId(id);
    setSelOpen(false);
    // авто-предложение фильтров из вакансии
    setSkills([...v.skills]);
    setRole(v.role); setExp(v.exp); setArea(v.area);
    setSalFrom(v.salFrom); setSalTo(v.salTo);
    // объём: берём первых N из найденного
    const proposeScan = Math.min(400, Math.max(100, Math.round(v.found * 0.6 / 50) * 50));
    setScanN(proposeScan);
    setInviteM(20);
    if (!silent) setMaxStep(m => Math.max(m, 2));
  }

  function clearTimers() { timers.current.forEach(clearTimeout); timers.current = []; clearInterval(evalIntRef.current); }
  const evalIntRef = useRefSS(null);

  function startRun() {
    clearTimers();
    setPhase('running'); setRunStage(0); setEvalCount(0);
    timers.current.push(setTimeout(() => {
      setRunStage(1);
      // count up eval
      let c = 0;
      const target = scanN;
      const step = Math.max(1, Math.round(target / 36));
      evalIntRef.current = setInterval(() => {
        c = Math.min(target, c + step);
        setEvalCount(c);
        if (c >= target) clearInterval(evalIntRef.current);
      }, 70);
    }, 1700));
    timers.current.push(setTimeout(() => setRunStage(2), 1700 + 36 * 70 + 400));
    timers.current.push(setTimeout(() => { setPhase('done'); }, 1700 + 36 * 70 + 400 + 1600));
  }

  useEffectSS(() => () => clearTimers(), []); // cleanup on unmount

  // вычисления результата
  const invitedList = useMemoSS(() => {
    if (!vac) return [];
    return [...CANDIDATES]
      .filter(c => c.score >= threshold)
      .sort((a, b) => b.score - a.score)
      .slice(0, inviteM);
  }, [vac, threshold, inviteM]);

  const passThreshold = useMemoSS(() => {
    // примерная оценка: доля оценённых выше порога
    const frac = Math.max(0.05, (100 - threshold) / 100 * 0.5);
    return Math.min(inviteM, Math.max(3, Math.round(scanN * frac)));
  }, [scanN, threshold, inviteM]);

  // ====== НЕТ ДОСТУПА ======
  if (!hasHhAccess) {
    return <SSNoAccess onGoSettings={onGoSettings}/>;
  }

  // ====== ВЫПОЛНЕНИЕ ======
  if (phase === 'running') {
    return (
      <div className="ss-page" data-screen-label="Smart Search / Running">
        <SSHeader/>
        <SSRunning stage={runStage} evalCount={evalCount} scanN={scanN} inviteM={Math.min(inviteM, passThreshold)} vac={vac}/>
      </div>
    );
  }

  // ====== РЕЗУЛЬТАТ ======
  if (phase === 'done') {
    const invitedCount = Math.min(inviteM, invitedList.length || passThreshold);
    return (
      <div className="ss-page" data-screen-label="Smart Search / Result">
        <SSHeader/>
        <SSResult
          vac={vac} found={vac ? vac.found : 0} evaluated={scanN}
          invited={invitedCount} threshold={threshold}
          invitedList={invitedList}
          onNew={() => resetAll()}
          onGoFunnel={onGoFunnel}
        />
        <SSHistory/>
      </div>
    );
  }

  // ====== КОНСТРУКТОР ======
  const stepState = (n) => maxStep > n ? 'is-done' : (maxStep === n ? 'is-current' : '');
  const canLaunch = maxStep >= 5 && vac;

  return (
    <div className="ss-page" data-screen-label="Smart Search / Constructor">
      <SSHeader/>

      {!vac && maxStep === 1 && <SSInitialHero/>}

      <div className="ssm-steps">
        {/* ---------- ШАГ 1 — Вакансия ---------- */}
        <div className={`ssm-step ${stepState(1)}`}>
          <div className="ssm-step-num">{maxStep > 1 ? <Icon name="check" size={18}/> : 1}</div>
          <div className="ssm-step-card">
            <div className="ssm-step-head">
              <span className="ssm-step-title">Под какую вакансию ищем?</span>
            </div>
            <div className="ssm-step-hint">Глафира возьмёт описание вакансии и построит фильтры автоматически.</div>

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
                  {SMART_VACANCIES.map(v => (
                    <div key={v.id}
                      className={`ss-select-opt ${vacId === v.id ? 'sel' : ''}`}
                      onClick={() => selectVacancy(v.id)}>
                      <Icon name="briefcase" size={15} className="ss-opt-ic"/>
                      <div className="ss-opt-main">
                        <div className="ss-opt-title">{v.title}</div>
                        <div className="ss-opt-meta">{v.city} · {ssFmt(v.salFrom)}–{ssFmt(v.salTo)} ₽</div>
                      </div>
                      <span className="ss-opt-found">~{ssFmt(v.found)} на hh</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {vac && (
              <div className="ss-vac-preview">
                <div className="ss-vp-top">
                  <div className="ss-vp-ic"><Icon name="briefcase" size={18}/></div>
                  <div style={{flex:1, minWidth:0}}>
                    <div className="ss-vp-title">{vac.title}</div>
                    <div className="ss-vp-meta">
                      <span><Icon name="pin" size={12} style={{verticalAlign:'-2px', marginRight:3, color:'var(--fg-3)'}}/>{vac.city}</span>
                      <span className="sep">·</span>
                      <span className="ss-vp-sal">{ssFmt(vac.salFrom)} – {ssFmt(vac.salTo)} ₽</span>
                      <span className="sep">·</span>
                      <span>опыт {vac.exp}</span>
                    </div>
                    <div className="ss-vp-reqs">
                      {vac.reqs.map((r, i) => <span key={i} className="ss-req-chip">{r}</span>)}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ---------- ШАГ 2 — Фильтры ---------- */}
        {maxStep >= 2 && (
          <div className={`ssm-step ${stepState(2)}`}>
            <div className="ssm-step-num">{maxStep > 2 ? <Icon name="check" size={18}/> : 2}</div>
            <div className="ssm-step-card">
              <div className="ssm-step-head">
                <span className="ssm-step-title">Фильтры поиска</span>
              </div>
              <div className="ss-glafira-note">
                <span className="em">💃</span> Глафира предложила фильтры из вакансии — можно скорректировать
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
                  {skills.map((s, i) => (
                    <span key={i} className="ss-chip">
                      {s}
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

              {maxStep === 2 && (
                <div className="ssm-step-actions">
                  <button className="btn btn-primary btn-sm" onClick={() => setMaxStep(3)}>
                    <Icon name="arrowRight" size={14}/> Далее
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ---------- ШАГ 3 — Зарплата ---------- */}
        {maxStep >= 3 && (
          <div className={`ssm-step ${stepState(3)}`}>
            <div className="ssm-step-num">{maxStep > 3 ? <Icon name="check" size={18}/> : 3}</div>
            <div className="ssm-step-card">
              <div className="ssm-step-head">
                <span className="ssm-step-title">Зарплатные ожидания</span>
              </div>
              <div className="ssm-step-hint">Резюме с ожиданиями вне диапазона будут отсеяны до оценки.</div>

              <div className="ss-salary-fields">
                <div className="ss-sal-field">
                  <div className="ss-field-label">От</div>
                  <div className="ss-sal-input-wrap">
                    <input className="ss-sal-input" type="text"
                      value={ssFmt(salFrom)}
                      onChange={e => setSalFrom(+e.target.value.replace(/\D/g, '') || 0)}/>
                    <span className="ss-sal-cur">₽</span>
                  </div>
                </div>
                <span className="ss-sal-dash">—</span>
                <div className="ss-sal-field">
                  <div className="ss-field-label">До</div>
                  <div className="ss-sal-input-wrap">
                    <input className="ss-sal-input" type="text"
                      value={ssFmt(salTo)}
                      onChange={e => setSalTo(+e.target.value.replace(/\D/g, '') || 0)}/>
                    <span className="ss-sal-cur">₽</span>
                  </div>
                </div>
              </div>

              <div className="ss-toggle-row">
                <div className="ss-tr-text">
                  <div className="ss-tr-title">Учитывать кандидатов, не указавших зарплату</div>
                  <div className="ss-tr-sub">Часто сильные кандидаты оставляют поле пустым</div>
                </div>
                <button className={`ss-switch ${inclNoSalary ? 'on' : ''}`}
                  onClick={() => setInclNoSalary(v => !v)} aria-label="Тумблер"/>
              </div>

              {maxStep === 3 && (
                <div className="ssm-step-actions">
                  <button className="btn btn-primary btn-sm" onClick={() => setMaxStep(4)}>
                    <Icon name="arrowRight" size={14}/> Далее
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ---------- ШАГ 4 — Объём выборки ---------- */}
        {maxStep >= 4 && (
          <div className={`ssm-step ${stepState(4)}`}>
            <div className="ssm-step-num">{maxStep > 4 ? <Icon name="check" size={18}/> : 4}</div>
            <div className="ssm-step-card">
              <div className="ssm-step-head">
                <span className="ssm-step-title">Объём выборки</span>
              </div>
              <div className="ssm-step-hint">
                По фильтрам найдено <b className="t-mono" style={{color:'var(--fg-1)'}}>~{ssFmt(vac ? vac.found : 0)}</b> резюме.
                Глафира оценит первые N и пригласит лучших.
              </div>

              <div className="ss-vol-grid">
                <div className="ss-vol-cell">
                  <div className="ss-vol-label">
                    <Icon name="sparkle" size={14} style={{color:'var(--ark-violet-500)'}}/>
                    Сканировать резюме
                  </div>
                  <div className="ss-vol-sub">Больше — точнее, но дольше и дороже по AI-токенам</div>
                  <div className="ss-vol-input-row">
                    <input className="ss-num-input" type="number" min="50"
                      max={vac ? vac.found : 1000} step="50"
                      value={scanN} onChange={e => setScanN(Math.max(50, +e.target.value || 50))}/>
                    <input className="ss-slider" type="range" min="50"
                      max={Math.min(vac ? vac.found : 1000, 800)} step="50"
                      value={Math.min(scanN, 800)} onChange={e => setScanN(+e.target.value)}/>
                  </div>
                </div>
                <div className="ss-vol-cell">
                  <div className="ss-vol-label">
                    <Icon name="mail" size={14} style={{color:'var(--ark-green-600)'}}/>
                    Пригласить лучших
                  </div>
                  <div className="ss-vol-sub">Скольким топ-кандидатам отправить приглашение</div>
                  <div className="ss-vol-input-row">
                    <input className="ss-num-input" type="number" min="1" max="100"
                      value={inviteM} onChange={e => setInviteM(Math.max(1, +e.target.value || 1))}/>
                    <input className="ss-slider" type="range" min="1" max="50"
                      value={Math.min(inviteM, 50)} onChange={e => setInviteM(+e.target.value)}/>
                  </div>
                </div>
              </div>

              {/* инфографика воронки */}
              <div className="ss-funnel">
                <div className="ss-fn-node ss-fn-found">
                  <div className="ss-fn-num">{ssFmt(vac ? vac.found : 0)}</div>
                  <div className="ss-fn-label">Найдено</div>
                  <div className="ss-fn-cap">по фильтрам</div>
                </div>
                <div className="ss-fn-arrow"><Icon name="chevR" size={16}/></div>
                <div className="ss-fn-node ss-fn-eval">
                  <div className="ss-fn-num">{ssFmt(scanN)}</div>
                  <div className="ss-fn-label">Оценим</div>
                  <div className="ss-fn-cap">AI-матчинг</div>
                </div>
                <div className="ss-fn-arrow"><Icon name="chevR" size={16}/></div>
                <div className="ss-fn-node ss-fn-invite">
                  <div className="ss-fn-num">{ssFmt(inviteM)}</div>
                  <div className="ss-fn-label">Пригласим</div>
                  <div className="ss-fn-cap">топ по баллу</div>
                </div>
              </div>

              <div className="ss-cost-hint">
                <Icon name="alert" size={15} className="ss-ch-ic"/>
                <span>
                  Оценка <b>{ssFmt(scanN)}</b> резюме — примерно <b className="t-mono">~{Math.ceil(scanN * 1.4 / 1000 * 10) / 10} тыс.</b> AI-токенов
                  и <b className="t-mono">~{Math.max(2, Math.round(scanN / 60))} мин</b> работы Глафиры.
                </span>
              </div>

              {maxStep === 4 && (
                <div className="ssm-step-actions">
                  <button className="btn btn-primary btn-sm" onClick={() => setMaxStep(5)}>
                    <Icon name="arrowRight" size={14}/> Далее
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ---------- ШАГ 5 — Порог приглашения ---------- */}
        {maxStep >= 5 && (
          <div className={`ssm-step is-last ${stepState(5)}`}>
            <div className="ssm-step-num">5</div>
            <div className="ssm-step-card">
              <div className="ssm-step-head">
                <span className="ssm-step-title">Порог приглашения</span>
              </div>
              <div className="ssm-step-hint">AI-балл, выше которого кандидат получает приглашение.</div>

              <div className="ss-thr-row">
                <div className="ss-thr-slider-wrap">
                  <div className="ss-thr-track">
                    <input className="ss-thr-range" type="range" min="0" max="100" step="1"
                      value={threshold} onChange={e => setThreshold(+e.target.value)}/>
                  </div>
                  <div className="ss-thr-ticks">
                    <span>0</span><span>50</span><span>80</span><span>100</span>
                  </div>
                  <div className="ss-thr-explain">
                    <Icon name="sparkle" size={14} className="ss-te-ic"/>
                    <span>
                      Пригласим только кандидатов с матчингом <b>выше {threshold}</b> — даже если их меньше {inviteM}.
                      Примерно пройдут порог: <b className="t-mono">~{passThreshold}</b> кандидатов.
                    </span>
                  </div>
                </div>
                <div className="ss-thr-readout">
                  <div className="ss-thr-badge" style={{background: ssThrColor(threshold).bg, color: ssThrColor(threshold).fg}}>
                    {threshold}
                  </div>
                  <div className="ss-thr-cap">{ssThrColor(threshold).label}</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ---------- ИТОГ-ПАНЕЛЬ ---------- */}
      {canLaunch && (
        <div className="ss-summary">
          <div className="ss-summary-head">
            <Icon name="sparkle" size={18} style={{color:'var(--accent)'}}/>
            Готово к запуску
          </div>

          <div className="ss-summary-grid">
            <span className="ss-sum-pill"><span className="k">Вакансия</span><span className="v">{vac.title}</span></span>
            <span className="ss-sum-pill"><span className="k">Навыков</span><span className="v t-mono">{skills.length}</span></span>
            <span className="ss-sum-pill"><span className="k">ЗП</span><span className="v t-mono">{ssFmt(salFrom)}–{ssFmt(salTo)} ₽</span></span>
            <span className="ss-sum-pill"><span className="k">Сканируем</span><span className="v t-mono">{ssFmt(scanN)}</span></span>
            <span className="ss-sum-pill"><span className="k">Приглашаем топ</span><span className="v t-mono">{inviteM}</span></span>
            <span className="ss-sum-pill"><span className="k">Порог</span><span className="v t-mono">≥ {threshold}</span></span>
          </div>

          <div className="ss-sum-sentence">
            Найдём <b>~{ssFmt(vac.found)}</b> резюме по фильтрам → оценим первые <span className="hl">{ssFmt(scanN)}</span> AI-матчингом
            → пригласим <span className="hl-g">топ-{inviteM}</span> с баллом <span className="hl-g">≥ {threshold}</span>.
            Приглашённые появятся в воронке вакансии.
          </div>

          <div className="ss-launch-row">
            <button className="ss-btn-launch" onClick={startRun}>
              <span className="em">💃</span> Запустить поиск
            </button>
            <div className="ss-launch-est">
              Примерно <span className="t-mono">~{Math.max(2, Math.round(scanN / 60))} мин</span> ·
              расход <span className="t-mono">~{Math.ceil(scanN * 1.4 / 1000 * 10) / 10} тыс.</span> токенов
            </div>
          </div>
        </div>
      )}

      <SSHistory/>
    </div>
  );
}

// ====== Шапка раздела ======
function SSHeader() {
  return (
    <div className="ss-head">
      <div className="ss-head-mark">💃</div>
      <div className="ss-head-text">
        <h1>Умный подбор <span className="ss-beta">beta</span></h1>
        <div className="ss-sub">
          Активный поиск кандидатов на hh.ru: Глафира строит фильтры из вакансии, сканирует резюме,
          оценивает их AI-матчингом и приглашает лучших — прямо в воронку.
        </div>
      </div>
    </div>
  );
}

// ====== Начальный hero (до выбора вакансии) ======
function SSInitialHero() {
  return (
    <div className="ss-hero">
      <div className="ss-hero-emoji">💃</div>
      <h2>Запустите активный поиск за пару минут</h2>
      <p>
        Не ждите откликов — Глафира сама найдёт подходящих кандидатов в базе резюме hh.ru,
        оценит соответствие вакансии и пригласит лучших на собеседование.
      </p>
      <div className="ss-hero-flow">
        <div className="ss-hflow-step">
          <div className="ss-hflow-ic"><Icon name="search" size={16}/></div>
          <div className="ss-hflow-t">Найдёт</div>
          <div className="ss-hflow-d">Соберёт фильтры из вакансии и найдёт резюме</div>
        </div>
        <div className="ss-hflow-step is-score">
          <div className="ss-hflow-ic"><Icon name="sparkle" size={16}/></div>
          <div className="ss-hflow-t">Оценит</div>
          <div className="ss-hflow-d">Сравнит каждое резюме с описанием вакансии</div>
        </div>
        <div className="ss-hflow-step is-invite">
          <div className="ss-hflow-ic"><Icon name="mail" size={16}/></div>
          <div className="ss-hflow-t">Пригласит</div>
          <div className="ss-hflow-d">Отправит приглашения лучшим автоматически</div>
        </div>
      </div>
      <div style={{fontSize:13, color:'var(--fg-3)'}}>
        ↓ Начните с выбора вакансии
      </div>
    </div>
  );
}

// ====== Состояние выполнения ======
function SSRunning({ stage, evalCount, scanN, inviteM, vac }) {
  const phases = [
    { t:'Глафира ищет резюме на hh.ru…', d: vac ? `по фильтрам вакансии «${vac.title}»` : '' },
    { t:`Оценивает резюме…`, d:`AI-матчинг ${ssFmt(evalCount)} из ${ssFmt(scanN)}` },
    { t:'Приглашает лучших…', d:`отправляем приглашения топ-${inviteM} кандидатам` },
  ];
  const cur = phases[stage] || phases[0];
  const pct = stage === 0 ? 12 : stage === 1 ? 12 + (evalCount / scanN) * 70 : 100;
  const stages = ['Поиск', 'Оценка', 'Приглашения'];
  return (
    <div className="ss-run">
      <div className="ss-run-dancer">💃</div>
      <div className="ss-run-phase">{cur.t}</div>
      <div className="ss-run-detail">{cur.d}</div>
      <div className="ss-run-bar"><span style={{width: `${pct}%`}}/></div>
      <div className="ss-run-stages">
        {stages.map((s, i) => (
          <div key={i} className={`ss-run-stage ${i === stage ? 'active' : ''} ${i < stage ? 'done' : ''}`}>
            <div className="ss-rs-dot">
              {i < stage ? <Icon name="check" size={14}/> : i + 1}
            </div>
            {s}
          </div>
        ))}
      </div>
    </div>
  );
}

// ====== Результат ======
function SSResult({ vac, found, evaluated, invited, threshold, invitedList, onNew, onGoFunnel }) {
  return (
    <div>
      <div className="ss-result-head">
        <div className="ss-result-check"><Icon name="check" size={24}/></div>
        <div>
          <h2>Поиск завершён</h2>
          <div className="ss-rh-sub">{vac ? vac.title : ''} · приглашённые добавлены в воронку</div>
        </div>
      </div>

      <div className="ss-result-stats">
        <div className="ss-rstat found">
          <div className="num">{ssFmt(found)}</div>
          <div className="lbl">Найдено резюме <b>по фильтрам</b></div>
        </div>
        <div className="ss-rstat eval">
          <div className="num">{ssFmt(evaluated)}</div>
          <div className="lbl">Оценено <b>AI-матчингом</b></div>
        </div>
        <div className="ss-rstat invite">
          <div className="num">{ssFmt(invited)}</div>
          <div className="lbl">Приглашено <b>с баллом ≥ {threshold}</b></div>
        </div>
      </div>

      <div className="ss-invited-card">
        <div className="ss-invited-head">
          <span className="title">Приглашённые кандидаты</span>
          <span className="count">{invited}</span>
          <div style={{flex:1}}/>
          <span className="live-dot">приглашения отправлены</span>
        </div>
        {invitedList.slice(0, invited).map(c => (
          <div key={c.id} className="ss-inv-row">
            <Avatar name={c.name} size="sm"/>
            <div className="ss-inv-main">
              <div className="ss-inv-name">{c.name}</div>
              <div className="ss-inv-meta">{c.age} лет · {c.lastDur} · {c.lastCo} · {c.city}</div>
            </div>
            <ScoreBadge score={c.score} size="md"/>
            <span className="ss-inv-sent"><Icon name="check" size={12}/> приглашён</span>
          </div>
        ))}
      </div>

      <div className="ss-result-actions">
        <button className="btn btn-primary" onClick={onGoFunnel}>
          <Icon name="funnel" size={15}/> Смотреть в воронке
        </button>
        <button className="btn btn-secondary" onClick={onNew}>
          <Icon name="refresh" size={14}/> Новый поиск
        </button>
      </div>
    </div>
  );
}

// ====== История поисков ======
function SSHistory() {
  return (
    <div className="ss-history">
      <div className="ss-history-head">
        <Icon name="clock" size={15} style={{color:'var(--fg-3)'}}/>
        <span className="title">История поисков</span>
        <span className="count">{SMART_HISTORY.length}</span>
      </div>
      <div className="ss-hist-list">
        {SMART_HISTORY.map(h => (
          <div key={h.id} className="ss-hist-row">
            <div className="ss-hist-main">
              <div className="ss-hist-vac">{h.vac}</div>
              <div className="ss-hist-date">{h.date}</div>
            </div>
            <div className="ss-hist-stats">
              <div className="ss-hist-stat">
                <div className="hv">{ssFmt(h.found)}</div>
                <div className="hl">найдено</div>
              </div>
              <div className="ss-hist-stat">
                <div className="hv">{ssFmt(h.evaluated)}</div>
                <div className="hl">оценено</div>
              </div>
              <div className="ss-hist-stat invite">
                <div className="hv">{h.invited}</div>
                <div className="hl">приглашено</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ====== Нет доступа hh ======
function SSNoAccess({ onGoSettings }) {
  return (
    <div className="ss-page" data-screen-label="Smart Search / No hh access">
      <SSHeader/>
      <div className="ss-noaccess">
        <div className="ss-noaccess-ic"><Icon name="search" size={28}/></div>
        <div className="ss-noaccess-body">
          <h2>Нужен платный доступ к базе резюме hh.ru</h2>
          <p>
            Активный поиск ищет резюме напрямую в базе hh.ru и отправляет приглашения.
            Для этого у компании должен быть подключён платный доступ к базе резюме hh.
          </p>
          <ul className="ss-noaccess-list">
            <li><span className="ss-na-check"><Icon name="check" size={12}/></span> Поиск по всей базе резюме hh.ru, а не только по откликам</li>
            <li><span className="ss-na-check"><Icon name="check" size={12}/></span> AI-оценка резюме Глафирой против описания вакансии</li>
            <li><span className="ss-na-check"><Icon name="check" size={12}/></span> Автоматические приглашения лучшим кандидатам</li>
          </ul>
          <div className="ss-noaccess-actions">
            <button className="btn btn-primary" onClick={onGoSettings}>
              <Icon name="settings" size={15}/> Подключить в Настройках
            </button>
            <button className="btn btn-secondary">
              <Icon name="open" size={14}/> Как это работает
            </button>
          </div>
          <div className="ss-na-note">
            Доступ настраивается в разделе <b>Настройки → Интеграции → hh.ru</b>. После подключения
            активный поиск станет доступен сразу — отклики и пассивный сорсинг работают и без него.
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { SmartSearch });
