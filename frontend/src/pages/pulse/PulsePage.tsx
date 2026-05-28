import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import './Pulse.css';
import { Icon } from '@/components/ui/Icon';
import { usePulseKpi, usePulseEmployees, usePulseAlerts } from '@/api/hooks/usePulse';
import { KpiStrip } from './components/KpiStrip';
import { AlertsList } from './components/AlertsList';
import { SegmentChips } from './components/SegmentChips';
import { EmployeesTable } from './components/EmployeesTable';

export function PulsePage() {
  const navigate = useNavigate();
  const [period, setPeriod] = useState('30d');
  const [activeSegment, setActiveSegment] = useState('all');

  const { data: kpi } = usePulseKpi(period);
  const { data: employeesData } = usePulseEmployees();
  const { data: alerts } = usePulseAlerts({ dismissed: false });

  const employees = employeesData?.items || [];

  // Фильтрация сотрудников по сегментам
  const filteredEmployees = useMemo(() => {
    if (activeSegment === 'all') return employees;

    return employees.filter(employee => {
      switch (activeSegment) {
        case 'onboarding':
          return employee.status === 'onboarding';
        case 'passed':
          return employee.status === 'passed';
        case 'high_risk':
          return employee.risk_level === 'high';
        case 'no_survey':
          // LIMITATION: client-side filter applies to current page only.
          // For full coverage backend would need ?survey_overdue_days=14 param.
          if (!employee.last_survey_date) return true;
          const daysSince = Math.floor(
            (Date.now() - new Date(employee.last_survey_date).getTime()) / (1000 * 60 * 60 * 24)
          );
          return daysSince > 14;
        case 'left':
          return employee.status === 'left';
        default:
          return true;
      }
    });
  }, [employees, activeSegment]);

  // Подсчёт для чипов сегментов
  const segmentCounts = useMemo(() => {
    return {
      all: employees.length,
      onboarding: employees.filter(e => e.status === 'onboarding').length,
      passed: employees.filter(e => e.status === 'passed').length,
      high_risk: employees.filter(e => e.risk_level === 'high').length,
      no_survey: employees.filter(e => {
        if (!e.last_survey_date) return true;
        const daysSince = Math.floor(
          (Date.now() - new Date(e.last_survey_date).getTime()) / (1000 * 60 * 60 * 24)
        );
        return daysSince > 14;
      }).length,
      left: employees.filter(e => e.status === 'left').length,
    };
  }, [employees]);

  const segments = [
    { id: 'all', label: 'Все', count: segmentCounts.all },
    { id: 'onboarding', label: 'На адаптации', count: segmentCounts.onboarding },
    { id: 'passed', label: 'Прошли', count: segmentCounts.passed },
    { id: 'high_risk', label: '🔴 Высокий риск', count: segmentCounts.high_risk },
    { id: 'no_survey', label: 'Без опроса >14д', count: segmentCounts.no_survey },
    { id: 'left', label: 'Уволенные', count: segmentCounts.left },
  ];

  const handleKpiClick = (metric: string) => {
    // Переключение на соответствующий сегмент
    switch (metric) {
      case 'onboarding':
        setActiveSegment('onboarding');
        break;
      case 'passed':
        setActiveSegment('passed');
        break;
      case 'left':
        setActiveSegment('left');
        break;
      default:
        break;
    }
  };

  const handleEmployeeClick = (employeeId: string) => {
    navigate(`/pulse/${employeeId}`);
  };

  const handleChatClick = (employeeId: string) => {
    navigate(`/pulse/${employeeId}?tab=chat`);
  };

  const handleSurveyClick = (employeeId: string) => {
    navigate(`/pulse/${employeeId}?tab=surveys`);
  };

  const getEmptyStateMessage = () => {
    if (employees.length === 0) {
      return {
        title: 'Нет сотрудников на адаптации',
        description: 'Здесь появятся ваши сотрудники после первого найма. Закройте первую вакансию — и Пульс начнёт за ними следить.',
      };
    }

    if (kpi?.onboarding_count === 0 && kpi?.passed_probation > 0) {
      return {
        title: '🎉 Все ваши сотрудники прошли испытательный',
        description: 'Отличная работа с адаптацией!',
      };
    }

    return null;
  };

  const emptyState = getEmptyStateMessage();

  return (
    <div style={{
      padding: 'var(--space-6)',
      backgroundColor: 'var(--bg-1)',
      minHeight: '100vh'
    }}>
      {/* Шапка */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: 'var(--space-6)'
      }}>
        <div>
          <h1 style={{
            fontSize: '32px',
            fontWeight: 700,
            color: 'var(--fg-1)',
            margin: 0,
            marginBottom: 'var(--space-1)'
          }}>
            Пульс
          </h1>
          <p style={{
            fontSize: '16px',
            color: 'var(--fg-2)',
            margin: 0
          }}>
            Адаптация и удержание новых сотрудников
          </p>
        </div>

        {/* Переключатель периода */}
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          style={{
            padding: 'var(--space-2) var(--space-3)',
            fontSize: '14px',
            backgroundColor: 'var(--bg-2)',
            border: '1px solid var(--border-1)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--fg-1)',
            cursor: 'pointer'
          }}
        >
          <option value="7d">Неделя</option>
          <option value="30d">Месяц</option>
          <option value="90d">Квартал</option>
          <option value="all">Всё время</option>
        </select>
      </div>

      {/* KPI полоса */}
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <KpiStrip kpi={kpi} onKpiClick={handleKpiClick} />
      </div>

      {/* Алерты Глафиры */}
      {alerts && alerts.length > 0 && (
        <div style={{ marginBottom: 'var(--space-6)' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            marginBottom: 'var(--space-4)'
          }}>
            <Icon name="alert-triangle" size={16} style={{ color: 'var(--risk-mid)' }} />
            <h2 style={{
              fontSize: '18px',
              fontWeight: 600,
              color: 'var(--fg-1)',
              margin: 0
            }}>
              Требуют вмешательства
            </h2>
            <span style={{
              padding: '2px 6px',
              backgroundColor: 'var(--risk-mid-soft)',
              color: 'var(--risk-mid)',
              borderRadius: '10px',
              fontSize: '11px',
              fontWeight: 600
            }}>
              {alerts.length}
            </span>
          </div>
          <AlertsList alerts={alerts} onEmployeeClick={handleEmployeeClick} />
        </div>
      )}

      {/* Сегменты */}
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <SegmentChips
          segments={segments}
          activeSegment={activeSegment}
          onSegmentChange={setActiveSegment}
        />
      </div>

      {/* Таблица сотрудников или Empty State */}
      {emptyState ? (
        <div style={{
          textAlign: 'center',
          padding: 'var(--space-12)',
          backgroundColor: 'var(--bg-2)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border-1)'
        }}>
          <Icon name="users" size={48} style={{
            color: 'var(--fg-4)',
            marginBottom: 'var(--space-4)'
          }} />
          <h3 style={{
            fontSize: '18px',
            fontWeight: 600,
            color: 'var(--fg-1)',
            margin: '0 0 var(--space-2) 0'
          }}>
            {emptyState.title}
          </h3>
          <p style={{
            fontSize: '14px',
            color: 'var(--fg-3)',
            margin: 0,
            maxWidth: '400px',
            marginLeft: 'auto',
            marginRight: 'auto',
            lineHeight: 1.5
          }}>
            {emptyState.description}
          </p>
        </div>
      ) : (
        <EmployeesTable
          employees={filteredEmployees}
          onEmployeeClick={handleEmployeeClick}
          onChatClick={handleChatClick}
          onSurveyClick={handleSurveyClick}
        />
      )}
    </div>
  );
}