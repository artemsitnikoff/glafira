import { Icon } from '@/components/ui/Icon';
import { useEvents } from '@/api/hooks/useEvents';

type Props = {
  candidateId?: string;
  candidate?: any;
  fromPool?: boolean;
};

// Event type mappings for display
const EVENT_LABELS = {
  qual: 'Квалификация',
  new: 'Добавление',
  score: 'AI-оценка',
  offer: 'Оффер',
  move: 'Перемещение',
  verify: 'Верификация',
  comment: 'Комментарий',
  document: 'Документ',
} as const;

export function AllActionsTab({ candidateId, candidate }: Props) {
  const actualCandidateId = candidateId || candidate?.id;
  const { data: events, isLoading } = useEvents({ candidate_id: actualCandidateId, limit: 100 });

  if (isLoading) {
    return (
      <div className="tab-content">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <Icon name="loader" size={24} />
          <p>Загружается история действий...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="tab-content">
      <h2 style={{ margin: '0 0 var(--space-4) 0', fontSize: '18px', fontWeight: '600' }}>
        История действий
      </h2>

      {events && events.length > 0 ? (
        <div className="events-timeline">
          {events.map((event) => (
            <div key={event.id} className={`timeline-event timeline-event--${event.type}`}>
              <div className="timeline-event__content">
                <div className="timeline-event__header">
                  <span className="timeline-event__type">
                    {EVENT_LABELS[event.type as keyof typeof EVENT_LABELS] || event.type}
                  </span>
                  <span className="timeline-event__time">
                    {new Date(event.created_at).toLocaleDateString('ru', {
                      day: 'numeric',
                      month: 'short',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </div>
                <p className="timeline-event__text">
                  {event.text}
                </p>
                {/* Show entities if available */}
                {event.entities && Object.keys(event.entities).length > 0 && (
                  <details style={{ marginTop: 'var(--space-2)', fontSize: '12px', color: 'var(--fg-3)' }}>
                    <summary style={{ cursor: 'pointer' }}>Детали события</summary>
                    <pre style={{ marginTop: 'var(--space-1)', whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
                      {JSON.stringify(event.entities, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <Icon name="activity" size={48} className="empty-state__icon" />
          <p className="empty-state__text">
            История действий пуста
          </p>
        </div>
      )}
    </div>
  );
}