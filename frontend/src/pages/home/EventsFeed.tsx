import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useHomeEvents } from '@/api/hooks/useHomeEvents';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { formatRelativeTime } from '@/lib/time';
import { EVENT_COLORS } from '@/lib/event-colors';

function highlightGlafira(text: string): React.ReactNode {
  const parts = text.split(/(Глафира)/g);
  return parts.map((part, i) =>
    part === 'Глафира' ? (
      <span key={i} className="glafira-mention">{part}</span>
    ) : (
      part
    )
  );
}

export function EventsFeed() {
  const { data, isLoading } = useHomeEvents(30);
  const navigate = useNavigate();

  if (isLoading) return <Skeleton height={380} />;

  const items = data ?? [];

  return (
    <section className="block events-block">
      <header className="block__head">
        <div className="block__title">
          Лента событий <span className="live-dot" />live
        </div>
      </header>
      <div className="events-list">
        {items.length === 0 ? (
          <EmptyState title="Пока событий нет" />
        ) : (
          items.map(ev => (
            <div key={ev.id} className="event-row">
              <span
                className="event-row__dot"
                style={{ background: EVENT_COLORS[ev.type] ?? 'var(--fg-3)' }}
              />
              <div className="event-row__body">
                <div className="event-row__text">{highlightGlafira(ev.text)}</div>
                {ev.entities && ev.entities.length > 0 && (
                  <div className="event-row__entities">
                    {ev.entities.map((e: any, i: number) => (
                      <button
                        key={i}
                        className={`entity-chip entity-chip--${e.type}`}
                        onClick={() => {
                          if (e.type === 'candidate') navigate(`/candidates/${e.id}`);
                          else if (e.type === 'vacancy') navigate(`/vacancies/${e.id}`);
                        }}
                      >
                        {e.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <span className="event-row__time">{formatRelativeTime(ev.created_at)}</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}