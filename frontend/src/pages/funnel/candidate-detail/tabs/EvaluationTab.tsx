import { Icon } from '@/components/ui/Icon';
import { useEvaluation } from '@/api/hooks/useEvaluation';
import { useEvaluate } from '@/api/mutations/candidateDetail';
import { useCandidateApplications } from '@/api/hooks/useCandidates';
import { AIVerdictCard } from '../AIVerdictCard';

type Props = {
  candidateId?: string;
  applicationId?: string;
  candidate?: any;
  fromPool?: boolean;
};

// Status values from backend contract: 'match'|'partial'|'miss'
const STATUS_ICONS = {
  match: '✅',
  partial: '⚠️',
  miss: '❌',
} as const;

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
  return (
    <div className="evaluation-card" style={{ marginBottom: 'var(--space-4)' }}>
      {vacancyName && (
        <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: '16px', fontWeight: '600' }}>
          {vacancyName}
        </h3>
      )}

      <AIVerdictCard
        evaluation={evaluation}
        onReEvaluate={onReEvaluate}
        loading={loading}
      />

      {/* Strengths and Risks */}
      <div className="strengths-risks">
        <div className="strengths-risks__column">
          <h4>✅ Сильные стороны</h4>
          {evaluation.strengths && evaluation.strengths.length > 0 ? (
            <ul className="strengths-risks__list">
              {evaluation.strengths.map((strength: string, index: number) => (
                <li key={index} className="strengths-risks__item">
                  {strength}
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ color: 'var(--fg-3)', fontStyle: 'italic' }}>Не выявлено</p>
          )}
        </div>

        <div className="strengths-risks__column">
          <h4>⚠️ Риски</h4>
          {evaluation.risks && evaluation.risks.length > 0 ? (
            <ul className="strengths-risks__list">
              {evaluation.risks.map((risk: string, index: number) => (
                <li key={index} className="strengths-risks__item">
                  {risk}
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ color: 'var(--fg-3)', fontStyle: 'italic' }}>Не выявлено</p>
          )}
        </div>
      </div>

      {/* Requirements Match Table */}
      {evaluation.requirements_match && evaluation.requirements_match.length > 0 && (
        <div>
          <h4 style={{ margin: 'var(--space-4) 0 var(--space-2) 0', fontSize: '14px', fontWeight: '600' }}>
            Соответствие требованиям
          </h4>
          <table className="requirements-table">
            <thead>
              <tr>
                <th>Требование</th>
                <th>Статус</th>
                <th>Комментарий</th>
              </tr>
            </thead>
            <tbody>
              {evaluation.requirements_match.map((match: any, index: number) => (
                <tr key={index}>
                  <td>{match.requirement}</td>
                  <td>
                    <div className="requirements-table__status">
                      <span className="requirements-table__status-icon">
                        {STATUS_ICONS[match.status as keyof typeof STATUS_ICONS] || '❓'}
                      </span>
                      <span>{match.status}</span>
                    </div>
                  </td>
                  <td>{match.comment || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Forecast */}
      {evaluation.forecast && (
        <div style={{ marginTop: 'var(--space-4)' }}>
          <h4 style={{ margin: '0 0 var(--space-2) 0', fontSize: '14px', fontWeight: '600' }}>
            Прогноз
          </h4>
          <p style={{ color: 'var(--fg-2)', lineHeight: '1.5' }}>
            {evaluation.forecast}
          </p>
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
    <div className="tab-content">
      <SingleEvaluation
        evaluation={evaluation}
        onReEvaluate={handleReEvaluate}
        loading={evaluateMutation.isPending}
      />
    </div>
  );
}