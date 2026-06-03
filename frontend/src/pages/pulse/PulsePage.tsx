import { useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import './Pulse.css';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { usePulseKpi, usePulseEmployees, usePulseAlerts } from '@/api/hooks/usePulse';
import { useSurveyTemplates, useBulkRunSurvey } from '@/api/hooks/usePulse';
import { useDismissAlert } from '@/api/mutations/pulse';
import type { EmployeeListItem } from '@/api/aliases';

export function PulsePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [period, setPeriod] = useState('30d');
  const [segment, setSegment] = useState('all');

  // Управление табами через URL
  const activeTab = searchParams.get('tab') || 'overview';
  const setActiveTab = (tab: string) => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('tab', tab);
    setSearchParams(newParams);
  };

  const { data: kpi } = usePulseKpi(period);
  const { data: employeesData } = usePulseEmployees();
  const { data: alerts } = usePulseAlerts({ dismissed: false });
  const { data: surveyTemplates = [] } = useSurveyTemplates();
  const bulkRunSurveyMutation = useBulkRunSurvey();
  const dismissAlertMutation = useDismissAlert();

  const employees = employeesData?.items || [];

  const handleEmployeeClick = (employeeId: string) => {
    navigate(`/pulse/${employeeId}`);
  };

  const getRiskBucketClass = (riskLevel: string): 'red' | 'yellow' | 'green' => {
    switch (riskLevel) {
      case 'high': return 'red';
      case 'mid': return 'yellow';
      case 'low': return 'green';
      default: return 'green';
    }
  };

  const pulseBucket = (riskLevel: string) => {
    return getRiskBucketClass(riskLevel);
  };

  // Группировка сотрудников по риску для светофора
  const segmentedEmployees = useMemo(() => {
    const filtered = employees.filter(_e =>
      segment === 'all' // || e.employment_type === segment  // нет в типе, показываем всех
    );

    const reds = filtered.filter(e => pulseBucket(e.risk_level) === 'red');
    const yellows = filtered.filter(e => pulseBucket(e.risk_level) === 'yellow');
    const greens = filtered.filter(e => pulseBucket(e.risk_level) === 'green');

    return { reds, yellows, greens, filtered };
  }, [employees, segment]);

  const formatLastSurveyDisplay = (employee: EmployeeListItem) => {
    if (!employee.last_survey_date) {
      return { day: '—', status: '—' };
    }

    const daysSince = Math.floor(
      (Date.now() - new Date(employee.last_survey_date).getTime()) / (1000 * 60 * 60 * 24)
    );

    const dayText = daysSince === 0 ? 'Сегодня' : `День ${daysSince}`;
    const statusClass = employee.last_survey_mood ? 'ok' : 'bad';
    const statusText = employee.last_survey_mood ? '✓ ответил' : '✗ нет ответа';

    return {
      day: dayText,
      status: statusText,
      statusClass
    };
  };

  // Навигация табами (эталон PulseChips)
  function PulseChips() {
    const chips = [
      { id: 'overview', label: 'Обзор' },
      { id: 'employees', label: 'Сотрудники' },
      { id: 'alerts', label: 'Алерты', badge: alerts?.length || 0 },
      { id: 'surveys', label: 'Опросы' },
    ];

    return (
      <div className="set-toptabs">
        {chips.map(c => (
          <button
            key={c.id}
            className={`set-toptab ${activeTab === c.id ? 'active' : ''}`}
            onClick={() => setActiveTab(c.id)}
          >
            {c.label}
            {c.badge ? <span className="pulse-tab-badge">{c.badge}</span> : null}
          </button>
        ))}
      </div>
    );
  }

  // Компонент карточки сотрудника для светофора (эталон PulseEmpCard)
  function PulseEmpCard({ emp }: { emp: EmployeeListItem }) {
    const bucket = pulseBucket(emp.risk_level);
    const surveyInfo = formatLastSurveyDisplay(emp);

    return (
      <div className={`emp-card ${bucket}`} onClick={() => handleEmployeeClick(emp.id)}>
        <div className="top">
          <Avatar name={emp.full_name} size="sm"/>
          <div className="top-text">
            <div className="name">{emp.full_name}</div>
            <div className="role">{emp.position || '—'} · {emp.department || '—'}</div>
          </div>
          <span className="day-pill">День {emp.adapt_day}</span>
        </div>
        <div className="risk-row">
          <span className="risk-num">Risk: <b>{emp.risk_level === 'high' ? '75' : emp.risk_level === 'mid' ? '45' : '15'}</b></span>
          <span style={{fontSize:11, color:'var(--fg-3)', fontFamily:'var(--font-mono)'}}>
            {emp.last_survey_date ? surveyInfo.day : '—'}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="pulse-wrap">
      {/* Навигация табами */}
      <PulseChips />

      {/* Контент таба */}
      {activeTab === 'overview' && <PulseOverview />}
      {activeTab === 'employees' && <PulseEmployees />}
      {activeTab === 'alerts' && <PulseAlerts />}
      {activeTab === 'surveys' && <PulseSurveys />}
    </div>
  );

  // ========== ОБЗОР ==========
  function PulseOverview() {
    const topAlerts = alerts?.slice(0, 4) || [];

    return (
      <div className="pulse-content">
        <div className="pulse-content-inner">
          {/* Шапка */}
          <div className="pulse-header">
            <div className="left">
              <h1>Пульс-Онбординг</h1>
              <div className="sub">
                Обновлено несколько минут назад · последний сбор данных: сейчас · Сегмент: {segment === 'all' ? 'все' : segment}
              </div>
            </div>
            <div className="pulse-header-actions">
              <select className="dropdown" value={period} onChange={(e) => setPeriod(e.target.value)}>
                <option value="7d">Неделя</option>
                <option value="30d">Месяц</option>
                <option value="90d">Квартал</option>
                <option value="all">Всё время</option>
              </select>
            </div>
          </div>

          {/* KPI полоса */}
          <div className="pulse-kpi-grid">
            <div className="kpi" title="Сотрудники в окне 0–90 дней с момента найма">
              <div className="kpi-label">На адаптации сейчас<span className="info">i</span></div>
              <div className="kpi-value-row">
                <span className="kpi-value">{kpi?.onboarding_count || 0}</span>
                <span className="kpi-unit">человек</span>
              </div>
              <div className="kpi-foot">
                <span className="kpi-sub">в первые 90 дней</span>
              </div>
            </div>
            <div className="kpi" title="Risk-score 61–100">
              <div className="kpi-label">🔴 Высокий риск<span className="info">i</span></div>
              <div className="kpi-value-row">
                <span className="kpi-value" style={{color:'var(--ark-red-600)'}}>{segmentedEmployees.reds.length}</span>
                <span className="kpi-unit">из {employees.length}</span>
              </div>
              <div className="kpi-foot">
                <span className="kpi-sub">требуют внимания</span>
              </div>
            </div>
            <div className="kpi" title="eNPS у сотрудников, прошедших опрос">
              <div className="kpi-label">eNPS<span className="info">i</span></div>
              <div className="kpi-value-row">
                <span className="kpi-value">{kpi?.enps ? `+${kpi.enps}` : '—'}</span>
                <span className="kpi-unit">{kpi?.enps ? 'из 100' : ''}</span>
              </div>
              <div className="kpi-foot">
                <span className="kpi-sub">лояльность новых</span>
              </div>
            </div>
            <div className="kpi" title="% сотрудников, ответивших на отправленный опрос">
              <div className="kpi-label">Completion опросов<span className="info">i</span></div>
              <div className="kpi-value-row">
                <span className="kpi-value">—</span>
                <span className="kpi-unit">%</span>
              </div>
              <div className="kpi-foot">
                <span className="kpi-sub">нет данных</span>
              </div>
            </div>
          </div>

          {/* Светофор сотрудников */}
          <div className="pulse-section-head">
            <h2>
              <Icon name="users" size={16}/>
              Светофор сотрудников на адаптации
              <span className="h-count">{segmentedEmployees.filtered.length}</span>
            </h2>
            <div style={{display:'flex', alignItems:'center', gap:8}}>
              <span style={{fontSize:11, color:'var(--fg-3)', textTransform:'uppercase', letterSpacing:'0.04em', fontWeight:500}}>Сегмент</span>
              <div className="seg-sm">
                <button className={segment === 'all' ? 'active' : ''} onClick={() => setSegment('all')}>Все</button>
                <button className={segment === 'mass' ? 'active' : ''} onClick={() => setSegment('mass')}>Массовый</button>
                <button className={segment === 'office' ? 'active' : ''} onClick={() => setSegment('office')}>Офис</button>
              </div>
            </div>
          </div>

          <div className="tl-board">
            <div className="tl-col red">
              <div className="tl-col-head">
                <span className="light"/> Высокий риск
                <span className="h-count">{segmentedEmployees.reds.length}</span>
              </div>
              {segmentedEmployees.reds.map(e => <PulseEmpCard key={e.id} emp={e}/>)}
              {segmentedEmployees.reds.length === 0 && (
                <div style={{fontSize:12, color:'var(--fg-3)', textAlign:'center', padding:'12px 0'}}>
                  Никого в красной зоне 🎉
                </div>
              )}
            </div>
            <div className="tl-col yellow">
              <div className="tl-col-head">
                <span className="light"/> Средний риск
                <span className="h-count">{segmentedEmployees.yellows.length}</span>
              </div>
              {segmentedEmployees.yellows.map(e => <PulseEmpCard key={e.id} emp={e}/>)}
            </div>
            <div className="tl-col green">
              <div className="tl-col-head">
                <span className="light"/> Норма
                <span className="h-count">{segmentedEmployees.greens.length}</span>
              </div>
              {segmentedEmployees.greens.map(e => <PulseEmpCard key={e.id} emp={e}/>)}
            </div>
          </div>

          {/* Требуют вмешательства */}
          <div className="pulse-section-head">
            <h2>
              <Icon name="alert-triangle" size={16}/>
              Требуют вмешательства
              <span className="h-count">{topAlerts.length}</span>
            </h2>
            <button className="btn btn-ghost btn-sm" onClick={() => setActiveTab('alerts')}>
              Все алерты <Icon name="chevron-right" size={14}/>
            </button>
          </div>
          {topAlerts.length > 0 ? topAlerts.map(alert => (
            <div key={alert.id} className="alert-row">
              <div className={`level ${alert.level === 'high' ? 'crit' : 'med'}`}>
                {alert.level === 'high' ? '🔴' : '🟡'}
              </div>
              <div className="body">
                <div className="who" onClick={() => alert.employee_id && handleEmployeeClick(alert.employee_id)} style={{cursor:'pointer'}}>
                  {(() => {
                    const emp = employees.find(e => e.id === alert.employee_id);
                    return emp ? emp.full_name : 'Сотрудник';
                  })()}
                  <span className="role-tag">· {alert.context || ''}</span>
                </div>
                <div className="reason">{alert.title}</div>
              </div>
              <div className="when">{new Date(alert.created_at).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit'})}</div>
              <div className="actions">
                <button className="btn btn-secondary btn-sm" onClick={() => alert.employee_id && handleEmployeeClick(alert.employee_id)}>Открыть</button>
                <button className="btn btn-ghost btn-sm" onClick={() => dismissAlertMutation.mutate(alert.id)}>Решено</button>
              </div>
            </div>
          )) : (
            <div style={{fontSize:13, color:'var(--fg-3)', textAlign:'center', padding:'20px'}}>
              Нет активных алертов 🎉
            </div>
          )}
        </div>
      </div>
    );
  }

  // ========== СОТРУДНИКИ ==========
  function PulseEmployees() {
    const [searchQuery, setSearchQuery] = useState('');
    const [stage, setStage] = useState('all');
    const [risk, setRisk] = useState('all');
    const [dept, setDept] = useState('all');
    const [sortConfig, setSortConfig] = useState<{ key: string; dir: 'asc' | 'desc' }>({ key: 'adapt_day', dir: 'asc' });

    // Фильтры
    const stages = [
      { id: 'all', label: 'Все' },
      { id: 'd0', label: 'День 0–7' },
      { id: 'd8', label: 'День 8–30' },
      { id: 'd31', label: 'День 31–60' },
      { id: 'd61', label: 'День 61–90' },
    ];

    const stageMatch = (d: number) => {
      if (stage === 'all') return true;
      if (stage === 'd0') return d <= 7;
      if (stage === 'd8') return d >= 8 && d <= 30;
      if (stage === 'd31') return d >= 31 && d <= 60;
      if (stage === 'd61') return d >= 61 && d <= 90;
      return true;
    };

    const riskMatch = (r: string) => {
      if (risk === 'all') return true;
      return pulseBucket(r) === risk;
    };

    const depts = ['all', ...new Set(employees.map(e => e.department).filter(Boolean) as string[])];

    const filteredEmployees = employees.filter(e =>
      stageMatch(e.adapt_day) &&
      riskMatch(e.risk_level) &&
      (segment === 'all') && // || e.employment_type === segment) нет в типе
      (dept === 'all' || e.department === dept || '') &&
      (!searchQuery || e.full_name.toLowerCase().includes(searchQuery.toLowerCase()))
    );

    const sortedEmployees = [...filteredEmployees].sort((a, b) => {
      const m = sortConfig.dir === 'asc' ? 1 : -1;
      if (sortConfig.key === 'risk_level') {
        const aRisk = a.risk_level === 'high' ? 3 : a.risk_level === 'mid' ? 2 : 1;
        const bRisk = b.risk_level === 'high' ? 3 : b.risk_level === 'mid' ? 2 : 1;
        return m * (aRisk - bRisk);
      }
      if (sortConfig.key === 'adapt_day') return m * (a.adapt_day - b.adapt_day);
      if (sortConfig.key === 'full_name') return m * a.full_name.localeCompare(b.full_name, 'ru');
      return 0;
    });

    const handleSort = (key: string) => {
      setSortConfig(prev => ({
        key,
        dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc'
      }));
    };

    const getSortIcon = (key: string) => {
      if (sortConfig.key !== key) return '';
      return sortConfig.dir === 'asc' ? ' ▲' : ' ▼';
    };

    return (
      <div className="pulse-content">
        <div className="pulse-content-inner">
          {/* Шапка */}
          <div className="pulse-header">
            <div className="left">
              <h1>Сотрудники на адаптации</h1>
              <div className="sub">
                {filteredEmployees.length} человек{filteredEmployees.length === 1 ? '' : filteredEmployees.length < 5 ? 'а' : ''} из {employees.length}
              </div>
            </div>
            <div className="pulse-header-actions">
              <button className="btn btn-secondary">
                <Icon name="plus" size={14}/> Добавить вручную
              </button>
            </div>
          </div>

          {/* Фильтры */}
          <div className="pulse-filters">
            <div className="filter-group">
              <span className="filter-label">Этап</span>
              <select className="dropdown" value={stage} onChange={e => setStage(e.target.value)}>
                {stages.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
            </div>
            <div className="filter-group">
              <span className="filter-label">Риск</span>
              <div className="seg-sm">
                <button className={risk === 'all' ? 'active' : ''} onClick={() => setRisk('all')}>Все</button>
                <button className={risk === 'red' ? 'active' : ''} onClick={() => setRisk('red')}>🔴 Высокий</button>
                <button className={risk === 'yellow' ? 'active' : ''} onClick={() => setRisk('yellow')}>🟡 Средний</button>
                <button className={risk === 'green' ? 'active' : ''} onClick={() => setRisk('green')}>🟢 Норма</button>
              </div>
            </div>
            <div className="filter-group">
              <span className="filter-label">Сегмент</span>
              <div className="seg-sm">
                <button className={segment === 'all' ? 'active' : ''} onClick={() => setSegment('all')}>Все</button>
                <button className={segment === 'mass' ? 'active' : ''} onClick={() => setSegment('mass')}>Массовый</button>
                <button className={segment === 'office' ? 'active' : ''} onClick={() => setSegment('office')}>Офис</button>
              </div>
            </div>
            <div className="filter-group">
              <span className="filter-label">Подразделение</span>
              <select className="dropdown" value={dept} onChange={e => setDept(e.target.value || 'all')}>
                {depts.map(d => <option key={d} value={d}>{d === 'all' ? 'Все' : d}</option>)}
              </select>
            </div>
            <div className="filter-spacer"/>
            <div className="pulse-search">
              <Icon name="search" size={13} style={{color:'var(--fg-3)'}}/>
              <input placeholder="Поиск по ФИО…" value={searchQuery} onChange={e => setSearchQuery(e.target.value)}/>
            </div>
          </div>

          {/* Таблица */}
          <div className="emp-table">
            <div className="emp-thead">
              <div onClick={() => handleSort('full_name')} style={{cursor:'pointer'}}>
                Сотрудник{getSortIcon('full_name')}
              </div>
              <div>Должность</div>
              <div>Подразделение</div>
              <div>Руководитель</div>
              <div onClick={() => handleSort('adapt_day')} style={{cursor:'pointer'}}>
                День{getSortIcon('adapt_day')}
              </div>
              <div onClick={() => handleSort('risk_level')} style={{cursor:'pointer'}}>
                Risk{getSortIcon('risk_level')}
              </div>
              <div>Последний опрос</div>
            </div>
            {sortedEmployees.length === 0 ? (
              <div style={{padding:'40px', textAlign:'center', color:'var(--fg-3)', fontSize:13}}>
                По заданным фильтрам никого не найдено
              </div>
            ) : sortedEmployees.map(employee => {
              const surveyInfo = formatLastSurveyDisplay(employee);
              return (
                <div key={employee.id} className="emp-trow" onClick={() => handleEmployeeClick(employee.id)}>
                  <div className="cell-emp">
                    <Avatar name={employee.full_name} size="sm"/>
                    <div className="em-text">
                      <div className="em-name">{employee.full_name}</div>
                      <div className="em-meta">
                        💼 Офис · нанят {new Date(employee.start_date).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit'})}
                      </div>
                    </div>
                  </div>
                  <div>{employee.position || '—'}</div>
                  <div>{employee.department || '—'}</div>
                  <div style={{color:'var(--fg-2)'}}>{employee.manager_full_name || '—'}</div>
                  <div className="day-num">{employee.adapt_day}</div>
                  <div>
                    <span className={`risk-pill ${pulseBucket(employee.risk_level)}`}>
                      <span className="dot"/>
                      {employee.risk_level === 'high' ? 'Высокий' : employee.risk_level === 'mid' ? 'Средний' : 'Норма'}
                    </span>
                  </div>
                  <div>
                    <div className="last-survey">
                      <span className="ls-day">{surveyInfo.day}</span>
                      <span className={`ls-status ${surveyInfo.statusClass || ''}`}>
                        {surveyInfo.status}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // ========== АЛЕРТЫ ==========
  function PulseAlerts() {
    const [level, setLevel] = useState('all');
    const [status, setStatus] = useState('active');

    const filteredAlerts = (alerts || []).filter(a => {
      if (level !== 'all' && (level === 'crit' ? a.level !== 'high' : a.level === 'high')) return false;
      if (status === 'active' && a.is_dismissed) return false;
      return true;
    });

    return (
      <div className="pulse-content">
        <div className="pulse-content-inner">
          {/* Шапка */}
          <div className="pulse-header">
            <div className="left">
              <h1>Алерты</h1>
              <div className="sub">
                {filteredAlerts.length} активных
              </div>
            </div>
          </div>

          {/* Фильтры */}
          <div className="pulse-filters">
            <div className="filter-group">
              <span className="filter-label">Уровень</span>
              <div className="seg-sm">
                <button className={level === 'all' ? 'active' : ''} onClick={() => setLevel('all')}>Все</button>
                <button className={level === 'crit' ? 'active' : ''} onClick={() => setLevel('crit')}>🔴 CRITICAL</button>
                <button className={level === 'med' ? 'active' : ''} onClick={() => setLevel('med')}>🟡 MEDIUM</button>
              </div>
            </div>
            <div className="filter-group">
              <span className="filter-label">Статус</span>
              <div className="seg-sm">
                <button className={status === 'active' ? 'active' : ''} onClick={() => setStatus('active')}>Активные</button>
                <button className={status === 'all' ? 'active' : ''} onClick={() => setStatus('all')}>Все</button>
              </div>
            </div>
          </div>

          {/* Таблица алертов */}
          <div className="alert-tbl">
            <div className="alert-thead">
              <div>Уровень</div>
              <div>Сотрудник</div>
              <div>Что произошло</div>
              <div>Дата</div>
              <div>Статус</div>
              <div>Действия</div>
            </div>
            {filteredAlerts.length === 0 ? (
              <div style={{padding:40, textAlign:'center', color:'var(--fg-3)', fontSize:13}}>
                Нет алертов по выбранным фильтрам 🎉
              </div>
            ) : filteredAlerts.map(a => (
              <div key={a.id} className="alert-trow">
                <div><span className={`lvl-pill ${a.level === 'high' ? 'crit' : 'med'}`}>{a.level === 'high' ? '🔴' : '🟡'}</span></div>
                <div>
                  <div style={{display:'flex', alignItems:'center', gap:8}}>
                    <Avatar name={employees.find(e => e.id === a.employee_id)?.full_name || 'Сотрудник'} size="sm"/>
                    <div style={{minWidth:0}}>
                      <div style={{fontSize:13, fontWeight:600, cursor:'pointer'}} onClick={() => a.employee_id && handleEmployeeClick(a.employee_id)}>
                        {employees.find(e => e.id === a.employee_id)?.full_name || 'Сотрудник'}
                      </div>
                      <div style={{fontSize:11, color:'var(--fg-3)'}}>{a.context || '—'}</div>
                    </div>
                  </div>
                </div>
                <div style={{fontSize:13}}>{a.title}</div>
                <div className="t-mono" style={{fontSize:12, color:'var(--fg-2)'}}>
                  {new Date(a.created_at).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit'})}
                </div>
                <div>
                  <span className={`status-tag ${a.is_dismissed ? 'closed' : 'open'}`}>
                    <span className="dot"/>
                    {a.is_dismissed ? 'Закрыт' : 'Открыт'}
                  </span>
                </div>
                <div style={{display:'flex', gap:6}}>
                  <button className="btn btn-secondary btn-sm" onClick={() => a.employee_id && handleEmployeeClick(a.employee_id)}>Открыть</button>
                  {!a.is_dismissed && (
                    <button className="btn btn-primary btn-sm" onClick={() => dismissAlertMutation.mutate(a.id)}>Закрыть</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ========== ОПРОСЫ ==========
  function PulseSurveys() {
    const handleBulkRun = (templateKey: string) => {
      const onboardingEmployeeIds = employees.map(e => e.id);
      if (onboardingEmployeeIds.length > 0) {
        bulkRunSurveyMutation.mutate({
          employee_ids: onboardingEmployeeIds,
          template_key: templateKey
        });
      }
    };

    return (
      <div className="pulse-content">
        <div className="pulse-content-inner">
          {/* Шапка */}
          <div className="pulse-header">
            <div className="left">
              <h1>Опросы</h1>
              <div className="sub">
                Шаблоны опросов для адаптации сотрудников
              </div>
            </div>
          </div>

          {surveyTemplates.length === 0 ? (
            <div style={{padding:'60px 20px', textAlign:'center', color:'var(--fg-3)'}}>
              <div style={{fontSize:16, marginBottom:8}}>📋</div>
              <div style={{fontSize:14, fontWeight:600, marginBottom:4}}>Шаблоны опросов не настроены</div>
              <div style={{fontSize:13}}>Настройте шаблоны в разделе Настройки</div>
            </div>
          ) : (
            surveyTemplates.map((template: any) => (
              <div key={template.id} className="survey-card">
                <div className="survey-head">
                  <div className="badge-day">
                    <div className="num">{template.trigger_day || '?'}</div>
                    <div className="lbl">день</div>
                  </div>
                  <div>
                    <div className="stitle">📋 «{template.name}»</div>
                    <div className="smeta">
                      {Array.isArray(template.questions) ? template.questions.length : Object.keys(template.questions || {}).length} вопросов ·
                      {template.is_enabled ? (
                        <span className="ok"> включён</span>
                      ) : (
                        <span style={{color:'var(--fg-3)'}}> отключён</span>
                      )}
                    </div>
                  </div>
                  <div style={{display:'flex', alignItems:'center', gap:12}}>
                    {template.is_enabled && (
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => handleBulkRun(template.name)}
                        disabled={bulkRunSurveyMutation.isPending || employees.length === 0}
                      >
                        {bulkRunSurveyMutation.isPending ? 'Запуск...' : `Запустить для ${employees.length}`}
                      </button>
                    )}
                  </div>
                </div>
                {/* Показать вопросы если есть */}
                {template.questions && Object.keys(template.questions).length > 0 && (
                  <div className="survey-body" style={{maxHeight: '200px', overflow: 'auto'}}>
                    {Object.entries(template.questions).map(([key, question]: [string, any], idx) => (
                      <div key={key} className="q-row" style={{margin: '8px 0'}}>
                        <div className="q-num">{idx + 1}</div>
                        <div>
                          <div className="q-text">{question.text || key}</div>
                          {question.goal && (
                            <div className="q-goal">
                              <span className="info-dot">i</span>
                              <span>Цель: {question.goal}</span>
                            </div>
                          )}
                        </div>
                        <div className="q-scale">
                          {question.scale || 'text'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    );
  }
}