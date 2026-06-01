import { useState, useRef, useEffect } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useUpdateUser, useDeleteUser } from '@/api/mutations/settings';
import type { UserListItem } from '@/api/hooks/useUsers';

interface Props {
  user: UserListItem;
  currentUserId: string;
  onError: (message: string) => void;
}

export function UserActionMenu({ user, currentUserId, onError }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const updateUserMutation = useUpdateUser();
  const deleteUserMutation = useDeleteUser();

  const isCurrentUser = user.id === currentUserId;

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

  if (showDeleteConfirm) {
    return (
      <div className="user-menu" ref={menuRef}>
        <div className="user-menu-content confirm">
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
        className="row-icon-btn"
        onClick={() => setIsOpen(!isOpen)}
      >
        <Icon name="more" size={16} />
      </button>

      {isOpen && (
        <div className="user-menu-content">
          <button
            className="user-menu-item"
            onClick={handleToggleActive}
            disabled={updateUserMutation.isPending || isCurrentUser}
          >
            <Icon name={user.is_active ? 'x' : 'check'} size={14} />
            {user.is_active ? 'Заблокировать' : 'Активировать'}
          </button>
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