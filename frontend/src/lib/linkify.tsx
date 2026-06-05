import type { ReactNode } from 'react';

// Превращает URL в обычном тексте в кликабельные ссылки.
// БЕЗОПАСНО: строит React-узлы из plain-текста (никакого dangerouslySetInnerHTML),
// поэтому XSS невозможен. Распознаёт только http(s):// и www.* — без «угадывания»
// голых доменов, чтобы не ловить ложные срабатывания в обычном тексте.
const URL_RE = /(https?:\/\/[^\s<]+|www\.[^\s<]+)/gi;
// Хвостовая пунктуация прозы (точка/запятая/скобка после ссылки) — не часть URL.
const TRAILING_PUNCT = /[.,!?;:)\]}'"»…]+$/;

export function linkify(text: string | null | undefined): ReactNode[] {
  if (!text) return [text ?? ''];

  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  URL_RE.lastIndex = 0;

  let match: RegExpExecArray | null;
  while ((match = URL_RE.exec(text)) !== null) {
    const start = match.index;
    const full = match[0];

    // Отрезаем хвостовую пунктуацию из ссылки в отдельный текстовый узел
    let url = full;
    let trailing = '';
    const tp = url.match(TRAILING_PUNCT);
    if (tp) {
      trailing = tp[0];
      url = url.slice(0, url.length - trailing.length);
    }

    if (start > lastIndex) nodes.push(text.slice(lastIndex, start));

    const href = url.toLowerCase().startsWith('www.') ? `https://${url}` : url;
    nodes.push(
      <a
        key={`lnk-${key++}`}
        href={href}
        target="_blank"
        rel="noopener noreferrer nofollow"
        // клик по ссылке не должен «проваливаться» в обработчики родителя (раскрытие и т.п.)
        onClick={(e) => e.stopPropagation()}
      >
        {url}
      </a>
    );
    if (trailing) nodes.push(trailing);

    lastIndex = start + full.length;
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));

  return nodes.length ? nodes : [text];
}
