import { Icon } from '@/components/ui/Icon';
import type { EvaluationOut } from '@/api/aliases';

type Props = {
  evaluation: EvaluationOut;
  onReEvaluate?: () => void;
  loading?: boolean;
};

export function AIVerdictCard({ evaluation, onReEvaluate, loading }: Props) {
  const verdictClass = `ai-verdict-card__verdict--${evaluation.verdict.replace('_', '-')}`;

  return (
    <div className="ai-verdict-card">
      <div className="ai-verdict-card__header">
        <h3 className="ai-verdict-card__title">
          AI-оценка: {evaluation.score}/100
        </h3>
        <span className={`ai-verdict-card__verdict ${verdictClass}`}>
          {evaluation.verdict}
        </span>
        <span className="score-badge score-badge--high" style={{ marginLeft: 'auto' }}>
          {evaluation.score}
        </span>
      </div>

      <p className="ai-verdict-card__summary">
        {evaluation.summary}
      </p>

      {evaluation.model && (
        <p style={{ color: 'var(--fg-3)', fontSize: '12px', margin: '0 0 var(--space-3) 0' }}>
          Модель: {evaluation.model} • {new Date(evaluation.created_at).toLocaleDateString('ru')}
        </p>
      )}

      <div className="ai-verdict-card__actions">
        {onReEvaluate && (
          <button
            className="candidate-toolbar__btn"
            onClick={onReEvaluate}
            disabled={loading}
          >
            <Icon name={loading ? "loader" : "refresh-cw"} size={16} />
            Переоценить
          </button>
        )}
      </div>
    </div>
  );
}