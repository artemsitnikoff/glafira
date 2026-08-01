// Категория результата теста → CSS-класс цвета (c5 высшая … c1 низшая).
// Ключи — из category_thresholds[].key на беке (seed: high/above/medium/below/low).
// Незнакомый ключ (кастомная категория админа) → нейтральный 'c0', без выдумок цвета.
export const TEST_CAT_CLASS: Record<string, string> = {
  high: 'c5',
  above: 'c4',
  medium: 'c3',
  below: 'c2',
  low: 'c1',
};

/** CSS-суффикс класса категории (.ts-cat cN / .ts-pill cN). */
export function testCatClass(key: string | null | undefined): string {
  return (key && TEST_CAT_CLASS[key]) || 'c0';
}

// Emoji-маркер порога (category_thresholds[].marker) → CSS-класс лампочки светофора.
// Маркеры из seed: 🟢/🟡/🟠/🔴. Незнакомый → нейтральный.
export function testMarkerClass(marker: string | null | undefined): string {
  switch (marker) {
    case '🟢':
      return 'lamp-green';
    case '🟡':
      return 'lamp-yellow';
    case '🟠':
      return 'lamp-orange';
    case '🔴':
      return 'lamp-red';
    default:
      return 'lamp-neutral';
  }
}
