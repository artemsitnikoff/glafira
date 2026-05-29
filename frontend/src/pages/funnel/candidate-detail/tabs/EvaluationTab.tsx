import { Icon } from '@/components/ui/Icon';
import { useEvaluation } from '@/api/hooks/useEvaluation';
import { useEvaluate } from '@/api/mutations/candidateDetail';
import { useCandidateApplications } from '@/api/hooks/useCandidates';
import { AIVerdictCard } from '@/components/candidates/AIVerdictCard';

type Props = {
  candidateId?: string;
  applicationId?: string;
  candidate?: any;
  fromPool?: boolean;
};

// Component for single evaluation display
function SingleEvaluation({
  evaluation,
  vacancyName,
  onReEvaluate,
  loading
}: {
  evaluation: any;
  vacancyName?: string;
  onReEvaluate: () => void;
  loading: boolean;
}) {
  // Calculate totals for criteria
  const totalPoints = evaluation.requirements_match?.reduce((sum: number, match: any) => sum + match.points, 0) || 0;
  const totalWeight = evaluation.requirements_match?.reduce((sum: number, match: any) => sum + match.weight, 0) || 0;

  return (
    <div className="ai-single">
      {vacancyName && (
        <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: '16px', fontWeight: '600' }}>
          {vacancyName}
        </h3>
      )}

      {/* AI Verdict Card with hideLink */}
      <AIVerdictCard evaluation={evaluation} hideLink />

      {/* Analysis AI */}
      <h3 className="cc-sec-title">Анализ AI</h3>

      {/* Сильные стороны */}
      {evaluation.strengths && evaluation.strengths.length > 0 && (
        <div className="msg ai-msg ai-msg-good" style={{ maxWidth: '100%' }}>
          <div className="ai-name ai-name-good">
            <span className="cc-sec-emoji">✅</span> Сильные стороны
          </div>
          <ul className="ai-msg-list">
            {evaluation.strengths.map((strength: string, index: number) => (
              <li key={index}>{strength}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Слабые стороны */}
      {evaluation.risks && evaluation.risks.length > 0 && (
        <div className="msg ai-msg ai-msg-warn" style={{ maxWidth: '100%', marginTop: '8px' }}>
          <div className="ai-name ai-name-warn">
            <span className="cc-sec-emoji">⚠️</span> Слабые стороны
          </div>
          <ul className="ai-msg-list">
            {evaluation.risks.map((risk: string, index: number) => (
              <li key={index}>{risk}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Вопросы для первого контакта */}
      {evaluation.questions && evaluation.questions.length > 0 && (
        <div className="msg ai-msg ai-msg-q" style={{ maxWidth: '100%', marginTop: '8px' }}>
          <div className="ai-name ai-name-q">
            <span className="cc-sec-emoji">💬</span> Вопросы для первого контакта
          </div>
          <ol className="ai-msg-list ai-msg-list-num">
            {evaluation.questions.slice(0, 5).map((question: string, index: number) => (
              <li key={index}>{question}</li>
            ))}
          </ol>
        </div>
      )}

      {/* Разбор по критериям */}
      {evaluation.requirements_match && evaluation.requirements_match.length > 0 && (
        <>
          <h3 className="cc-sec-title">
            Разбор по критериям
            <span className="crit-total">
              <span className="t-mono">{totalPoints}</span> / <span className="t-mono">{totalWeight}</span>
            </span>
          </h3>
          <div className="crit-list">
            {evaluation.requirements_match.map((match: any, index: number) => {
              const pct = match.weight ? Math.round((match.points / match.weight) * 100) : 0;
              const color = match.weight === 0 ? 'gray' : pct >= 80 ? 'green' : pct >= 40 ? 'yellow' : 'red';
              return (
                <div key={index} className={`crit-row crit-${color}`}>
                  <div className="crit-head">
                    <span className="crit-label">{match.criterion}</span>
                    <span className="crit-pts t-mono">
                      {match.points}<span className="crit-pts-max"> / {match.weight || '—'}</span>
                    </span>
                  </div>
                  <div className="crit-bar">
                    <span style={{ width: `${pct}%` }} />
                  </div>
                  <div className="crit-comment">{match.comment}</div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {onReEvaluate && (
        <div style={{ marginTop: '16px', textAlign: 'right' }}>
          <button
            className="btn btn-sm btn-secondary"
            onClick={onReEvaluate}
            disabled={loading}
          >
            <Icon name={loading ? "loader" : "refresh-cw"} size={14} />
            Переоценить
          </button>
        </div>
      )}
    </div>
  );
}

// Component for evaluation per vacancy for fromPool mode
function EvaluationPerVacancy({
  application,
  candidateId
}: {
  application: any;
  candidateId: string;
}) {
  const { data: evaluation, isLoading: evalLoading, error: evalError } = useEvaluation(
    candidateId,
    application.application_id
  );
  const evaluateMutation = useEvaluate();

  const handleEvaluate = () => {
    evaluateMutation.mutate({
      candidate_id: candidateId,
      vacancy_id: application.vacancy_id,
    });
  };

  if (evalLoading) {
    return (
      <div className="evaluation-card" style={{ marginBottom: 'var(--space-4)' }}>
        <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: '16px', fontWeight: '600' }}>
          {application.vacancy_name}
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <Icon name="loader" size={24} />
          <p>Загрузка оценки...</p>
        </div>
      </div>
    );
  }

  if (evalError || !evaluation) {
    return (
      <div className="evaluation-card" style={{ marginBottom: 'var(--space-4)' }}>
        <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: '16px', fontWeight: '600' }}>
          {application.vacancy_name}
        </h3>
        <div className="empty-state">
          <Icon name="brain" size={32} className="empty-state__icon" />
          <p className="empty-state__text">
            {evalError ? 'Ошибка загрузки оценки' : 'Оценка не проводилась'}
          </p>
          <button
            className="candidate-toolbar__btn candidate-toolbar__btn--primary"
            onClick={handleEvaluate}
            disabled={evaluateMutation.isPending}
            style={{ marginTop: 'var(--space-2)' }}
          >
            <Icon name={evaluateMutation.isPending ? "loader" : "zap"} size={16} />
            Запустить оценку
          </button>
        </div>
      </div>
    );
  }

  return (
    <SingleEvaluation
      evaluation={evaluation}
      vacancyName={application.vacancy_name}
      onReEvaluate={handleEvaluate}
      loading={evaluateMutation.isPending}
    />
  );
}

export function EvaluationTab({ candidateId, applicationId, candidate, fromPool }: Props) {
  const actualCandidateId = candidateId || candidate?.id;

  // Get all applications if fromPool mode
  const { data: applications, isLoading: applicationsLoading } = useCandidateApplications(
    fromPool ? actualCandidateId : '',
  );

  // Single evaluation for regular funnel mode
  const { data: evaluation, isLoading: evalLoading, error } = useEvaluation(
    actualCandidateId,
    (!fromPool && applicationId) ? applicationId : ''
  );

  const evaluateMutation = useEvaluate();

  function handleReEvaluate() {
    evaluateMutation.mutate({
      candidate_id: actualCandidateId,
      vacancy_id: null, // Will be resolved from application
    });
  }

  // FromPool mode: show evaluations per vacancy
  if (fromPool) {
    if (applicationsLoading) {
      return (
        <div className="tab-content">
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <Icon name="loader" size={24} />
            <p>Загружаются заявки...</p>
          </div>
        </div>
      );
    }

    if (!applications || applications.length === 0) {
      return (
        <div className="tab-content">
          <div className="empty-state">
            <Icon name="briefcase" size={48} className="empty-state__icon" />
            <h3 style={{ margin: '0 0 var(--space-2) 0', fontSize: '16px', fontWeight: '600' }}>
              Нет участий в вакансиях
            </h3>
            <p className="empty-state__text">
              Кандидат не участвовал в вакансиях, оценка невозможна
            </p>
          </div>
        </div>
      );
    }

    return (
      <div className="tab-content">
        <h2 style={{ margin: '0 0 var(--space-4) 0', fontSize: '18px', fontWeight: '600' }}>
          Оценки по вакансиям
        </h2>
        {applications.map((application) => (
          <EvaluationPerVacancy
            key={application.application_id}
            application={application}
            candidateId={actualCandidateId}
          />
        ))}
      </div>
    );
  }

  // Regular funnel mode: single evaluation
  if (evalLoading) {
    return (
      <div className="tab-content">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <Icon name="loader" size={24} />
          <p>Загружается оценка...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="tab-content">
        <div className="empty-state">
          <Icon name="alert-circle" size={48} className="empty-state__icon" />
          <p className="empty-state__text">
            Ошибка загрузки оценки: {error.message}
          </p>
          <button
            className="candidate-toolbar__btn candidate-toolbar__btn--primary"
            onClick={handleReEvaluate}
            disabled={evaluateMutation.isPending}
            style={{ marginTop: 'var(--space-3)' }}
          >
            <Icon name={evaluateMutation.isPending ? "loader" : "refresh-cw"} size={16} />
            Попробовать снова
          </button>
        </div>
      </div>
    );
  }

  if (!evaluation) {
    return (
      <div className="tab-content">
        <div className="empty-state">
          <Icon name="brain" size={48} className="empty-state__icon" />
          <h3 style={{ margin: '0 0 var(--space-2) 0', fontSize: '16px', fontWeight: '600' }}>
            Оценка не найдена
          </h3>
          <p className="empty-state__text">
            Для данной вакансии оценка ещё не проводилась. Запустите AI-анализ для получения подробного отчёта.
          </p>
          <button
            className="candidate-toolbar__btn candidate-toolbar__btn--primary"
            onClick={handleReEvaluate}
            disabled={evaluateMutation.isPending}
            style={{ marginTop: 'var(--space-3)' }}
          >
            <Icon name={evaluateMutation.isPending ? "loader" : "zap"} size={16} />
            Запустить оценку
          </button>
        </div>
      </div>
    );
  }

  return (
    <SingleEvaluation
      evaluation={evaluation}
      onReEvaluate={handleReEvaluate}
      loading={evaluateMutation.isPending}
    />
  );
}