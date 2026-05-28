import { STAGES, type StageKey } from '@/lib/stages';

interface StageChipProps {
  stage: StageKey | string;
  size?: 'sm' | 'md';
}

export function StageChip({ stage, size = 'md' }: StageChipProps) {
  const cfg = STAGES[stage as StageKey];
  if (!cfg) return null;

  const padding = size === 'sm' ? '2px 8px' : '4px 12px';
  const fs = size === 'sm' ? 11 : 11;

  return (
    <span
      style={{
        background: cfg.color,
        color: '#fff',
        padding,
        borderRadius: 'var(--radius-chip)',
        fontSize: fs,
        fontWeight: 500
      }}
    >
      {cfg.label}
    </span>
  );
}