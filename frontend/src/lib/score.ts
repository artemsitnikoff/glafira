// Единый порог «балл → диапазон» (80/50). Источник правды, чтобы цвета и тексты скоринга
// не расходились между компонентами. (До этого AIVerdictCard ошибочно брал 60 для цвета,
// но 50 для текста вердикта — латентный баг: красная точка при жёлтом тексте.)
export type ScoreBand = 'green' | 'yellow' | 'red' | 'none';

export function scoreBand(value: number | null | undefined): ScoreBand {
  if (value == null) return 'none';
  if (value >= 80) return 'green';
  if (value >= 50) return 'yellow';
  return 'red';
}

// CSS-класс воронки (.score-green / .score-yellow / .score-red), '' для пустого значения.
export function scoreClass(value: number | null | undefined): string {
  const b = scoreBand(value);
  return b === 'none' ? '' : `score-${b}`;
}
