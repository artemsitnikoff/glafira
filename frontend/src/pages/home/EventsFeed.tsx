import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useHomeEvents } from '@/api/hooks/useHomeEvents';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { formatRelativeTime } from '@/lib/time';

import { Icon } from '@/components/ui/Icon';

// Расширение типа события для контекста (openapi не регенерён)
interface ExtendedEvent {
  id: string;
  type: string;
  text: string;
  created_at: string;
  candidate_id?: string;
  candidate_name?: string;
  vacancy_id?: string;
  vacancy_name?: string;
}

const EVENT_ICON: Record<string, any> = {
  qual: 'check',
  new: 'sparkle',
  score: 'star',
  offer: 'check',
  move: 'chevR',
};

// Экранируем пользовательский текст (ФИО/имя файла/комментарий) ДО подсветки —
// иначе '<'/'>' из Event.text попадут в DOM как разметка (Stored XSS). & — первым.
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function parseEventText(text: string): React.ReactNode {
  // Highlight Глафира (по уже экранированному тексту — подсветка добавляет только безопасные span)
  let result = escapeHtml(text).replace(/Глафира/g, '<span class="anatoly">Глафира</span>');

  // Find entities (кандидат/вакансия names) and mark them for highlighting
  result = result.replace(/([«»])([^«»]+)\1/g, '<span class="ent">$2</span>');
  result = result.replace(/(кандидат(?:а|у)?) ([А-ЯЁ][а-яё]+ [А-ЯЁ]\.?)/g, '$1 <span class="ent">$2</span>');
  result = result.replace(/(Заказчик) ([«»])([^«»]+)\2/g, '$1 <span class="ent">«$3»</span>');

  return <span dangerouslySetInnerHTML={{ __html: result }} />;
}

export function EventsFeed() {
  const { data, isLoading } = useHomeEvents(30);
  const navigate = useNavigate();

  if (isLoading) return <Skeleton height={380} />;

  const items = (data ?? []) as ExtendedEvent[];

  return (
    <div className="card-block">
      <div className="card-block-head">
        <div className="title">Лента событий</div>
        <span className="live-dot">live</span>
      </div>
      <div style={{maxHeight: 380, overflowY: 'auto', margin: '0 -4px', padding: '0 4px'}}>
        {items.length === 0 ? (
          <EmptyState title="Пока событий нет" />
        ) : (
          items.map(ev => (
            <div key={ev.id} className="event-row">
              <div className={`event-icon ${ev.type}`}>
                <Icon name={EVENT_ICON[ev.type] || 'check'} size={12}/>
              </div>
              <div className="body">
                <div className="text">{parseEventText(ev.text)}</div>
                {(ev.candidate_name || ev.vacancy_name) && (
                  <div className="context">
                    {ev.candidate_name && (
                      <span
                        className="ent"
                        onClick={() => navigate(`/candidates/${ev.candidate_id}`)}
                      >
                        {ev.candidate_name}
                      </span>
                    )}
                    {ev.candidate_name && ev.vacancy_name && (
                      <span className="context-sep"> • </span>
                    )}
                    {ev.vacancy_name && (
                      <span
                        className="ent"
                        onClick={() => navigate(`/vacancies/${ev.vacancy_id}`)}
                      >
                        {ev.vacancy_name}
                      </span>
                    )}
                  </div>
                )}
                <div className="time">{formatRelativeTime(ev.created_at)}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}