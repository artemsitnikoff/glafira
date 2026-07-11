import { useState, useRef, useEffect } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useUpdateUser, useDeleteUser } from '@/api/mutations/settings';
import { api } from '@/api/client';
import type { UserListItem } from '@/api/hooks/useUsers';

interface Props {
  user: UserListItem;
  currentUserId: string;
  onError: (message: string) => void;
  showB24?: boolean; // показывать действие «Привязать к Битрикс24»
}

export function UserActionMenu({ user, currentUserId, onError, showB24 = false }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  // Если снизу мало места (последний ряд) — открываем меню вверх, чтобы не уезжало за экран.
  const [openUp, setOpenUp] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  // B24 маппинг
  const [showB24Form, setShowB24Form] = useState(false);
  const [b24IdInput, setB24IdInput] = useState<string>('');
  const [b24Syncing, setB24Syncing] = useState(false);
  const [b24Saving, setB24Saving] = useState(false);
  const [b24Msg, setB24Msg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const handleToggle = () => {
    if (!isOpen && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      // ~140px — высота меню (2 пункта / подтверждение) с запасом.
      setOpenUp(window.innerHeight - rect.bottom < 140);
    }
    setIsOpen((o) => !o);
  };

  const updateUserMutation = useUpdateUser();
  const deleteUserMutation = useDeleteUser();

  const isCurrentUser = user.id === currentUserId;

  const currentB24Id = (user as unknown as { b24_user_id?: number | null }).b24_user_id;

  const handleOpenB24Form = () => {
    setB24IdInput(currentB24Id != null ? String(currentB24Id) : '');
    setB24Msg(null);
    setShowB24Form(true);
    setIsOpen(false);
  };

  const handleB24Sync = async () => {
    setB24Syncing(true);
    setB24Msg(null);
    try {
      const res = await api.post<{ b24_user_id: number }>(`/integrations/bitrix24/users/${user.id}/b24/sync`);
      setB24IdInput(String(res.data.b24_user_id));
      setB24Msg({ type: 'ok', text: `Найден ID: ${res.data.b24_user_id}` });
    } catch (e: unknown) {
      const msg = (e as { error?: { message?: string } })?.error?.message;
      setB24Msg({ type: 'err', text: msg || 'Не удалось найти пользователя в Битрикс24' });
    } finally {
      setB24Syncing(false);
    }
  };

  const handleB24Save = async () => {
    setB24Saving(true);
    setB24Msg(null);
    const idNum = b24IdInput.trim() ? parseInt(b24IdInput.trim(), 10) : null;
    try {
      await api.patch(`/integrations/bitrix24/users/${user.id}/b24`, { b24_user_id: idNum });
      setB24Msg({ type: 'ok', text: idNum != null ? `ID Битрикс24 сохранён: ${idNum}` : 'Привязка сброшена' });
    } catch (e: unknown) {
      const msg = (e as { error?: { message?: string } })?.error?.message;
      setB24Msg({ type: 'err', text: msg || 'Ошибка при сохранении' });
    } finally {
      setB24Saving(false);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setShowDeleteConfirm(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const handleToggleActive = async () => {
    if (isCurrentUser) return;

    try {
      await updateUserMutation.mutateAsync({
        id: user.id,
        data: { is_active: !user.is_active }
      });
      setIsOpen(false);
    } catch (err: any) {
      onError(err?.error?.message || 'Произошла ошибка при изменении статуса');
    }
  };

  const handleDelete = async () => {
    try {
      await deleteUserMutation.mutateAsync(user.id);
      setIsOpen(false);
      setShowDeleteConfirm(false);
    } catch (err: any) {
      onError(err?.error?.message || 'Произошла ошибка при удалении пользователя');
      setShowDeleteConfirm(false);
    }
  };

  if (showB24Form) {
    return (
      <div className="user-menu" ref={menuRef}>
        <div className={`user-menu-content${openUp ? ' up' : ''}`} style={{ width: 240, padding: '12px' }}>
          <div style={{ fontSize: '12px', color: 'var(--fg-2)', marginBottom: '8px', fontWeight: 600 }}>
            ID пользователя Битрикс24
          </div>
          {currentB24Id != null && (
            <div style={{ fontSize: '11px', color: 'var(--fg-3)', marginBottom: '6px' }}>
              Текущий: {currentB24Id}
            </div>
          )}
          <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
            <input
              type="number"
              placeholder="b24_user_id"
              value={b24IdInput}
              onChange={(e) => setB24IdInput(e.target.value)}
              style={{
                flex: 1,
                height: '30px',
                border: '1px solid var(--border-1)',
                borderRadius: 'var(--radius-md)',
                padding: '0 8px',
                fontSize: '13px',
                fontFamily: 'var(--font-mono)',
                background: 'var(--bg-1)',
                color: 'var(--fg-1)',
              }}
            />
            <button
              className="btn btn-sm btn-secondary"
              onClick={handleB24Sync}
              disabled={b24Syncing}
              title="Найти по email"
              style={{ whiteSpace: 'nowrap', fontSize: '11px' }}
            >
              {b24Syncing ? '…' : 'По email'}
            </button>
          </div>
          {b24Msg && (
            <div style={{
              fontSize: '11px',
              color: b24Msg.type === 'ok' ? 'var(--success-fg)' : 'var(--error-fg)',
              marginBottom: '8px',
            }}>
              {b24Msg.text}
            </div>
          )}
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              className="btn btn-sm btn-primary"
              onClick={handleB24Save}
              disabled={b24Saving}
            >
              {b24Saving ? '...' : 'Сохранить'}
            </button>
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => setShowB24Form(false)}
            >
              Отмена
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (showDeleteConfirm) {
    return (
      <div className="user-menu" ref={menuRef}>
        <div className={`user-menu-content confirm${openUp ? ' up' : ''}`}>
          <div className="confirm-text">
            Удалить пользователя {user.full_name}?
          </div>
          <div className="confirm-actions">
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => setShowDeleteConfirm(false)}
            >
              Отмена
            </button>
            <button
              className="btn btn-sm btn-danger"
              onClick={handleDelete}
              disabled={deleteUserMutation.isPending}
            >
              {deleteUserMutation.isPending ? '...' : 'Удалить'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="user-menu" ref={menuRef}>
      <button
        ref={btnRef}
        className="row-icon-btn"
        onClick={handleToggle}
      >
        <Icon name="more" size={16} />
      </button>

      {isOpen && (
        <div className={`user-menu-content${openUp ? ' up' : ''}`}>
          <button
            className="user-menu-item"
            onClick={handleToggleActive}
            disabled={updateUserMutation.isPending || isCurrentUser}
          >
            <Icon name={user.is_active ? 'x' : 'check'} size={14} />
            {user.is_active ? 'Заблокировать' : 'Активировать'}
          </button>
          {showB24 && (
            <button
              className="user-menu-item"
              onClick={handleOpenB24Form}
            >
              <Icon name="link" size={14} />
              {currentB24Id != null ? `Битрикс24: ${currentB24Id}` : 'Привязать к Битрикс24'}
            </button>
          )}
          <button
            className="user-menu-item danger"
            onClick={() => setShowDeleteConfirm(true)}
            disabled={deleteUserMutation.isPending || isCurrentUser}
          >
            <Icon name="trash" size={14} />
            Удалить
          </button>
        </div>
      )}
    </div>
  );
}