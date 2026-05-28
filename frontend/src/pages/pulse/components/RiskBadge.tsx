type Props = {
  riskLevel: string;
  variant?: 'table' | 'large';
};

export function RiskBadge({ riskLevel, variant = 'table' }: Props) {
  // Цвета риска из токенов
  const colors = {
    low: { fg: 'var(--risk-low)', bg: 'var(--risk-low-soft)' },
    mid: { fg: 'var(--risk-mid)', bg: 'var(--risk-mid-soft)' },
    high: { fg: 'var(--risk-high)', bg: 'var(--risk-high-soft)' },
  };

  const color = colors[riskLevel as keyof typeof colors] || colors.low;

  const labels = {
    low: 'Норма',
    mid: 'Средний',
    high: 'Высокий',
  };

  if (variant === 'large') {
    return (
      <div
        style={{
          backgroundColor: color.bg,
          color: color.fg,
          padding: 'var(--space-3) var(--space-4)',
          borderRadius: 'var(--radius-md)',
          fontSize: '14px',
          fontWeight: 600,
          textAlign: 'center',
          border: `1px solid ${color.fg}20`,
        }}
      >
        <div style={{ fontSize: '11px', opacity: 0.7, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Риск ухода
        </div>
        <div style={{ marginTop: '2px' }}>
          {riskLevel === 'high' ? '🔴' : riskLevel === 'mid' ? '🟡' : '🟢'} {labels[riskLevel as keyof typeof labels] || riskLevel}
        </div>
      </div>
    );
  }

  return (
    <span
      style={{
        backgroundColor: color.bg,
        color: color.fg,
        padding: '2px 6px',
        borderRadius: 'var(--radius-sm)',
        fontSize: '11px',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
      }}
    >
      <span>{riskLevel === 'high' ? '🔴' : riskLevel === 'mid' ? '🟡' : '🟢'}</span>
      {labels[riskLevel as keyof typeof labels] || riskLevel}
    </span>
  );
}