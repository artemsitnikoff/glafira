import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { ScoreLabel } from '@/components/ui/ScoreLabel';
import { api } from '@/api/client';
import {
  useSmartAccess,
  useSmartVacancies,
  useStartSmartSearch,
  useSmartRun,
  useSmartHistory,
  useDeriveVacancyFilters,
  useSmartCount,
  useSmartAreaSuggest,
  useSmartInvite,
  useSmartBaseSearch,
  useSmartBaseHistory,
  useSmartBaseCount,
  useMarkBaseRunAdded,
  useSmartBaseRun,
  useSmartBaseIndexStatus,
  type SmartVacancy,
  type SmartCandidate,
  type SmartScoredResume,
  type SmartSearchRequest,
  type SmartCountRequest,
  type SmartAreaSuggestItem,
  type BaseSearchCandidate,
  type BaseSearchRequest,
  type BaseSearchRunStatus,
  type BaseSearchRunItem,
} from '@/api/hooks/useSmartSearch';
import { AssignToVacancyModal } from '../candidates/components/AssignToVacancyModal';
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

type Mode = 'hh' | 'base' | null;

export default function SmartSearchPage() {
  const navigate = useNavigate();

  // Режим: null = развилка, 'hh' = ветка hh, 'base' = ветка по своей базе
  const [mode, setMode] = useState<Mode>(null);

  // Запросы к API
  const { data: accessData } = useSmartAccess();
  const { data: vacancies = [] } = useSmartVacancies();
  const { data: history = [] } = useSmartHistory();
  const { data: baseCount = { count: 0 } } = useSmartBaseCount();
  const startSearch = useStartSmartSearch();
  const deriveFilters = useDeriveVacancyFilters();
  const countMut = useSmartCount();

  // Состояние компонента
  const [phase, setPhase] = useState<Phase>('build');
  const [vacId, setVacId] = useState<string | null>(null);
  const [maxStep, setMaxStep] = useState(1);
  const [selOpen, setSelOpen] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [showCostConfirm, setShowCostConfirm] = useState(false);
  const [detailCandidate, setDetailCandidate] = useState<SmartCandidate | null>(null);

  // Step 2 — фильтры
  const [skills, setSkills] = useState<string[]>([]);
  const [role, setRole] = useState('');
  const [exp, setExp] = useState('');
  const [area, setArea] = useState('');
  const [areaId, setAreaId] = useState<string | null>(null);
  const [areaLabel, setAreaLabel] = useState('');
  const [period, setPeriod] = useState<number | undefined>(undefined);

  // Step 3 — зарплата
  const [salFrom, setSalFrom] = useState(0);
  const [salTo, setSalTo] = useState(0);
  const [inclNoSalary, setInclNoSalary] = useState(true);

  // Step 4 — объём
  const [scanN, setScanN] = useState(300);
  const [inviteM, setInviteM] = useState(20);

  // Step 5 — порог
  const [threshold, setThreshold] = useState(75);

  // Живой счётчик найденных резюме
  const [previewFound, setPreviewFound] = useState<number | null>(null);

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

  // Debounce-эффект для живого счётчика найденных резюме
  useEffect(() => {
    if (!vac) return; // нет выбранной вакансии

    const timer = setTimeout(() => {
      const request: SmartCountRequest = {
        vacancy_id: vac.id,
        area,
        professional_role: role,
        experience: exp,
        skills,
        salary_from: salFrom > 0 ? salFrom : undefined,
        salary_to: salTo > 0 ? salTo : undefined,
        include_no_salary: inclNoSalary,
        area_id: areaId ?? undefined,
        period,
      };

      countMut.mutate(request, {
        onSuccess: (response) => setPreviewFound(response.found),
      });
    }, 500);

    return () => clearTimeout(timer);
    // countMut НЕ в deps: объект мутации меняет ссылку каждый рендер → был бы
    // бесконечный цикл вызовов. countMut.mutate стабилен, поэтому безопасно.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vac?.id, area, role, exp, skills, salFrom, salTo, inclNoSalary, areaId, period]);

  const resetAll = () => {
    setPhase('build');
    setVacId(null);
    setMaxStep(1);
    setSelOpen(false);
    setRunId(null);
    setShowCostConfirm(false);
    setDetailCandidate(null);
    setSkills([]);
    setRole('');
    setExp('');
    setArea('');
    setAreaId(null);
    setAreaLabel('');
    setPeriod(undefined);
    setSalFrom(0);
    setSalTo(0);
    setInclNoSalary(true);
    setScanN(300);
    setInviteM(20);
    setThreshold(75);
    setPreviewFound(null);
  };

  const selectVacancy = (id: string) => {
    const v = vacancies.find(x => x.id === id);
    if (!v) return;

    setVacId(id);
    setSelOpen(false);
    setPreviewFound(null); // новая вакансия → сбросить старое число

    // Сначала заполним превью данные (город/зарплата/found остаются из вакансии)
    setSalFrom(v.salary_from ?? 0);
    setSalTo(v.salary_to ?? 0);

    // объём: берём первых N из найденного
    const proposeScan = Math.min(400, Math.max(100, Math.round((v.found || 300) * 0.6 / 50) * 50));
    setScanN(proposeScan);
    setInviteM(20);

    // Раскрываем шаги сразу (не блокируем переход)
    setMaxStep(Math.max(maxStep, 2));

    // Best-effort префилл из города вакансии
    if (v.city) {
      api.get('/smart/area-suggest', { params: { text: v.city } })
        .then(response => {
          const areas = response.data as SmartAreaSuggestItem[];
          if (areas.length > 0) {
            const topArea = areas[0];
            setAreaId(topArea.id);
            setAreaLabel(topArea.text);
          }
        })
        .catch(() => {
          // Graceful - при ошибке оставляем пустым
        });
    }

    // AI-подбор фильтров area/professional_role/experience/skills
    deriveFilters.mutate(id, {
      onSuccess: (filters) => {
        setArea(filters.area);
        setRole(filters.professional_role);
        setExp(filters.experience);
        setSkills(filters.skills);
      },
      onError: () => {
        // При ошибке оставляем поля пустыми — пользователь дозаполнит
        setArea('');
        setRole('');
        setExp('');
        setSkills([]);
      }
    });
  };

  const handleStartSearch = async (confirmCost = false) => {
    if (!vac) return;

    // Если scan_n > 50 и не подтверждён расход - показать баннер подтверждения
    if (scanN > 50 && !confirmCost && !showCostConfirm) {
      setShowCostConfirm(true);
      return;
    }

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
      confirm_cost: confirmCost,
      area_id: areaId ?? undefined,
      period,
    };

    try {
      const response = await startSearch.mutateAsync(request);
      setRunId(response.run_id);
      setPhase('running');
      setShowCostConfirm(false);
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
  // Приглашения возможны только при платном доступе И опубликованной на hh вакансии;
  // иначе — превью-режим (поиск + AI-оценка без приглашений). Запуск доступен всегда.
  const willInvite = !!(accessData?.has_paid_access && vac?.hh_published);

  // Рендер ветки Б (по своей базе)
  if (mode === 'base') {
    return (
      <div className="ss-page">
        <SSHeader
          onBack={() => setMode(null)}
          sub={<>Поиск среди ваших кандидатов: опишите промтом, кто нужен, — или включите поиск под открытую вакансию с автофильтрами.</>}
        />
        <SSBaseFlow
          vacancies={vacancies}
          onOpenCandidate={(candidateId) => navigate(`/candidates/${candidateId}`)}
          onGoFunnel={() => navigate('/vacancies')} // переход в общий список вакансий
        />
      </div>
    );
  }

  // Рендер развилки (вход в раздел)
  if (mode === null) {
    return (
      <div className="ss-page">
        <SSHeader
          sub={<>С чего начнём? Глафира умеет искать кандидатов <b>снаружи</b> — в базе резюме hh.ru — и <b>внутри</b>, по вашей собственной базе кандидатов.</>}
        />
        <SSFork
          hasHhAccess={accessData?.has_access ?? false}
          poolCount={baseCount.count}
          onPick={setMode}
        />
      </div>
    );
  }

  // Ниже — оригинальная логика ветки hh (mode === 'hh')
  // Нет доступа к hh.ru
  if (!accessData?.has_access) {
    return <SSNoAccess onGoSettings={() => navigate('/settings')} onBack={() => setMode(null)} />;
  }

  // Выполнение
  if (phase === 'running') {
    return (
      <div className="ss-page">
        <SSHeader onBack={() => setMode(null)} />
        <SSRunning
          runData={runData}
          vac={vac}
          onOpenCandidate={setDetailCandidate}
        />
        {detailCandidate && (
          <SSCandidateDetail
            candidate={detailCandidate}
            onClose={() => setDetailCandidate(null)}
          />
        )}
      </div>
    );
  }

  // Результат
  if (phase === 'done' && runData) {
    return (
      <div className="ss-page">
        <SSHeader onBack={() => setMode(null)} />
        <SSResult
          runData={runData}
          vac={vac}
          threshold={threshold}
          accessData={accessData}
          runId={runId}
          onNew={resetAll}
          onGoFunnel={() => navigate(`/vacancies/${vacId}`)}
          onOpenCandidate={setDetailCandidate}
        />
        <SSHistory history={history} />
        {detailCandidate && (
          <SSCandidateDetail
            candidate={detailCandidate}
            onClose={() => setDetailCandidate(null)}
          />
        )}
      </div>
    );
  }

  // Конструктор hh
  return (
    <div className="ss-page">
      <SSHeader onBack={() => setMode(null)} />

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
                <span className="em">💃</span>
                {deriveFilters.isPending
                  ? 'Глафира подбирает фильтры из вакансии…'
                  : 'Глафира предложила фильтры из вакансии — можно скорректировать'}
              </div>

              <div className="ss-field-row" style={{ marginBottom: 14 }}>
                <div className="ss-field">
                  <div className="ss-field-label">Область / профобласть</div>
                  <input
                    className="ss-input"
                    value={area}
                    onChange={e => setArea(e.target.value)}
                    placeholder={deriveFilters.isPending ? 'Глафира подбирает…' : ''}
                  />
                </div>
                <div className="ss-field">
                  <div className="ss-field-label">Проф-роль</div>
                  <input
                    className="ss-input"
                    value={role}
                    onChange={e => setRole(e.target.value)}
                    placeholder={deriveFilters.isPending ? 'Глафира подбирает…' : ''}
                  />
                </div>
                <div className="ss-field" style={{ maxWidth: 160 }}>
                  <div className="ss-field-label">Опыт</div>
                  <input
                    className="ss-input"
                    value={exp}
                    onChange={e => setExp(e.target.value)}
                    placeholder={deriveFilters.isPending ? 'Глафира подбирает…' : ''}
                  />
                </div>
              </div>

              <div className="ss-field-row" style={{ marginBottom: 14 }}>
                <SmartAreaSelector
                  areaId={areaId}
                  areaLabel={areaLabel}
                  onSelect={(id, label) => {
                    setAreaId(id);
                    setAreaLabel(label);
                  }}
                  onClear={() => {
                    setAreaId(null);
                    setAreaLabel('');
                  }}
                />
                <SmartPeriodSelector
                  period={period}
                  onChange={setPeriod}
                />
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
                По фильтрам найдено {previewFound !== null ? <b className="t-mono" style={{ color: 'var(--fg-1)' }}>~{ssFmt(previewFound)}</b> : <b>резюме</b>}{previewFound === null && countMut.isPending ? ' (считаем…)' : ''}.
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
                  <div className="ss-fn-num">{previewFound !== null ? ssFmt(previewFound) : (countMut.isPending ? '…' : '—')}</div>
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
            Найдём {previewFound !== null ? <b>~{ssFmt(previewFound)}</b> : <b>резюме</b>}{previewFound === null && countMut.isPending ? ' (считаем…)' : ''} по фильтрам → оценим первые <span className="hl">{ssFmt(scanN)}</span> AI-матчингом
            {willInvite ? (
              <> → пригласим <span className="hl-g">топ-{inviteM}</span> с баллом <span className="hl-g">≥ {threshold}</span>. Приглашённые появятся в воронке вакансии.</>
            ) : (
              <> → покажем <span className="hl-g">превью лучших</span> с баллом <span className="hl-g">≥ {threshold}</span>.</>
            )}
          </div>

          {!willInvite && (
            <div className="info-banner small" style={{ margin: '12px 0 20px' }}>
              <Icon name="alert-triangle" size={14} />
              <div>
                {!accessData?.has_paid_access
                  ? 'На счёте hh нет квоты на открытие контактов — приглашения не отправляются.'
                  : 'Вакансия не опубликована на hh — приглашать некуда.'}
                {' '}Глафира выполнит поиск и AI-оценку (превью лучших кандидатов).{' '}
                {!accessData?.has_paid_access
                  ? 'Чтобы приглашать — пополните квоту контактов на hh.ru.'
                  : 'Опубликуйте вакансию на hh, чтобы приглашать.'}
              </div>
            </div>
          )}

          {showCostConfirm && (
            <div className="info-banner" style={{ marginBottom: '16px' }}>
              <Icon name="alert-triangle" size={14} />
              <div>
                ⚠ Будет просмотрено до <strong>{ssFmt(scanN)}</strong> резюме — это платные просмотры базы hh. Продолжить?
              </div>
            </div>
          )}

          <div className="ss-launch-row">
            <button
              className="ss-btn-launch"
              onClick={() => showCostConfirm ? handleStartSearch(true) : handleStartSearch()}
              disabled={startSearch.isPending}
            >
              <span className="em">💃</span> {showCostConfirm ? 'Подтвердить и запустить' : (willInvite ? 'Запустить поиск' : 'Найти и оценить')}
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
function SSHeader({ onBack, sub }: { onBack?: () => void; sub?: React.ReactNode }) {
  return (
    <div>
      {onBack && (
        <button className="ss-back" onClick={onBack}>
          <Icon name="chevron-left" size={14} /> Выбор источника
        </button>
      )}
      <div className="ss-head">
        <div className="ss-head-mark">💃</div>
        <div className="ss-head-text">
          <h1>Умный подбор <span className="ss-beta">beta</span></h1>
          <div className="ss-sub">
            {sub || <>Активный поиск кандидатов на hh.ru: Глафира строит фильтры из вакансии, сканирует резюме,
            оценивает их AI-матчингом и приглашает лучших — прямо в воронку.</>}
          </div>
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

function SSRunning({ runData, vac, onOpenCandidate }: {
  runData: any;
  vac: SmartVacancy | null;
  onOpenCandidate?: (candidate: SmartCandidate) => void;
}) {
  if (!runData) return null;

  // Цель оценки = сколько реально оценим: min(план скана, найдено фильтром). Знаменатель
  // ФИКСИРОВАН (не растёт вместе с evaluated, как было со scanned).
  const f = Number(runData.found) || 0;
  const s = Number(runData.scan_n) || 0;
  const evalTarget = (f > 0 && s > 0 ? Math.min(f, s) : (f || s)) || Number(runData.scanned) || Number(runData.evaluated) || 1;
  // Прошедшие порог — считаем ЖИВЬЁМ из scored_candidates (passed_threshold проставляется
  // только на финализации, до неё = 0).
  const passedLive = (runData.scored_candidates || []).filter((c: any) => c.passed).length;

  const phases = [
    { t: 'Глафира ищет резюме на hh.ru…', d: vac ? `по фильтрам вакансии «${vac.title}»` : '' },
    { t: `Оценивает резюме…`, d: `AI-матчинг ${ssFmt(runData.evaluated)} из ${ssFmt(evalTarget)}` },
    { t: 'Готовим результаты…', d: `финализируем оценку кандидатов` },
  ];

  const stageIndex = runData.stage === 'search' ? 0 : runData.stage === 'eval' ? 1 : 2;
  const cur = phases[stageIndex] || phases[0];

  // Прогресс в процентах
  let pct = 12;
  if (runData.stage === 'eval') {
    pct = 12 + Math.min(1, runData.evaluated / evalTarget) * 70;
  } else if (runData.stage === 'finalizing' || runData.stage === 'invite' || runData.stage === 'done') {
    pct = 100;
  }

  const stages = ['Поиск', 'Оценка', 'Готово'];

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

      {/* Живые баллы во время оценки */}
      {runData.scored_candidates && runData.scored_candidates.length > 0 && (
        <div style={{ marginTop: '24px' }}>
          <div className="ss-invited-card">
            <div className="ss-invited-head">
              <span className="title">Оценённые кандидаты</span>
              <span className="count">{runData.scored_candidates.length}</span>
              <div style={{ flex: 1 }} />
              <span className="live-dot">оценка в реальном времени</span>
            </div>
            {runData.scored_candidates.map((c: any, index: number) => (
              <div
                key={c.candidate_id || index}
                className="ss-inv-row ss-inv-row-clickable"
                style={{ opacity: c.passed === false ? 0.6 : 1 }}
                onClick={() => onOpenCandidate?.(c)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onOpenCandidate?.(c);
                  }
                }}
                tabIndex={0}
                role="button"
                aria-label={`Открыть детальный разбор кандидата ${c.name}`}
              >
                <Avatar name={c.name} size="sm" />
                <div className="ss-inv-main">
                  <div className="ss-inv-name">{c.name}</div>
                  <div className="ss-inv-meta">{c.age} лет · {c.experience_years} лет опыта · {c.last_company} · {c.city}</div>
                </div>
                <ScoreLabel value={c.score} size="md" />
                <span className="ss-inv-sent" style={{
                  background: c.passed === false ? 'var(--ark-gray-200)' : 'var(--ark-green-100)',
                  color: c.passed === false ? 'var(--fg-3)' : 'var(--ark-green-600)'
                }}>
                  <Icon name={c.passed === false ? 'x' : 'check'} size={12} />
                  {c.passed === false ? 'не прошёл' : 'прошёл порог'}
                </span>
              </div>
            ))}
          </div>
          <div style={{
            marginTop: '12px',
            fontSize: '13px',
            color: 'var(--fg-2)',
            textAlign: 'center'
          }}>
            Оценено {runData.evaluated} из {evalTarget} · Прошли порог: <strong>{passedLive}</strong>
          </div>
        </div>
      )}

      {/* Журнал в процессе выполнения */}
      {runData.log && runData.log.length > 0 && (
        <details style={{ marginTop: '24px' }}>
          <summary style={{
            cursor: 'pointer',
            fontSize: '13px',
            fontWeight: '600',
            color: 'var(--fg-2)',
            marginBottom: '8px'
          }}>
            Журнал поиска
          </summary>
          <div style={{
            background: 'var(--bg-panel-2)',
            border: '1px solid var(--border-1)',
            borderRadius: '8px',
            padding: '12px',
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            lineHeight: '1.4',
            color: 'var(--fg-2)',
            maxHeight: '200px',
            overflowY: 'auto'
          }}>
            {runData.log.map((line: string, i: number) => (
              <div key={i}>{line}</div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function SSResult({ runData, vac, threshold, accessData, runId, onNew, onGoFunnel, onOpenCandidate }: {
  runData: any;
  vac: SmartVacancy | null;
  threshold: number;
  accessData?: any;
  runId: string | null;
  onNew: () => void;
  onGoFunnel: () => void;
  onOpenCandidate?: (candidate: SmartCandidate) => void;
}) {
  if (!runData) return null;

  const isPreview = runData.invites_skipped === true;
  const passedCandidates = (runData.scored_candidates || []).filter((c: SmartCandidate) => c.passed);
  const noOnePassed = passedCandidates.length === 0;
  const canInvite = !!(accessData?.has_paid_access && vac?.hh_published);

  // Состояние для выбора кандидатов к приглашению
  const [selectedResumeIds, setSelectedResumeIds] = useState<Set<string>>(new Set());
  const [inviteResults, setInviteResults] = useState<any>(null);

  const smartInvite = useSmartInvite(runId || '');

  // Обработчики выбора
  const toggleSelect = (resumeId: string, invited: boolean) => {
    if (invited) return; // нельзя выбирать уже приглашённых
    setSelectedResumeIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(resumeId)) {
        newSet.delete(resumeId);
      } else {
        newSet.add(resumeId);
      }
      return newSet;
    });
  };

  const selectAll = () => {
    const allEligible = passedCandidates
      .filter((c: SmartCandidate) => c.hh_resume_id && !c.invited)
      .map((c: SmartCandidate) => c.hh_resume_id!)
      .filter(Boolean);
    setSelectedResumeIds(new Set(allEligible));
  };

  const clearSelection = () => {
    setSelectedResumeIds(new Set());
  };

  const handleInvite = async () => {
    const resumeIds = Array.from(selectedResumeIds);
    if (resumeIds.length === 0) return;

    try {
      const response = await smartInvite.mutateAsync(resumeIds);
      setInviteResults(response);

      // Обновляем состояние кандидатов локально
      if (runData.scored_candidates) {
        response.results.forEach(result => {
          const candidate = runData.scored_candidates.find((c: SmartCandidate) => c.hh_resume_id === result.resume_id);
          if (candidate && result.status === 'invited') {
            candidate.invited = true;
          }
        });
      }

      // Очищаем выбор приглашённых
      setSelectedResumeIds(prev => {
        const newSet = new Set(prev);
        response.results.forEach(result => {
          if (result.status === 'invited') {
            newSet.delete(result.resume_id);
          }
        });
        return newSet;
      });
    } catch (error) {
      // Ошибка обрабатывается через smartInvite.error в UI
    }
  };

  return (
    <div>
      <div className="ss-result-head">
        <div className="ss-result-check"><Icon name="check" size={24} /></div>
        <div>
          <h2>Оценка завершена</h2>
          <div className="ss-rh-sub">
            {vac ? vac.title : ''}{passedCandidates.length > 0 ? ' · выберите кандидатов для приглашения ниже' : ''}
          </div>
        </div>
      </div>

      {/* Честная итоговая заметка */}
      {runData.note && (
        <div className={`ss-sum-sentence ${noOnePassed ? 'info-banner muted' : ''}`} style={{ marginBottom: '18px' }}>
          {runData.note}
        </div>
      )}

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
          <div className="num">{isPreview ? ssFmt(passedCandidates.length) : ssFmt(runData.invited)}</div>
          <div className="lbl">{isPreview ? 'Прошли порог' : `Приглашено <b>с баллом ≥ ${threshold}</b>`}</div>
        </div>
      </div>

      {/* Прошедшие порог — выбор и приглашение */}
      {passedCandidates.length > 0 && (
        <div className="ss-invited-card">
          <div className="ss-invited-head">
            <span className="title">Прошедшие порог — выберите кого пригласить</span>
            <span className="count">Прошли: {passedCandidates.length}</span>
            <div style={{ flex: 1 }} />
            {inviteResults && (
              <span className="live-dot">Приглашено: {inviteResults.invited_count}</span>
            )}
          </div>

          {/* Гейт приглашений */}
          {!canInvite && (
            <div className="info-banner" style={{ margin: '12px 0' }}>
              <Icon name="alert-triangle" size={14} />
              <div>
                {!accessData?.has_paid_access
                  ? 'На счёте hh нет квоты на открытие контактов — приглашения недоступны (поиск и AI-оценка работают без неё). Квота пополняется на стороне hh.ru.'
                  : 'Вакансия не опубликована на hh.ru — приглашать некуда.'}
              </div>
            </div>
          )}

          {/* Управление выбором */}
          {canInvite && (
            <div className="ss-invite-controls">
              <label className="ss-master-checkbox">
                <input
                  type="checkbox"
                  checked={selectedResumeIds.size > 0 && passedCandidates.filter((c: SmartCandidate) => c.hh_resume_id && !c.invited).every((c: SmartCandidate) => selectedResumeIds.has(c.hh_resume_id!))}
                  onChange={(e) => {
                    if (e.target.checked) {
                      selectAll();
                    } else {
                      clearSelection();
                    }
                  }}
                />
                Выбрать всех
              </label>
              <button
                className="btn btn-primary btn-sm"
                disabled={selectedResumeIds.size === 0 || smartInvite.isPending}
                onClick={handleInvite}
              >
                <Icon name="mail" size={14} />
                Пригласить выбранных ({selectedResumeIds.size})
              </button>
            </div>
          )}

          {/* Список кандидатов */}
          {passedCandidates.map((c: SmartCandidate, index: number) => (
            <div
              key={c.candidate_id || index}
              className={`ss-inv-row ss-inv-row-clickable ${canInvite ? 'ss-inv-row-selectable' : ''}`}
              onClick={() => onOpenCandidate?.(c)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onOpenCandidate?.(c);
                }
              }}
              tabIndex={0}
              role="button"
              aria-label={`Открыть детальный разбор кандидата ${c.name}`}
            >
              {canInvite && c.hh_resume_id && (
                <input
                  type="checkbox"
                  className="ss-row-checkbox"
                  checked={selectedResumeIds.has(c.hh_resume_id)}
                  disabled={c.invited}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => {
                    e.stopPropagation();
                    toggleSelect(c.hh_resume_id!, !!c.invited);
                  }}
                />
              )}
              <Avatar name={c.name} size="sm" />
              <div className="ss-inv-main">
                <div className="ss-inv-name">{c.name}</div>
                <div className="ss-inv-meta">{c.age} лет · {c.experience_years} лет опыта · {c.last_company} · {c.city}</div>
              </div>
              <ScoreLabel value={c.score} size="md" />
              <span className="ss-inv-sent" style={{
                background: c.invited ? 'var(--ark-green-100)' : 'var(--ark-blue-100)',
                color: c.invited ? 'var(--ark-green-600)' : 'var(--accent)'
              }}>
                <Icon name={c.invited ? 'check' : 'user'} size={12} />
                {c.invited ? '✓ приглашён' : 'прошёл порог'}
              </span>
              {c.hh_resume_id && (
                <a
                  href={`https://hh.ru/resume/${c.hh_resume_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="icon-btn"
                  onClick={(e) => e.stopPropagation()}
                  title="Открыть на hh.ru"
                  style={{ marginLeft: '8px' }}
                >
                  <Icon name="open" size={14} />
                </a>
              )}
            </div>
          ))}

          {/* Результаты приглашения */}
          {inviteResults && (
            <div className="ss-invite-results">
              <div className="ss-ir-summary">
                <Icon name="check-circle" size={16} style={{ color: 'var(--ark-green-600)' }} />
                Приглашено: <strong>{inviteResults.invited_count}</strong>
              </div>
              {inviteResults.results.some((r: any) => r.status === 'already' || r.status === 'error') && (
                <div className="ss-ir-details">
                  {inviteResults.results.map((result: any, i: number) => (
                    result.status !== 'invited' && (
                      <div key={i} className={`ss-ir-item ss-ir-${result.status}`}>
                        <span className="ss-ir-name">{result.name || result.resume_id}</span>
                        <span className="ss-ir-status">
                          {result.status === 'already' ? (result.message || 'уже в базе') : `ошибка: ${result.message}`}
                        </span>
                      </div>
                    )
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Если никто не прошёл порог — показать всех оценённых */}
      {noOnePassed && runData.scored_candidates && runData.scored_candidates.length > 0 && (
        <div className="ss-invited-card">
          <div className="ss-invited-head">
            <span className="title">Все оценённые кандидаты</span>
            <span className="count">{runData.scored_candidates.length}</span>
            <div style={{ flex: 1 }} />
            <span className="live-dot">порог не пройден</span>
          </div>
          {runData.scored_candidates.map((c: SmartCandidate, index: number) => (
            <div
              key={c.candidate_id || index}
              className="ss-inv-row ss-inv-row-clickable"
              style={{ opacity: c.passed === false ? 0.6 : 1 }}
              onClick={() => onOpenCandidate?.(c)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onOpenCandidate?.(c);
                }
              }}
              tabIndex={0}
              role="button"
              aria-label={`Открыть детальный разбор кандидата ${c.name}`}
            >
              <Avatar name={c.name} size="sm" />
              <div className="ss-inv-main">
                <div className="ss-inv-name">{c.name}</div>
                <div className="ss-inv-meta">{c.age} лет · {c.experience_years} лет опыта · {c.last_company} · {c.city}</div>
              </div>
              <ScoreLabel value={c.score} size="md" />
              <span className="ss-inv-sent" style={{
                background: c.passed === false ? 'var(--ark-gray-200)' : 'var(--ark-blue-100)',
                color: c.passed === false ? 'var(--fg-3)' : 'var(--accent)'
              }}>
                <Icon name={c.passed === false ? 'x' : 'check'} size={12} />
                {c.passed === false ? 'не прошёл' : `${c.score} баллов`}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Журнал поиска */}
      {runData.log && runData.log.length > 0 && (
        <details style={{ marginTop: '18px', marginBottom: '18px' }}>
          <summary style={{
            cursor: 'pointer',
            fontSize: '13px',
            fontWeight: '600',
            color: 'var(--fg-2)',
            marginBottom: '8px'
          }}>
            Журнал поиска
          </summary>
          <div style={{
            background: 'var(--bg-panel-2)',
            border: '1px solid var(--border-1)',
            borderRadius: '8px',
            padding: '12px',
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            lineHeight: '1.4',
            color: 'var(--fg-2)',
            maxHeight: '200px',
            overflowY: 'auto'
          }}>
            {runData.log.map((line: string, i: number) => (
              <div key={i}>{line}</div>
            ))}
          </div>
        </details>
      )}

      <div className="ss-result-actions">
        {!isPreview && (
          <button className="btn btn-primary" onClick={onGoFunnel}>
            <Icon name="filter" size={15} /> Смотреть в воронке
          </button>
        )}
        <button className="btn btn-secondary" onClick={onNew}>
          <Icon name="refresh-cw" size={14} /> Новый поиск
        </button>
      </div>

      {runData.error && (
        <div className="error-banner" style={{ marginTop: '16px' }}>
          {runData.error}
        </div>
      )}

      {smartInvite.error && (
        <div className="error-banner" style={{ marginTop: '16px' }}>
          {(smartInvite.error as any)?.response?.data?.error?.message || 'Ошибка отправки приглашений'}
        </div>
      )}
    </div>
  );
}

function SSHistory({ history }: { history: any[] }) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

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
          <div
            key={h.id}
            className="ss-hist-row ss-hist-row-clickable"
            onClick={() => setSelectedRunId(h.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setSelectedRunId(h.id);
              }
            }}
            tabIndex={0}
            role="button"
            aria-label={`Открыть результаты поиска для вакансии ${h.vacancy_title}`}
          >
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
              <div className="ss-hist-stat">
                <div className="hv">{ssFmt(h.passed)}</div>
                <div className="hl">прошло отбор</div>
              </div>
              <div className="ss-hist-stat invite">
                <div className="hv">{h.invited}</div>
                <div className="hl">приглашено</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {selectedRunId && (
        <SSHistoryRunDetail
          runId={selectedRunId}
          onClose={() => setSelectedRunId(null)}
        />
      )}
    </div>
  );
}

function SSNoAccess({ onGoSettings, onBack }: { onGoSettings: () => void; onBack?: () => void }) {
  return (
    <div className="ss-page">
      <SSHeader onBack={onBack} />
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

// Компонент автокомплита для выбора города/региона
function SmartAreaSelector({
  areaId,
  areaLabel,
  onSelect,
  onClear,
}: {
  areaId: string | null;
  areaLabel: string;
  onSelect: (id: string, label: string) => void;
  onClear: () => void;
}) {
  const [inputValue, setInputValue] = useState('');
  const [debouncedValue, setDebouncedValue] = useState('');
  const [isOpen, setIsOpen] = useState(false);

  // Debounce для запросов
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(inputValue);
    }, 300);
    return () => clearTimeout(timer);
  }, [inputValue]);

  const { data: suggestions = [] } = useSmartAreaSuggest(debouncedValue);

  const displayValue = areaId ? areaLabel : inputValue;

  const handleSelect = (item: SmartAreaSuggestItem) => {
    onSelect(item.id, item.text);
    setInputValue('');
    setIsOpen(false);
  };

  const handleClear = () => {
    onClear();
    setInputValue('');
    setIsOpen(false);
  };

  const handleAllRussia = () => {
    onSelect('113', 'Вся Россия');
    setInputValue('');
    setIsOpen(false);
  };

  return (
    <div className="ss-field" style={{ position: 'relative' }}>
      <div className="ss-field-label">Город / регион</div>
      <div className="ss-area-input-wrap">
        <input
          className="ss-input"
          value={displayValue}
          onChange={(e) => {
            setInputValue(e.target.value);
            setIsOpen(true);
            if (!e.target.value && areaId) {
              onClear();
            }
          }}
          onFocus={() => {
            if (!areaId) setIsOpen(true);
          }}
          placeholder="Начните печатать город..."
        />
        {areaId && (
          <button className="ss-area-clear" onClick={handleClear} type="button">
            <Icon name="x" size={14} />
          </button>
        )}
      </div>

      {isOpen && !areaId && (
        <div className="ss-area-dropdown">
          <div className="ss-area-option" onClick={handleAllRussia}>
            <Icon name="pin" size={16} className="ss-area-icon" />
            <span>Вся Россия</span>
          </div>
          {suggestions.map((item) => (
            <div
              key={item.id}
              className="ss-area-option"
              onClick={() => handleSelect(item)}
            >
              <Icon name="pin" size={16} className="ss-area-icon" />
              <span>{item.text}</span>
            </div>
          ))}
          {inputValue.trim().length >= 2 && suggestions.length === 0 && (
            <div className="ss-area-empty">Ничего не найдено</div>
          )}
        </div>
      )}
    </div>
  );
}

// Компонент селектора свежести резюме
function SmartPeriodSelector({
  period,
  onChange,
}: {
  period: number | undefined;
  onChange: (period: number | undefined) => void;
}) {
  const options = [
    { value: undefined, label: 'За всё время' },
    { value: 1, label: 'За сутки' },
    { value: 3, label: 'За 3 дня' },
    { value: 7, label: 'За неделю' },
    { value: 30, label: 'За месяц' },
    { value: 365, label: 'За год' },
  ];

  return (
    <div className="ss-field" style={{ maxWidth: 180 }}>
      <div className="ss-field-label">Свежесть резюме</div>
      <select
        className="ss-input ss-period-select"
        value={period ?? ''}
        onChange={(e) => {
          const val = e.target.value;
          onChange(val === '' ? undefined : Number(val));
        }}
      >
        {options.map((opt) => (
          <option key={opt.value ?? 'all'} value={opt.value ?? ''}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

// Компонент детального просмотра кандидата из умного подбора
function SSCandidateDetail({
  candidate,
  onClose,
}: {
  candidate: SmartCandidate;
  onClose: () => void;
}) {
  // Форматирование стажа в человекочитаемый вид
  const formatExperience = (months: number | undefined): string => {
    if (!months) return '';
    const years = Math.floor(months / 12);
    const remainingMonths = months % 12;
    if (years === 0) return `${remainingMonths} мес`;
    if (remainingMonths === 0) return `${years} лет`;
    return `${years} лет ${remainingMonths} мес`;
  };

  // Проверка пустого резюме
  const isEmptyResume = (resume: SmartScoredResume | undefined): boolean => {
    if (!resume) return true;
    return (!resume.experience || resume.experience.length === 0) &&
           (!resume.skills || resume.skills.length === 0);
  };

  // Вычисления для requirements_match
  const totalPoints = candidate.requirements_match?.reduce((sum, match) => sum + match.points, 0) || 0;
  const totalWeight = candidate.requirements_match?.reduce((sum, match) => sum + match.weight, 0) || 0;

  // Обработка Esc
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  return (
    <div className="ss-page-modal-overlay" onClick={onClose}>
      <div className="ss-page-modal-content" onClick={(e) => e.stopPropagation()}>
        {/* Шапка */}
        <div className="ss-page-modal-header">
          <div className="ss-page-modal-title-area">
            <h2 className="ss-page-modal-title">
              {candidate.name || 'Без имени'}
            </h2>
            <div className="ss-page-modal-meta">
              <ScoreLabel value={candidate.score} size="lg" />
              <span className="ss-page-modal-verdict">{candidate.verdict}</span>
              {candidate.passed !== undefined && (
                <span className={`ss-page-modal-threshold ${candidate.passed ? 'passed' : 'failed'}`}>
                  {candidate.passed ? '✓ Прошёл порог' : '✗ Не прошёл порог'}
                </span>
              )}
            </div>
          </div>
          <button
            className="ss-page-modal-close"
            onClick={onClose}
            aria-label="Закрыть"
          >
            <Icon name="x" size={20} />
          </button>
        </div>

        <div className="ss-page-modal-body">
          {/* Резюме (тело) */}
          <section className="ss-page-modal-section">
            <h3 className="ss-page-modal-section-title">
              <Icon name="file-text" size={16} />
              Резюме
            </h3>

            {isEmptyResume(candidate.resume) ? (
              <div className="ss-page-empty-resume">
                <Icon name="alert-triangle" size={20} className="ss-page-empty-resume-icon" />
                <div>
                  <strong>hh вернул резюме без содержимого</strong>
                  <p>Тело резюме скрыто или пустое — вероятно, поэтому низкий балл</p>
                </div>
              </div>
            ) : (
              <div className="ss-page-resume-content">
                {candidate.resume?.title && (
                  <div className="ss-page-resume-title">{candidate.resume.title}</div>
                )}

                <div className="ss-page-resume-meta">
                  {candidate.resume?.total_experience_months && (
                    <span>Общий стаж: {formatExperience(candidate.resume.total_experience_months)}</span>
                  )}
                  {candidate.resume?.city && <span>Город: {candidate.resume.city}</span>}
                  {candidate.resume?.age && <span>Возраст: {candidate.resume.age} лет</span>}
                  {candidate.resume?.salary && <span>Ожидаемая ЗП: {candidate.resume.salary}</span>}
                </div>

                {candidate.resume?.experience && candidate.resume.experience.length > 0 && (
                  <div className="ss-page-resume-block">
                    <h4>Опыт работы</h4>
                    {candidate.resume.experience.map((exp, index) => (
                      <div key={index} className="ss-page-resume-exp">
                        <div className="ss-page-resume-exp-header">
                          {exp.position && <span className="ss-page-resume-exp-position">{exp.position}</span>}
                          {exp.company && <span className="ss-page-resume-exp-company">{exp.company}</span>}
                          {exp.period && <span className="ss-page-resume-exp-period">{exp.period}</span>}
                        </div>
                        {exp.description && (
                          <div className="ss-page-resume-exp-desc">{exp.description}</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {candidate.resume?.skills && candidate.resume.skills.length > 0 && (
                  <div className="ss-page-resume-block">
                    <h4>Навыки</h4>
                    <div className="ss-page-resume-skills">
                      {candidate.resume.skills.map((skill, index) => (
                        <span key={index} className="ss-page-resume-skill">{skill}</span>
                      ))}
                    </div>
                  </div>
                )}

                {candidate.resume?.education && (
                  <div className="ss-page-resume-block">
                    <h4>Образование</h4>
                    <div className="ss-page-resume-education">{candidate.resume.education}</div>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* Разбор AI (как в карточке Глафиры) */}
          <section className="ss-page-modal-section">
            <h3 className="ss-page-modal-section-title">
              <Icon name="sparkles" size={16} />
              Анализ AI
            </h3>

            {candidate.summary && (
              <div className="ss-page-ai-summary">{candidate.summary}</div>
            )}

            {candidate.strengths && candidate.strengths.length > 0 && (
              <div className="ss-page-ai-block ss-page-ai-good">
                <div className="ss-page-ai-header ss-page-ai-header-good">
                  <span className="ss-page-ai-emoji">✅</span>
                  Сильные стороны
                </div>
                <ul className="ss-page-ai-list">
                  {candidate.strengths.map((strength, index) => (
                    <li key={index}>{strength}</li>
                  ))}
                </ul>
              </div>
            )}

            {candidate.risks && candidate.risks.length > 0 && (
              <div className="ss-page-ai-block ss-page-ai-warn">
                <div className="ss-page-ai-header ss-page-ai-header-warn">
                  <span className="ss-page-ai-emoji">⚠️</span>
                  Слабые стороны
                </div>
                <ul className="ss-page-ai-list">
                  {candidate.risks.map((risk, index) => (
                    <li key={index}>{risk}</li>
                  ))}
                </ul>
              </div>
            )}

            {candidate.requirements_match && candidate.requirements_match.length > 0 && (
              <div className="ss-page-requirements">
                <h4 className="ss-page-requirements-title">
                  Разбор по критериям
                  <span className="ss-page-requirements-total">
                    <span className="t-mono">{totalPoints}</span> / <span className="t-mono">{totalWeight}</span>
                  </span>
                </h4>
                <div className="ss-page-requirements-list">
                  {candidate.requirements_match.map((match, index) => {
                    const pct = match.weight ? Math.round((match.points / match.weight) * 100) : 0;
                    const color = match.weight === 0 ? 'gray' : pct >= 80 ? 'green' : pct >= 40 ? 'yellow' : 'red';
                    return (
                      <div key={index} className={`ss-page-requirements-item ss-page-req-${color}`}>
                        <div className="ss-page-req-head">
                          <span className="ss-page-req-criterion">{match.criterion}</span>
                          <span className="ss-page-req-points t-mono">
                            {match.points}<span className="ss-page-req-points-max"> / {match.weight || '—'}</span>
                          </span>
                        </div>
                        <div className="ss-page-req-bar">
                          <span style={{ width: `${pct}%` }} />
                        </div>
                        {match.comment && (
                          <div className="ss-page-req-comment">{match.comment}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {candidate.forecast && (
              <div className="ss-page-ai-forecast">{candidate.forecast}</div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

// Компонент детального просмотра прошедших кандидатов из истории
function SSHistoryRunDetail({
  runId,
  onClose,
}: {
  runId: string;
  onClose: () => void;
}) {
  const { data: runData } = useSmartRun(runId, true);

  // Обработка Esc
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  if (!runData) {
    return (
      <div className="ss-page-modal-overlay" onClick={onClose}>
        <div className="ss-page-modal-content" onClick={(e) => e.stopPropagation()}>
          <div className="ss-page-modal-header">
            <div className="ss-page-modal-title-area">
              <h2 className="ss-page-modal-title">Загрузка...</h2>
            </div>
            <button
              className="ss-page-modal-close"
              onClick={onClose}
              aria-label="Закрыть"
            >
              <Icon name="x" size={20} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  const passedCandidates = (runData.scored_candidates || []).filter((c: SmartCandidate) => c.passed);

  return (
    <div className="ss-page-modal-overlay" onClick={onClose}>
      <div className="ss-page-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="ss-page-modal-header">
          <div className="ss-page-modal-title-area">
            <h2 className="ss-page-modal-title">
              Прошли порог: {passedCandidates.length}
            </h2>
            <div className="ss-page-modal-meta">
              <span>Результаты поиска</span>
            </div>
          </div>
          <button
            className="ss-page-modal-close"
            onClick={onClose}
            aria-label="Закрыть"
          >
            <Icon name="x" size={20} />
          </button>
        </div>

        <div className="ss-page-modal-body">
          {passedCandidates.length > 0 ? (
            <div className="ss-invited-card">
              <div className="ss-invited-head">
                <span className="title">Прошли порог: {passedCandidates.length}</span>
                <div style={{ flex: 1 }} />
                <span className="live-dot">Приглашено: {runData.invited}</span>
              </div>

              {passedCandidates.map((c: SmartCandidate, index: number) => (
                <div key={c.candidate_id || index} className="ss-inv-row">
                  <Avatar name={c.name} size="sm" />
                  <div className="ss-inv-main">
                    <div className="ss-inv-name">{c.name}</div>
                    <div className="ss-inv-meta">{c.age} лет · {c.experience_years} лет опыта · {c.last_company} · {c.city}</div>
                  </div>
                  <ScoreLabel value={c.score} />
                  {c.hh_resume_id && (
                    <a
                      href={`https://hh.ru/resume/${c.hh_resume_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="icon-btn"
                      title="Открыть на hh.ru"
                      style={{ marginLeft: '8px' }}
                    >
                      <Icon name="open" size={14} />
                    </a>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div style={{
              padding: '40px 20px',
              textAlign: 'center',
              color: 'var(--fg-3)',
              fontSize: '14px'
            }}>
              Никто не прошёл порог
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ====== Развилка: выбор источника подбора ======
function SSFork({ hasHhAccess, poolCount, onPick }: {
  hasHhAccess: boolean;
  poolCount: number;
  onPick: (mode: Mode) => void;
}) {
  return (
    <div className="ssf-grid">
      {/* hh.ru */}
      <button className="ssf-card ssf-hh" onClick={() => onPick('hh')}>
        <div className="ssf-card-top">
          <div className="ssf-card-ic ic-hh"><Icon name="zap" size={22} /></div>
          {hasHhAccess
            ? <span className="ssf-tag on"><Icon name="check" size={11} /> доступ к hh подключён</span>
            : <span className="ssf-tag off"><Icon name="key" size={11} /> нужен платный доступ</span>}
        </div>
        <div className="ssf-card-title">Умный подбор на hh.ru</div>
        <div className="ssf-card-desc">
          Активный поиск в базе резюме hh.ru. Глафира строит фильтры из вакансии,
          сканирует резюме, оценивает AI-матчингом и приглашает лучших.
        </div>
        <ul className="ssf-card-list">
          <li><Icon name="search" size={14} /> Поиск по всей базе резюме hh.ru</li>
          <li><Icon name="sparkles" size={14} /> AI-оценка против описания вакансии</li>
          <li><Icon name="mail" size={14} /> Авто-приглашения в воронку</li>
        </ul>
        <span className="ssf-go">Выбрать <Icon name="arrow-right" size={15} /></span>
      </button>

      {/* своя база */}
      <button className="ssf-card ssf-base" onClick={() => onPick('base')}>
        <div className="ssf-card-top">
          <div className="ssf-card-ic ic-base"><Icon name="users" size={22} /></div>
          <span className="ssf-tag neutral"><span className="t-mono">{ssFmt(poolCount)}</span> кандидатов в базе</span>
        </div>
        <div className="ssf-card-title">Подбор по своей базе кандидатов</div>
        <div className="ssf-card-desc">
          AI-поиск среди уже накопленных кандидатов. Опишите словами, кто нужен,
          или ищите под открытую вакансию с автофильтрами.
        </div>
        <ul className="ssf-card-list">
          <li><Icon name="message-circle" size={14} /> Поиск промтом — «напишите, кто нужен»</li>
          <li><Icon name="briefcase" size={14} /> Или поиск под открытую вакансию</li>
          <li><Icon name="filter" size={14} /> Автофильтры как на hh — по базе</li>
        </ul>
        <span className="ssf-go">Выбрать <Icon name="arrow-right" size={15} /></span>
      </button>
    </div>
  );
}

// ====== Ветка Б: поиск по своей базе ======
function SSBaseFlow({ vacancies, onOpenCandidate, onGoFunnel }: {
  vacancies: SmartVacancy[];
  onOpenCandidate: (candidateId: string) => void;
  onGoFunnel: () => void;
}) {
  const [byVacancy, setByVacancy] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [phase, setPhase] = useState<'build' | 'running' | 'done'>('build');

  // режим вакансии
  const [vacId, setVacId] = useState<string | null>(null);
  const [selOpen, setSelOpen] = useState(false);
  const [skills, setSkills] = useState<string[]>([]);
  const [role, setRole] = useState('');
  const [exp, setExp] = useState('');
  const [city, setCity] = useState('');
  const [salFrom, setSalFrom] = useState(0);
  const [salTo, setSalTo] = useState(0);
  const [newSkill, setNewSkill] = useState('');

  // результаты
  const [runId, setRunId] = useState<string | null>(null);
  const [added, setAdded] = useState<Set<string>>(new Set());

  // хуки
  const searchMutation = useSmartBaseSearch();
  const { data: baseHistory = [] } = useSmartBaseHistory();
  const markAdded = useMarkBaseRunAdded();
  const deriveFilters = useDeriveVacancyFilters();
  const { data: runData } = useSmartBaseRun(runId, phase === 'running' || phase === 'done');

  // модал назначения
  const [assignCandidateId, setAssignCandidateId] = useState<string | null>(null);

  const vac = useMemo(() => vacancies.find(v => v.id === vacId) || null, [vacancies, vacId]);

  // Обработчик завершения запуска
  useEffect(() => {
    if (runData && phase === 'running') {
      if (runData.status === 'done' || runData.status === 'error') {
        setPhase('done');
      }
    }
  }, [runData, phase]);

  const selectVacancy = (id: string) => {
    const v = vacancies.find(x => x.id === id);
    if (!v) return;
    setVacId(id);
    setSelOpen(false);

    // AI-подбор фильтров (бек отдаёт и город/ЗП прямо из вакансии)
    deriveFilters.mutate(id, {
      onSuccess: (filters) => {
        setRole(filters.professional_role);
        setExp(filters.experience);
        setSkills(filters.skills);
        setCity(filters.city || '');
        setSalFrom(filters.salary_from || 0);
        setSalTo(filters.salary_to || 0);
      },
      onError: () => {
        setRole('');
        setExp('');
        setSkills([]);
        setCity('');
        setSalFrom(0);
        setSalTo(0);
      }
    });
  };

  const canSearch = byVacancy ? !!vac : prompt.trim().length > 2;

  const runSearch = async () => {
    if (!canSearch) return;

    const request: BaseSearchRequest = byVacancy && vac
      ? {
          search_type: 'vacancy',
          vacancy_id: vac.id,
          // Шлём (правленые) автофильтры — бек ищет по базе именно по ним.
          role,
          skills,
          city,
          salary_from: salFrom > 0 ? salFrom : undefined,
          salary_to: salTo > 0 ? salTo : undefined,
        }
      : { search_type: 'prompt', query: prompt.trim() };

    setPhase('running');

    try {
      const response = await searchMutation.mutateAsync(request);
      setRunId(response.run_id);
    } catch (error) {
      setPhase('build');
    }
  };

  const resetSearch = () => {
    setPhase('build');
    setRunId(null);
    setAdded(new Set());
  };

  // повтор поиска из истории
  const pickHistory = (h: BaseSearchRunItem) => {
    if (h.search_type === 'vacancy') {
      setByVacancy(true);
      setVacId(h.vacancy_id);
    } else {
      setByVacancy(false);
      setVacId(null);
      setSelOpen(false);
      setPrompt(h.query_text);
    }
  };

  // обработка "В вакансию"
  const handleAddToVacancy = (candidate: BaseSearchCandidate) => {
    setAssignCandidateId(candidate.id);
  };

  const handleAssignSuccess = async () => {
    if (!assignCandidateId || !runId) return;

    setAdded(prev => new Set(prev).add(assignCandidateId));
    setAssignCandidateId(null);

    // отметить добавление в истории
    try {
      await markAdded.mutateAsync(runId);
    } catch {
      // не критично
    }
  };

  // Выполнение
  if (phase === 'running') {
    const st = runData;
    const isRerank = st?.stage === 'rerank';
    const evald = st?.evaluated ?? 0;
    const total = st?.to_evaluate ?? 0;
    const pct = isRerank && total > 0 ? 12 + Math.min(1, evald / total) * 88 : 12;
    return (
      <div className="ss-run">
        <div className="ss-run-dancer">💃</div>
        <div className="ss-run-phase">
          {isRerank ? 'Глафира оценивает кандидатов…' : 'Глафира читает вашу базу…'}
        </div>
        <div className="ss-run-detail">
          {isRerank && total > 0
            ? <>AI-матчинг <span className="t-mono">{ssFmt(evald)}</span> из <span className="t-mono">{ssFmt(total)}</span></>
            : 'сопоставляет кандидатов по критериям'}
        </div>
        <div className="ss-run-bar"><span style={{ width: `${pct}%` }} /></div>
      </div>
    );
  }

  // Результаты
  if (phase === 'done' && runData?.status === 'error') {
    return (
      <div className="ssb-res-head">
        <div className="error-banner" role="alert">{runData.error || 'Ошибка поиска'}</div>
        <button className="btn btn-secondary btn-sm" onClick={resetSearch}>
          <Icon name="refresh-cw" size={14}/> Новый поиск
        </button>
      </div>
    );
  }

  if (phase === 'done' && runData?.status === 'done') {
    return (
      <div>
        <SSBaseResults
          run={runData}
          added={added}
          onToggleAdd={handleAddToVacancy}
          onOpen={onOpenCandidate}
          onReset={resetSearch}
          onGoFunnel={onGoFunnel}
        />

        {assignCandidateId && (
          <AssignToVacancyModal
            candidateId={assignCandidateId}
            candidateName={runData.results.find(r => r.id === assignCandidateId)?.full_name || 'Кандидат'}
            isOpen={true}
            onClose={() => setAssignCandidateId(null)}
            onSuccess={handleAssignSuccess}
          />
        )}
      </div>
    );
  }

  // Конструктор ввода
  return (
    <div>
      {/* Метод 1: поиск промтом */}
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
            onChange={(e) => { if (byVacancy) setByVacancy(false); setPrompt(e.target.value); }}
            onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') runSearch(); }}
          />
        </div>
        <div className="ssb-examples">
          <span className="ssb-ex-label">Примеры:</span>
          {[
            'Senior Frontend на React, от 5 лет, Москва',
            'Менеджер по продажам B2B с опытом холодных звонков',
            'DevOps-инженер: Kubernetes, Docker, CI/CD',
            'QA-автоматизатор на Python'
          ].map((ex, i) => (
            <button key={i} className="ssb-ex-chip"
              onClick={() => { setByVacancy(false); setPrompt(ex); }}>
              {ex}
            </button>
          ))}
        </div>
      </div>

      {/* разделитель */}
      <div className="ssb-or"><span>или</span></div>

      {/* Метод 2: по открытой вакансии */}
      <div className={`ssb-method ${byVacancy ? 'is-active' : 'is-dim'}`}>
        <label className="ssb-method-head ssb-method-toggle">
          <input type="checkbox" checked={byVacancy}
            onChange={(e) => { setByVacancy(e.target.checked); setVacId(null); setSelOpen(false); }} />
          <span className="ssb-check-box">
            <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
              <rect x="1" y="1" width="20" height="20" rx="6"
                fill={byVacancy ? '#7E5CF0' : '#fff'}
                stroke={byVacancy ? '#7E5CF0' : '#C9CFD6'} strokeWidth="1.5" />
              {byVacancy && <path d="M6 11.2l3 3 6.5-7" fill="none"
                stroke="#fff" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" />}
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
                    </div>
                  ))}
                </div>
              )}
            </div>

            {vac && (
              <div className="ssb-autofilters">
                <div className="ss-glafira-note">
                  <span className="em">💃</span>
                  {deriveFilters.isPending
                    ? 'Глафира подбирает фильтры из вакансии…'
                    : 'Глафира собрала автофильтры из вакансии — поправьте при необходимости'}
                </div>

                <div className="ss-field-row" style={{ marginBottom: 14 }}>
                  <div className="ss-field">
                    <div className="ss-field-label">Должность</div>
                    <input className="ss-input" value={role} onChange={(e) => setRole(e.target.value)}
                      placeholder="любая должность" />
                  </div>
                  <div className="ss-field">
                    <div className="ss-field-label">Город</div>
                    <input className="ss-input" value={city} onChange={(e) => setCity(e.target.value)}
                      placeholder="любой город" />
                  </div>
                  <div className="ss-field" style={{ maxWidth: 180 }}>
                    <div className="ss-field-label">Опыт</div>
                    <input className="ss-input" value={exp} onChange={(e) => setExp(e.target.value)}
                      placeholder="любой опыт" />
                  </div>
                </div>

                <div className="ss-field-row" style={{ marginBottom: 14 }}>
                  <div className="ss-field" style={{ maxWidth: 200 }}>
                    <div className="ss-field-label">Зарплата от, ₽</div>
                    <input className="ss-input t-mono" type="number" min={0} value={salFrom || ''}
                      onChange={(e) => setSalFrom(Number(e.target.value) || 0)} placeholder="не важно" />
                  </div>
                  <div className="ss-field" style={{ maxWidth: 200 }}>
                    <div className="ss-field-label">Зарплата до, ₽</div>
                    <input className="ss-input t-mono" type="number" min={0} value={salTo || ''}
                      onChange={(e) => setSalTo(Number(e.target.value) || 0)} placeholder="не важно" />
                  </div>
                </div>

                <div className="ss-filter-group">
                  <div className="ss-fg-label">Ключевые навыки</div>
                  <div className="ss-chip-row">
                    {skills.map((sk, i) => (
                      <span key={i} className="ss-chip">
                        {sk}
                        <button className="ss-chip-x" onClick={() => setSkills(skills.filter((_, j) => j !== i))} aria-label="Убрать">
                          <Icon name="x" size={11} />
                        </button>
                      </span>
                    ))}
                    <input
                      className="ss-input"
                      style={{ maxWidth: 200 }}
                      value={newSkill}
                      onChange={(e) => setNewSkill(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          const v = newSkill.trim();
                          if (v && !skills.some(s => s.toLowerCase() === v.toLowerCase())) {
                            setSkills([...skills, v]);
                          }
                          setNewSkill('');
                        }
                      }}
                      placeholder="+ навык (Enter)"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Индикатор индексации семантического поиска */}
      <SSIndexingIndicator />

      {/* кнопка поиска */}
      <div className="ssb-actions">
        <button className="ssb-search-btn" disabled={!canSearch} onClick={runSearch}>
          <Icon name="search" size={16} /> Найти в базе
        </button>
        <span className="ssb-actions-hint">
          <Icon name="users" size={13} className="ssb-hint-ic" />
          Поиск только по вашей базе. Доступ к hh.ru не требуется.
        </span>
      </div>

      <SSBaseHistory history={baseHistory} onPick={pickHistory} />
    </div>
  );
}

// Результаты по базе
function SSBaseResults({ run, added, onToggleAdd, onOpen, onReset, onGoFunnel }: {
  run: BaseSearchRunStatus;
  added: Set<string>;
  onToggleAdd: (candidate: BaseSearchCandidate) => void;
  onOpen: (candidateId: string) => void;
  onReset: () => void;
  onGoFunnel: () => void;
}) {
  const results = run.results;
  const hasSkillCrit = (run.criteria?.skills?.length ?? 0) > 0;
  const exact = !hasSkillCrit || results.some(r => r.matched_skills.length > 0);

  return (
    <div>
      <div className="ssb-res-head">
        <div className="ssb-res-check"><Icon name="check" size={22} /></div>
        <div className="ssb-res-head-text">
          <h2>Нашлось {results.length} {results.length === 1 ? 'кандидат' : results.length <= 4 ? 'кандидата' : 'кандидатов'} в базе</h2>
          <div className="ssb-res-sub">
            {run.vacancy_title
              ? <>под вакансию «{run.vacancy_title}»</>
              : <>по запросу «{run.query_echo}»</>}
            {!exact && <span className="ssb-res-flag"> · точных совпадений нет — показаны ближайшие по AI-баллу</span>}
          </div>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={onReset}>
          <Icon name="refresh-cw" size={14} /> Новый поиск
        </button>
      </div>

      <div className="ssb-res-list">
        {results.map(c => {
          const isAdded = added.has(c.id);
          const relColor = c.match_percent != null && c.match_percent >= 80 ? 'green' :
                          c.match_percent != null && c.match_percent >= 60 ? 'blue' : 'gray';
          return (
            <div key={c.id} className="ssb-row">
              <Avatar name={c.full_name} size="md" />
              <div className="ssb-row-main">
                <div className="ssb-row-name-line">
                  <span className="ssb-row-name">{c.full_name}</span>
                  {c.match_percent != null && (
                    <span className={`ssb-rel ssb-rel-${relColor}`}>{c.match_percent}% совпадение</span>
                  )}
                </div>
                <div className="ssb-row-meta">
                  {[
                    c.age && `${c.age} лет`,
                    c.last_period,
                    c.last_company,
                    c.city
                  ].filter(Boolean).join(' · ')}
                </div>
                <div className="ssb-row-chips">
                  {c.all_skills.map((t, i) => {
                    const hit = c.matched_skills.includes(t);
                    return (
                      <span key={i} className={`ssb-tag ${hit ? 'hit' : ''}`}>
                        {hit && <Icon name="check" size={10} />}{t}
                      </span>
                    );
                  })}
                </div>
              </div>
              {c.ai_score != null && <ScoreLabel value={c.ai_score} size="md" />}
              <div className="ssb-row-actions">
                <button className="ssb-act open" onClick={() => onOpen(c.id)}>
                  <Icon name="external-link" size={14} /> Открыть
                </button>
                <button className={`ssb-act add ${isAdded ? 'is-added' : ''}`} onClick={() => onToggleAdd(c)}>
                  <Icon name={isAdded ? 'check' : 'plus'} size={14} /> {isAdded ? 'В вакансии' : 'В вакансию'}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {added.size > 0 && (
        <div className="ssb-res-bar">
          <span><b className="t-mono">{added.size}</b> {added.size === 1 ? 'кандидат' : added.size <= 4 ? 'кандидата' : 'кандидатов'} добавлено в воронку</span>
          <button className="btn btn-primary btn-sm" onClick={onGoFunnel}>
            <Icon name="filter" size={14} /> Смотреть в воронке
          </button>
        </div>
      )}
    </div>
  );
}

// История поиска по базе
function SSBaseHistory({ history, onPick }: { history: BaseSearchRunItem[]; onPick: (h: BaseSearchRunItem) => void }) {
  return (
    <div className="ss-history ssb-history">
      <div className="ss-history-head">
        <Icon name="clock" size={15} style={{ color: 'var(--fg-3)' }} />
        <span className="title">История поиска по базе</span>
        <span className="count">{history.length}</span>
      </div>
      <div className="ss-hist-list">
        {history.map(h => (
          <div key={h.id} className="ss-hist-row" onClick={() => onPick(h)} title="Повторить — заполнит поиск">
            <span className={`ssb-hist-kind ${h.search_type}`}>
              <Icon name={h.search_type === 'vacancy' ? 'briefcase' : 'message-circle'} size={11} />
              {h.search_type === 'vacancy' ? 'по вакансии' : 'промт'}
            </span>
            <div className="ss-hist-main">
              <div className="ss-hist-vac">{h.query_text}</div>
              <div className="ss-hist-date">{new Date(h.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })}</div>
            </div>
            <div className="ss-hist-stats">
              <div className="ss-hist-stat">
                <div className="hv">{h.found}</div>
                <div className="hl">найдено</div>
              </div>
              <div className="ss-hist-stat invite">
                <div className="hv">{h.added_to_funnel}</div>
                <div className="hl">в воронку</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Минимальный статичный индикатор индексации семантического поиска
function SSIndexingIndicator() {
  const { data: indexStatus } = useSmartBaseIndexStatus();

  // Не показывать если нет данных о статусе или нет кандидатов
  if (!indexStatus || indexStatus.total_candidates === 0) return null;

  const { indexed_candidates: indexed, indexing } = indexStatus;

  return (
    <div className="ss-indexing-indicator">
      <div className="ss-indexing-text">
        <span className="ss-indexing-title">
          Семантический поиск: проиндексировано {indexed} кандидатов
        </span>
        {indexing && (
          <span className="ss-indexing-hint">
            — идёт индексация...
          </span>
        )}
        <span className="ss-indexing-settings-link">
          Управление — в Настройках → AI
        </span>
      </div>
    </div>
  );
}