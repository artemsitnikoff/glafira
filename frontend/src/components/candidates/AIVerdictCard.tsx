import { scoreBand, scoreClass } from '@/lib/score';

type Props = {
  evaluation: any;
  hideLink?: boolean;
  onOpenAI?: () => void;
};

export function AIVerdictCard({ evaluation, hideLink, onOpenAI }: Props) {
  if (!evaluation) return null;

  // Score color — единый порог 80/50 (раньше тут было 60 → расходилось с текстом ниже)
  const getScoreColor = (score: number) => scoreClass(score);

  // Use real AI summary or fallback based on score (порог из того же scoreBand)
  const getSummaryText = () => {
    if (evaluation.summary) {
      return evaluation.summary;
    }
    const band = scoreBand(evaluation.score);
    return band === 'green'
      ? 'Хорошо подходит. Релевантный опыт, ключевые навыки совпадают с требованиями вакансии.'
      : band === 'red'
      ? 'Не подходит. Опыт не совпадает с требованиями вакансии.'
      : 'Подходит частично. Есть релевантный опыт, но не хватает части ключевых навыков.';
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