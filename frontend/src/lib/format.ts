// Форматирование зарплатной вилки. «220 000 ₽» (ru-локаль). RUB → ₽, иначе код валюты.
export function formatSalaryRange(from: number | null | undefined, to: number | null | undefined, currency?: string | null): string {
  const sym = !currency || currency === 'RUB' ? '₽' : currency;

  if (from == null && to == null) return '';

  // Только from
  if (from != null && to == null) {
    return `от ${from.toLocaleString('ru-RU')} ${sym}`;
  }

  // Только to
  if (from == null && to != null) {
    return `до ${to.toLocaleString('ru-RU')} ${sym}`;
  }

  // Оба есть
  if (from != null && to != null) {
    // Одинаковые значения
    if (from === to) {
      return `${from.toLocaleString('ru-RU')} ${sym}`;
    }
    // Разные значения
    return `${from.toLocaleString('ru-RU')} – ${to.toLocaleString('ru-RU')} ${sym}`;
  }

  return '';
}
