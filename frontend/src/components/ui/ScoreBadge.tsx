interface ScoreBadgeProps {
  value: number | null;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

export function ScoreBadge({ value, size = 'md' }: ScoreBadgeProps) {
  let bg: string;
  const text = String(value ?? '—');

  if (value === null) {
    bg = 'var(--bg-3)';
  } else if (value >= 80) {
    bg = 'var(--score-green)';
  } else if (value >= 50) {
    bg = 'var(--score-yellow)';
  } else {
    bg = 'var(--score-red)';
  }

  const sizes = {
    sm: { fs: 11, p: '2px 6px' },
    md: { fs: 13, p: '3px 8px' },
    lg: { fs: 16, p: '4px 12px' },
    xl: { fs: 24, p: '8px 16px' }
  };

  return (
    <span
      className="mono"
      style={{
        background: bg,
        color: '#fff',
        padding: sizes[size].p,
        borderRadius: 'var(--radius-chip)',
        fontSize: sizes[size].fs,
        fontWeight: 600
      }}
    >
      {text}
    </span>
  );
}