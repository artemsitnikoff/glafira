// HTML → плоский текст с сохранением переводов строк.
// Часть описаний (опыт/«о себе») из Потока приходит с разметкой (<p>/<br>/&nbsp;),
// а таб «Резюме» рендерит их как текст → раньше были видны теги. Здесь блочные
// теги превращаем в переводы строк, остальные снимаем, сущности декодируем.
// Для уже чистого текста (без тегов/сущностей) — no-op (быстрый выход).
export function htmlToText(input?: string | null): string {
  if (!input) return '';
  if (!/[<&]/.test(input)) return input;

  const withBreaks = input
    .replace(/<\s*br\s*\/?\s*>/gi, '\n')
    .replace(/<\/\s*(p|div|li|h[1-6]|tr)\s*>/gi, '\n');

  // DOMParser снимает оставшиеся теги и декодирует сущности (&nbsp; →  , &amp; → &).
  const text = new DOMParser().parseFromString(withBreaks, 'text/html').body.textContent ?? '';

  return text
    .replace(/\u00A0/g, ' ')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
