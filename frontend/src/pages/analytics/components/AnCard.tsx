import type { ReactNode } from 'react';

interface AnCardProps {
  title?: string;
  sub?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function AnCard({ title, sub, right, children, className }: AnCardProps) {
  return (
    <div className={`an-card ${className || ''}`}>
      {(title || right) && (
        <div className="an-card-head">
          <div>
            {title && <div className="title">{title}</div>}
            {sub && <div className="sub">{sub}</div>}
          </div>
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

interface AnCardEmptyProps {
  title?: string;
  sub?: string;
}

/** Честный empty-state «Недостаточно данных за период» внутри карточки. */
export function AnCardEmpty({
  title = 'Недостаточно данных за период',
  sub = 'Расширьте период или измените фильтры.',
}: AnCardEmptyProps) {
  return (
    <div className="an-card-empty">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 3v18h18" />
        <path d="M7 14l3-3 3 3 4-5" />
      </svg>
      <div className="em-title">{title}</div>
      <div className="em-sub">{sub}</div>
    </div>
  );
}
