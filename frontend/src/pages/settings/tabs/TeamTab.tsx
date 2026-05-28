import { useState, useMemo, useEffect } from 'react';
import { useUsers } from '@/api/hooks/useUsers';
import { useInviteUser, useUpdateUser } from '@/api/mutations/settings';
import { Avatar } from '@/components/ui/Avatar';
import { Icon } from '@/components/ui/Icon';

type Props = {
  onDirtyChange: (dirty: boolean) => void;
  onSaveHandler: (handler: (() => Promise<void>) | null) => void;
  onDiscardHandler: (handler: (() => void) | null) => void;
};

type RoleFilter = 'all' | 'admin' | 'manager' | 'recruiter';
type StatusFilter = 'all' | 'active' | 'inactive';

export function TeamTab({ onDirtyChange, onSaveHandler, onDiscardHandler }: Props) {
  const { data: usersData, isLoading } = useUsers();
  const inviteUser = useInviteUser();
  const updateUser = useUpdateUser();

  const [showInviteModal, setShowInviteModal] = useState(false);
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [inviteForm, setInviteForm] = useState({
    email: '',
    role: 'recruiter',
  });

  // TeamTab doesn't have persistent dirty state
  useEffect(() => {
    onDirtyChange(false);
    onSaveHandler(null);
    onDiscardHandler(null);
  }, [onDirtyChange, onSaveHandler, onDiscardHandler]);

  const users = usersData?.items || [];

  // Filter users
  const filteredUsers = useMemo(() => {
    return users.filter(user => {
      const roleMatch = roleFilter === 'all' || user.role === roleFilter;
      const statusMatch = statusFilter === 'all' ||
        (statusFilter === 'active') ||
        (statusFilter === 'inactive');
      return roleMatch && statusMatch;
    });
  }, [users, roleFilter, statusFilter]);

  const handleInvite = async () => {
    await inviteUser.mutateAsync({
      email: inviteForm.email,
      full_name: inviteForm.email.split('@')[0], // Use email prefix as temporary full_name
      role: inviteForm.role,
    });
    setInviteForm({ email: '', role: 'recruiter' });
    setShowInviteModal(false);
  };

  const handleToggleUserStatus = async (userId: string, currentStatus: boolean) => {
    await updateUser.mutateAsync({
      id: userId,
      data: { is_active: !currentStatus },
    });
  };

  const getRoleBadgeClass = (role: string) => {
    switch (role) {
      case 'admin': return 'badge-red';
      case 'manager': return 'badge-blue';
      case 'recruiter': return 'badge-gray';
      default: return 'badge-gray';
    }
  };

  const getRoleLabel = (role: string) => {
    switch (role) {
      case 'admin': return 'Админ';
      case 'manager': return 'Менеджер';
      case 'recruiter': return 'Рекрутер';
      default: return role;
    }
  };

  if (isLoading) {
    return <div className="settings-loading">Загрузка...</div>;
  }

  return (
    <div className="settings-content-inner">
      <div className="settings-card">
        <div className="settings-card-header">
          <div className="settings-card-header-main">
            <h2 className="settings-card-title">Команда</h2>
            <p className="settings-card-desc">Управление пользователями и правами доступа</p>
          </div>
          <button
            className="btn btn-primary"
            onClick={() => setShowInviteModal(true)}
          >
            <Icon name="plus" size={16} />
            Пригласить
          </button>
        </div>

        {/* Filters */}
        <div className="team-filters">
          <div className="filter-group">
            <label className="filter-label">Роль:</label>
            <select
              className="form-select form-select-sm"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value as RoleFilter)}
            >
              <option value="all">Все роли</option>
              <option value="admin">Админ</option>
              <option value="manager">Менеджер</option>
              <option value="recruiter">Рекрутер</option>
            </select>
          </div>

          <div className="filter-group">
            <label className="filter-label">Статус:</label>
            <select
              className="form-select form-select-sm"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            >
              <option value="all">Все</option>
              <option value="active">Активные</option>
              <option value="inactive">Неактивные</option>
            </select>
          </div>
        </div>

        {/* Users Table */}
        <div className="team-table">
          <div className="table-header">
            <div className="table-cell">Пользователь</div>
            <div className="table-cell">Email</div>
            <div className="table-cell">Роль</div>
            <div className="table-cell">Статус</div>
            <div className="table-cell">Действия</div>
          </div>

          {filteredUsers.length === 0 ? (
            <div className="empty-state">
              <Icon name="users" size={48} />
              <p>Пользователи не найдены</p>
            </div>
          ) : (
            filteredUsers.map((user) => (
              <div key={user.id} className="table-row">
                <div className="table-cell">
                  <div className="user-cell">
                    <Avatar name={user.full_name} src={user.avatar_url} size="sm" />
                    <span className="user-name">{user.full_name}</span>
                  </div>
                </div>
                <div className="table-cell">
                  <span className="user-email">email@company.ru</span>
                </div>
                <div className="table-cell">
                  <span className={`badge ${getRoleBadgeClass(user.role)}`}>
                    {getRoleLabel(user.role)}
                  </span>
                </div>
                <div className="table-cell">
                  <span className="status-dot active">
                    Активен
                  </span>
                </div>
                <div className="table-cell">
                  <div className="table-actions">
                    <button className="btn btn-ghost btn-sm">
                      <Icon name="settings" size={14} />
                      Редактировать
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => handleToggleUserStatus(user.id, true)}
                    >
                      <Icon name="x" size={14} />
                      Деактивировать
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Invite Modal */}
      {showInviteModal && (
        <div className="modal-overlay" onClick={() => setShowInviteModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">Пригласить пользователя</h3>
              <button
                className="modal-close"
                onClick={() => setShowInviteModal(false)}
              >
                <Icon name="x" size={20} />
              </button>
            </div>

            <div className="modal-body">
              <div className="form-field">
                <label className="form-label">Email <span className="required">*</span></label>
                <input
                  type="email"
                  className="form-input"
                  value={inviteForm.email}
                  onChange={(e) => setInviteForm(prev => ({ ...prev, email: e.target.value }))}
                  placeholder="user@company.ru"
                />
              </div>

              <div className="form-field">
                <label className="form-label">Роль <span className="required">*</span></label>
                <select
                  className="form-select"
                  value={inviteForm.role}
                  onChange={(e) => setInviteForm(prev => ({ ...prev, role: e.target.value }))}
                >
                  <option value="recruiter">Рекрутер</option>
                  <option value="manager">Менеджер</option>
                  <option value="admin">Админ</option>
                </select>
              </div>
            </div>

            <div className="modal-footer">
              <button
                className="btn btn-secondary"
                onClick={() => setShowInviteModal(false)}
              >
                Отмена
              </button>
              <button
                className="btn btn-primary"
                onClick={handleInvite}
                disabled={!inviteForm.email || inviteUser.isPending}
              >
                {inviteUser.isPending ? 'Отправка...' : 'Пригласить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}