import { Icon } from '@/components/ui/Icon';
import { useEvaluation } from '@/api/hooks/useEvaluation';
import { useEvaluate } from '@/api/mutations/candidateDetail';
import { useCandidateApplications } from '@/api/hooks/useCandidates';

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
  // Get score label based on score value
  const getScoreLabel = (score: number) => {
    if (score >= 80) return 'Отлично';
    if (score >= 60) return 'Хорошо';
    if (score >= 40) return 'Средне';
    return 'Слабо';
  };

  // Get color class based on score
  const getScoreColorClass = (score: number) => {
    if (score >= 80) return 'score-green';
    if (score >= 60) return 'score-yellow';
    if (score >= 40) return 'score-yellow';
    return 'score-red';
  };

  return (
    <div className="ai-single" style={{ marginBottom: 'var(--space-4)' }}>
      {vacancyName && (
        <h3 style={{ margin: '0 0 var(--space-3) 0', fontSize: '16px', fontWeight: '600' }}>
          {vacancyName}
        </h3>
      )}

      {/* AI Score Header */}
      {evaluation.score !== undefined && (
        <div className="ai-score-header" style={{ marginBottom: '20px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            marginBottom: '12px',
            padding: '16px',
            background: 'var(--bg-panel-2)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border-1)'
          }}>
            <div className={`score-badge score-xl ${getScoreColorClass(evaluation.score)}`}>
              {evaluation.score}
            </div>
            <div>
              <div style={{
                fontSize: '18px',
                fontWeight: '700',
                color: `var(--${getScoreColorClass(evaluation.score).replace('score-', 'ark-')}-600)`,
                marginBottom: '4px'
              }}>
                {evaluation.score}/100 ({getScoreLabel(evaluation.score)})
              </div>
              {evaluation.summary && (
                <div style={{
                  fontSize: '14px',
                  color: 'var(--fg-2)',
                  lineHeight: '1.4'
                }}>
                  {evaluation.summary}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Requirements breakdown table */}
      {evaluation.requirements_match && evaluation.requirements_match.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <h4 style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: '600', color: 'var(--fg-1)' }}>
            Разбивка по критериям
          </h4>
          <table className="crit-table" style={{
            width: '100%',
            borderCollapse: 'collapse',
            background: '#fff',
            border: '1px solid var(--border-1)',
            borderRadius: 'var(--radius-md)',
            overflow: 'hidden'
          }}>
            <thead>
              <tr style={{ background: 'var(--bg-panel-2)' }}>
                <th className="crit-cell" style={{
                  padding: 'var(--space-2) var(--space-3)',
                  borderBottom: '1px solid var(--border-1)',
                  textAlign: 'left',
                  fontSize: '13px',
                  fontWeight: '600',
                  color: 'var(--fg-1)'
                }}>Критерий</th>
                <th className="crit-cell" style={{
                  padding: 'var(--space-2) var(--space-3)',
                  borderBottom: '1px solid var(--border-1)',
                  textAlign: 'left',
                  fontSize: '13px',
                  fontWeight: '600',
                  color: 'var(--fg-1)',
                  width: '100px'
                }}>Баллы</th>
                <th className="crit-cell" style={{
                  padding: 'var(--space-2) var(--space-3)',
                  borderBottom: '1px solid var(--border-1)',
                  textAlign: 'left',
                  fontSize: '13px',
                  fontWeight: '600',
                  color: 'var(--fg-1)'
                }}>Комментарий</th>
              </tr>
            </thead>
            <tbody>
              {evaluation.requirements_match.map((match: any, index: number) => (
                <tr key={index} className="crit-row">
                  <td className="crit-cell" style={{
                    padding: 'var(--space-2) var(--space-3)',
                    borderBottom: '1px solid var(--border-1)',
                    fontSize: '13px',
                    color: 'var(--fg-1)'
                  }}>
                    {match.criterion}
                  </td>
                  <td className="crit-cell" style={{
                    padding: 'var(--space-2) var(--space-3)',
                    borderBottom: '1px solid var(--border-1)',
                    fontSize: '13px',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--fg-1)'
                  }}>
                    {match.points}/{match.weight}
                  </td>
                  <td className="crit-cell" style={{
                    padding: 'var(--space-2) var(--space-3)',
                    borderBottom: '1px solid var(--border-1)',
                    fontSize: '13px',
                    color: 'var(--fg-2)'
                  }}>
                    {match.comment || '—'}
                  </td>
                </tr>
              ))}
              {/* Total row */}
              <tr style={{ background: 'var(--bg-panel-2)', fontWeight: '600' }}>
                <td className="crit-cell" style={{
                  padding: 'var(--space-2) var(--space-3)',
                  fontSize: '13px',
                  fontWeight: '600',
                  color: 'var(--fg-1)'
                }}>
                  ИТОГО
                </td>
                <td className="crit-cell" style={{
                  padding: 'var(--space-2) var(--space-3)',
                  fontSize: '13px',
                  fontFamily: 'var(--font-mono)',
                  fontWeight: '600',
                  color: 'var(--fg-1)'
                }}>
                  {evaluation.score}
                </td>
                <td className="crit-cell" style={{
                  padding: 'var(--space-2) var(--space-3)',
                  fontSize: '13px',
                  color: 'var(--fg-2)'
                }}>
                  —
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Three analysis blocks */}
      <div style={{ marginBottom: '20px' }}>
        {evaluation.strengths && evaluation.strengths.length > 0 && (
          <div className="msg ai-msg-good">
            <span style={{ marginRight: '8px' }}>✅</span>
            <div>
              <strong>Сильные стороны</strong>
              <ul style={{ margin: '4px 0 0', paddingLeft: '20px' }}>
                {evaluation.strengths.map((strength: string, index: number) => (
                  <li key={index}>{strength}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {evaluation.risks && evaluation.risks.length > 0 && (
          <div className="msg ai-msg-warn">
            <span style={{ marginRight: '8px' }}>⚠️</span>
            <div>
              <strong>Риски</strong>
              <ul style={{ margin: '4px 0 0', paddingLeft: '20px' }}>
                {evaluation.risks.map((risk: string, index: number) => (
                  <li key={index}>{risk}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {evaluation.questions && Object.keys(evaluation.questions).length > 0 && (
          <div className="msg ai-msg-q">
            <span style={{ marginRight: '8px' }}>💬</span>
            <div>
              <strong>Вопросы для первого контакта</strong>

              {evaluation.questions.resume && evaluation.questions.resume.length > 0 && (
                <div style={{ marginTop: '8px' }}>
                  <strong style={{ fontSize: '14px', color: 'var(--fg-3)' }}>По резюме:</strong>
                  <ol style={{ margin: '4px 0 0', paddingLeft: '20px' }}>
                    {evaluation.questions.resume.map((question: string, index: number) => (
                      <li key={index} style={{ marginBottom: '4px' }}>{question}</li>
                    ))}
                  </ol>
                </div>
              )}

              {evaluation.questions.risks && evaluation.questions.risks.length > 0 && (
                <div style={{ marginTop: '8px' }}>
                  <strong style={{ fontSize: '14px', color: 'var(--fg-3)' }}>По выявленным рискам:</strong>
                  <ol style={{ margin: '4px 0 0', paddingLeft: '20px' }}>
                    {evaluation.questions.risks.map((question: string, index: number) => (
                      <li key={index} style={{ marginBottom: '4px' }}>{question}</li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

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