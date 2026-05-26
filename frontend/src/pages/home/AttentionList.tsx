import { useNavigate } from 'react-router-dom';
import { useHomeAttention } from '@/api/hooks/useHomeAttention';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Badge } from '@/components/ui/Badge';
import { Icon } from '@/components/ui/Icon';

const KIND_COLOR: Record<string, string> = {
  urgent: 'var(--risk-high)',
  warn: 'var(--risk-mid)',
  deadline: 'var(--score-yellow)',
};

const KIND_ICON: Record<string, any> = {
  urgent: 'flag',
  warn: 'alert-triangle',
  deadline: 'clock',
};

export function AttentionList() {
  const { data, isLoading } = useHomeAttention();
  const navigate = useNavigate();

  if (isLoading) return <Skeleton height={200} />;

  const items = data ?? [];

  return (
    <section className="block attention-block">
      <header className="block__head">
        <div className="block__title">
          Требуют внимания <Badge>{items.length}</Badge>
        </div>
        <button className="ghost-btn" onClick={() => navigate('/vacancies')}>
          Все вакансии →
        </button>
      </header>
      {items.length === 0 ? (
        <EmptyState
          title="Все спокойно"
          description="Сейчас нет вакансий, требующих внимания"
        />
      ) : (
        <div className="att-list">
          {items.map((item, i) => (
            <button
              key={`${item.vacancy_id}-${i}`}
              className="att-row"
              onClick={() => navigate(`/vacancies/${item.vacancy_id}`)}
            >
              <span className="att-row__flag" style={{ color: KIND_COLOR[item.kind] }}>
                <Icon name={KIND_ICON[item.kind]} size={16} />
              </span>
              <div className="att-row__body">
                <div className="att-row__name">{item.vacancy_name}</div>
                <div className="att-row__text">{item.text}</div>
              </div>
              <Icon name="chevron-right" size={16} className="att-row__arrow" />
            </button>
          ))}
        </div>
      )}
    </section>
  );
}