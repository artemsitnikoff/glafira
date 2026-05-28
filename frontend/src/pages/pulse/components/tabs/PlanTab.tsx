import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useTogglePlanItem } from '@/api/mutations/pulse';
import type { EmployeeDetail, PlanItemOut } from '@/api/aliases';

type Props = {
  employee: EmployeeDetail;
};

const PHASE_LABELS = {
  welcome: 'Welcome',
  month1: 'Месяц 1',
  month2: 'Месяц 2',
  month3: 'Месяц 3',
} as const;

const RESPONSIBLE_LABELS = {
  hr: 'HR',
  manager: 'Руководитель',
  employee: 'Сотрудник',
} as const;

export function PlanTab({ employee }: Props) {
  const toggleMutation = useTogglePlanItem();
  const [optimisticUpdates, setOptimisticUpdates] = useState<Record<string, boolean>>({});

  const handleTogglePlanItem = async (item: PlanItemOut) => {
    const newDoneState = !item.is_done;

    // Optimistic update
    setOptimisticUpdates(prev => ({
      ...prev,
      [item.id]: newDoneState
    }));

    try {
      await toggleMutation.mutateAsync({
        itemId: item.id,
        isDone: newDoneState
      });
    } catch (error) {
      // Откат optimistic update при ошибке
      setOptimisticUpdates(prev => {
        const newState = { ...prev };
        delete newState[item.id];
        return newState;
      });
      console.error('Failed to toggle plan item:', error);
    }
  };

  const getItemStatus = (item: PlanItemOut) => {
    if (optimisticUpdates[item.id] !== undefined) {
      return optimisticUpdates[item.id];
    }
    return item.is_done;
  };

  const isOverdue = (item: PlanItemOut) => {
    if (!item.deadline_day || item.is_done) return false;
    return employee.adapt_day > item.deadline_day;
  };

  // Группировка по фазам
  const groupedPlan = (employee.plan || []).reduce((acc, item) => {
    if (!acc[item.phase]) {
      acc[item.phase] = [];
    }
    acc[item.phase].push(item);
    return acc;
  }, {} as Record<string, PlanItemOut[]>);

  // Сортировка по order_index внутри каждой фазы
  Object.keys(groupedPlan).forEach(phase => {
    groupedPlan[phase].sort((a, b) => a.order_index - b.order_index);
  });

  const phases = ['welcome', 'month1', 'month2', 'month3'].filter(phase => groupedPlan[phase]);

  if (phases.length === 0) {
    return (
      <div style={{
        padding: 'var(--space-8)',
        textAlign: 'center',
        backgroundColor: 'var(--bg-panel-2)',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border-1)'
      }}>
        <Icon name="clipboard" size={32} style={{
          color: 'var(--fg-4)',
          marginBottom: 'var(--space-3)'
        }} />
        <h3 style={{
          fontSize: '16px',
          fontWeight: 600,
          color: 'var(--fg-2)',
          margin: '0 0 var(--space-2) 0'
        }}>
          План адаптации не назначен
        </h3>
        <p style={{
          fontSize: '14px',
          color: 'var(--fg-3)',
          margin: 0
        }}>
          Глафира создаст план автоматически в ближайшее время
        </p>
      </div>
    );
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-5)'
    }}>
      {phases.map((phase) => (
        <div key={phase}>
          {/* Заголовок фазы */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            marginBottom: 'var(--space-3)',
            paddingBottom: 'var(--space-2)',
            borderBottom: '1px solid var(--border-1)'
          }}>
            <div style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: 'var(--accent)',
            }} />
            <h3 style={{
              fontSize: '16px',
              fontWeight: 600,
              color: 'var(--fg-1)',
              margin: 0
            }}>
              {PHASE_LABELS[phase as keyof typeof PHASE_LABELS] || phase}
            </h3>
            <span style={{
              padding: '2px 6px',
              fontSize: '10px',
              backgroundColor: 'var(--bg-3)',
              color: 'var(--fg-3)',
              borderRadius: 'var(--radius-sm)',
              fontWeight: 500
            }}>
              {groupedPlan[phase].filter(item => getItemStatus(item)).length} / {groupedPlan[phase].length}
            </span>
          </div>

          {/* Пункты плана */}
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2)'
          }}>
            {groupedPlan[phase].map((item) => {
              const isDone = getItemStatus(item);
              const overdue = isOverdue(item);

              return (
                <div
                  key={item.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--space-3)',
                    padding: 'var(--space-3)',
                    backgroundColor: 'var(--bg-2)',
                    border: `1px solid ${overdue && !isDone ? 'var(--risk-high)' : 'var(--border-1)'}`,
                    borderRadius: 'var(--radius-md)',
                    opacity: isDone ? 0.7 : 1,
                    transition: 'all 0.2s ease'
                  }}
                >
                  {/* Чекбокс */}
                  <button
                    onClick={() => handleTogglePlanItem(item)}
                    disabled={toggleMutation.isPending}
                    style={{
                      width: '20px',
                      height: '20px',
                      borderRadius: 'var(--radius-sm)',
                      border: `2px solid ${isDone ? 'var(--accent)' : 'var(--border-2)'}`,
                      backgroundColor: isDone ? 'var(--accent)' : 'transparent',
                      color: 'white',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      transition: 'all 0.2s ease',
                      flexShrink: 0
                    }}
                  >
                    {isDone && <Icon name="check" size={12} />}
                  </button>

                  {/* Контент */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: '14px',
                      fontWeight: 500,
                      color: isDone ? 'var(--fg-3)' : 'var(--fg-1)',
                      marginBottom: '2px',
                      textDecoration: isDone ? 'line-through' : 'none'
                    }}>
                      {item.title}
                    </div>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--space-3)',
                      fontSize: '11px',
                      color: 'var(--fg-3)'
                    }}>
                      {item.deadline_day && (
                        <span>
                          Дедлайн: день {item.deadline_day}
                          {overdue && !isDone && (
                            <span style={{ color: 'var(--risk-high)', marginLeft: 'var(--space-1)' }}>
                              (просрочен)
                            </span>
                          )}
                        </span>
                      )}
                      <span>•</span>
                      <span>
                        Ответственный: {RESPONSIBLE_LABELS[item.responsible as keyof typeof RESPONSIBLE_LABELS] || item.responsible}
                      </span>
                      {isDone && item.done_at && (
                        <>
                          <span>•</span>
                          <span>
                            Выполнено: {new Date(item.done_at).toLocaleDateString('ru-RU')}
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Индикатор просрочки */}
                  {overdue && !isDone && (
                    <div style={{
                      padding: '2px 6px',
                      fontSize: '10px',
                      backgroundColor: 'var(--risk-high-soft)',
                      color: 'var(--risk-high)',
                      borderRadius: 'var(--radius-sm)',
                      fontWeight: 500
                    }}>
                      ПРОСРОЧЕН
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}