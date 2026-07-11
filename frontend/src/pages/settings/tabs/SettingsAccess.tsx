import { useState, useMemo } from 'react';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { PageHead, Card, Select } from '../components/FormComponents';
import { useUsers } from '@/api/hooks/useUsers';
import { useAuthStore } from '@/store/authStore';
import { useBitrix24Status } from '@/api/hooks/useBitrix24Integration';
import { BitrixImportModal } from './components/BitrixImportModal';
import { CreateUserModal } from './components/CreateUserModal';
import { UserActionMenu } from './components/UserActionMenu';
import { useDebounce } from '@/hooks/useDebounce';
import './components/BitrixImportModal.css';
import './components/UserActionMenu.css';

const ROLE_INFO = [
  {
    id: 'admin', label: 'Администратор', tone: 'admin',
    sum: 'Настраивает систему',
    can: 'Всё: интеграции, пользователи, воронка, теги. Полный доступ ко всем вакансиям и аналитике.',
    sees: 'Все разделы и все данные.',
  },
  {
    id: 'recruiter', label: 'Рекрутер', tone: 'recruiter',
    sum: 'Основной пользователь',
    can: 'Создаёт и ведёт вакансии, работает с кандидатами, передаёт по воронке, общается через Глафиру.',
    sees: 'Свои вакансии, общую базу кандидатов, Аналитику (без отчёта «Рекрутеры»). Не видит Общие настройки, Воронку, Права, Интеграции.',
  },
  {
    id: 'manager', label: 'Нанимающий менеджер', tone: 'manager',
    sum: 'Лёгкий пользователь · заказчик',
    can: 'Согласует требования, оценивает кандидатов, проводит интервью на своей стороне. Не двигает кандидатов между этапами (кроме своей зоны).',
    sees: 'Только вакансии, где он указан заказчиком. Не видит Аналитику и Настройки (кроме Профиля). Не видит общую базу.',
  },
];

const roleLabel = { admin: 'Администратор', recruiter: 'Рекрутёр', manager: 'Нанимающий менеджер' };
const roleClass = { admin: 'admin', recruiter: 'recruiter', manager: 'manager' };

interface SettingsAccessProps {
  readOnly?: boolean;
}

export function SettingsAccess({ readOnly = false }: SettingsAccessProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const debouncedSearch = useDebounce(searchQuery, 300);
  const user = useAuthStore(s => s.user);
  const isAdmin = user?.role === 'admin';

  const { data: b24Status } = useBitrix24Status();
  const canImportFromB24 = b24Status?.verified === true;

  const usersFilters = useMemo(() => {
    const filters: any = {};
    if (debouncedSearch) filters.search = debouncedSearch;
    if (roleFilter && roleFilter !== 'all') filters.role = roleFilter;
    if (statusFilter && statusFilter !== 'all') {
      filters.is_active = statusFilter === 'active';
    }
    return filters;
  }, [debouncedSearch, roleFilter, statusFilter]);

  const { data: usersData, isLoading: usersLoading } = useUsers(usersFilters);
  const users = usersData?.items || [];
  const totalUsers = usersData?.total || 0;
  const activeUsers = users.filter(u => u.is_active).length;

  const formatLastActivity = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffHours = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60));

    if (diffHours < 1) return 'Только что';
    if (diffHours < 24) return `${diffHours} ч назад`;
    if (diffHours < 48) return 'Вчера';
    if (diffHours < 24 * 30) return `${Math.floor(diffHours / 24)} дн назад`;
    return `${Math.floor(diffHours / (24 * 30))} мес назад`;
  };

  const showError = (message: string) => {
    setErrorMessage(message);
    setTimeout(() => setErrorMessage(null), 5000);
  };

  return (
    <div className="set-content-inner">
      <PageHead title="Права доступа"
        subtitle="Пользователи системы и их роли"/>

      {errorMessage && (
        <div className="error-banner">
          <Icon name="alert-circle" size={16} />
          <span>{errorMessage}</span>
          <button onClick={() => setErrorMessage(null)}>
            <Icon name="x" size={16} />
          </button>
        </div>
      )}

      <Card title="Роли в системе">
        <div className="roles-grid">
          {ROLE_INFO.map(r => (
            <div key={r.id} className={`role-card role-${r.tone}`}>
              <div className="role-card-head">
                <div className={`role-pill role-${r.tone}`}>{r.label}</div>
                <div className="role-sum">{r.sum}</div>
              </div>
              <div className="role-block">
                <div className="role-cap">Что может</div>
                <div className="role-text">{r.can}</div>
              </div>
              <div className="role-block">
                <div className="role-cap">Что видит</div>
                <div className="role-text">{r.sees}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Пользователи" desc={`Всего ${totalUsers}: ${activeUsers} активных`} className="set-card-overflow">
        <div className="users-toolbar">
          <div className="users-search">
            <Icon name="search" size={14}/>
            <input
              placeholder="Поиск по ФИО или email…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <Select
            value={roleFilter}
            onChange={setRoleFilter}
            options={[
              { value: '', label: 'Все роли' },
              { value: 'admin', label: 'Администраторы' },
              { value: 'recruiter', label: 'Рекрутёры' },
              { value: 'manager', label: 'Нанимающие менеджеры' }
            ]}
          />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { value: '', label: 'Все статусы' },
              { value: 'active', label: 'Активные' },
              { value: 'blocked', label: 'Заблокированные' }
            ]}
          />
          <div style={{ flex: 1 }} />
          {isAdmin && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setIsImportModalOpen(true)}
              disabled={!canImportFromB24 || readOnly}
              title={readOnly ? 'Только просмотр' : (!canImportFromB24 ? 'Подключите Битрикс24' : 'Импорт пользователей из Битрикс24')}
            >
              <Icon name="download" size={14} />Импорт из Б24
            </button>
          )}
          {isAdmin && (
            <button className="btn btn-primary btn-sm" onClick={() => setIsCreateModalOpen(true)}>
              <Icon name="plus" size={14} />Создать
            </button>
          )}
        </div>

        <div className="users-table">
          <div className="ut-thead">
            <div>Пользователь</div>
            <div>Роль</div>
            <div>Источник</div>
            <div>Последний вход</div>
            <div>Статус</div>
            <div></div>
          </div>
          {usersLoading ? (
            <div className="users-loading">
              <Icon name="loader" size={16} />
              Загрузка...
            </div>
          ) : users.length === 0 ? (
            <div className="users-empty">
              Пользователи не найдены
            </div>
          ) : (
            users.map((u) => (
              <div key={u.id} className="ut-row">
                <div className="ut-user">
                  <Avatar name={u.full_name} size="sm"/>
                  <div>
                    <div className="ut-fio">{u.full_name}</div>
                    <div className="ut-email">{u.email}</div>
                  </div>
                </div>
                <div><span className={`role-pill role-${roleClass[u.role as keyof typeof roleClass]}`}>{roleLabel[u.role as keyof typeof roleLabel]}</span></div>
                <div className="ut-cell">
                  {u.source === 'b24' ? (
                    <span className="src-pill src-b24">Импортирован из Б24</span>
                  ) : (
                    <span className="t-secondary">Создан в системе</span>
                  )}
                </div>
                <div className="ut-cell t-mono" style={{ fontSize: 12 }}>
                  {formatLastActivity(u.created_at)}
                </div>
                <div>
                  <span className={`status-pill status-${u.is_active ? 'active' : 'blocked'}`}>
                    <span className="st-dot"/>{u.is_active ? 'Активен' : 'Заблокирован'}
                  </span>
                </div>
                <div style={{ textAlign: 'right' }}>
                  {isAdmin && !readOnly && (
                    <UserActionMenu
                      user={u}
                      currentUserId={user?.id || ''}
                      onError={showError}
                      showB24={canImportFromB24}
                    />
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </Card>

      <BitrixImportModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
      />

      <CreateUserModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
      />
    </div>
  );
}