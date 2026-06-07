import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { ScoreLabel } from '@/components/ui/ScoreLabel';
import {
  useSmartAccess,
  useSmartVacancies,
  useStartSmartSearch,
  useSmartRun,
  useSmartHistory,
  type SmartVacancy,
  type SmartCandidate,
  type SmartSearchRequest,
} from '@/api/hooks/useSmartSearch';
import './smart-search.css';

// Форматирование чисел с разделителями
function ssFmt(n: number | null | undefined) {
  if (n === null || n === undefined) return '—';
  return n.toLocaleString('ru-RU').replace(/ /g, ' ');
}

// Цвета и метки порога
function ssThrColor(v: number) {
  if (v >= 80) return { cls: 'green', bg: 'var(--ark-green-100)', fg: 'var(--ark-green-600)', label: 'высокий порог' };
  if (v >= 50) return { cls: 'yellow', bg: 'var(--ark-yellow-100)', fg: 'var(--ark-yellow-600)', label: 'средний порог' };
  return { cls: 'red', bg: 'var(--ark-red-100)', fg: 'var(--ark-red-600)', label: 'низкий порог' };
}

type Phase = 'build' | 'running' | 'done';

export default function SmartSearchPage() {
  const navigate = useNavigate();

  // Запросы к API
  const { data: accessData } = useSmartAccess();
  const { data: vacancies = [] } = useSmartVacancies();
  const { data: history = [] } = useSmartHistory();
  const startSearch = useStartSmartSearch();

  // Состояние компонента
  const [phase, setPhase] = useState<Phase>('build');
  const [vacId, setVacId] = useState<string | null>(null);
  const [maxStep, setMaxStep] = useState(1);
  const [selOpen, setSelOpen] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);

  // Step 2 — фильтры
  const [skills, setSkills] = useState<string[]>([]);
  const [role, setRole] = useState('');
  const [exp, setExp] = useState('');
  const [area, setArea] = useState('');

  // Step 3 — зарплата
  const [salFrom, setSalFrom] = useState(0);
  const [salTo, setSalTo] = useState(0);
  const [inclNoSalary, setInclNoSalary] = useState(true);

  // Step 4 — объём
  const [scanN, setScanN] = useState(300);
  const [inviteM, setInviteM] = useState(20);

  // Step 5 — порог
  const [threshold, setThreshold] = useState(75);

  // Поллинг прогресса
  const { data: runData } = useSmartRun(runId, phase === 'running' || phase === 'done');

  const vac = useMemo(() => vacancies.find(v => v.id === vacId) || null, [vacancies, vacId]);

  // Обработчик завершения запуска
  useEffect(() => {
    if (runData && phase === 'running') {
      if (runData.status === 'done' || runData.status === 'error') {
        setPhase('done');
      }
    }
  }, [runData, phase]);

  const resetAll = () => {
    setPhase('build');
    setVacId(null);
    setMaxStep(1);
    setSelOpen(false);
    setRunId(null);
    setSkills([]);
    setRole('');
    setExp('');
    setArea('');
    setSalFrom(0);
    setSalTo(0);
    setInclNoSalary(true);
    setScanN(300);
    setInviteM(20);
    setThreshold(75);
  };

  const selectVacancy = (id: string) => {
    const v = vacancies.find(x => x.id === id);
    if (!v) return;

    setVacId(id);
    setSelOpen(false);

    // авто-предложение фильтров из вакансии
    setSkills([...v.skills]);
    setRole(v.professional_role ?? '');
    setExp(v.experience ?? '');
    setArea(v.area ?? '');
    setSalFrom(v.salary_from ?? 0);
    setSalTo(v.salary_to ?? 0);

    // объём: берём первых N из найденного
    const proposeScan = Math.min(400, Math.max(100, Math.round((v.found || 300) * 0.6 / 50) * 50));
    setScanN(proposeScan);
    setInviteM(20);

    setMaxStep(Math.max(maxStep, 2));
  };

  const handleStartSearch = async () => {
    if (!vac) return;

    const request: SmartSearchRequest = {
      vacancy_id: vac.id,
      area,
      professional_role: role,
      experience: exp,
      skills,
      salary_from: salFrom || undefined,
      salary_to: salTo || undefined,
      include_no_salary: inclNoSalary,
      scan_n: scanN,
      invite_m: inviteM,
      threshold,
    };

    try {
      const response = await startSearch.mutateAsync(request);
      setRunId(response.run_id);
      setPhase('running');
    } catch {
      // Ошибка сервера (квота/вакансия не на hh) отображается через startSearch.error в UI
    }
  };

  // Вычисления
  const passThreshold = useMemo(() => {
    const frac = Math.max(0.05, (100 - threshold) / 100 * 0.5);
    return Math.min(inviteM, Math.max(3, Math.round(scanN * frac)));
  }, [scanN, threshold, inviteM]);

  const stepState = (n: number) => maxStep > n ? 'is-done' : (maxStep === n ? 'is-current' : '');
  const canLaunch = maxStep >= 5 && vac;

  // Нет доступа к hh.ru
  if (!accessData?.has_access) {
    return <SSNoAccess onGoSettings={() => navigate('/settings')} />;
  }

  // Выполнение
  if (phase === 'running') {
    return (
      <div className="ss-page">
        <SSHeader />
        <SSRunning runData={runData} vac={vac} />
      </div>
    );
  }

  // Результат
  if (phase === 'done' && runData) {
    return (
      <div className="ss-page">
        <SSHeader />
        <SSResult
          runData={runData}
          vac={vac}
          threshold={threshold}
          onNew={resetAll}
          onGoFunnel={() => navigate(`/vacancies/${vacId}`)}
        />
        <SSHistory history={history} />
      </div>
    );
  }

  // Конструктор
  return (
    <div className="ss-page">
      <SSHeader />

      {!vac && maxStep === 1 && <SSInitialHero />}

      <div className="ssm-steps">
        {/* Шаг 1 — Вакансия */}
        <div className={`ssm-step ${stepState(1)}`}>
          <div className="ssm-step-num">{maxStep > 1 ? <Icon name="check" size={18} /> : 1}</div>
          <div className="ssm-step-card">
            <div className="ssm-step-head">
              <span className="ssm-step-title">Под какую вакансию ищем?</span>
            </div>
            <div className="ssm-step-hint">Глафира возьмёт описание вакансии и построит фильтры автоматически.</div>

            <div className="ss-select-wrap">
              <button className={`ss-select ${selOpen ? 'open' : ''}`} onClick={() => setSelOpen(o => !o)}>
                <Icon name="briefcase" size={16} style={{ color: 'var(--fg-3)', flex: 'none' }} />
                {vac
                  ? <span className="ss-select-val">{vac.title}</span>
                  : <span className="ss-select-ph">Выберите вакансию компании…</span>}
                <Icon name="chevron-down" size={16} className="ss-chev" />
              </button>
              {selOpen && (
                <div className="ss-select-menu">
                  {vacancies.map(v => (
                    <div key={v.id}
                      className={`ss-select-opt ${vacId === v.id ? 'sel' : ''}`}
                      onClick={() => selectVacancy(v.id)}>
                      <Icon name="briefcase" size={15} className="ss-opt-ic" />
                      <div className="ss-opt-main">
                        <div className="ss-opt-title">{v.title}</div>
                        <div className="ss-opt-meta">{v.city} · {ssFmt(v.salary_from)}–{ssFmt(v.salary_to)} ₽</div>
                      </div>
                      {v.found !== null && (
                        <span className="ss-opt-found">~{ssFmt(v.found)} на hh</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {vac && (
              <>
                {!vac.hh_published && (
                  <div className="error-banner" style={{ marginTop: '14px' }}>
                    Вакансия не опубликована на hh.ru — приглашения невозможны
                  </div>
                )}
                <div className="ss-vac-preview">
                  <div className="ss-vp-top">
                    <div className="ss-vp-ic"><Icon name="briefcase" size={18} /></div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="ss-vp-title">{vac.title}</div>
                      <div className="ss-vp-meta">
                        <span><Icon name="pin" size={12} style={{ verticalAlign: '-2px', marginRight: 3, color: 'var(--fg-3)' }} />{vac.city}</span>
                        <span className="sep">·</span>
                        <span className="ss-vp-sal">{ssFmt(vac.salary_from)} – {ssFmt(vac.salary_to)} ₽</span>
                        <span className="sep">·</span>
                        <span>опыт {vac.experience}</span>
                      </div>
                      <div className="ss-vp-reqs">
                        {vac.skills.slice(0, 5).map((r, i) => <span key={i} className="ss-req-chip">{r}</span>)}
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Шаг 2 — Фильтры */}
        {maxStep >= 2 && (
          <div className={`ssm-step ${stepState(2)}`}>
            <div className="ssm-step-num">{maxStep > 2 ? <Icon name="check" size={18} /> : 2}</div>
            <div className="ssm-step-card">
              <div className="ssm-step-head">
                <span className="ssm-step-title">Фильтры поиска</span>
              </div>
              <div className="ss-glafira-note">
                <span className="em">💃</span> Глафира предложила фильтры из вакансии — можно скорректировать
              </div>

              <div className="ss-field-row" style={{ marginBottom: 14 }}>
                <div className="ss-field">
                  <div className="ss-field-label">Область / профобласть</div>
                  <input className="ss-input" value={area} onChange={e => setArea(e.target.value)} />
                </div>
                <div className="ss-field">
                  <div className="ss-field-label">Проф-роль</div>
                  <input className="ss-input" value={role} onChange={e => setRole(e.target.value)} />
                </div>
                <div className="ss-field" style={{ maxWidth: 160 }}>
                  <div className="ss-field-label">Опыт</div>
                  <input className="ss-input" value={exp} onChange={e => setExp(e.target.value)} />
                </div>
              </div>

              <div className="ss-filter-group">
                <div className="ss-fg-label">Ключевые навыки</div>
                <div className="ss-chip-row">
                  {skills.map((s, i) => (
                    <span key={i} className="ss-chip">
                      {s}
                      <button className="ss-chip-x" onClick={() => setSkills(skills.filter((_, j) => j !== i))} aria-label="Убрать">
                        <Icon name="x" size={11} />
                      </button>
                    </span>
                  ))}
                  <button className="ss-chip-add" onClick={() => {
                    const extra = ['Git', 'Agile', 'English B2', 'SQL', 'Code review'].find(x => !skills.includes(x));
                    if (extra) setSkills([...skills, extra]);
                  }}>
                    <Icon name="plus" size={12} /> навык
                  </button>
                </div>
              </div>

              {maxStep === 2 && (
                <div className="ssm-step-actions">
                  <button className="btn btn-primary btn-sm" onClick={() => setMaxStep(3)}>
                    <Icon name="arrow-right" size={14} /> Далее
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Шаг 3 — Зарплата */}
        {maxStep >= 3 && (
          <div className={`ssm-step ${stepState(3)}`}>
            <div className="ssm-step-num">{maxStep > 3 ? <Icon name="check" size={18} /> : 3}</div>
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
                      onChange={e => setSalFrom(+e.target.value.replace(/\D/g, '') || 0)} />
                    <span className="ss-sal-cur">₽</span>
                  </div>
                </div>
                <span className="ss-sal-dash">—</span>
                <div className="ss-sal-field">
                  <div className="ss-field-label">До</div>
                  <div className="ss-sal-input-wrap">
                    <input className="ss-sal-input" type="text"
                      value={ssFmt(salTo)}
                      onChange={e => setSalTo(+e.target.value.replace(/\D/g, '') || 0)} />
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
                  onClick={() => setInclNoSalary(v => !v)} aria-label="Тумблер" />
              </div>

              {maxStep === 3 && (
                <div className="ssm-step-actions">
                  <button className="btn btn-primary btn-sm" onClick={() => setMaxStep(4)}>
                    <Icon name="arrow-right" size={14} /> Далее
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Шаг 4 — Объём выборки */}
        {maxStep >= 4 && (
          <div className={`ssm-step ${stepState(4)}`}>
            <div className="ssm-step-num">{maxStep > 4 ? <Icon name="check" size={18} /> : 4}</div>
            <div className="ssm-step-card">
              <div className="ssm-step-head">
                <span className="ssm-step-title">Объём выборки</span>
              </div>
              <div className="ssm-step-hint">
                По фильтрам найдено <b className="t-mono" style={{ color: 'var(--fg-1)' }}>~{ssFmt(vac ? vac.found || 0 : 0)}</b> резюме.
                Глафира оценит первые N и пригласит лучших.
              </div>

              <div className="ss-vol-grid">
                <div className="ss-vol-cell">
                  <div className="ss-vol-label">
                    <Icon name="sparkles" size={14} style={{ color: 'var(--ark-violet-500)' }} />
                    Сканировать резюме
                  </div>
                  <div className="ss-vol-sub">Больше — точнее, но дольже и дороже по AI-токенам</div>
                  <div className="ss-vol-input-row">
                    <input className="ss-num-input" type="number" min="50"
                      max={vac ? vac.found || 1000 : 1000} step="50"
                      value={scanN} onChange={e => setScanN(Math.max(50, +e.target.value || 50))} />
                    <input className="ss-slider" type="range" min="50"
                      max={Math.min(vac ? vac.found || 1000 : 1000, 800)} step="50"
                      value={Math.min(scanN, 800)} onChange={e => setScanN(+e.target.value)} />
                  </div>
                </div>
                <div className="ss-vol-cell">
                  <div className="ss-vol-label">
                    <Icon name="mail" size={14} style={{ color: 'var(--ark-green-600)' }} />
                    Пригласить лучших
                  </div>
                  <div className="ss-vol-sub">Скольким топ-кандидатам отправить приглашение</div>
                  <div className="ss-vol-input-row">
                    <input className="ss-num-input" type="number" min="1" max="100"
                      value={inviteM} onChange={e => setInviteM(Math.max(1, +e.target.value || 1))} />
                    <input className="ss-slider" type="range" min="1" max="50"
                      value={Math.min(inviteM, 50)} onChange={e => setInviteM(+e.target.value)} />
                  </div>
                </div>
              </div>

              {/* инфографика воронки */}
              <div className="ss-funnel">
                <div className="ss-fn-node ss-fn-found">
                  <div className="ss-fn-num">{ssFmt(vac ? vac.found || 0 : 0)}</div>
                  <div className="ss-fn-label">Найдено</div>
                  <div className="ss-fn-cap">по фильтрам</div>
                </div>
                <div className="ss-fn-arrow"><Icon name="chevron-right" size={16} /></div>
                <div className="ss-fn-node ss-fn-eval">
                  <div className="ss-fn-num">{ssFmt(scanN)}</div>
                  <div className="ss-fn-label">Оценим</div>
                  <div className="ss-fn-cap">AI-матчинг</div>
                </div>
                <div className="ss-fn-arrow"><Icon name="chevron-right" size={16} /></div>
                <div className="ss-fn-node ss-fn-invite">
                  <div className="ss-fn-num">{ssFmt(inviteM)}</div>
                  <div className="ss-fn-label">Пригласим</div>
                  <div className="ss-fn-cap">топ по баллу</div>
                </div>
              </div>

              <div className="ss-cost-hint">
                <Icon name="alert-triangle" size={15} className="ss-ch-ic" />
                <span>
                  Оценка <b>{ssFmt(scanN)}</b> резюме — примерно <b className="t-mono">~{Math.ceil(scanN * 1.4 / 1000 * 10) / 10} тыс.</b> AI-токенов
                  и <b className="t-mono">~{Math.max(2, Math.round(scanN / 60))} мин</b> работы Глафиры.
                </span>
              </div>

              {maxStep === 4 && (
                <div className="ssm-step-actions">
                  <button className="btn btn-primary btn-sm" onClick={() => setMaxStep(5)}>
                    <Icon name="arrow-right" size={14} /> Далее
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Шаг 5 — Порог приглашения */}
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
                      value={threshold} onChange={e => setThreshold(+e.target.value)} />
                  </div>
                  <div className="ss-thr-ticks">
                    <span>0</span><span>50</span><span>80</span><span>100</span>
                  </div>
                  <div className="ss-thr-explain">
                    <Icon name="sparkles" size={14} className="ss-te-ic" />
                    <span>
                      Пригласим только кандидатов с матчингом <b>выше {threshold}</b> — даже если их меньше {inviteM}.
                      Примерно пройдут порог: <b className="t-mono">~{passThreshold}</b> кандидатов.
                    </span>
                  </div>
                </div>
                <div className="ss-thr-readout">
                  <div className="ss-thr-badge" style={{ background: ssThrColor(threshold).bg, color: ssThrColor(threshold).fg }}>
                    {threshold}
                  </div>
                  <div className="ss-thr-cap">{ssThrColor(threshold).label}</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Итог-панель */}
      {canLaunch && (
        <div className="ss-summary">
          <div className="ss-summary-head">
            <Icon name="sparkles" size={18} style={{ color: 'var(--accent)' }} />
            Готово к запуску
          </div>

          <div className="ss-summary-grid">
            <span className="ss-sum-pill"><span className="k">Вакансия</span><span className="v">{vac!.title}</span></span>
            <span className="ss-sum-pill"><span className="k">Навыков</span><span className="v t-mono">{skills.length}</span></span>
            <span className="ss-sum-pill"><span className="k">ЗП</span><span className="v t-mono">{ssFmt(salFrom)}–{ssFmt(salTo)} ₽</span></span>
            <span className="ss-sum-pill"><span className="k">Сканируем</span><span className="v t-mono">{ssFmt(scanN)}</span></span>
            <span className="ss-sum-pill"><span className="k">Приглашаем топ</span><span className="v t-mono">{inviteM}</span></span>
            <span className="ss-sum-pill"><span className="k">Порог</span><span className="v t-mono">≥ {threshold}</span></span>
          </div>

          <div className="ss-sum-sentence">
            Найдём <b>~{ssFmt(vac!.found || 0)}</b> резюме по фильтрам → оценим первые <span className="hl">{ssFmt(scanN)}</span> AI-матчингом
            → пригласим <span className="hl-g">топ-{inviteM}</span> с баллом <span className="hl-g">≥ {threshold}</span>.
            Приглашённые появятся в воронке вакансии.
          </div>

          <div className="ss-launch-row">
            <button
              className="ss-btn-launch"
              onClick={handleStartSearch}
              disabled={!vac?.hh_published || startSearch.isPending}
            >
              <span className="em">💃</span> Запустить поиск
            </button>
            <div className="ss-launch-est">
              Примерно <span className="t-mono">~{Math.max(2, Math.round(scanN / 60))} мин</span> ·
              расход <span className="t-mono">~{Math.ceil(scanN * 1.4 / 1000 * 10) / 10} тыс.</span> токенов
            </div>
          </div>

          {startSearch.error && (
            <div className="error-banner" style={{ marginTop: '12px' }}>
              {(startSearch.error as any)?.response?.data?.error?.message || 'Ошибка запуска поиска'}
            </div>
          )}
        </div>
      )}

      <SSHistory history={history} />
    </div>
  );
}

// Компоненты состояний
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
          <div className="ss-hflow-ic"><Icon name="search" size={16} /></div>
          <div className="ss-hflow-t">Найдёт</div>
          <div className="ss-hflow-d">Соберёт фильтры из вакансии и найдёт резюме</div>
        </div>
        <div className="ss-hflow-step is-score">
          <div className="ss-hflow-ic"><Icon name="sparkles" size={16} /></div>
          <div className="ss-hflow-t">Оценит</div>
          <div className="ss-hflow-d">Сравнит каждое резюме с описанием вакансии</div>
        </div>
        <div className="ss-hflow-step is-invite">
          <div className="ss-hflow-ic"><Icon name="mail" size={16} /></div>
          <div className="ss-hflow-t">Пригласит</div>
          <div className="ss-hflow-d">Отправит приглашения лучшим автоматически</div>
        </div>
      </div>
      <div style={{ fontSize: 13, color: 'var(--fg-3)' }}>
        ↓ Начните с выбора вакансии
      </div>
    </div>
  );
}

function SSRunning({ runData, vac }: { runData: any; vac: SmartVacancy | null }) {
  if (!runData) return null;

  const phases = [
    { t: 'Глафира ищет резюме на hh.ru…', d: vac ? `по фильтрам вакансии «${vac.title}»` : '' },
    { t: `Оценивает резюме…`, d: `AI-матчинг ${ssFmt(runData.evaluated)} из ${ssFmt(runData.scanned)}` },
    { t: 'Приглашает лучших…', d: `отправляем приглашения топ-${runData.invited} кандидатам` },
  ];

  const stageIndex = runData.stage === 'search' ? 0 : runData.stage === 'eval' ? 1 : 2;
  const cur = phases[stageIndex] || phases[0];

  // Прогресс в процентах
  let pct = 12;
  if (runData.stage === 'eval') {
    pct = 12 + (runData.evaluated / (runData.scanned || 1)) * 70;
  } else if (runData.stage === 'invite' || runData.stage === 'done') {
    pct = 100;
  }

  const stages = ['Поиск', 'Оценка', 'Приглашения'];

  return (
    <div className="ss-run">
      <div className="ss-run-dancer">💃</div>
      <div className="ss-run-phase">{cur.t}</div>
      <div className="ss-run-detail">{cur.d}</div>
      <div className="ss-run-bar"><span style={{ width: `${pct}%` }} /></div>
      <div className="ss-run-stages">
        {stages.map((s, i) => (
          <div key={i} className={`ss-run-stage ${i === stageIndex ? 'active' : ''} ${i < stageIndex ? 'done' : ''}`}>
            <div className="ss-rs-dot">
              {i < stageIndex ? <Icon name="check" size={14} /> : i + 1}
            </div>
            {s}
          </div>
        ))}
      </div>
    </div>
  );
}

function SSResult({ runData, vac, threshold, onNew, onGoFunnel }: {
  runData: any;
  vac: SmartVacancy | null;
  threshold: number;
  onNew: () => void;
  onGoFunnel: () => void;
}) {
  if (!runData) return null;

  return (
    <div>
      <div className="ss-result-head">
        <div className="ss-result-check"><Icon name="check" size={24} /></div>
        <div>
          <h2>Поиск завершён</h2>
          <div className="ss-rh-sub">{vac ? vac.title : ''} · приглашённые добавлены в воронку</div>
        </div>
      </div>

      <div className="ss-result-stats">
        <div className="ss-rstat found">
          <div className="num">{ssFmt(runData.found)}</div>
          <div className="lbl">Найдено резюме <b>по фильтрам</b></div>
        </div>
        <div className="ss-rstat eval">
          <div className="num">{ssFmt(runData.evaluated)}</div>
          <div className="lbl">Оценено <b>AI-матчингом</b></div>
        </div>
        <div className="ss-rstat invite">
          <div className="num">{ssFmt(runData.invited)}</div>
          <div className="lbl">Приглашено <b>с баллом ≥ {threshold}</b></div>
        </div>
      </div>

      {runData.invited_candidates && runData.invited_candidates.length > 0 && (
        <div className="ss-invited-card">
          <div className="ss-invited-head">
            <span className="title">Приглашённые кандидаты</span>
            <span className="count">{runData.invited}</span>
            <div style={{ flex: 1 }} />
            <span className="live-dot">приглашения отправлены</span>
          </div>
          {runData.invited_candidates.map((c: SmartCandidate) => (
            <div key={c.candidate_id} className="ss-inv-row">
              <Avatar name={c.name} size="sm" />
              <div className="ss-inv-main">
                <div className="ss-inv-name">{c.name}</div>
                <div className="ss-inv-meta">{c.age} лет · {c.experience_years} лет опыта · {c.last_company} · {c.city}</div>
              </div>
              <ScoreLabel value={c.score} size="md" />
              <span className="ss-inv-sent"><Icon name="check" size={12} /> приглашён</span>
            </div>
          ))}
        </div>
      )}

      <div className="ss-result-actions">
        <button className="btn btn-primary" onClick={onGoFunnel}>
          <Icon name="filter" size={15} /> Смотреть в воронке
        </button>
        <button className="btn btn-secondary" onClick={onNew}>
          <Icon name="refresh-cw" size={14} /> Новый поиск
        </button>
      </div>

      {runData.error && (
        <div className="error-banner" style={{ marginTop: '16px' }}>
          {runData.error}
        </div>
      )}
    </div>
  );
}

function SSHistory({ history }: { history: any[] }) {
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'long',
      year: 'numeric'
    });
  };

  return (
    <div className="ss-history">
      <div className="ss-history-head">
        <Icon name="clock" size={15} style={{ color: 'var(--fg-3)' }} />
        <span className="title">История поисков</span>
        <span className="count">{history.length}</span>
      </div>
      <div className="ss-hist-list">
        {history.map(h => (
          <div key={h.id} className="ss-hist-row">
            <div className="ss-hist-main">
              <div className="ss-hist-vac">{h.vacancy_title}</div>
              <div className="ss-hist-date">{formatDate(h.created_at)}</div>
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

function SSNoAccess({ onGoSettings }: { onGoSettings: () => void }) {
  return (
    <div className="ss-page">
      <SSHeader />
      <div className="ss-noaccess">
        <div className="ss-noaccess-ic"><Icon name="search" size={28} /></div>
        <div className="ss-noaccess-body">
          <h2>Нужен платный доступ к базе резюме hh.ru</h2>
          <p>
            Активный поиск ищет резюме напрямую в базе hh.ru и отправляет приглашения.
            Для этого у компании должен быть подключён платный доступ к базе резюме hh.
          </p>
          <ul className="ss-noaccess-list">
            <li><span className="ss-na-check"><Icon name="check" size={12} /></span> Поиск по всей базе резюме hh.ru, а не только по откликам</li>
            <li><span className="ss-na-check"><Icon name="check" size={12} /></span> AI-оценка резюме Глафирой против описания вакансии</li>
            <li><span className="ss-na-check"><Icon name="check" size={12} /></span> Автоматические приглашения лучшим кандидатам</li>
          </ul>
          <div className="ss-noaccess-actions">
            <button className="btn btn-primary" onClick={onGoSettings}>
              <Icon name="settings" size={15} /> Подключить в Настройках
            </button>
            <button className="btn btn-secondary">
              <Icon name="external-link" size={14} /> Как это работает
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