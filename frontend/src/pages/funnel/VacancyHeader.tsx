import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import type { components } from '@/api/types';

type VacancyDetail = components['schemas']['VacancyDetail'];

type Props = {
  vacancy: VacancyDetail;
  onEdit: () => void;
  onAddCandidate: () => void;
};

export default function VacancyHeader({ vacancy, onEdit, onAddCandidate }: Props) {
  const handleShare = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      alert('Ссылка скопирована'); // TODO: replace with proper toast
    } catch (error) {
      console.error('Failed to copy link:', error);
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
        {vacancy.salary_from && vacancy.salary_to && (
          <div className="vh-salary">
            {vacancy.salary_from.toLocaleString()} - {vacancy.salary_to.toLocaleString()} ₽
          </div>
        )}
        <div className="vh-mode">
          Глафира: режим {vacancy.glafira_mode}
          {vacancy.responsible_user && (
            <span className="vh-responsible">
              <Avatar name={vacancy.responsible_user.full_name} size="xs" />
              {vacancy.responsible_user.full_name}
            </span>
          )}
        </div>
      </div>

      <div className="vh-actions">
        <button className="btn btn-secondary btn-sm" onClick={handleShare}>
          <Icon name="open" size={14} /> Поделиться
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