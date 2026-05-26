interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'error';
  size?: 'sm' | 'md';
}

export function Badge({ children, variant = 'default', size = 'md' }: BadgeProps) {
  const variants = {
    default: 'var(--bg-3)',
    success: 'var(--status-success)',
    warning: 'var(--score-yellow)',
    error: 'var(--status-error)',
  };

  const padding = size === 'sm' ? '2px 6px' : '4px 8px';
  const fontSize = size === 'sm' ? 11 : 12;

  return (
    <span
      style={{
        background: variants[variant],
        color: variant === 'default' ? 'var(--fg-1)' : '#fff',
        padding,
        borderRadius: 'var(--radius-chip)',
        fontSize,
        fontWeight: 500,
        display: 'inline-flex',
        alignItems: 'center',
      }}
    >
      {children}
    </span>
  );
}