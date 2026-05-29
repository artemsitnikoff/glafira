import { useNavigate } from 'react-router-dom';
import { useHomeAttention } from '@/api/hooks/useHomeAttention';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Icon } from '@/components/ui/Icon';

const KIND_ICON: Record<string, any> = {
  urgent: 'alert',
  warn: 'clock',
  deadline: 'calClock',
};

export function AttentionList() {
  const { data, isLoading } = useHomeAttention();
  const navigate = useNavigate();

  if (isLoading) return <Skeleton height={200} />;

  const items = data ?? [];

  return (
    <div className="card-block">
      <div className="card-block-head">
        <div className="title">
          Требуют внимания
          <span className="count-pill">{items.length}</span>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/vacancies')}>
          Все вакансии <Icon name="chevR" size={14}/>
        </button>
      </div>
      {items.length === 0 ? (
        <EmptyState
          title="Все спокойно"
          description="Сейчас нет вакансий, требующих внимания"
        />
      ) : (
        <div>
          {items.map((item, i) => (
            <div
              key={`${item.vacancy_id}-${i}`}
              className="att-row"
              onClick={() => navigate(`/vacancies/${item.vacancy_id}`)}
            >
              <div className={`flag-icon ${item.kind}`}>
                <Icon name={KIND_ICON[item.kind]} size={16}/>
              </div>
              <div className="body">
                <div className="name">{item.vacancy_name}</div>
                <div className="reason">{item.text}</div>
              </div>
              <div className="arrow">
                <Icon name="chevR" size={16}/>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}