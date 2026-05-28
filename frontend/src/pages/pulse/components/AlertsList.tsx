import { Icon } from '@/components/ui/Icon';
import { useDismissAlert } from '@/api/mutations/pulse';
import type { AlertOut } from '@/api/aliases';

type Props = {
  alerts: AlertOut[];
  onEmployeeClick?: (employeeId: string) => void;
};

export function AlertsList({ alerts, onEmployeeClick }: Props) {
  const dismissMutation = useDismissAlert();

  const handleDismiss = async (e: React.MouseEvent, alertId: string) => {
    e.stopPropagation();
    try {
      await dismissMutation.mutateAsync(alertId);
    } catch (error) {
      console.error('Failed to dismiss alert:', error);
    }
  };

  const getActionLabel = (actionType: string | null) => {
    switch (actionType) {
      case 'contact': return 'Связаться';
      case 'survey': return 'Запустить опрос';
      case 'escalate': return 'Эскалировать';
      default: return 'Открыть карточку';
    }
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'high': return 'var(--risk-high)';
      case 'mid': return 'var(--risk-mid)';
      case 'info': return 'var(--accent)';
      default: return 'var(--fg-3)';
    }
  };

  if (alerts.length === 0) {
    return (
      <div style={{
        textAlign: 'center',
        padding: 'var(--space-8)',
        color: 'var(--fg-3)',
        backgroundColor: 'var(--bg-2)',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border-1)'
      }}>
        <Icon name="check-circle" size={24} style={{ marginBottom: 'var(--space-2)', opacity: 0.5 }} />
        <div>Нет активных алертов</div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      {alerts.map((alert) => (
        <div
          key={alert.id}
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: 'var(--space-4)',
            backgroundColor: 'var(--bg-2)',
            border: '1px solid var(--border-1)',
            borderLeft: `4px solid ${getLevelColor(alert.level)}`,
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
          }}
          onClick={() => onEmployeeClick?.(alert.employee_id)}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-3)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-2)';
          }}
        >
          {/* Иконка уровня */}
          <div style={{ marginRight: 'var(--space-3)' }}>
            {alert.level === 'high' && <span style={{ fontSize: '16px' }}>🔴</span>}
            {alert.level === 'mid' && <span style={{ fontSize: '16px' }}>🟡</span>}
            {alert.level === 'info' && <Icon name="info" size={16} style={{ color: 'var(--accent)' }} />}
          </div>

          {/* Контент */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: '14px',
              fontWeight: 600,
              color: 'var(--fg-1)',
              marginBottom: '2px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap'
            }}>
              {alert.title}
            </div>
            {alert.context && (
              <div style={{
                fontSize: '12px',
                color: 'var(--fg-3)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap'
              }}>
                {alert.context}
              </div>
            )}
          </div>

          {/* Время */}
          <div style={{
            fontSize: '11px',
            color: 'var(--fg-3)',
            fontFamily: 'var(--font-mono)',
            marginRight: 'var(--space-3)',
            minWidth: '80px',
            textAlign: 'right'
          }}>
            {new Date(alert.created_at).toLocaleDateString('ru-RU')}
          </div>

          {/* Действия */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <button
              style={{
                padding: '4px 8px',
                fontSize: '11px',
                backgroundColor: 'var(--accent)',
                color: 'white',
                border: 'none',
                borderRadius: 'var(--radius-sm)',
                cursor: 'pointer',
                fontWeight: 500,
              }}
              onClick={(e) => {
                e.stopPropagation();
                onEmployeeClick?.(alert.employee_id);
              }}
            >
              {getActionLabel(alert.action_type || null)}
            </button>

            <button
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
              onClick={(e) => handleDismiss(e, String(alert.id))}
              disabled={dismissMutation.isPending}
              title="Отметить как просмотренный"
            >
              <Icon name="x" size={14} />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}