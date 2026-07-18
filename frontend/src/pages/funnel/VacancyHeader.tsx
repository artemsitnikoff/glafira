import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import { useAuthStore } from '@/store/authStore';
import { useDuplicateVacancy, useArchiveVacancy } from '@/api/mutations/vacancies';
import type { components } from '@/api/types';
import type { ApiError } from '@/api/aliases';
import '../requests/requests.css';

type VacancyDetail = components['schemas']['VacancyDetail'];

type Props = {
  vacancy: VacancyDetail;
  onEdit: () => void;
  onAddCandidate: () => void;
};

export default function VacancyHeader({ vacancy, onEdit, onAddCandidate }: Props) {
  const [copied, setCopied] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [archiveMode, setArchiveMode] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const navigate = useNavigate();
  const duplicateMutation = useDuplicateVacancy();
  const archiveMutation = useArchiveVacancy();

  // Менеджер не управляет вакансиями (создание/закрытие) — бэк всё равно вернёт 403.
  const canManage = useAuthStore(s => s.user?.role) !== 'manager';

  const closeMenu = () => {
    setMenuOpen(false);
    setArchiveMode(false);
    setActionError(null);
  };

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

  const handleDuplicate = async () => {
    setActionError(null);
    try {
      const created = await duplicateMutation.mutateAsync(vacancy.id);
      closeMenu();
      navigate(`/vacancies/${created.id}`);
    } catch (e) {
      setActionError((e as unknown as ApiError).error?.message || 'Не удалось дублировать вакансию');
    }
  };

  const handleArchive = async (result: string) => {
    setActionError(null);
    try {
      await archiveMutation.mutateAsync({ id: vacancy.id, result });
      closeMenu();
      navigate('/vacancies');
    } catch (e) {
      setActionError((e as unknown as ApiError).error?.message || 'Не удалось закрыть вакансию');
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
          {(vacancy as any).request_num != null && (
            <>
              <span className="sep">·</span>
              <button
                className="vh-req-link"
                title="Открыть заявку на подбор"
                onClick={() => navigate(`/requests?open=${(vacancy as any).request_id}`)}
              >
                <Icon name="link" size={11} /> по заявке №{(vacancy as any).request_num}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="vh-actions">
        {canManage && (
          <div className="vh-action-wrap">
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => { setArchiveMode(false); setActionError(null); setMenuOpen(o => !o); }}
            >
              Действие <Icon name="chevD" size={14} />
            </button>
            {menuOpen && (
              <>
                <div className="vh-action-backdrop" onClick={closeMenu} />
                <div className="vh-action-pop" role="menu">
                  {!archiveMode ? (
                    <>
                      <button className="vh-action-item" onClick={handleDuplicate} disabled={duplicateMutation.isPending}>
                        <Icon name="copy" size={15} />
                        {duplicateMutation.isPending ? 'Дублирование…' : 'Дублировать'}
                      </button>
                      <button className="vh-action-item" onClick={() => setArchiveMode(true)}>
                        <Icon name="archive" size={15} />
                        Закрыть вакансию
                      </button>
                    </>
                  ) : (
                    <>
                      <div className="vh-action-head">Результат закрытия</div>
                      <button className="vh-action-item" onClick={() => handleArchive('hired')} disabled={archiveMutation.isPending}>
                        <span className="vh-action-dot" style={{ background: 'var(--ark-green-500)' }} />
                        Закрыто, кандидат найден
                      </button>
                      <button className="vh-action-item" onClick={() => handleArchive('cancelled')} disabled={archiveMutation.isPending}>
                        <span className="vh-action-dot" style={{ background: 'var(--ark-gray-400)' }} />
                        Кандидат не найден
                      </button>
                    </>
                  )}
                  {actionError && <div className="vh-action-err">{actionError}</div>}
                </div>
              </>
            )}
          </div>
        )}

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
