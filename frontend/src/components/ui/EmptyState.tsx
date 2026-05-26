import { Icon, type IconName } from './Icon';

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: IconName;
  action?: React.ReactNode;
}

export function EmptyState({ title, description, icon, action }: EmptyStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-8)',
        textAlign: 'center',
        color: 'var(--fg-3)',
      }}
    >
      {icon && <Icon name={icon} size={32} style={{ marginBottom: 'var(--space-3)' }} />}
      <h3 style={{ fontSize: 16, fontWeight: 500, color: 'var(--fg-2)', marginBottom: 'var(--space-2)' }}>
        {title}
      </h3>
      {description && (
        <p style={{ fontSize: 14, marginBottom: action ? 'var(--space-4)' : 0 }}>
          {description}
        </p>
      )}
      {action}
    </div>
  );
}