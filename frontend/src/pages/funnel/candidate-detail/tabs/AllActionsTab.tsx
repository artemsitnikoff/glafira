import { Icon } from '@/components/ui/Icon';
import { useEvents } from '@/api/hooks/useEvents';

type Props = {
  candidateId?: string;
  candidate?: any;
  fromPool?: boolean;
};

// Локальный тип для событий с полями actor_type и actor_name (которых может ещё не быть в сгенерированном типе)
type ActionEvent = {
  id: string;
  type: string;
  text: string;
  created_at: string;
  actor_type?: 'human' | 'ai' | 'system';
  actor_name?: string | null;
  entities?: any;
};

// Маппинг типа события → { icon, ai, who }
const EVENT_MAPPING = {
  score: { icon: 'sparkle' as const, ai: true, who: 'Глафира' },
  verify: { icon: 'shield' as const, ai: true, who: 'Глафира' },
  comment: { icon: 'message-square' as const, ai: false, who: null },
  move: { icon: 'arrow-right' as const, ai: false, who: null },
  document: { icon: 'file-text' as const, ai: false, who: null },
  new: { icon: 'plus' as const, ai: false, who: 'Источник' },
  offer: { icon: 'check-circle' as const, ai: false, who: null },
  qual: { icon: 'sparkle' as const, ai: true, who: 'Глафира' },
};

export function AllActionsTab({ candidateId, candidate }: Props) {
  const actualCandidateId = candidateId || candidate?.id;
  const { data: events, isLoading } = useEvents({ candidate_id: actualCandidateId, limit: 100 });

  if (isLoading) {
    return (
      <div className="card-block">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', padding: '12px 0' }}>
          <Icon name="loader" size={16} />
          <span style={{ fontSize: '13px', color: 'var(--fg-3)' }}>Загружается история действий...</span>
        </div>
      </div>
    );
  }

  const formatTime = (isoDate: string) => {
    const date = new Date(isoDate);
    const dateStr = date.toLocaleDateString('ru', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
    });
    const timeStr = date.toLocaleTimeString('ru', {
      hour: '2-digit',
      minute: '2-digit',
    });
    return `${dateStr} · ${timeStr}`;
  };

  const getEventMeta = (event: ActionEvent) => {
    const eventData = event as any;
    const mapping = EVENT_MAPPING[event.type as keyof typeof EVENT_MAPPING];

    if (!mapping) {
      return {
        icon: 'open' as const,
        ai: eventData.actor_type === 'ai',
        who: eventData.actor_name || '—',
      };
    }

    // Общее правило: если actor_type === 'ai' → перекрываем маппинг
    if (eventData.actor_type === 'ai') {
      return {
        icon: mapping.icon,
        ai: true,
        who: 'Глафира',
      };
    }

    return {
      icon: mapping.icon,
      ai: mapping.ai,
      who: mapping.who || eventData.actor_name || 'Рекрутёр',
    };
  };

  return (
    <div className="card-block">
      <div className="actions-feed">
        {events && events.length > 0 ? (
          events.map((event) => {
            const eventTyped = event as ActionEvent;
            const { icon, ai, who } = getEventMeta(eventTyped);
            return (
              <div key={event.id} className="action-row">
                <div className={`action-icon ${ai ? 'ai' : ''}`}>
                  <Icon name={icon} size={13} />
                </div>
                <div className="action-body">
                  <div className="action-text">
                    <span className={`action-who ${ai ? 'ai' : ''}`}>{who}</span>
                    {' '}
                    {event.text}
                  </div>
                  <div className="action-time t-mono">{formatTime(event.created_at)}</div>
                </div>
              </div>
            );
          })
        ) : (
          <div style={{ padding: '20px 0', textAlign: 'center', color: 'var(--fg-3)', fontSize: '13px' }}>
            История действий пуста
          </div>
        )}
      </div>
    </div>
  );
}