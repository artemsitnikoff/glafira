export function formatRelativeTime(input: string | number | Date): string {
  const t = typeof input === 'string' || typeof input === 'number' ? new Date(input).getTime() : input.getTime();
  const diffSec = Math.floor((Date.now() - t) / 1000);
  if (diffSec < 60) return 'только что';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} мин назад`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} ч назад`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay === 1) return 'вчера';
  if (diffDay < 7) return `${diffDay} дн назад`;
  return new Date(t).toLocaleDateString('ru-RU');
}

export function formatHHMM(input: number | Date = Date.now()): string {
  const d = typeof input === 'number' ? new Date(input) : input;
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}