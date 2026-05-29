import { Icon } from '@/components/ui/Icon';
import { useCandidateDetail } from '@/api/hooks/useCandidateDetail';
import type { ApplicationRow } from '@/api/aliases';

type Props = {
  candidateId: string;
  application: ApplicationRow;
  onClose: () => void;
};

export function CandidateHeader({ candidateId, onClose }: Props) {
  const { data: candidate, isLoading } = useCandidateDetail(candidateId);

  if (isLoading || !candidate) {
    return (
      <div className="cd-header">
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

  // Get source for context display
  const getSourceLabel = () => {
    // Derive source from stage or other data - for now use placeholder
    return 'Отклик с HeadHunter';
  };

  const formatDate = () => {
    // Format application date - use a placeholder date for now
    return new Date().toLocaleDateString('ru');
  };

  // Mock vacancy name - in real app would come from props or context
  const vacancyName = 'Frontend-разработчик (Senior)';

  return (
    <div className="cd-header">
      <div className="cd-context">
        <span className="src-pill src-hh">
          {getSourceLabel()}
        </span>
        <span>от {formatDate()}</span>
        <span className="sep">·</span>
        <span>{vacancyName}</span>
      </div>

      <div className="cd-h-main">
        <div className="cd-h-left">
          <div className="cd-name-row">
            <h1 className="cd-name">{candidate.full_name}</h1>
            {/* PdN badge - TODO: implement when has_pdn field is available */}
            {candidate.ai_score && (
              <span className={`score-badge score-${candidate.ai_score >= 80 ? 'green' : candidate.ai_score >= 50 ? 'yellow' : 'red'} score-lg`}>
                {candidate.ai_score}
              </span>
            )}
          </div>
          <div className="cd-exp-line">
            {candidate.experience?.[0]?.period || 'Опыт не указан'} · {candidate.experience?.[0]?.company || 'Компания не указана'}
          </div>
          <div className="cd-salary-line">
            <span className="cd-salary t-mono">
              {candidate.salary_expectation ? `${candidate.salary_expectation.toLocaleString()} ₽` : '—'}
            </span>
            <span className="cd-salary-label">ожидания</span>
          </div>
          <div className="cd-tags-row">
            <button className="tag-add">+ Добавить тег</button>
          </div>
        </div>

        <div className="cd-contact-box">
          <div className="cb-row">
            <span className="cb-label">Телефон:</span>
            <span className="t-mono cb-strong">{candidate.phone || 'Не указан'}</span>
            <div className="mess-icons-row">
              {/* TODO: Add messenger icons when available */}
            </div>
          </div>
          <div className="cb-row">
            <span className="cb-label">Город:</span>
            <span>{candidate.city || 'Не указан'}</span>
          </div>
          <div className="cb-row">
            <span className="cb-label">E-mail:</span>
            <span>{candidate.email || 'Не указан'}</span>
          </div>
        </div>
      </div>

      <button className="candidate-header__close" onClick={onClose} title="Закрыть (Esc)">
        <Icon name="x" size={20} />
      </button>
    </div>
  );
}