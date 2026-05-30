type Props = {
  evaluation: any;
  hideLink?: boolean;
  onOpenAI?: () => void;
};

export function AIVerdictCard({ evaluation, hideLink, onOpenAI }: Props) {
  if (!evaluation) return null;

  // Score color
  const getScoreColor = (score: number) => {
    if (score >= 80) return 'score-green';
    if (score >= 60) return 'score-yellow';
    return 'score-red';
  };

  // Use real AI summary or fallback based on score
  const getSummaryText = () => {
    if (evaluation.summary) {
      return evaluation.summary;
    }
    // Fallback based on score
    return evaluation.score >= 80
      ? 'Хорошо подходит. Релевантный опыт, ключевые навыки совпадают с требованиями вакансии.'
      : evaluation.score >= 50
      ? 'Подходит частично. Есть релевантный опыт, но не хватает части ключевых навыков.'
      : 'Не подходит. Опыт не совпадает с требованиями вакансии.';
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
            <div className="filo-sub">{getSummaryText()}</div>
          </div>
        </div>
        <span className={`score-badge score-xl ${getScoreColor(evaluation.score)}`}>
          {evaluation.score}
        </span>
      </div>
      {!hideLink && (
        <div className="filo-link-row">
          <a
            className="filo-link"
            href="#"
            onClick={(e) => {
              e.preventDefault();
              if (onOpenAI) onOpenAI();
            }}
          >
            Посмотреть подробную оценку →
          </a>
        </div>
      )}
    </div>
  );
}