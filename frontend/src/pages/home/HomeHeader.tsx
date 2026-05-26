import { useState, useEffect } from 'react';
import { useMe } from '@/api/hooks/useMe';
import { useUiStore } from '@/store/uiStore';
import { useHomeKpi } from '@/api/hooks/useHomeKpi';
import { formatRelativeTime, formatHHMM } from '@/lib/time';

interface Props {
  period: string;
  onPeriodChange: (p: string) => void;
}

const PERIODS = [
  { id: 'week', label: 'Неделя' },
  { id: 'month', label: 'Месяц' },
  { id: 'quarter', label: 'Квартал' },
  { id: 'year', label: 'Год' },
  { id: 'all', label: 'Всё время' },
];

export function HomeHeader({ period, onPeriodChange }: Props) {
  const { data: me } = useMe();
  const { greeting } = useUiStore();
  const { dataUpdatedAt } = useHomeKpi(period, false);
  const [, setTick] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setTick(x => x + 1), 30_000);
    return () => clearInterval(t);
  }, []);

  const firstName = me ? (me.full_name.split(' ')[1] || me.full_name.split(' ')[0]) : '';
  const title = greeting && firstName ? `Привет, ${firstName}` : 'Главная';

  return (
    <header className="home-header">
      <div className="home-header__left">
        <h1 className="home-header__title">{title}</h1>
        <div className="home-header__updated">
          Обновлено {dataUpdatedAt ? formatRelativeTime(dataUpdatedAt) : '…'} · {formatHHMM()}
        </div>
      </div>
      <div className="home-header__period">
        {PERIODS.map(p => (
          <button
            key={p.id}
            className={`home-header__period-btn ${p.id === period ? 'is-active' : ''}`}
            onClick={() => onPeriodChange(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>
    </header>
  );
}