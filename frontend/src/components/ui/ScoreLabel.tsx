// ЕДИНЫЙ бейдж AI-скоринга для всего проекта: светлый пастельный фон + цветной текст,
// моноширинный, фикс-бокс по размеру. 1:1 с эталоном (.score-badge .score-green = ark-green-100/600).
// Инлайн-стили = точные значения эталона, без зависимости от scoped-CSS — совпадает на любом экране
// (воронка / список / пул / карточка / AI-вердикт). Порог цвета — из lib/score.scoreBand (80/50).
import { scoreBand } from '@/lib/score';

type Size = 'sm' | 'md' | 'lg' | 'xl';

const SIZES: Record<Size, { w: number; h: number; fs: number; r: number }> = {
  sm: { w: 30, h: 22, fs: 11, r: 6 },
  md: { w: 36, h: 26, fs: 13, r: 6 },
  lg: { w: 42, h: 32, fs: 15, r: 6 },
  xl: { w: 56, h: 56, fs: 22, r: 8 },
};

const BAND_COLORS = {
  green: { bg: 'var(--ark-green-100)', fg: 'var(--ark-green-600)' },
  yellow: { bg: 'var(--ark-yellow-100)', fg: 'var(--ark-yellow-600)' },
  red: { bg: 'var(--ark-red-100)', fg: 'var(--ark-red-600)' },
  none: { bg: 'var(--bg-3)', fg: 'var(--fg-3)' },
} as const;

function colors(v: number | null | undefined): { bg: string; fg: string } {
  return BAND_COLORS[scoreBand(v)];
}

export function ScoreLabel({ value, size = 'lg', title }: { value: number | null | undefined; size?: Size; title?: string }) {
  const s = SIZES[size];
  const c = colors(value);
  return (
    <span
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'var(--font-mono)',
        fontWeight: 600,
        flex: 'none',
        width: s.w,
        height: s.h,
        fontSize: s.fs,
        borderRadius: s.r,
        background: c.bg,
        color: c.fg,
      }}
    >
      {value == null ? '—' : value}
    </span>
  );
}
