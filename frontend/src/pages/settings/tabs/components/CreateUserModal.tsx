import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useInviteUser } from '@/api/mutations/settings';
import type { ApiError } from '@/api/aliases';

// Модалка ручного создания пользователя. ФИО + email + роль (как в импорте).
// Источник у созданного — «manual» (бэк по умолчанию). Показывает temp-пароль.
interface Props {
  isOpen: boolean;
  onClose: () => void;
}

const ROLE_OPTIONS = [
  { value: 'admin', label: 'Администратор' },
  { value: 'recruiter', label: 'Рекрутёр' },
  { value: 'manager', label: 'Нанимающий менеджер' },
];

interface CreatedResult {
  email: string;
  full_name: string;
  temp_password: string;
}

export function CreateUserModal({ isOpen, onClose }: Props) {
  const inviteUser = useInviteUser();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('recruiter');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreatedResult | null>(null);

  const handleClose = () => {
    setFullName('');
    setEmail('');
    setRole('recruiter');
    setError(null);
    setResult(null);
    onClose();
  };

  const handleSubmit = async () => {
    setError(null);
    try {
      const res = await inviteUser.mutateAsync({
        email: email.trim(),
        full_name: fullName.trim(),
        role,
      });
      const r = res as unknown as { email: string; full_name: string; temp_password: string };
      setResult({
        email: r.email,
        full_name: r.full_name ?? fullName.trim(),
        temp_password: r.temp_password,
      });
    } catch (err) {
      const e = err as unknown as ApiError;
      setError(e.error?.message || 'Не удалось создать пользователя');
    }
  };

  if (!isOpen) return null;

  const canSubmit = !!fullName.trim() && !!email.trim() && !inviteUser.isPending;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Создать пользователя</h2>
          <button type="button" onClick={handleClose} className="modal-close" aria-label="Закрыть">
            <Icon name="x" size={16} />
          </button>
        </div>

        <div className="modal-body">
          {!result ? (
            <>
              <div className="import-filters">
                <div className="import-filter">
                  <label>ФИО</label>
                  <input
                    className="form-input"
                    type="text"
                    placeholder="Имя Фамилия"
                    value={fullName}
                    autoFocus
                    onChange={(e) => setFullName(e.target.value)}
                  />
                </div>
                <div className="import-filter">
                  <label>Email</label>
                  <input
                    className="form-input"
                    type="email"
                    placeholder="user@company.ru"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
                <div className="import-filter">
                  <label>Роль</label>
                  <select className="form-select" value={role} onChange={(e) => setRole(e.target.value)}>
                    {ROLE_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {error && (
                <div className="error-banner">
                  <Icon name="alert-circle" size={16} />
                  <span>{error}</span>
                </div>
              )}

              <div className="info-banner small">
                <Icon name="info" size={14} />
                <div>Пользователь создаётся с временным паролем — после создания скопируйте логин и пароль и передайте сотруднику.</div>
              </div>
            </>
          ) : (
            <div className="import-result">
              <div className="import-result-summary">
                <Icon name="check-circle" size={20} />
                <h3>Пользователь создан</h3>
              </div>
              <div className="import-stat">
                <strong>{result.full_name}</strong>
                <div className="temp-password-item">
                  <div className="temp-password">
                    Логин: <code>{result.email}</code>
                  </div>
                  <div className="temp-password">
                    Временный пароль: <code>{result.temp_password}</code>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          {!result ? (
            <>
              <button type="button" className="btn btn-secondary" onClick={handleClose}>
                Отмена
              </button>
              <button type="button" className="btn btn-primary" onClick={handleSubmit} disabled={!canSubmit}>
                {inviteUser.isPending ? 'Создание…' : 'Создать'}
              </button>
            </>
          ) : (
            <button type="button" className="btn btn-primary" onClick={handleClose}>
              Готово
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
