import { useEffect } from 'react';
import { useBilling } from '@/api/hooks/useBilling';
import { Icon } from '@/components/ui/Icon';

type Props = {
  onDirtyChange: (dirty: boolean) => void;
  onSaveHandler: (handler: (() => Promise<void>) | null) => void;
  onDiscardHandler: (handler: (() => void) | null) => void;
};

// TODO: Биллинг — UI-заглушка по ТЗ-10 §3.7, требует отдельных endpoints
export function BillingTab({ onDirtyChange, onSaveHandler, onDiscardHandler }: Props) {
  const { data: billing, isLoading } = useBilling();

  // BillingTab doesn't have dirty state
  useEffect(() => {
    onDirtyChange(false);
    onSaveHandler(null);
    onDiscardHandler(null);
  }, [onDirtyChange, onSaveHandler, onDiscardHandler]);

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Не указано';
    return new Date(dateString).toLocaleDateString('ru-RU', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const getPlanLabel = (plan: string) => {
    switch (plan) {
      case 'starter': return 'Starter';
      case 'professional': return 'Professional';
      case 'enterprise': return 'Enterprise';
      default: return plan;
    }
  };

  // Get real usage data from backend
  const currentUsers = billing?.current_users ?? 0;
  const currentCandidates = billing?.current_candidates ?? 0;
  const currentVacancies = billing?.current_vacancies ?? 0;

  if (isLoading) {
    return <div className="settings-loading">Загрузка...</div>;
  }

  return (
    <div className="settings-content-inner">
      {/* Current Plan */}
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">Текущий тариф</h2>
          <p className="settings-card-desc">Информация о вашем тарифном плане</p>
        </div>
        <div className="settings-card-body">
          {billing && (
            <div className="billing-plan-card">
              <div className="plan-header">
                <h3 className="plan-name">{getPlanLabel(billing.plan)}</h3>
                <div className="plan-actions">
                  <button
                    className="btn btn-secondary"
                    disabled
                    title="Скоро"
                  >
                    <Icon name="settings" size={16} />
                    Изменить тариф
                  </button>
                </div>
              </div>

              <div className="plan-details">
                <div className="plan-detail">
                  <span className="plan-detail-label">Списание до:</span>
                  <span className="plan-detail-value">
                    {formatDate(billing.billing_until)}
                  </span>
                </div>
              </div>

              {/* Usage Limits */}
              <div className="usage-section">
                <h4 className="usage-title">Использование лимитов</h4>

                <div className="usage-item">
                  <div className="usage-header">
                    <span className="usage-label">Пользователи</span>
                    <span className="usage-values">
                      {currentUsers} / {billing.users_limit}
                    </span>
                  </div>
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{
                        width: `${Math.min(100, (currentUsers / billing.users_limit) * 100)}%`
                      }}
                    />
                  </div>
                </div>

                <div className="usage-item">
                  <div className="usage-header">
                    <span className="usage-label">Кандидаты</span>
                    <span className="usage-values">
                      {currentCandidates} / {billing.candidates_limit}
                    </span>
                  </div>
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{
                        width: `${Math.min(100, (currentCandidates / billing.candidates_limit) * 100)}%`
                      }}
                    />
                  </div>
                </div>

                <div className="usage-item">
                  <div className="usage-header">
                    <span className="usage-label">Вакансии</span>
                    <span className="usage-values">
                      {currentVacancies} / {billing.vacancies_limit}
                    </span>
                  </div>
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{
                        width: `${Math.min(100, (currentVacancies / billing.vacancies_limit) * 100)}%`
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Payment History */}
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">История платежей</h2>
          <p className="settings-card-desc">Информация о ваших платежах и счетах</p>
        </div>
        <div className="settings-card-body">
          {/* Static example or empty state since backend doesn't provide history */}
          <div className="empty-state">
            <Icon name="file" size={48} />
            <h3>История платежей недоступна</h3>
            <p>Информация о платежах будет доступна в следующих версиях</p>
            {/* TODO: Implement when backend provides payment history endpoint */}
          </div>
        </div>
      </div>
    </div>
  );
}