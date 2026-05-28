import { useState, useMemo } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useDebounce } from '@/hooks/useDebounce';
import { AdaptBar } from './AdaptBar';
import { RiskBadge } from './RiskBadge';
import { MoodIcon } from './MoodIcon';
import type { EmployeeListItem } from '@/api/aliases';

type Props = {
  employees: EmployeeListItem[];
  onEmployeeClick?: (employeeId: string) => void;
  onChatClick?: (employeeId: string) => void;
  onSurveyClick?: (employeeId: string) => void;
};

type SortConfig = {
  key: string;
  direction: 'asc' | 'desc';
};

export function EmployeesTable({ employees, onEmployeeClick, onChatClick, onSurveyClick }: Props) {
  const [searchQuery, setSearchQuery] = useState('');
  const [sortConfig, setSortConfig] = useState<SortConfig>({ key: 'adapt_day', direction: 'asc' });

  const debouncedSearch = useDebounce(searchQuery, 200);

  // Фильтрация по поиску
  const filteredEmployees = useMemo(() => {
    if (!debouncedSearch) return employees;

    const query = debouncedSearch.toLowerCase();
    return employees.filter(employee =>
      employee.full_name.toLowerCase().includes(query) ||
      (employee.position && employee.position.toLowerCase().includes(query)) ||
      (employee.department && employee.department.toLowerCase().includes(query))
    );
  }, [employees, debouncedSearch]);


  // Сортировка (клиентская)
  const sortedEmployees = useMemo(() => {
    const sorted = [...filteredEmployees].sort((a, b) => {
      const aValue = a[sortConfig.key as keyof EmployeeListItem];
      const bValue = b[sortConfig.key as keyof EmployeeListItem];

      if (aValue === null || aValue === undefined) return 1;
      if (bValue === null || bValue === undefined) return -1;

      if (typeof aValue === 'string' && typeof bValue === 'string') {
        return sortConfig.direction === 'asc'
          ? aValue.localeCompare(bValue, 'ru')
          : bValue.localeCompare(aValue, 'ru');
      }

      if (typeof aValue === 'number' && typeof bValue === 'number') {
        return sortConfig.direction === 'asc' ? aValue - bValue : bValue - aValue;
      }

      return 0;
    });

    return sorted;
  }, [filteredEmployees, sortConfig]);

  const handleSort = (key: string) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }));
  };

  const getSortIcon = (key: string) => {
    if (sortConfig.key !== key) return null;
    return sortConfig.direction === 'asc' ? '▲' : '▼';
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit'
    });
  };

  const formatSurveyInfo = (employee: EmployeeListItem) => {
    if (!employee.last_survey_date) {
      return { text: 'Нет опросов', mood: null };
    }

    const daysSince = Math.floor(
      (Date.now() - new Date(employee.last_survey_date).getTime()) / (1000 * 60 * 60 * 24)
    );

    return {
      text: daysSince === 0 ? 'Сегодня' : `${daysSince} дн. назад`,
      mood: employee.last_survey_mood
    };
  };

  return (
    <div>
      {/* Поиск */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        marginBottom: 'var(--space-4)',
        padding: 'var(--space-3)',
        backgroundColor: 'var(--bg-2)',
        border: '1px solid var(--border-1)',
        borderRadius: 'var(--radius-md)'
      }}>
        <Icon name="search" size={16} style={{ color: 'var(--fg-3)' }} />
        <input
          type="text"
          placeholder="Поиск по ФИО, должности, отделу..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            flex: 1,
            border: 'none',
            outline: 'none',
            backgroundColor: 'transparent',
            fontSize: '14px',
            color: 'var(--fg-1)'
          }}
        />
      </div>

      {/* Таблица */}
      <div style={{
        backgroundColor: 'var(--bg-2)',
        border: '1px solid var(--border-1)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden'
      }}>
        {/* Заголовки */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '2fr 1fr 120px 100px 120px 140px 60px',
          gap: 'var(--space-3)',
          padding: 'var(--space-3) var(--space-4)',
          backgroundColor: 'var(--bg-3)',
          borderBottom: '1px solid var(--border-1)',
          fontSize: '12px',
          fontWeight: 600,
          color: 'var(--fg-2)',
          textTransform: 'uppercase',
          letterSpacing: '0.04em'
        }}>
          <button
            onClick={() => handleSort('full_name')}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              textAlign: 'left',
              fontSize: 'inherit',
              fontWeight: 'inherit',
              color: 'inherit',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-1)'
            }}
          >
            Сотрудник {getSortIcon('full_name')}
          </button>
          <button
            onClick={() => handleSort('manager_full_name')}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              textAlign: 'left',
              fontSize: 'inherit',
              fontWeight: 'inherit',
              color: 'inherit',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-1)'
            }}
          >
            Руководитель {getSortIcon('manager_full_name')}
          </button>
          <button
            onClick={() => handleSort('start_date')}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              textAlign: 'left',
              fontSize: 'inherit',
              fontWeight: 'inherit',
              color: 'inherit',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-1)'
            }}
          >
            Дата выхода {getSortIcon('start_date')}
          </button>
          <div>День N из M</div>
          <button
            onClick={() => handleSort('risk_level')}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              textAlign: 'left',
              fontSize: 'inherit',
              fontWeight: 'inherit',
              color: 'inherit',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-1)'
            }}
          >
            Риск {getSortIcon('risk_level')}
          </button>
          <div>Последний опрос</div>
          <div>Действия</div>
        </div>

        {/* Строки */}
        {sortedEmployees.length === 0 ? (
          <div style={{
            padding: 'var(--space-8)',
            textAlign: 'center',
            color: 'var(--fg-3)'
          }}>
            {searchQuery ? 'Ничего не найдено по вашему запросу' : 'Нет сотрудников'}
          </div>
        ) : (
          sortedEmployees.map((employee) => {
            const surveyInfo = formatSurveyInfo(employee);

            return (
              <div
                key={employee.id}
                onClick={() => onEmployeeClick?.(employee.id)}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '2fr 1fr 120px 100px 120px 140px 60px',
                  gap: 'var(--space-3)',
                  padding: 'var(--space-4)',
                  borderBottom: '1px solid var(--border-1)',
                  cursor: 'pointer',
                  transition: 'background-color 0.2s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-3)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                {/* Сотрудник */}
                <div style={{ minWidth: 0 }}>
                  <div style={{
                    fontSize: '14px',
                    fontWeight: 600,
                    color: 'var(--fg-1)',
                    marginBottom: '2px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    {employee.full_name}
                  </div>
                  <div style={{
                    fontSize: '12px',
                    color: 'var(--fg-3)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    {employee.position && employee.department
                      ? `${employee.position} · ${employee.department}`
                      : employee.position || employee.department || '—'
                    }
                  </div>
                </div>

                {/* Руководитель */}
                <div style={{
                  fontSize: '13px',
                  color: 'var(--fg-2)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap'
                }}>
                  {employee.manager_full_name || '—'}
                </div>

                {/* Дата выхода */}
                <div style={{
                  fontSize: '12px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--fg-2)'
                }}>
                  {formatDate(employee.start_date)}
                </div>

                {/* День N из M + AdaptBar */}
                <div>
                  <div style={{
                    fontSize: '12px',
                    color: 'var(--fg-2)',
                    marginBottom: '4px'
                  }}>
                    День {employee.adapt_day} из {employee.probation_days}
                  </div>
                  <AdaptBar
                    adaptDay={employee.adapt_day}
                    probationDays={employee.probation_days}
                    riskLevel={employee.risk_level}
                    variant="compact"
                  />
                </div>

                {/* Риск */}
                <div>
                  <RiskBadge riskLevel={employee.risk_level} variant="table" />
                </div>

                {/* Последний опрос */}
                <div>
                  <div style={{
                    fontSize: '11px',
                    color: 'var(--fg-3)',
                    marginBottom: '2px'
                  }}>
                    {surveyInfo.text}
                  </div>
                  <div style={{ fontSize: '16px' }}>
                    <MoodIcon mood={surveyInfo.mood} />
                  </div>
                </div>

                {/* Действия */}
                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onChatClick?.(employee.id);
                    }}
                    title="Связаться"
                    style={{
                      padding: '4px',
                      backgroundColor: 'transparent',
                      border: 'none',
                      borderRadius: 'var(--radius-sm)',
                      cursor: 'pointer',
                      color: 'var(--fg-3)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    💬
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onSurveyClick?.(employee.id);
                    }}
                    title="Запустить опрос"
                    style={{
                      padding: '4px',
                      backgroundColor: 'transparent',
                      border: 'none',
                      borderRadius: 'var(--radius-sm)',
                      cursor: 'pointer',
                      color: 'var(--fg-3)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    📋
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}