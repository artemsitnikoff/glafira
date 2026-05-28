import { Icon } from '@/components/ui/Icon';
import { useCandidateDetail } from '@/api/hooks/useCandidateDetail';
import { useUpdateCandidate } from '@/api/mutations/candidateDetail';
import type { ApplicationRow } from '@/api/aliases';

type Props = {
  candidateId: string;
  application: ApplicationRow;
  onClose: () => void;
};

export function CandidateHeader({ candidateId, application, onClose }: Props) {
  const { data: candidate, isLoading } = useCandidateDetail(candidateId);
  const updateMutation = useUpdateCandidate(candidateId);

  if (isLoading || !candidate) {
    return (
      <div className="candidate-header">
        <div className="candidate-header__avatar">
          <Icon name="user" size={24} />
        </div>
        <div className="candidate-header__info">
          <div style={{ width: '200px', height: '24px', background: 'var(--bg-3)', borderRadius: 'var(--radius-md)' }} />
        </div>
        <button className="candidate-header__close" onClick={onClose}>
          <Icon name="x" size={20} />
        </button>
      </div>
    );
  }

  const initials = candidate.full_name
    .split(' ')
    .map(name => name[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  const scoreClass = candidate.ai_score
    ? candidate.ai_score >= 80 ? 'score-badge--high'
      : candidate.ai_score >= 50 ? 'score-badge--mid'
      : 'score-badge--low'
    : '';

  const stageClass = `stage-chip--${application.stage.replace('_', '-')}`;

  function handlePreferredChannelChange(e: React.ChangeEvent<HTMLSelectElement>) {
    updateMutation.mutate({
      preferred_channel: e.target.value,
    });
  }

  return (
    <div className="candidate-header">
      <div className="candidate-header__avatar">
        {initials}
      </div>

      <div className="candidate-header__info">
        <h1 className="candidate-header__name">
          {candidate.full_name}
        </h1>

        <div className="candidate-header__badges">
          {candidate.ai_score && (
            <span className={`score-badge ${scoreClass}`}>
              {candidate.ai_score}
            </span>
          )}
          <span className={`stage-chip ${stageClass}`}>
            {application.stage}
          </span>
        </div>

        <div className="candidate-header__meta">
          <div>
            📱 {candidate.phone || 'Не указан'} •
            ✉️ {candidate.email || 'Не указан'}
          </div>
          <div>
            📍 {candidate.city || 'Город не указан'} •
            💰 {candidate.salary_expectation ? `${candidate.salary_expectation.toLocaleString()} ₽` : 'З/п не указана'}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginTop: 'var(--space-1)' }}>
            <span>Предпочитаемый канал:</span>
            <select
              className="preferred-channel-select"
              value={candidate.preferred_channel}
              onChange={handlePreferredChannelChange}
            >
              <option value="telegram">Telegram</option>
              <option value="phone">Телефон</option>
              <option value="email">Email</option>
              <option value="whatsapp">WhatsApp</option>
            </select>
          </div>
        </div>
      </div>

      <button className="candidate-header__close" onClick={onClose} title="Закрыть (Esc)">
        <Icon name="x" size={20} />
      </button>
    </div>
  );
}