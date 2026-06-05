import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useChangePassword } from '@/api/mutations/settings';
import type { ApiError } from '@/api/aliases';

// ОТДЕЛЬНАЯ форма смены пароля. Намеренно НЕ привязана к «Сохранить профиль» и
// использует autocomplete=new-password — это фикс прошлого бага с лок-аутами
// (autofill + авто-сабмит профиля молча перезаписывал пароль). Явный сабмит.
interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export function ChangePasswordModal({ isOpen, onClose }: Props) {
  const changePassword = useChangePassword();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const reset = () => {
    setCurrent('');
    setNext('');
    setConfirm('');
    setError(null);
    setDone(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async () => {
    setError(null);
    if (next.length < 8) {
      setError('Новый пароль должен быть не короче 8 символов');
      return;
    }
    if (next !== confirm) {
      setError('Новый пароль и подтверждение не совпадают');
      return;
    }
    try {
      await changePassword.mutateAsync({
        current_password: current,
        new_password: next,
        new_password_confirm: confirm,
      });
      setDone(true);
    } catch (err) {
      const e = err as unknown as ApiError;
      setError(e.error?.message || 'Не удалось сменить пароль');
    }
  };

  if (!isOpen) return null;

  const canSubmit =
    !!current && !!next && !!confirm && !changePassword.isPending;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Смена пароля</h2>
          <button type="button" onClick={handleClose} className="modal-close" aria-label="Закрыть">
            <Icon name="x" size={16} />
          </button>
        </div>

        <div className="modal-body">
          {done ? (
            <div className="import-result">
              <div className="import-result-summary">
                <Icon name="check-circle" size={20} />
                <h3>Пароль изменён</h3>
              </div>
              <div className="import-stat">
                Используйте новый пароль при следующем входе.
              </div>
            </div>
          ) : (
            // form предотвращает «тихий» сабмит: явная кнопка + autocomplete=new-password
            <form
              autoComplete="off"
              onSubmit={(e) => { e.preventDefault(); handleSubmit(); }}
            >
              <div className="import-filters">
                <div className="import-filter">
                  <label>Текущий пароль</label>
                  <input
                    className="form-input"
                    type="password"
                    autoComplete="current-password"
                    value={current}
                    onChange={(e) => setCurrent(e.target.value)}
                  />
                </div>
                <div className="import-filter">
                  <label>Новый пароль</label>
                  <input
                    className="form-input"
                    type="password"
                    autoComplete="new-password"
                    placeholder="Минимум 8 символов"
                    value={next}
                    onChange={(e) => setNext(e.target.value)}
                  />
                </div>
                <div className="import-filter">
                  <label>Повторите новый пароль</label>
                  <input
                    className="form-input"
                    type="password"
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                  />
                </div>
              </div>

              {error && (
                <div className="error-banner">
                  <Icon name="alert-circle" size={16} />
                  <span>{error}</span>
                </div>
              )}
              {/* скрытая кнопка submit, чтобы Enter работал внутри form */}
              <button type="submit" style={{ display: 'none' }} aria-hidden="true" />
            </form>
          )}
        </div>

        <div className="modal-footer">
          {done ? (
            <button type="button" className="btn btn-primary" onClick={handleClose}>
              Готово
            </button>
          ) : (
            <>
              <button type="button" className="btn btn-secondary" onClick={handleClose}>
                Отмена
              </button>
              <button type="button" className="btn btn-primary" onClick={handleSubmit} disabled={!canSubmit}>
                {changePassword.isPending ? 'Сохранение…' : 'Сменить пароль'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
