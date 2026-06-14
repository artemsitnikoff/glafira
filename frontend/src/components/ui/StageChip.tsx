import { STAGES, type StageKey } from '@/lib/stages';

interface StageChipProps {
  stage: StageKey | string;
  size?: 'sm' | 'md';
  label?: string;
  color?: string;
}

export function StageChip({ stage, size = 'md', label, color }: StageChipProps) {
  const cfg = STAGES[stage as StageKey];
  const text = label ?? cfg?.label ?? stage;
  const bg = color ?? cfg?.color ?? STAGES.added.color;

  if (!text) return null;

  const padding = size === 'sm' ? '2px 8px' : '4px 12px';
  const fs = size === 'sm' ? 11 : 11;

  return (
    <span
      style={{
        background: bg,
        color: '#fff',
        padding,
        borderRadius: 'var(--radius-chip)',
        fontSize: fs,
        fontWeight: 500
      }}
    >
      {text}
    </span>
  );
}