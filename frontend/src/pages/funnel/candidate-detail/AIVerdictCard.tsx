import { Icon } from '@/components/ui/Icon';
import { ScoreBadge } from '@/components/ui/ScoreBadge';
import type { EvaluationOut } from '@/api/aliases';

type Props = {
  evaluation: EvaluationOut;
  onReEvaluate?: () => void;
  loading?: boolean;
};

export function AIVerdictCard({ evaluation, onReEvaluate, loading }: Props) {
  const getVerdictText = () => {
    if (evaluation.score >= 80) return 'Хорошо подходит. Релевантный опыт, ключевые навыки совпадают с требованиями вакансии.';
    if (evaluation.score >= 50) return 'Подходит частично. Есть релевантный опыт, но не хватает части ключевых навыков.';
    return 'Не подходит. Опыт не совпадает с требованиями вакансии.';
  };

  return (
    <div className="filo-card filo-card-compact">
      <div className="filo-head">
        <div className="filo-head-left">
          <div className="filo-ai-mark filo-glafira" aria-label="Глафира">
            <span className="glafira-emoji">👩🏻</span>
          </div>
          <div>
            <div className="filo-title">Оценка от Глафиры</div>
            <div className="filo-sub">{getVerdictText()}</div>
          </div>
        </div>
        <ScoreBadge value={evaluation.score} size="xl" />
      </div>

      <div className="filo-link-row">
        <a className="filo-link" href="#" onClick={(e) => { e.preventDefault(); /* TODO: navigate to detailed evaluation */ }}>
          Посмотреть подробную оценку →
        </a>
      </div>

      {onReEvaluate && (
        <div className="ai-verdict-card__actions" style={{ marginTop: '12px' }}>
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