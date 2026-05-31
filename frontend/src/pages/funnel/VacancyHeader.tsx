import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import type { components } from '@/api/types';

type VacancyDetail = components['schemas']['VacancyDetail'];

type Props = {
  vacancy: VacancyDetail;
  onEdit: () => void;
  onAddCandidate: () => void;
};

export default function VacancyHeader({ vacancy, onEdit, onAddCandidate }: Props) {
  const [copied, setCopied] = useState(false);

  const handleShare = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard может быть недоступен (нет https/прав) — тихо игнорируем
    }
  };

  const handleHHLink = () => {
    if (vacancy.external_url) {
      window.open(vacancy.external_url, '_blank');
    }
  };

  return (
    <div className="vac-header">
      <div className="vh-left">
        <h1 className="vh-title">{vacancy.name}</h1>
        <div className="vh-meta">
          <span>{vacancy.client_name || 'Без клиента'}</span>
          <span className="sep">·</span>
          <span>{vacancy.responsible_user?.full_name || 'Без ответственного'}</span>
          <span className="sep">·</span>
          <span>{vacancy.city || 'Удалённо'}</span>
          <span className="sep">·</span>
          <span>создана {new Date(vacancy.created_at).toLocaleDateString('ru-RU')}</span>
        </div>
      </div>

      <div className="vh-actions">
        <button className="btn btn-secondary btn-sm" onClick={handleShare}>
          <Icon name={copied ? "check" : "open"} size={14} /> {copied ? 'Скопировано' : 'Поделиться'}
        </button>

        <button
          className={`btn btn-secondary btn-sm ${!vacancy.external_url ? 'is-disabled' : ''}`}
          onClick={handleHHLink}
          disabled={!vacancy.external_url}
          title={!vacancy.external_url ? 'Не подключено' : undefined}
        >
          <Icon name="open" size={14} /> Перейти на hh
        </button>

        <button className="btn btn-secondary btn-sm" onClick={onEdit}>
          Редактировать
        </button>

        <button className="btn btn-primary btn-sm" onClick={onAddCandidate}>
          <Icon name="plus" size={14} /> Добавить кандидата
        </button>
      </div>
    </div>
  );
}