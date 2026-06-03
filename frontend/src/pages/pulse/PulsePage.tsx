import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import './Pulse.css';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { usePulseKpi, usePulseEmployees, usePulseAlerts } from '@/api/hooks/usePulse';
import type { EmployeeListItem, AlertOut } from '@/api/aliases';

export function PulsePage() {
  const navigate = useNavigate();
  const [period, setPeriod] = useState('30d');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortConfig, setSortConfig] = useState<{ key: string; dir: 'asc' | 'desc' }>({ key: 'adapt_day', dir: 'asc' });

  const { data: kpi } = usePulseKpi(period);
  const { data: employeesData } = usePulseEmployees();
  const { data: alerts } = usePulseAlerts({ dismissed: false });

  const employees = employeesData?.items || [];

  // Фильтрация сотрудников по поиску
  const filteredEmployees = useMemo(() => {
    if (!searchQuery) return employees;

    const query = searchQuery.toLowerCase();
    return employees.filter(employee =>
      employee.full_name.toLowerCase().includes(query) ||
      (employee.position && employee.position.toLowerCase().includes(query)) ||
      (employee.department && employee.department.toLowerCase().includes(query))
    );
  }, [employees, searchQuery]);

  // Сортировка
  const sortedEmployees = useMemo(() => {
    const sorted = [...filteredEmployees].sort((a, b) => {
      const aValue = a[sortConfig.key as keyof EmployeeListItem];
      const bValue = b[sortConfig.key as keyof EmployeeListItem];

      if (aValue === null || aValue === undefined) return 1;
      if (bValue === null || bValue === undefined) return -1;

      if (typeof aValue === 'string' && typeof bValue === 'string') {
        return sortConfig.dir === 'asc'
          ? aValue.localeCompare(bValue, 'ru')
          : bValue.localeCompare(aValue, 'ru');
      }

      if (typeof aValue === 'number' && typeof bValue === 'number') {
        return sortConfig.dir === 'asc' ? aValue - bValue : bValue - aValue;
      }

      return 0;
    });

    return sorted;
  }, [filteredEmployees, sortConfig]);

  const handleSort = (key: string) => {
    setSortConfig(prev => ({
      key,
      dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc'
    }));
  };

  const getSortIcon = (key: string) => {
    if (sortConfig.key !== key) return null;
    return sortConfig.dir === 'asc' ? '▲' : '▼';
  };

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

  return (
    <div className="pulse-content">
      <div className="pulse-content-inner">
        {/* Шапка в стиле эталона */}
        <div className="pulse-header">
          <div className="left">
            <h1>Пульс-Онбординг</h1>
            <div className="sub">
              Обновлено несколько минут назад · последний сбор данных: сейчас · {filteredEmployees.length} сотрудников
            </div>
          </div>
          <div className="pulse-header-actions">
            <select
              className="dropdown"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              <option value="7d">Неделя</option>
              <option value="30d">Месяц</option>
              <option value="90d">Квартал</option>
              <option value="all">Всё время</option>
            </select>
          </div>
        </div>

        {/* KPI полоса в стиле эталона */}
        <div className="pulse-kpi-grid">
          <div className="kpi" title="Сотрудники в окне 0–90 дней с момента найма">
            <div className="kpi-label">На адаптации сейчас</div>
            <div className="kpi-value-row">
              <span className="kpi-value">{kpi?.onboarding_count || 0}</span>
              <span className="kpi-unit">человек</span>
            </div>
            <div className="kpi-foot">
              <span className="kpi-sub">в первые 90 дней</span>
            </div>
          </div>
          <div className="kpi" title="Сотрудники, успешно завершившие испытательный срок">
            <div className="kpi-label">Прошли испытательный</div>
            <div className="kpi-value-row">
              <span className="kpi-value">{kpi?.passed_probation || 0}</span>
              <span className="kpi-unit">человек</span>
            </div>
            <div className="kpi-foot">
              {kpi?.passed_probation_delta !== undefined && (
                <span className={`delta ${kpi.passed_probation_delta >= 0 ? 'up' : 'down'}`}>
                  {kpi.passed_probation_delta >= 0 ? '▲' : '▼'} {Math.abs(kpi.passed_probation_delta)}
                </span>
              )}
              <span className="kpi-sub">к прошлому периоду</span>
            </div>
          </div>
          <div className="kpi" title="Процент ушедших в первые 90 дней">
            <div className="kpi-label">Ушли в 90 дней</div>
            <div className="kpi-value-row">
              <span className="kpi-value">{kpi?.left_in_90d || 0}</span>
              <span className="kpi-unit">{kpi?.left_in_90d_pct?.toFixed(1) || '0'}%</span>
            </div>
            <div className="kpi-foot">
              <span className="kpi-sub">текучка в адаптации</span>
            </div>
          </div>
          <div className="kpi" title="eNPS новых сотрудников">
            <div className="kpi-label">eNPS</div>
            <div className="kpi-value-row">
              <span className="kpi-value">
                {kpi?.enps ? `+${kpi.enps}` : '—'}
              </span>
              <span className="kpi-unit">{kpi?.enps ? 'из 100' : ''}</span>
            </div>
            <div className="kpi-foot">
              <span className="kpi-sub">лояльность новых</span>
            </div>
          </div>
        </div>

        {/* Алерты Глафиры */}
        {alerts && alerts.length > 0 && (
          <>
            <div className="pulse-section-head">
              <h2>
                <Icon name="alert-triangle" size={16}/>
                Требуют вмешательства
                <span className="h-count">{alerts.length}</span>
              </h2>
            </div>
            {alerts.map((alert: AlertOut) => (
              <div key={alert.id} className="alert-row">
                <div className={`level ${alert.level === 'high' ? 'crit' : 'med'}`}>
                  {alert.level === 'high' ? '🔴' : '🟡'}
                </div>
                <div className="body">
                  <div className="who" onClick={() => alert.employee_id && handleEmployeeClick(alert.employee_id)} style={{cursor:'pointer'}}>
                    {/* Ищем сотрудника для получения имени */}
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
                </div>
              </div>
            ))}
          </>
        )}

        {/* Поиск */}
        <div className="pulse-filters">
          <div className="filter-spacer"/>
          <div className="pulse-search">
            <Icon name="search" size={13} style={{color:'var(--fg-3)'}}/>
            <input
              placeholder="Поиск по ФИО…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        {/* Таблица сотрудников в стиле эталона */}
        <div className="emp-table">
          <div className="emp-thead">
            <div onClick={() => handleSort('full_name')} style={{cursor:'pointer'}}>
              Сотрудник {getSortIcon('full_name')}
            </div>
            <div>Должность</div>
            <div>Подразделение</div>
            <div>Руководитель</div>
            <div onClick={() => handleSort('adapt_day')} style={{cursor:'pointer'}}>
              День {getSortIcon('adapt_day')}
            </div>
            <div onClick={() => handleSort('risk_level')} style={{cursor:'pointer'}}>
              Risk {getSortIcon('risk_level')}
            </div>
            <div>Последний опрос</div>
          </div>
          {sortedEmployees.length === 0 ? (
            <div style={{padding:'40px', textAlign:'center', color:'var(--fg-3)', fontSize:13}}>
              {searchQuery ? 'По заданным фильтрам никого не найдено' : 'Нет сотрудников на адаптации'}
            </div>
          ) : (
            sortedEmployees.map(employee => {
              const bucket = getRiskBucketClass(employee.risk_level);
              const surveyInfo = formatLastSurveyDisplay(employee);

              return (
                <div key={employee.id} className="emp-trow" onClick={() => handleEmployeeClick(employee.id)}>
                  <div className="cell-emp">
                    <Avatar name={employee.full_name} size="sm"/>
                    <div className="em-text">
                      <div className="em-name">{employee.full_name}</div>
                      <div className="em-meta">
                        Нанят {new Date(employee.start_date).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit', year: '2-digit'})}
                      </div>
                    </div>
                  </div>
                  <div>{employee.position || '—'}</div>
                  <div>{employee.department || '—'}</div>
                  <div style={{color:'var(--fg-2)'}}>{employee.manager_full_name || '—'}</div>
                  <div className="day-num">{employee.adapt_day}</div>
                  <div>
                    <span className={`risk-pill ${bucket}`}>
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
            })
          )}
        </div>
      </div>
    </div>
  );
}