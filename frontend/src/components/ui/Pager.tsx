import { Icon } from './Icon';
import './Pager.css';

// Список номеров страниц с «…» (шаблон как в .ssa-pager/.av-pager).
function pageList(cur: number, count: number): (number | '…')[] {
  const out: (number | '…')[] = [];
  for (let p = 1; p <= count; p++) {
    if (p === 1 || p === count || (p >= cur - 1 && p <= cur + 1)) {
      out.push(p);
    } else if (out[out.length - 1] !== '…') {
      out.push('…');
    }
  }
  return out;
}

type Props = {
  page: number; // 1-based
  pages: number;
  total?: number;
  rangeStart?: number;
  rangeEnd?: number;
  onPage: (p: number) => void;
};

// Общий номерной пагинатор. Единый стиль на всё приложение — дизайн не выдумывать.
export function Pager({ page, pages, total, rangeStart, rangeEnd, onPage }: Props) {
  if (pages <= 1) return null;
  const go = (p: number) => {
    const next = Math.min(Math.max(1, p), pages);
    if (next !== page) onPage(next);
  };
  const showInfo = total != null && rangeStart != null && rangeEnd != null;
  return (
    <div className="pgr">
      {showInfo && (
        <div className="pgr-info">
          Показано <b>{rangeStart}–{rangeEnd}</b> из <b className="t-mono">{total}</b>
        </div>
      )}
      <div className="pgr-ctrls">
        <button className="pgr-nav" disabled={page <= 1} onClick={() => go(page - 1)} aria-label="Назад">
          <Icon name="chevron-left" size={15} />
        </button>
        {pageList(page, pages).map((p, i) =>
          p === '…' ? (
            <span key={`e${i}`} className="pgr-ell">…</span>
          ) : (
            <button
              key={p}
              className={`pgr-pg ${p === page ? 'active' : ''}`}
              onClick={() => go(p)}
            >
              {p}
            </button>
          )
        )}
        <button className="pgr-nav" disabled={page >= pages} onClick={() => go(page + 1)} aria-label="Вперёд">
          <Icon name="chevron-right" size={15} />
        </button>
      </div>
    </div>
  );
}
