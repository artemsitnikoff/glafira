import { scoreBand } from '@/lib/score';

interface ScoreBadgeProps {
  value: number | null;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

const BAND_BG = {
  green: 'var(--score-green)',
  yellow: 'var(--score-yellow)',
  red: 'var(--score-red)',
  none: 'var(--bg-3)',
} as const;

export function ScoreBadge({ value, size = 'md' }: ScoreBadgeProps) {
  const text = String(value ?? '—');
  const bg = BAND_BG[scoreBand(value)];

  const sizes = {
    sm: { fs: 11, p: '2px 6px' },
    md: { fs: 13, p: '3px 8px' },
    lg: { fs: 15, p: '4px 12px' },
    xl: { fs: 22, p: '8px 16px' }
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