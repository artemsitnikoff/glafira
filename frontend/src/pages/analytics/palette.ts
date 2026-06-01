/**
 * Палитра ЦВЕТОВ ДАННЫХ для графиков аналитики.
 * Это НЕ UI-токены (tokens.css) — это легитимные hex для серий/категорий
 * данных, где у бека нет своего поля `color`. ank-палитра.
 *
 * Цвета этапов/источников, пришедшие С БЕКА (поле `color`), используются
 * напрямую и здесь не дублируются.
 */
export const ANALYTICS_PALETTE = {
  blue: '#2A8AF0',
  violet: '#7E5CF0',
  red: '#DC4646',
  yellow: '#E0A21A',
  orange: '#E08A3C',
  teal: '#3FA3B3',
  green: '#16A34A',
  gray: '#5B6573',
} as const;

// Упорядоченный список для циклического назначения по индексу серии.
export const ANALYTICS_PALETTE_SEQ: string[] = [
  ANALYTICS_PALETTE.blue,
  ANALYTICS_PALETTE.violet,
  ANALYTICS_PALETTE.teal,
  ANALYTICS_PALETTE.orange,
  ANALYTICS_PALETTE.green,
  ANALYTICS_PALETTE.yellow,
  ANALYTICS_PALETTE.red,
  ANALYTICS_PALETTE.gray,
];

export function paletteAt(index: number): string {
  return ANALYTICS_PALETTE_SEQ[index % ANALYTICS_PALETTE_SEQ.length];
}
